from django.db import models
from django.utils.translation import gettext_lazy as _
from members.models import Member


class Feedback(models.Model):
    """A note left through the feedback button, from any page of the site.

    Anyone may send one — the button sits on the public website as well as in
    Kompass — so ``submitted_by`` is empty for a visitor without an account.
    """

    message = models.TextField(verbose_name=_("Message"))
    created = models.DateTimeField(verbose_name=_("Received on"), auto_now_add=True)
    submitted_by = models.ForeignKey(
        Member,
        verbose_name=_("Submitted by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback",
    )
    # Filled in only when the sender ticked "send the current page". The dialog
    # shows them the exact values beforehand, so nothing is collected silently.
    page_url = models.CharField(verbose_name=_("Page"), max_length=500, blank=True)
    user_agent = models.CharField(verbose_name=_("Browser"), max_length=300, blank=True)
    # Set once someone has dealt with the note; cleared again on reopening.
    resolved_at = models.DateTimeField(verbose_name=_("Resolved on"), null=True, blank=True)
    resolved_by = models.ForeignKey(
        Member,
        verbose_name=_("Resolved by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="resolved_feedback",
    )

    def __str__(self):
        excerpt = self.message.strip().splitlines()[0] if self.message.strip() else ""
        return excerpt[:60] or str(_("(empty)"))

    @property
    def has_context(self):
        return bool(self.page_url or self.user_agent)

    @property
    def is_resolved(self):
        return self.resolved_at is not None

    @property
    def can_respond(self):
        """Whether the sender can be answered by mail: signed in, with an address."""
        member = self.submitted_by
        return member is not None and any(
            getattr(member, email_fd) for email_fd, _confirmed, _key in member.email_fields
        )

    class Meta:
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedback")
        ordering = ["-created"]


class FeedbackResponse(models.Model):
    """An answer mailed to the sender of a piece of feedback.

    A note can be answered several times; the replies form a short thread on it.
    """

    feedback = models.ForeignKey(
        Feedback,
        verbose_name=_("Feedback"),
        on_delete=models.CASCADE,
        related_name="responses",
    )
    author = models.ForeignKey(
        Member,
        verbose_name=_("Author"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="feedback_responses",
    )
    message = models.TextField(verbose_name=_("Message"))
    created = models.DateTimeField(verbose_name=_("Sent on"), auto_now_add=True)

    def __str__(self):
        return self.message.strip()[:60] or str(_("(empty)"))

    class Meta:
        verbose_name = _("Feedback response")
        verbose_name_plural = _("Feedback responses")
        ordering = ["created"]
