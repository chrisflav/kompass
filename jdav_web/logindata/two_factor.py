"""Second factors for the built-in login: authenticator apps, security keys, recovery codes.

Everything that decides whether a second factor is valid lives here, so the
login views and the API that manages factors share one implementation.

* TOTP (RFC 6238) through ``pyotp``. Secrets are encrypted with a key derived
  from ``SECRET_KEY`` (its fallbacks still decrypt, so a key rotation keeps
  them readable), and a code is accepted at most once.
* WebAuthn through ``webauthn`` (py_webauthn), which verifies the ceremonies;
  this module only stores challenges and credentials.
* Recovery codes, stored as SHA-256 hashes and deleted when used.

Attempts are counted per account in :class:`~logindata.models.TwoFactorAttempts`
(see :func:`claim_attempt`): every ``TWO_FACTOR_MAX_FAILURES`` of them lock the
account's second step, for ``TWO_FACTOR_LOCKOUT_SECONDS`` and twice as long each
further time, whichever session the attempts came from.

Whether a login needs a second step is :func:`required_for`. Today that is
"the user has set up a factor"; making it mandatory for some accounts would
change that one function and send those without a factor to a setup page.
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from datetime import timedelta

import pyotp
from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from cryptography.fernet import MultiFernet
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext_lazy as _
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_refresh_token_model
from webauthn import generate_authentication_options
from webauthn import generate_registration_options
from webauthn import options_to_json
from webauthn import verify_authentication_response
from webauthn import verify_registration_response
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers.exceptions import WebAuthnException
from webauthn.helpers.structs import AuthenticatorSelectionCriteria
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
from webauthn.helpers.structs import ResidentKeyRequirement
from webauthn.helpers.structs import UserVerificationRequirement

from .models import RecoveryCode
from .models import TOTPDevice
from .models import TwoFactorAttempts
from .models import WebAuthnCredential

logger = logging.getLogger(__name__)

RECOVERY_CODE_COUNT = 10
# 16 characters of base32 are 80 random bits.
RECOVERY_CODE_LENGTH = 16
RECOVERY_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"


class InvalidCredential(Exception):
    """A WebAuthn response that does not verify, for whatever reason."""


def available():
    """Whether Kompass handles second factors at all: not where OIDC signs users in."""
    return not settings.OIDC_ENABLED


def enabled_for(user):
    """Whether ``user`` has set up a second factor (recovery codes alone are none)."""
    return user.totp_devices.exists() or user.webauthn_credentials.exists()


def required_for(user):
    """Whether signing in as ``user`` takes a second step after the password."""
    return enabled_for(user)


# --- lockout ----------------------------------------------------------------


def _lock_seconds(failures):
    """How long ``failures`` lock the account: doubling with each threshold, at most a day."""
    rounds = failures // settings.TWO_FACTOR_MAX_FAILURES
    return min(
        settings.TWO_FACTOR_LOCKOUT_SECONDS * 2 ** (rounds - 1),
        settings.TWO_FACTOR_MAX_LOCKOUT_SECONDS,
    )


def claim_attempt(user):
    """Count an attempt *before* it is checked; its number, or ``None`` while locked.

    Counting first, under a row lock, means requests racing each other cannot
    all slip through before the lock is written. Every
    ``TWO_FACTOR_MAX_FAILURES`` attempts lock the account, each time for twice
    as long as the last, up to a day; only a successful second factor
    (:func:`record_success`) clears the count. Afterwards the caller reports the
    outcome: :func:`attempt_failed` or :func:`refund_attempt`.
    """
    TwoFactorAttempts.objects.get_or_create(user=user)
    with transaction.atomic():
        attempts = TwoFactorAttempts.objects.select_for_update().filter(user=user).first()
        if attempts is None:
            # A success deleted the row in between: start from a new one.
            attempts, _created = TwoFactorAttempts.objects.get_or_create(user=user)
        if attempts.locked_until and attempts.locked_until > timezone.now():
            return None
        attempts.failures += 1
        if attempts.failures % settings.TWO_FACTOR_MAX_FAILURES == 0:
            attempts.locked_until = timezone.now() + timedelta(
                seconds=_lock_seconds(attempts.failures)
            )
        attempts.save()
    return attempts.failures


def attempt_failed(user, number):
    """The claimed attempt ``number`` failed; the first lock tells the user by mail.

    Once only, until a second factor succeeds: ``lock_mailed`` is set by a
    conditional UPDATE, so neither a refunded attempt that hands out the same
    number again nor two racing requests mail twice.
    """
    if number % settings.TWO_FACTOR_MAX_FAILURES == 0 and TwoFactorAttempts.objects.filter(
        user=user, lock_mailed=False
    ).update(lock_mailed=True):
        notify(user, _("Your Kompass login was locked"), settings.TWO_FACTOR_LOCKED_TEXT)


def refund_attempt(user, number):
    """Take back attempt ``number``, which was right but is no second factor (a password).

    A lock that attempt set is lifted with it.
    """
    with transaction.atomic():
        attempts = TwoFactorAttempts.objects.select_for_update().filter(user=user).first()
        if attempts is None:
            # A success already cleared the count.
            return
        attempts.failures = max(attempts.failures - 1, 0)
        if number % settings.TWO_FACTOR_MAX_FAILURES == 0:
            attempts.locked_until = None
        attempts.save()


def record_success(user):
    """A second factor checked out: the count starts again."""
    TwoFactorAttempts.objects.filter(user=user).delete()


def revoke_other_tokens(user, keep):
    """End every OAuth2 token of ``user`` but ``keep`` (and its refresh token).

    For when the first factor is added: a token obtained with the password alone
    before (through the password grant, say) must not outlive that. Personal
    access tokens stay; they can only be created from a frontend sign-in.
    """
    get_refresh_token_model().objects.filter(user=user).exclude(access_token=keep).delete()
    get_access_token_model().objects.filter(user=user, personal__isnull=True).exclude(
        pk=getattr(keep, "pk", None)
    ).delete()


def notify(user, subject, text, **context):
    """Mail ``user`` about their sign-in security, if they have a member profile to mail.

    ``text`` is a template from the texts settings, filled with the member's
    ``name`` and ``context``.
    """
    member = getattr(user, "member", None)
    if member is not None:
        member.send_mail(subject, text.format(name=member.prename, **context))


# --- TOTP -------------------------------------------------------------------


def _fernet():
    def key(secret):
        digest = salted_hmac(
            "logindata.two_factor.totp", "fernet", secret=secret, algorithm="sha256"
        ).digest()
        return Fernet(base64.urlsafe_b64encode(digest))

    return MultiFernet([key(s) for s in [settings.SECRET_KEY, *settings.SECRET_KEY_FALLBACKS]])


def encrypt_secret(secret):
    return _fernet().encrypt(secret.encode()).decode()


def decrypt_secret(token):
    """The plain secret, or ``None`` if no current or fallback key decrypts it."""
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None


def usable_totp_devices(user):
    """The user's apps with their secrets, leaving out (and reporting) any no key decrypts.

    That happens when ``SECRET_KEY`` changed without the old key kept in
    ``SECRET_KEY_FALLBACKS``: those apps can no longer be checked at all, which
    is the deployment's fault and not something to count against the user.
    """
    usable = []
    for device in user.totp_devices.all():
        secret = decrypt_secret(device.encrypted_secret)
        if secret is None:
            logger.error(
                "The secret of authenticator app %s of user %s cannot be decrypted; "
                "was SECRET_KEY changed without keeping the old one in SECRET_KEY_FALLBACKS?",
                device.pk,
                user.pk,
            )
        else:
            usable.append((device, secret))
    return usable


def new_totp_secret():
    return pyotp.random_base32()


def totp_uri(secret, user):
    return pyotp.TOTP(secret).provisioning_uri(
        name=user.username, issuer_name=settings.WEBAUTHN_RP_NAME
    )


def _normalize_code(code):
    return "".join(c for c in code.lower() if c.isalnum())


def totp_counter(secret, code):
    """The time step ``code`` is valid for, allowing one step of clock drift, else ``None``."""
    code = _normalize_code(code)
    totp = pyotp.TOTP(secret)
    now = totp.timecode(timezone.now())
    for counter in (now - 1, now, now + 1):
        if hmac.compare_digest(totp.generate_otp(counter), code):
            return counter
    return None


def verify_totp(user, code):
    """Accept ``code`` from one of the user's apps, once; record that it was used."""
    for device, secret in usable_totp_devices(user):
        counter = totp_counter(secret, code)
        # One conditional UPDATE, so of two requests racing with the same code
        # only one moves the counter on.
        if counter is not None and TOTPDevice.objects.filter(
            pk=device.pk, last_counter__lt=counter
        ).update(last_counter=counter, last_used=timezone.now()):
            return True
    return False


# --- recovery codes ---------------------------------------------------------


def _hash_code(code):
    return hashlib.sha256(_normalize_code(code).encode()).hexdigest()


def generate_recovery_codes(user):
    """Replace the user's recovery codes with new ones and return them, the only time."""
    codes = []
    for _i in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(RECOVERY_ALPHABET) for _j in range(RECOVERY_CODE_LENGTH))
        codes.append("-".join(raw[i : i + 4] for i in range(0, RECOVERY_CODE_LENGTH, 4)))
    with transaction.atomic():
        user.recovery_codes.all().delete()
        RecoveryCode.objects.bulk_create(
            [RecoveryCode(user=user, code_hash=_hash_code(c)) for c in codes]
        )
    return codes


def use_recovery_code(user, code):
    """Accept ``code`` if it is one of the user's unused codes, and use it up."""
    deleted, _per_model = user.recovery_codes.filter(code_hash=_hash_code(code)).delete()
    return deleted > 0


def remove_all(user):
    """Remove every second factor of ``user``, as an administrator's reset does."""
    with transaction.atomic():
        user.totp_devices.all().delete()
        user.webauthn_credentials.all().delete()
        user.recovery_codes.all().delete()
        TwoFactorAttempts.objects.filter(user=user).delete()


def factor_removed(user):
    """Without any factor left, recovery codes would only be a way around nothing."""
    if not enabled_for(user):
        user.recovery_codes.all().delete()


# --- WebAuthn ---------------------------------------------------------------


def _user_handle(user):
    return str(user.pk).encode()


def registration_options(user):
    """Options for ``navigator.credentials.create`` and the challenge they carry.

    A resident key and user verification are preferred, not required: a plain
    security key still works as a second factor, and a passkey can also sign
    in without a password. ``credProps`` asks the browser to report which of the
    two it got.
    """
    options = generate_registration_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        rp_name=settings.WEBAUTHN_RP_NAME,
        user_id=_user_handle(user),
        user_name=user.username,
        user_display_name=user.get_full_name() or user.username,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in user.webauthn_credentials.all()
        ],
    )
    data = json.loads(options_to_json(options))
    data["extensions"] = {"credProps": True}
    return data, bytes_to_base64url(options.challenge)


def register_credential(user, name, credential, challenge):
    """Verify a registration response and store the new credential."""
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
        )
    except (WebAuthnException, ValueError, KeyError) as e:
        raise InvalidCredential(str(e)) from e
    credential_id = bytes_to_base64url(verified.credential_id)
    if WebAuthnCredential.objects.filter(credential_id=credential_id).exists():
        raise InvalidCredential("This key is already registered.")
    extensions = credential.get("clientExtensionResults") or {}
    resident = (extensions.get("credProps") or {}).get("rk") is True
    return WebAuthnCredential.objects.create(
        user=user,
        name=name,
        credential_id=credential_id,
        public_key=verified.credential_public_key,
        sign_count=verified.sign_count,
        discoverable=resident and verified.user_verified,
    )


def authentication_options(credentials, user_verification):
    """Options for ``navigator.credentials.get`` and their challenge.

    ``credentials`` empty asks for any discoverable credential of this site,
    which is how the passwordless login starts.
    """
    options = generate_authentication_options(
        rp_id=settings.WEBAUTHN_RP_ID,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(c.credential_id))
            for c in credentials
        ],
        user_verification=user_verification,
    )
    return json.loads(options_to_json(options)), bytes_to_base64url(options.challenge)


def authenticate_credential(credentials, credential, challenge, require_user_verification):
    """Verify an assertion against one of ``credentials`` and return that credential."""
    try:
        stored = credentials.get(credential_id=credential["id"])
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(challenge),
            expected_rp_id=settings.WEBAUTHN_RP_ID,
            expected_origin=settings.WEBAUTHN_ORIGINS,
            credential_public_key=bytes(stored.public_key),
            credential_current_sign_count=stored.sign_count,
            require_user_verification=require_user_verification,
        )
    except (WebAuthnCredential.DoesNotExist, WebAuthnException, ValueError, KeyError) as e:
        raise InvalidCredential(str(e)) from e
    # A discoverable credential names its account; it has to be the one stored.
    handle = (credential.get("response") or {}).get("userHandle")
    if handle and base64url_to_bytes(handle) != _user_handle(stored.user):
        raise InvalidCredential("The key names another account.")
    stored.sign_count = verified.new_sign_count
    stored.last_used = timezone.now()
    stored.save(update_fields=["sign_count", "last_used"])
    return stored


# --- challenges between two requests ------------------------------------------


def store_challenge(session, purpose, challenge):
    session["two_factor_challenge"] = {
        "purpose": purpose,
        "challenge": challenge,
        "expires": time.time() + settings.TWO_FACTOR_PENDING_SECONDS,
    }


def pop_challenge(session, purpose):
    """The stored challenge for ``purpose``, used up; ``None`` if there is none."""
    stored = session.pop("two_factor_challenge", None)
    if not stored or stored["purpose"] != purpose or stored["expires"] < time.time():
        return None
    return stored["challenge"]
