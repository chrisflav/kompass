from datetime import datetime

from contrib.media import media_path
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import send as send_mail
from members.pdf import render_tex

from .member_on_list import NewMemberOnList


class MemberNoteList(models.Model):
    """
    A member list with a title and a bunch of members to take some notes.
    Can also be used to generate crisis intervention lists for smaller events.
    """

    title = models.CharField(verbose_name=_("Title"), default="", max_length=50)
    date = models.DateField(default=datetime.today, verbose_name=_("Date"), null=True, blank=True)
    date_end = models.DateField(
        verbose_name=_("End date (optional)"),
        null=True,
        blank=True,
        help_text=_("End date for multi-day activities"),
    )
    location = models.CharField(
        verbose_name=_("Location"),
        max_length=100,
        blank=True,
        default="",
        help_text=_("Location of the activity (for crisis intervention lists)"),
    )
    description = models.TextField(
        verbose_name=_("Description"),
        blank=True,
        default="",
        help_text=_("Additional information about the activity"),
    )
    membersonlist = GenericRelation(NewMemberOnList)

    def __str__(self):
        """String represenation"""
        return self.title

    def get_dropdown_display(self):
        """Return a string suitable for display in admin dropdown menus."""
        if self.date:
            return f"{self.title} - {self.date.strftime('%d.%m.%Y')}"
        return self.title

    def get_absolute_url(self):
        return reverse("admin:members_membernotelist_change", args=[str(self.id)])

    @property
    def time_period_str(self):
        """Format the time period as a string."""
        if not self.date:
            return ""
        time_period = self.date.strftime("%d.%m.%Y")
        if self.date_end and self.date_end != self.date:
            time_period += " - " + self.date_end.strftime("%d.%m.%Y")
        return time_period

    @property
    def code(self):
        """Generate a code for this member note list."""
        if self.date:
            return f"N{self.date:%y}-{self.pk}"
        return f"N-{self.pk}"

    def send_crisis_intervention_list(self, recipients=None):
        """
        Generate and send the crisis intervention list as PDF.

        Args:
            recipients: List of email addresses to send to. If None, sends to crisis intervention email.
        """
        if recipients is None:
            recipients = [settings.SEKTION_CRISIS_INTERVENTION_MAIL]

        context = dict(memberlist=self, settings=settings)
        filename = render_tex(
            f"{self.code}_{self.title}_Krisenliste",
            "members/crisis_intervention_list.tex",
            context,
            date=self.date if self.date else datetime.today(),
            save_only=True,
        )

        # Create email with attachment
        send_mail(
            _("Crisis intervention list for %(activity)s") % {"activity": self.title},
            _(
                "Please find attached the crisis intervention list for the activity '%(activity)s'.\n\n"
                "Time period: %(time_period)s\n"
                "Location: %(location)s"
            )
            % {
                "activity": self.title,
                "time_period": self.time_period_str,
                "location": self.location or _("Not specified"),
            },
            sender=settings.DEFAULT_SENDING_MAIL,
            recipients=recipients,
            attachments=[media_path(filename)],
        )

    @staticmethod
    def filter_queryset_by_change_permissions(user, queryset=None):
        if queryset is None:
            queryset = MemberNoteList.objects.all()
        if user.has_perm("members.change_membernotelist"):
            return queryset
        else:
            return MemberNoteList.objects.none()

    def add_members(self, queryset):
        content_type = ContentType.objects.get_for_model(MemberNoteList)

        # Add selected members to the note list
        for member in queryset:
            NewMemberOnList.objects.get_or_create(
                member=member, content_type=content_type, object_id=self.pk
            )

    class Meta:
        verbose_name = "Notizliste"
        verbose_name_plural = "Notizlisten"
