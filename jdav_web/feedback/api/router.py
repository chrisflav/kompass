"""Feedback API routes.

Sending feedback is open to everyone: the button sits on the public website as
well as inside Kompass, and a visitor without an account must be able to use it.
Submissions are attributed when the caller presents a valid bearer token (see
``contrib.api.auth.optional_bearer``).

Reading feedback is staff work, gated on the standard ``feedback.view_feedback``
permission; marking it resolved or answering the sender needs
``feedback.change_feedback`` as well.
"""

from contrib.api.auth import optional_bearer
from contrib.api.perms import authorize
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from feedback.models import Feedback
from feedback.models import FeedbackResponse
from mailer.mailutils import SENT
from ninja import Router

from .schemas import FeedbackBrief
from .schemas import FeedbackIn
from .schemas import FeedbackOut
from .schemas import RespondIn

router = Router()

# Generous, but bounded: a stray loop or a bored visitor should not be able to
# fill the table with megabytes. The dialog counts the sender down to this.
MAX_MESSAGE_LENGTH = 5000
# How much of the original note an answer quotes back to its sender.
QUOTE_LENGTH = 500


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
    return Feedback.objects.select_related("submitted_by").prefetch_related("submitted_by__group")


def _get_feedback(feedback_id):
    return get_object_or_404(
        Feedback.objects.select_related("submitted_by", "resolved_by").prefetch_related(
            "responses__author"
        ),
        pk=feedback_id,
    )


@router.get("/{feedback_id}", response=FeedbackOut)
def retrieve_feedback(request, feedback_id: int):
    """One piece of feedback."""
    authorize(request, "feedback.view_feedback")
    return _get_feedback(feedback_id)


@router.post("/{feedback_id}/resolve", response=FeedbackOut)
def resolve_feedback(request, feedback_id: int):
    """Mark a piece of feedback as dealt with, recording who did it."""
    # The response carries the whole note, so changing it must not be a way
    # around the view permission.
    authorize(request, "feedback.view_feedback")
    authorize(request, "feedback.change_feedback")
    feedback = _get_feedback(feedback_id)
    # Resolving twice keeps the original record of who closed it and when.
    if not feedback.is_resolved:
        feedback.resolved_at = timezone.now()
        feedback.resolved_by = getattr(request.user, "member", None)
        feedback.save(update_fields=["resolved_at", "resolved_by"])
    return feedback


@router.post("/{feedback_id}/respond", response=FeedbackOut)
def respond_to_feedback(request, feedback_id: int, payload: RespondIn):
    """Answer the sender by mail, keeping the answer on the note.

    With ``resolve``, the note is marked as dealt with in the same step.
    """
    authorize(request, "feedback.view_feedback")
    authorize(request, "feedback.change_feedback")
    feedback = _get_feedback(feedback_id)
    message = payload.message.strip()
    if not message:
        raise ValidationError({"message": [_("Please enter a response.")]})
    if len(message) > MAX_MESSAGE_LENGTH:
        raise ValidationError(
            {
                "message": [
                    _("A response is limited to %(limit)s characters.")
                    % {"limit": MAX_MESSAGE_LENGTH}
                ]
            }
        )
    if not feedback.can_respond:
        raise ValidationError(
            {
                "message": [
                    _(
                        "The sender cannot be answered: the feedback was sent without an "
                        "account, or the account has no email address."
                    )
                ]
            }
        )
    member = getattr(request.user, "member", None)
    responder = member or request.user
    # Locked while mailing, so two answers sent at once neither both announce
    # the resolution nor overwrite who resolved it. The mail goes out before
    # anything is stored: if it fails, the transaction rolls back and sending
    # can simply be tried again.
    with transaction.atomic():
        feedback = Feedback.objects.select_for_update().get(pk=feedback.pk)
        resolve = payload.resolve and not feedback.is_resolved
        if _mail_response(feedback, message, responder, resolve) != SENT:
            raise ValidationError(
                {"message": [_("The email could not be sent. Please try again later.")]}
            )
        FeedbackResponse.objects.create(feedback=feedback, author=member, message=message)
        if resolve:
            feedback.resolved_at = timezone.now()
            feedback.resolved_by = member
            feedback.save(update_fields=["resolved_at", "resolved_by"])
    return _get_feedback(feedback_id)


def _mail_response(feedback, message, responder, resolved):
    """Send ``message`` to the sender of ``feedback``, quoting their note back."""
    sender = feedback.submitted_by
    original = feedback.message
    if len(original) > QUOTE_LENGTH:
        original = original[:QUOTE_LENGTH].rstrip() + " […]"
    # ``responder`` is a member, or the bare user for an account without one.
    name = getattr(responder, "name", None) or responder.get_full_name() or responder.username
    status = "\n{}\n".format(_("Your feedback is now marked as resolved.")) if resolved else ""
    # Answers from the sender should reach the responder, not the shared
    # sending mailbox.
    reply_to = [responder.email] if responder.email else None
    return sender.send_mail(
        _("Response to your feedback"),
        settings.FEEDBACK_RESPONSE_TEXT.format(
            name=sender.prename,
            responder=name,
            response=message,
            status=status,
            message="\n".join("> {}".format(line) for line in original.splitlines()),
        ),
        reply_to=reply_to,
    )


@router.post("/{feedback_id}/reopen", response=FeedbackOut)
def reopen_feedback(request, feedback_id: int):
    """Put resolved feedback back into the open inbox."""
    # The response carries the whole note, so changing it must not be a way
    # around the view permission.
    authorize(request, "feedback.view_feedback")
    authorize(request, "feedback.change_feedback")
    feedback = _get_feedback(feedback_id)
    feedback.resolved_at = None
    feedback.resolved_by = None
    feedback.save(update_fields=["resolved_at", "resolved_by"])
    return feedback


@router.delete("/{feedback_id}", response={204: None})
def delete_feedback(request, feedback_id: int):
    """Discard a piece of feedback once it has been dealt with."""
    authorize(request, "feedback.delete_feedback")
    get_object_or_404(Feedback, pk=feedback_id).delete()
    return 204, None
