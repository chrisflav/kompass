from django.db import models
from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import prepend_base_url

from .constants import WEEKDAYS


class Group(models.Model):
    """
    Represents one group of the association
    e.g: J1, J2, Jugendleiter, etc.
    """

    name = models.CharField(max_length=50, verbose_name=_("name"))  # e.g: J1
    description = models.TextField(verbose_name=_("description"), default="", blank=True)
    show_website = models.BooleanField(verbose_name=_("show on website"), default=False)
    year_from = models.IntegerField(verbose_name=_("lowest year"), default=2010)
    year_to = models.IntegerField(verbose_name=_("highest year"), default=2011)
    leiters = models.ManyToManyField(
        "members.Member", verbose_name=_("youth leaders"), related_name="leited_groups", blank=True
    )
    weekday = models.IntegerField(
        verbose_name=_("week day"), choices=WEEKDAYS, null=True, blank=True
    )
    start_time = models.TimeField(verbose_name=_("Starting time"), null=True, blank=True)
    end_time = models.TimeField(verbose_name=_("Ending time"), null=True, blank=True)
    contact_email = models.ForeignKey(
        "mailer.EmailAddress",
        verbose_name=_("Contact email"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        """String representation"""
        return self.name

    class Meta:
        verbose_name = _("group")
        verbose_name_plural = _("groups")

    @property
    def sorted_members(self):
        """Returns the members of this group sorted by their last name."""
        return self.member_set.all().order_by("lastname")

    def has_time_info(self):
        # return if the group has all relevant time slot information filled
        return self.weekday and self.start_time and self.end_time

    def get_time_info(self):
        if self.has_time_info():
            return settings.GROUP_TIME_AVAILABLE_TEXT.format(
                weekday=WEEKDAYS[self.weekday][1],
                start_time=self.start_time.strftime("%H:%M"),
                end_time=self.end_time.strftime("%H:%M"),
            )
        else:
            return ""

    def has_age_info(self):
        return self.year_from and self.year_to

    def get_age_info(self):
        if self.has_age_info():
            return _("years %(from)s to %(to)s") % {"from": self.year_from, "to": self.year_to}
        return ""

    def get_invitation_text_template(self):
        """The text template used to invite waiters to this group. This contains
        placeholders for the name of the waiter and personalized links."""
        if self.show_website:
            group_link = "({url}) ".format(
                url=prepend_base_url(reverse("startpage:gruppe_detail", args=[self.name]))
            )
        else:
            group_link = ""
        if self.has_time_info():
            group_time = self.get_time_info()
        else:
            group_time = settings.GROUP_TIME_UNAVAILABLE_TEXT.format(
                contact_email=self.contact_email
            )
        if self.has_age_info():
            group_age = self.get_age_info()
        else:
            group_age = _("no information available")

        return settings.INVITE_TEXT.format(
            group_time=group_time,
            group_name=self.name,
            group_age=group_age,
            group_link=group_link,
            contact_email=self.contact_email,
        )
