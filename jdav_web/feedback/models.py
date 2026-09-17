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

    def __str__(self):
        excerpt = self.message.strip().splitlines()[0] if self.message.strip() else ""
        return excerpt[:60] or str(_("(empty)"))

    @property
    def has_context(self):
        return bool(self.page_url or self.user_agent)

    class Meta:
        verbose_name = _("Feedback")
        verbose_name_plural = _("Feedback")
        ordering = ["-created"]
