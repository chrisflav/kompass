from contrib.models import CommonModel
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from members.models import Group
from members.models import Member


class Calendar(CommonModel):
    """Represents a calendar that can contain events."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=100,
    )
    visibility_group = models.ManyToManyField(
        Group,
        verbose_name=_("Visible to groups"),
        blank=True,
        related_name="visible_calendars_group",
    )
    visibility_member = models.ManyToManyField(
        Member,
        verbose_name=_("Visible to members"),
        blank=True,
        related_name="visible_calendars_member",
    )

    def __str__(self):
        return self.name

    class Meta(CommonModel.Meta):
        verbose_name = _("Calendar")
        verbose_name_plural = _("Calendars")


class Event(CommonModel):
    """Base event model for calendar events."""

    name = models.CharField(
        verbose_name=_("Name"),
        max_length=200,
    )
    description = models.TextField(
        verbose_name=_("Description"),
        blank=True,
    )

    start_datetime = models.DateTimeField(
        verbose_name=_("Start"),
        default=timezone.now,
    )
    end_datetime = models.DateTimeField(
        verbose_name=_("End"),
        default=timezone.now,
    )

    def __str__(self):
        return self.name

    class Meta(CommonModel.Meta):
        verbose_name = _("Event")
        verbose_name_plural = _("Events")


class ManualEvent(Event):
    """A manually created event that belongs to a specific calendar."""

    calendar = models.ForeignKey(
        Calendar,
        verbose_name=_("Calendar"),
        on_delete=models.CASCADE,
        related_name="manual_events",
    )

    class Meta(Event.Meta):
        verbose_name = _("Manual Event")
        verbose_name_plural = _("Manual Events")


class RepeatedEvent(Event):
    """An event that repeats at regular intervals."""

    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"

    REPEAT_INTERVAL_CHOICES = [
        (DAILY, _("Daily")),
        (WEEKLY, _("Weekly")),
        (BIWEEKLY, _("Biweekly")),
        (MONTHLY, _("Monthly")),
    ]

    repeat = models.BooleanField(
        verbose_name=_("Repeat"),
        default=False,
    )
    repeat_interval = models.CharField(
        verbose_name=_("Repeat Interval"),
        max_length=10,
        choices=REPEAT_INTERVAL_CHOICES,
        default=WEEKLY,
        blank=True,
    )

    def __str__(self):
        if self.repeat:
            return f"{self.name} ({self.get_repeat_interval_display()})"
        return self.name

    class Meta(Event.Meta):
        verbose_name = _("Repeated Event")
        verbose_name_plural = _("Repeated Events")


# Create your models here.
