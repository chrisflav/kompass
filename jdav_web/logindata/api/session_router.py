"""Signing out of the web interface.

The frontend holds a bearer token, but the provider at ``/o/`` remembers the
browser through Django's session cookie, sent along because the API shares the
frontend's origin. Dropping the token alone would leave that session behind,
and the next login would come straight back signed in without asking for a
password. Signing out therefore ends both.
"""

from django.contrib.auth import logout as end_session
from ninja import Router

router = Router()


@router.post("/logout", response={204: None})
def logout(request):
    """Revoke the bearer token of this request and end the browser's session.

    A personal access token is left alone: it belongs to a script, not to the
    browser signing out, and is ended from the token list instead.
    """
    if request.personal_token is None:
        request.access_token.revoke()
    end_session(request)
    return 204, None
