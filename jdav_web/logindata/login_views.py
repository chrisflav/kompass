"""The second step of the built-in login, and the passwordless login with a passkey.

After a correct password, ``BuiltinLoginView`` does not log a user with a second
factor in. It only notes in the session who is half way through
(:func:`begin_second_step`): the account, the backend that checked the
password, a fingerprint of the password hash and a deadline. Nothing reads that
note as a login: ``request.user`` stays anonymous, and so does every page,
``/o/authorize/`` included, until :func:`login_two_factor` has checked the
second factor and called ``login()``.

Both views exist only where Kompass checks passwords itself; with OIDC enabled
the provider handles every factor and these answer 404, like the password form.
"""

import json
import time

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth import login
from django.contrib.auth.views import redirect_to_login
from django.http import Http404
from django.http import HttpResponseRedirect
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from webauthn.helpers.structs import UserVerificationRequirement

from . import two_factor
from .models import WebAuthnCredential

PENDING_KEY = "two_factor_pending"
MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"

LOCKED = _("Too many failed attempts. Please wait a few minutes and try again.")
WRONG = _("That did not work. Please try again.")
PASSKEY_FAILED = _("Signing in with this security key did not work.")
UNREADABLE = _(
    "Your authenticator app cannot be checked at the moment. "
    "Please use a security key or a recovery code."
)


def _require_available():
    if not two_factor.available():
        raise Http404("No local login where an identity provider is configured.")


def begin_second_step(request, user, next_url):
    """Remember that ``user`` gave the right password, without logging them in."""
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "user": user.pk,
        "backend": user.backend,
        "hash": user.get_session_auth_hash(),
        "next": next_url,
        "expires": time.time() + settings.TWO_FACTOR_PENDING_SECONDS,
    }


def _pending(request):
    """The user half way through logging in and their note, or ``(None, None)``.

    The note lapses after its deadline, and when the password changed since or
    the account was deactivated.
    """
    pending = request.session.get(PENDING_KEY)
    if not pending or pending["expires"] < time.time():
        return None, None
    user = get_user_model().objects.filter(pk=pending["user"], is_active=True).first()
    if user is None or not constant_time_compare(user.get_session_auth_hash(), pending["hash"]):
        return None, None
    return user, pending


def _credential(request):
    """The WebAuthn response the login page's script posted, as a dict."""
    try:
        credential = json.loads(request.POST.get("credential", ""))
    except ValueError:
        return None
    return credential if isinstance(credential, dict) else None


def _options_response(request, purpose, credentials, user_verification):
    options, challenge = two_factor.authentication_options(credentials, user_verification)
    two_factor.store_challenge(request.session, purpose, challenge)
    return JsonResponse({"publicKey": options})


def _verify_key(request, credentials, purpose, require_user_verification):
    challenge = two_factor.pop_challenge(request.session, purpose)
    credential = _credential(request)
    if challenge is None or credential is None:
        return None
    try:
        return two_factor.authenticate_credential(
            credentials, credential, challenge, require_user_verification
        )
    except two_factor.InvalidCredential:
        return None


@sensitive_post_parameters()
@never_cache
def login_two_factor(request):
    """Ask for the second factor of the user who just gave their password."""
    _require_available()
    user, pending = _pending(request)
    if user is None:
        request.session.pop(PENDING_KEY, None)
        return HttpResponseRedirect(settings.LOGIN_URL)
    error = ""
    if request.method == "POST":
        method = request.POST.get("method")
        code = request.POST.get("code", "")
        is_totp = method not in ("webauthn", "recovery")
        if is_totp and not two_factor.usable_totp_devices(user):
            # Not the user's mistake (see usable_totp_devices), so not counted.
            error = UNREADABLE
        else:
            number = two_factor.claim_attempt(user)
            if number is None:
                error = LOCKED
            else:
                if method == "webauthn":
                    ok = _verify_key(request, user.webauthn_credentials.all(), "login", False)
                elif method == "recovery":
                    ok = two_factor.use_recovery_code(user, code)
                else:
                    ok = two_factor.verify_totp(user, code)
                if ok:
                    request.session.pop(PENDING_KEY)
                    two_factor.record_success(user)
                    login(request, user, backend=pending["backend"])
                    return HttpResponseRedirect(pending["next"])
                two_factor.attempt_failed(user, number)
                error = WRONG
    preferred, preferred_key = two_factor.preferred(user)
    keys = user.webauthn_credentials.count()
    return render(
        request,
        "registration/login_two_factor.html",
        {
            "error": error,
            "has_totp": user.totp_devices.exists(),
            "has_keys": keys > 0,
            "other_keys": keys > 1,
            "preferred": preferred,
            "preferred_key": preferred_key,
            # Ask the key straight away on arrival, not again after a failed
            # attempt: the page then waits for a click.
            "autostart": request.method == "GET",
            "method": request.POST.get("method", ""),
        },
    )


@require_POST
@never_cache
def login_two_factor_options(request):
    """WebAuthn options for the second step: the pending user's keys, or the one ``?key=`` names."""
    _require_available()
    user, _pending_note = _pending(request)
    if user is None:
        raise Http404("No login in progress.")
    keys = user.webauthn_credentials.all()
    # The default key alone, so the browser goes straight to it.
    one = keys.filter(pk=request.GET["key"]) if request.GET.get("key", "").isdigit() else None
    return _options_response(request, "login", one or keys, UserVerificationRequirement.PREFERRED)


@require_POST
@never_cache
def passkey_options(request):
    """WebAuthn options for a passwordless login: any passkey of this site, verified."""
    _require_available()
    return _options_response(request, "passkey", [], UserVerificationRequirement.REQUIRED)


@require_POST
@never_cache
def passkey_login(request):
    """Log in with a passkey alone: a discoverable credential that verified its user."""
    _require_available()
    next_url = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = settings.LOGIN_REDIRECT_URL
    stored = _verify_key(
        request,
        WebAuthnCredential.objects.filter(discoverable=True, user__is_active=True),
        "passkey",
        True,
    )
    if stored is None:
        return render(
            request,
            "registration/login.html",
            {
                "next": next_url,
                "passkey_error": PASSKEY_FAILED,
            },
            status=400,
        )
    request.session.pop(PENDING_KEY, None)
    login(request, stored.user, backend=MODEL_BACKEND)
    return HttpResponseRedirect(next_url)


def admin_login(request, extra_context=None):
    """Stands in for the admin's own login form, which knows no second factor.

    Sends everyone to ``LOGIN_URL`` (the form here, or the identity provider),
    and a user who is signed in and may use the admin straight on.
    """
    next_url = request.GET.get("next", "")
    if not url_has_allowed_host_and_scheme(
        next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        next_url = reverse("admin:index")
    if request.user.is_active and request.user.is_staff:
        return HttpResponseRedirect(next_url)
    return redirect_to_login(next_url, settings.LOGIN_URL)
