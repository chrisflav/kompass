"""Authentication for the REST API.

Primary mechanism is a bearer token issued by the project's own OAuth2/OIDC
provider (``django-oauth-toolkit``, mounted at ``/o/``). This reuses the
existing identity infrastructure — no new token system is introduced.

A personal access token (``logindata.PersonalAccessToken``) is such a token too,
created from the web interface rather than by an OAuth flow. One marked read
only is refused for anything but reading.
"""

from django.utils.translation import gettext_lazy as _
from ninja.security import HttpBearer
from oauth2_provider.models import get_access_token_model

from .perms import Forbidden

SAFE_METHODS = ("GET", "HEAD", "OPTIONS")


def user_for_token(token, request=None):
    """Resolve a bearer token to its user, or ``None`` if it is unusable.

    With ``request``, a personal access token is recorded on it as
    ``request.personal_token``, and a read-only one is refused (403) for any
    method that is not safe.
    """
    AccessToken = get_access_token_model()
    try:
        access_token = AccessToken.objects.select_related("user", "personal").get(token=token)
    except AccessToken.DoesNotExist:
        return None
    if not access_token.is_valid():
        return None
    personal = getattr(access_token, "personal", None)
    if request is not None and personal is not None:
        if personal.read_only and request.method not in SAFE_METHODS:
            raise Forbidden(_("This access token may only read."))
        request.personal_token = personal
    return access_token.user


class OAuth2Bearer(HttpBearer):
    """Validate an OAuth2 access token and bind ``request.user``."""

    def authenticate(self, request, token):
        user = user_for_token(token, request)
        if user is None:
            return None
        # Bind the authenticated user so downstream permission checks
        # (user.has_perm, user.member) resolve against the token's user.
        request.user = user
        return user


def optional_bearer(request):
    """Auth that binds a bearer token's user when there is one, but never rejects.

    For endpoints open to everyone that still want to know who is calling — the
    feedback form is reachable from the public website and from inside Kompass,
    and the same submission should be attributed when the sender is signed in.
    ``auth=None`` cannot do this: it skips authentication entirely, leaving
    ``request.user`` anonymous even when a valid token was sent.

    The one exception is a read-only personal access token sent to write: it
    is refused like anywhere else rather than quietly treated as anonymous.
    """
    header = request.headers.get("Authorization", "")
    scheme, _sep, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        user = user_for_token(token.strip(), request)
        if user is not None:
            request.user = user
    # Truthy: the request is always allowed through.
    return True
