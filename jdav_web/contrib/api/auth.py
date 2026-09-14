"""Authentication for the REST API.

Primary mechanism is a bearer token issued by the project's own OAuth2/OIDC
provider (``django-oauth-toolkit``, mounted at ``/o/``). This reuses the
existing identity infrastructure — no new token system is introduced.
"""

from ninja.security import HttpBearer
from oauth2_provider.models import get_access_token_model


def user_for_token(token):
    """Resolve a bearer token to its user, or ``None`` if it is unusable."""
    AccessToken = get_access_token_model()
    try:
        access_token = AccessToken.objects.select_related("user").get(token=token)
    except AccessToken.DoesNotExist:
        return None
    if not access_token.is_valid():
        return None
    return access_token.user


class OAuth2Bearer(HttpBearer):
    """Validate an OAuth2 access token and bind ``request.user``."""

    def authenticate(self, request, token):
        user = user_for_token(token)
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
    """
    header = request.headers.get("Authorization", "")
    scheme, _sep, token = header.partition(" ")
    if scheme.lower() == "bearer" and token.strip():
        user = user_for_token(token.strip())
        if user is not None:
            request.user = user
    # Truthy: the request is always allowed through.
    return True
