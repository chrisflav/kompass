"""Two-factor authentication: a user's own authenticator apps, security keys and recovery codes.

Everything here needs the web interface's own sign-in (as for personal access
tokens), so no token held by a script or another application can see or change
a factor. Before anything but the bare status, the sign-in has to be *elevated*:
``POST /two-factor/confirm`` checks who is using it, and records a
:class:`~logindata.models.TwoFactorElevation` for that access token, valid for
ten minutes:

* with a second factor (an authenticator code, a security key, a recovery code)
  for a user who has one: the password alone is not enough then;
* with the password for a user who has none yet.

Confirmation attempts count towards the same lockout as codes at login (a right
password is taken back, a right factor clears the count). An elevation belongs
to one access token, so it cannot be used by another token or account, and it
ends with the token. Adding the first factor leaves it in place until it expires.

Adding a factor takes two requests; the first answers with a ``state`` naming a
:class:`~logindata.models.TwoFactorSetup` that holds the new secret or the
WebAuthn challenge for ten minutes, and the second uses it up, so it cannot be
replayed. Removing a factor tells the user by mail. Where OIDC is configured,
the identity provider owns the second factor, and changing anything is refused.
"""

import secrets
from datetime import datetime
from datetime import timedelta
from typing import Any
from typing import Literal

from contrib.api.perms import Forbidden
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from logindata import two_factor
from logindata.login_views import UNREADABLE
from logindata.models import TOTPDevice
from logindata.models import TwoFactorElevation
from logindata.models import TwoFactorSetup
from logindata.models import WebAuthnCredential
from ninja import Router
from ninja import Schema
from webauthn.helpers.structs import UserVerificationRequirement

from .tokens_router import require_session

router = Router()

STATE_MAX_AGE = 600
ELEVATION_SECONDS = 600

FactorKind = Literal["totp", "webauthn"]


class FactorOut(Schema):
    id: int
    kind: FactorKind
    name: str
    created: datetime
    last_used: datetime | None
    # A security key that also signs in without a password.
    passwordless: bool


class TwoFactorStatus(Schema):
    # False where an identity provider handles sign-in and its factors.
    available: bool
    enabled: bool
    # What the user can confirm with, before the sign-in is elevated.
    has_totp: bool
    has_webauthn: bool
    # Until when this sign-in may manage factors; null when it has to confirm.
    elevated_until: datetime | None
    # Empty and zero until the sign-in is elevated.
    factors: list[FactorOut]
    recovery_codes_remaining: int


class ConfirmIn(Schema):
    """One proof of who is signed in: the password only where there is no factor.

    ``credential`` answers the options of ``/two-factor/confirm/options``, whose
    ``state`` comes with it.
    """

    password: str | None = None
    code: str | None = None
    recovery_code: str | None = None
    credential: dict[str, Any] | None = None
    state: str | None = None


class ConfirmOptions(Schema):
    """The ``publicKey`` options for ``navigator.credentials.get``."""

    options: dict[str, Any]
    state: str


class Elevated(Schema):
    elevated_until: datetime


class TOTPSetup(Schema):
    """A new secret, to show as a QR code and as text; ``state`` confirms it."""

    secret: str
    uri: str
    state: str


class TOTPConfirmIn(Schema):
    name: str
    code: str
    state: str


class WebAuthnSetup(Schema):
    """The ``publicKey`` options for ``navigator.credentials.create``."""

    options: dict[str, Any]
    state: str


class WebAuthnConfirmIn(Schema):
    name: str
    # The browser's ``PublicKeyCredential``, as JSON with base64url buffers.
    credential: dict[str, Any]
    state: str


class FactorAdded(Schema):
    factor: FactorOut
    # The recovery codes, shown this once, when this was the first factor;
    # empty otherwise.
    recovery_codes: list[str]


class RenameIn(Schema):
    name: str


class RecoveryCodesOut(Schema):
    codes: list[str]


def _require_session(request):
    require_session(
        request, _("Two-factor authentication can only be managed after signing in to Kompass.")
    )


def _require_available():
    if not two_factor.available():
        raise Forbidden(_("Two-factor authentication is handled by your identity provider."))


def _elevation(request):
    """Until when the requesting sign-in may manage factors, or ``None``."""
    elevation = TwoFactorElevation.objects.filter(
        access_token=request.access_token, expires__gt=timezone.now()
    ).first()
    return elevation.expires if elevation else None


def _require_elevation(request):
    _require_session(request)
    _require_available()
    if _elevation(request) is None:
        raise Forbidden(_("Please confirm it is you first."))


def _verify_proof(request, payload):
    """Whether ``payload`` proves who is signed in, and whether it was a second factor.

    Raises for a request that cannot be checked at all: a password where a
    factor is needed, or an authenticator app no key decrypts (not counted).
    """
    user = request.user
    if not two_factor.enabled_for(user):
        return user.check_password(payload.password or ""), False
    if payload.credential is not None:
        setup, challenge = _from_state(request, "confirm", payload.state or "")
        _use_up(setup)
        try:
            two_factor.authenticate_credential(
                user.webauthn_credentials.all(), payload.credential, challenge, False
            )
        except two_factor.InvalidCredential:
            return False, True
        return True, True
    if payload.recovery_code:
        return two_factor.use_recovery_code(user, payload.recovery_code), True
    if payload.code:
        if not two_factor.usable_totp_devices(user):
            raise ValidationError(UNREADABLE)
        return two_factor.verify_totp(user, payload.code), True
    raise ValidationError(_("Please confirm with one of your second factors."))


def _state(request, kind, value):
    """Keep ``value`` for the second request of a setup; the nonce that names it."""
    TwoFactorSetup.objects.filter(user=request.user).delete()
    setup = TwoFactorSetup.objects.create(
        user=request.user,
        kind=kind,
        nonce=secrets.token_urlsafe(32),
        encrypted_value=two_factor.encrypt_secret(value),
    )
    return setup.nonce


def _from_state(request, kind, state):
    """The setup ``state`` names, if it is this user's, of this kind and recent."""
    setup = TwoFactorSetup.objects.filter(
        user=request.user,
        kind=kind,
        nonce=state,
        created__gte=timezone.now() - timedelta(seconds=STATE_MAX_AGE),
    ).first()
    value = two_factor.decrypt_secret(setup.encrypted_value) if setup else None
    if value is None:
        raise ValidationError(_("This setup has expired. Please start again."))
    return setup, value


def _use_up(setup):
    """Delete the setup, failing for the second of two requests racing with the same state."""
    deleted, _per_model = TwoFactorSetup.objects.filter(pk=setup.pk).delete()
    if not deleted:
        raise ValidationError(_("This setup has expired. Please start again."))


def _clean_name(name):
    name = name.strip()
    if not name:
        raise ValidationError({"name": [_("Give it a name.")]})
    if len(name) > 100:
        raise ValidationError({"name": [_("At most 100 characters.")]})
    return name


def _factor(obj):
    is_key = isinstance(obj, WebAuthnCredential)
    return {
        "id": obj.pk,
        "kind": "webauthn" if is_key else "totp",
        "name": obj.name,
        "created": obj.created,
        "last_used": obj.last_used,
        "passwordless": is_key and obj.discoverable,
    }


def _factor_model(kind):
    return WebAuthnCredential if kind == "webauthn" else TOTPDevice


def _added(request, factor, first):
    codes = []
    if first:
        codes = two_factor.generate_recovery_codes(request.user)
        # Signed in elsewhere with the password alone: that ends here.
        two_factor.revoke_other_tokens(request.user, request.access_token)
    return 201, {"factor": _factor(factor), "recovery_codes": codes}


@router.get("/two-factor", response=TwoFactorStatus)
def two_factor_status(request):
    """What the requesting user can confirm with, and their factors once confirmed."""
    _require_session(request)
    user = request.user
    totp = list(user.totp_devices.all())
    keys = list(user.webauthn_credentials.all())
    elevated_until = _elevation(request)
    factors = sorted([*totp, *keys], key=lambda f: f.created) if elevated_until else []
    return {
        "available": two_factor.available(),
        "enabled": bool(totp or keys),
        "has_totp": bool(totp),
        "has_webauthn": bool(keys),
        "elevated_until": elevated_until,
        "factors": [_factor(f) for f in factors],
        "recovery_codes_remaining": user.recovery_codes.count() if elevated_until else 0,
    }


@router.post("/two-factor/confirm/options", response=ConfirmOptions)
def confirm_options(request):
    """Request options for confirming with one of the user's security keys."""
    _require_session(request)
    _require_available()
    keys = request.user.webauthn_credentials.all()
    if not keys:
        raise ValidationError(_("You have no security key."))
    options, challenge = two_factor.authentication_options(
        keys, UserVerificationRequirement.PREFERRED
    )
    return {"options": options, "state": _state(request, "confirm", challenge)}


@router.post("/two-factor/confirm", response=Elevated)
def confirm(request, payload: ConfirmIn):
    """Confirm who is signed in; the sign-in may then manage factors for ten minutes."""
    _require_session(request)
    _require_available()
    user = request.user
    number = two_factor.claim_attempt(user)
    if number is None:
        raise Forbidden(_("Too many failed attempts. Please wait a few minutes and try again."))
    try:
        ok, second_factor = _verify_proof(request, payload)
    except ValidationError:
        # Nothing was checked, so nothing is counted.
        two_factor.refund_attempt(user, number)
        raise
    if not ok:
        two_factor.attempt_failed(user, number)
        raise ValidationError(_("That did not work. Please try again."))
    if second_factor:
        two_factor.record_success(user)
    else:
        two_factor.refund_attempt(user, number)
    expires = timezone.now() + timedelta(seconds=ELEVATION_SECONDS)
    TwoFactorElevation.objects.update_or_create(
        access_token=request.access_token, defaults={"expires": expires}
    )
    return {"elevated_until": expires}


@router.post("/two-factor/totp/setup", response=TOTPSetup)
def start_totp(request):
    """Start adding an authenticator app: hand out a new secret."""
    _require_elevation(request)
    secret = two_factor.new_totp_secret()
    return {
        "secret": secret,
        "uri": two_factor.totp_uri(secret, request.user),
        "state": _state(request, "totp", secret),
    }


@router.post("/two-factor/totp", response={201: FactorAdded})
def confirm_totp(request, payload: TOTPConfirmIn):
    """Save the authenticator app once it produced a valid code."""
    _require_elevation(request)
    setup, secret = _from_state(request, "totp", payload.state)
    name = _clean_name(payload.name)
    counter = two_factor.totp_counter(secret, payload.code)
    if counter is None:
        raise ValidationError({"code": [_("The code is not correct. Please try again.")]})
    with transaction.atomic():
        _use_up(setup)
        first = not two_factor.enabled_for(request.user)
        device = TOTPDevice.objects.create(
            user=request.user,
            name=name,
            encrypted_secret=two_factor.encrypt_secret(secret),
            last_counter=counter,
        )
        return _added(request, device, first)


@router.post("/two-factor/webauthn/setup", response=WebAuthnSetup)
def start_webauthn(request):
    """Start adding a security key: hand out the creation options."""
    _require_elevation(request)
    options, challenge = two_factor.registration_options(request.user)
    return {"options": options, "state": _state(request, "webauthn", challenge)}


@router.post("/two-factor/webauthn", response={201: FactorAdded})
def confirm_webauthn(request, payload: WebAuthnConfirmIn):
    """Verify the browser's answer to the creation options and save the key."""
    _require_elevation(request)
    setup, challenge = _from_state(request, "webauthn", payload.state)
    name = _clean_name(payload.name)
    # A key that does not verify rolls the deletion back: the setup stays for
    # another try.
    with transaction.atomic():
        _use_up(setup)
        first = not two_factor.enabled_for(request.user)
        try:
            key = two_factor.register_credential(request.user, name, payload.credential, challenge)
        except two_factor.InvalidCredential:
            raise ValidationError(_("The security key could not be registered.")) from None
        return _added(request, key, first)


@router.patch("/two-factor/{kind}/{factor_id}", response=FactorOut)
def rename_factor(request, kind: FactorKind, factor_id: int, payload: RenameIn):
    _require_elevation(request)
    factor = get_object_or_404(_factor_model(kind), pk=factor_id, user=request.user)
    factor.name = _clean_name(payload.name)
    factor.save(update_fields=["name"])
    return _factor(factor)


@router.post("/two-factor/{kind}/{factor_id}/remove", response={204: None})
def remove_factor(request, kind: FactorKind, factor_id: int):
    """Remove a factor; the recovery codes go with the last one."""
    _require_elevation(request)
    factor = get_object_or_404(_factor_model(kind), pk=factor_id, user=request.user)
    with transaction.atomic():
        factor.delete()
        two_factor.factor_removed(request.user)
    two_factor.notify(
        request.user,
        _("A second factor was removed from your Kompass login"),
        settings.TWO_FACTOR_REMOVED_TEXT,
        factor=factor.name,
    )
    return 204, None


@router.post("/two-factor/recovery-codes", response=RecoveryCodesOut)
def regenerate_recovery_codes(request):
    """Replace the recovery codes with new ones; the old ones stop working."""
    _require_elevation(request)
    if not two_factor.enabled_for(request.user):
        raise ValidationError(_("Set up a second factor first."))
    return {"codes": two_factor.generate_recovery_codes(request.user)}
