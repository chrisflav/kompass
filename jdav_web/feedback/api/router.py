"""Feedback API routes.

Sending feedback is open to everyone: the button sits on the public website as
well as inside Kompass, and a visitor without an account must be able to use it.
Submissions are attributed when the caller presents a valid bearer token (see
``contrib.api.auth.optional_bearer``).

Reading feedback is staff work, gated on the standard ``feedback.view_feedback``
permission.
"""

from contrib.api.auth import optional_bearer
from contrib.api.perms import authorize
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from feedback.models import Feedback
from ninja import Router

from .schemas import FeedbackBrief
from .schemas import FeedbackIn
from .schemas import FeedbackOut

router = Router()

# Generous, but bounded: a stray loop or a bored visitor should not be able to
# fill the table with megabytes. The dialog counts the sender down to this.
MAX_MESSAGE_LENGTH = 5000


@router.post("", auth=optional_bearer, response=FeedbackOut)
def create_feedback(request, payload: FeedbackIn):
    """Store one piece of feedback, attributing it when the sender is signed in."""
    message = payload.message.strip()
    if not message:
        raise ValidationError({"message": [_("Please enter your feedback.")]})
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValidationError(
            {
                "message": [
                    _("Feedback is limited to %(limit)s characters.")
                    % {"limit": MAX_MESSAGE_LENGTH}
                ]
            }
        )
    # ``optional_bearer`` binds request.user for a valid token; an anonymous
    # user has no ``member``, which is the unattributed case.
    member = getattr(request.user, "member", None) if request.user.is_authenticated else None
    feedback = Feedback(
        message=message,
        submitted_by=member,
        # Truncated rather than rejected: context is a convenience, and a long
        # URL should never cost someone the note they just typed.
        page_url=payload.page_url[:500],
        user_agent=payload.user_agent[:300],
    )
    feedback.save()
    return feedback


@router.get("", response=list[FeedbackBrief])
def list_feedback(request):
    """All feedback, newest first."""
    authorize(request, "feedback.view_feedback")
    return Feedback.objects.select_related("submitted_by").all()


@router.get("/{feedback_id}", response=FeedbackOut)
def retrieve_feedback(request, feedback_id: int):
    """One piece of feedback."""
    authorize(request, "feedback.view_feedback")
    return get_object_or_404(Feedback, pk=feedback_id)


@router.delete("/{feedback_id}", response={204: None})
def delete_feedback(request, feedback_id: int):
    """Discard a piece of feedback once it has been dealt with."""
    authorize(request, "feedback.delete_feedback")
    get_object_or_404(Feedback, pk=feedback_id).delete()
    return 204, None
