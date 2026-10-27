"""Signing out of the web interface.

The frontend holds a bearer token, but the provider at ``/o/`` remembers the
browser through Django's session cookie, sent along because the API shares the
frontend's origin. Dropping the token alone would leave that session behind,
and the next login would come straight back signed in without asking for a
password. Signing out therefore ends both.

The session must end even when the token no longer works, an expired one
being the common case, so the sign-out also takes the session as its
authentication. A cookie travels on every request, so that path is guarded by
Django's CSRF check; the frontend fetches the token for it from ``/csrf``.
"""

from contrib.api.auth import OAuth2Bearer
from django.contrib.auth import logout as end_session
from django.core.exceptions import ObjectDoesNotExist
from django.middleware.csrf import get_token
from ninja import Router
from ninja import Schema
from ninja.security import django_auth
from oauth2_provider.models import get_access_token_model

router = Router()


class CsrfOut(Schema):
    token: str


@router.get("/csrf", auth=None, response=CsrfOut)
def csrf(request):
    """The CSRF token for signing out by session, set as its cookie too.

    Readable only from the frontend's own origin, which is the point: a page
    elsewhere cannot learn it and so cannot sign the user out.
    """
    return CsrfOut(token=get_token(request))


def _presented_token(request):
    """The access token the request names, valid or not; ``None`` without one."""
    scheme, _sep, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return get_access_token_model().objects.filter(token=token.strip()).first()


def _revoke(access_token):
    """End an access token together with the refresh token issued with it."""
    try:
        refresh_token = access_token.refresh_token
    except ObjectDoesNotExist:
        access_token.revoke()
    else:
        # Revokes the access token as well.
        refresh_token.revoke()


@router.post("/logout", auth=[OAuth2Bearer(), django_auth], response={204: None})
def logout(request):
    """Revoke the token the request names and end the browser's session.

    The token is revoked even when it has expired: knowing it is all it takes
    to end it, and its refresh token would otherwise stay usable. A personal
    access token is left alone: it belongs to a script, not to the browser
    signing out, and is ended from the token list instead. A confirmation for
    the second-factor settings goes with the revoked token, which it cascades
    from.
    """
    access_token = _presented_token(request)
    if access_token is not None and getattr(access_token, "personal", None) is None:
        _revoke(access_token)
    end_session(request)
    return 204, None
