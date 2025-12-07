from contrib.admin import CommonAdminMixin
from django.contrib import admin

from .models import Calendar
from .models import ManualEvent
from .models import RepeatedEvent


@admin.register(Calendar)
class CalendarAdmin(CommonAdminMixin, admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("visibility_group", "visibility_member")
    search_fields = ("name",)


@admin.register(ManualEvent)
class ManualEventAdmin(CommonAdminMixin, admin.ModelAdmin):
    list_display = ("name", "calendar", "start_datetime", "end_datetime")
    list_filter = ("calendar", "start_datetime")
    search_fields = ("name", "description")
    ordering = ("-start_datetime",)
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "description", "calendar"),
            },
        ),
        (
            "Timing",
            {
                "fields": ("start_datetime", "end_datetime"),
            },
        ),
    )


@admin.register(RepeatedEvent)
class RepeatedEventAdmin(CommonAdminMixin, admin.ModelAdmin):
    list_display = ("name", "repeat", "repeat_interval", "start_datetime")
    list_filter = ("repeat", "repeat_interval", "start_datetime")
    search_fields = ("name", "description")
    ordering = ("-start_datetime",)
    fieldsets = (
        (
            None,
            {
                "fields": ("name", "description"),
            },
        ),
        (
            "Timing",
            {
                "fields": ("start_datetime", "end_datetime"),
            },
        ),
        (
            "Repetition",
            {
                "fields": ("repeat", "repeat_interval"),
                "description": "Configure if and how this event repeats",
            },
        ),
    )
