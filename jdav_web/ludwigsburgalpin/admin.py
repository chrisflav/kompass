from django.contrib import admin

from .excel import generate_termin_overview
from .models import Termin


class TerminAdmin(admin.ModelAdmin):
    list_display = ("title", "start_date", "end_date", "group", "category", "responsible")
    list_filter = ("group",)
    ordering = ("start_date", "end_date")
    actions = ["make_overview"]

    def make_overview(self, request, queryset):
        return generate_termin_overview(queryset)

    make_overview.short_description = "Termine in Excel Liste überführen"


# Register your models here.
admin.site.register(Termin, TerminAdmin)
