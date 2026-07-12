"""Authentication for the REST API.

Primary mechanism is a bearer token issued by the project's own OAuth2/OIDC
provider (``django-oauth-toolkit``, mounted at ``/o/``). This reuses the
existing identity infrastructure — no new token system is introduced.
"""

from ninja.security import HttpBearer
from oauth2_provider.models import get_access_token_model


class OAuth2Bearer(HttpBearer):
    """Validate an OAuth2 access token and bind ``request.user``."""

    def authenticate(self, request, token):
        AccessToken = get_access_token_model()
        try:
            access_token = AccessToken.objects.select_related("user").get(token=token)
        except AccessToken.DoesNotExist:
            return None
        if not access_token.is_valid():
            return None
        # Bind the authenticated user so downstream permission checks
        # (user.has_perm, user.member) resolve against the token's user.
        request.user = access_token.user
        return access_token.user
