"""Public (unauthenticated) mailer endpoints.

Mirrors :func:`mailer.views.unsubscribe`: a newsletter recipient unsubscribes by
following an emailed link carrying their per-member ``unsubscribe_key``. The
legacy view verifies *and* consumes the key in a single GET; the API splits this
into a non-destructive verify (GET) and the destructive confirm (POST) so a
client can present a confirmation screen first.

Every route takes ``auth=None`` — the caller is an email recipient with no
Kompass account — and the secret key is validated manually, exactly as the view
does (matching ``unsubscribe_key`` and honoring the ``unsubscribe_expire``
deadline).
"""

from django.http import Http404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from members.models import Member
from ninja import Router

from .schemas import UnsubscribeIn
from .schemas import UnsubscribeInfo

router = Router()


def _member_for_unsubscribe_key(key):
    """Return the member for a valid, unexpired ``unsubscribe_key`` or raise 404.

    Mirrors the guard in ``mailer.views.unsubscribe``. An empty key is rejected
    outright: the field default is ``""``, so it must never resolve a member.
    """
    if not key:
        raise Http404(_("Can't verify this link. Try again!"))
    try:
        member = Member.objects.get(unsubscribe_key=key)
    except (Member.DoesNotExist, Member.MultipleObjectsReturned):
        raise Http404(_("Can't verify this link. Try again!"))
    if timezone.now() >= member.unsubscribe_expire:
        raise Http404(_("Can't verify this link. Try again!"))
    return member


@router.get("/unsubscribe", auth=None, response=UnsubscribeInfo)
def verify_unsubscribe_key(request, key: str):
    """Verify an unsubscribe key without consuming it (non-destructive)."""
    return _member_for_unsubscribe_key(key)


@router.post("/unsubscribe", auth=None, response=UnsubscribeInfo)
def confirm_unsubscribe(request, payload: UnsubscribeIn):
    """Unsubscribe the member behind the key from the newsletter.

    Delegates to ``Member.unsubscribe`` (which clears the newsletter flag for
    every member sharing the address and invalidates the key), never
    reimplementing the unsubscribe logic here.
    """
    member = _member_for_unsubscribe_key(payload.key)
    if not member.unsubscribe(payload.key):  # pragma: no cover
        # Belt and braces: `_member_for_unsubscribe_key` has already matched the
        # key and checked its expiry, which is everything `unsubscribe` tests,
        # so there is no input that reaches here. Kept so the two cannot drift.
        raise Http404(_("Can't verify this link. Try again!"))
    return member
