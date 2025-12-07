from datetime import datetime

from django.db import models
from django.utils.translation import gettext_lazy as _

from .group import Group
from .member import Member


class Klettertreff(models.Model):
    """This model represents a Klettertreff event.

    A Klettertreff can take a date, location, Jugendleiter, attending members
    as input.
    """

    date = models.DateField(_("Date"), default=datetime.today)
    location = models.CharField(_("Location"), default="", max_length=60)
    topic = models.CharField(_("Topic"), default="", max_length=60)
    jugendleiter = models.ManyToManyField(Member)
    group = models.ForeignKey(Group, default="", verbose_name=_("Group"), on_delete=models.CASCADE)

    def __str__(self):
        return self.location + " " + self.date.strftime("%d.%m.%Y")

    def get_jugendleiter(self):
        jl_string = ", ".join(j.name for j in self.jugendleiter.all())
        return jl_string

    def has_attendee(self, member):
        queryset = KlettertreffAttendee.objects.filter(
            member__id__contains=member.id, klettertreff__id__contains=self.id
        )
        if queryset:
            return True
        return False

    def has_jugendleiter(self, jugendleiter):
        if jugendleiter in self.jugendleiter.all():
            return True
        return False

    get_jugendleiter.short_description = _("Jugendleiter")

    class Meta:
        verbose_name = _("Klettertreff")
        verbose_name_plural = _("Klettertreffs")


class KlettertreffAttendee(models.Model):
    """Connects members to Klettertreffs."""

    member = models.ForeignKey(Member, verbose_name=_("Member"), on_delete=models.CASCADE)
    klettertreff = models.ForeignKey(Klettertreff, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.member)

    class Meta:
        verbose_name = _("Member")
        verbose_name_plural = _("Members")
