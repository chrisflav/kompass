"""Two-factor authentication: a user's own authenticator apps, security keys and recovery codes.

Everything here needs the web interface's own sign-in (as for personal access
tokens), so no token held by a script or another application can add or remove
a factor. And every change that weakens or replaces one needs the account's
password again, typed into the same dialog:

* adding a factor asks for it when the setup starts. The answer carries a
  ``state``, naming a :class:`~logindata.models.TwoFactorSetup` that holds the
  new secret or the WebAuthn challenge for ten minutes; the step that saves the
  factor needs it and uses it up, so a stolen sign-in token without the
  password cannot add one, and a state cannot be replayed;
* removing a factor and replacing the recovery codes ask for it in the request.

Password attempts count towards the same lockout as codes at login (a right
one is taken back). Removing a factor tells the user by mail.

Renaming a factor and listing them need no password. Where OIDC is configured,
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
from logindata.models import TOTPDevice
from logindata.models import TwoFactorSetup
from logindata.models import WebAuthnCredential
from ninja import Router
from ninja import Schema

from .tokens_router import require_session

router = Router()

STATE_MAX_AGE = 600

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
    factors: list[FactorOut]
    recovery_codes_remaining: int


class PasswordIn(Schema):
    password: str


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


def _require_available():
    if not two_factor.available():
        raise Forbidden(_("Two-factor authentication is handled by your identity provider."))


def _reauthenticate(request, password):
    """Check the account's password again before a change to its factors."""
    user = request.user
    number = two_factor.claim_attempt(user)
    if number is None:
        raise Forbidden(_("Too many failed attempts. Please wait a few minutes and try again."))
    if not user.check_password(password):
        two_factor.attempt_failed(user, number)
        raise ValidationError({"password": [_("The password is not correct.")]})
    two_factor.refund_attempt(user, number)


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
    """The requesting user's second factors."""
    require_session(request)
    user = request.user
    factors = [*user.totp_devices.all(), *user.webauthn_credentials.all()]
    return {
        "available": two_factor.available(),
        "enabled": bool(factors),
        "factors": [_factor(f) for f in sorted(factors, key=lambda f: f.created)],
        "recovery_codes_remaining": user.recovery_codes.count(),
    }


@router.post("/two-factor/totp/setup", response=TOTPSetup)
def start_totp(request, payload: PasswordIn):
    """Start adding an authenticator app: check the password, hand out a secret."""
    require_session(request)
    _require_available()
    _reauthenticate(request, payload.password)
    secret = two_factor.new_totp_secret()
    return {
        "secret": secret,
        "uri": two_factor.totp_uri(secret, request.user),
        "state": _state(request, "totp", secret),
    }


@router.post("/two-factor/totp", response={201: FactorAdded})
def confirm_totp(request, payload: TOTPConfirmIn):
    """Save the authenticator app once it produced a valid code."""
    require_session(request)
    _require_available()
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
def start_webauthn(request, payload: PasswordIn):
    """Start adding a security key: check the password, hand out the creation options."""
    require_session(request)
    _require_available()
    _reauthenticate(request, payload.password)
    options, challenge = two_factor.registration_options(request.user)
    return {"options": options, "state": _state(request, "webauthn", challenge)}


@router.post("/two-factor/webauthn", response={201: FactorAdded})
def confirm_webauthn(request, payload: WebAuthnConfirmIn):
    """Verify the browser's answer to the creation options and save the key."""
    require_session(request)
    _require_available()
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
    require_session(request)
    factor = get_object_or_404(_factor_model(kind), pk=factor_id, user=request.user)
    factor.name = _clean_name(payload.name)
    factor.save(update_fields=["name"])
    return _factor(factor)


@router.post("/two-factor/{kind}/{factor_id}/remove", response={204: None})
def remove_factor(request, kind: FactorKind, factor_id: int, payload: PasswordIn):
    """Remove a factor; the recovery codes go with the last one."""
    require_session(request)
    _require_available()
    factor = get_object_or_404(_factor_model(kind), pk=factor_id, user=request.user)
    _reauthenticate(request, payload.password)
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
def regenerate_recovery_codes(request, payload: PasswordIn):
    """Replace the recovery codes with new ones; the old ones stop working."""
    require_session(request)
    _require_available()
    if not two_factor.enabled_for(request.user):
        raise ValidationError(_("Set up a second factor first."))
    _reauthenticate(request, payload.password)
    return {"codes": two_factor.generate_recovery_codes(request.user)}
