import os

from django.contrib import admin
from wsgiref.util import FileWrapper
from django.http import HttpResponse
from django.conf import settings
from .models import Group, Termin

import xlsxwriter


class GroupAdmin(admin.ModelAdmin):
    list_display = ('name',)


class TerminAdmin(admin.ModelAdmin):
    list_display = ('title','start_date', 'end_date', 'group', 'responsible')
    list_filter = ('group',)
    ordering = ('start_date','end_date')
    actions = ['make_overview']

    def make_overview(self, request, queryset):
        filename = 'termine.xlsx'
        workbook = xlsxwriter.Workbook(media_path(filename))
        bold = workbook.add_format({'bold': True})
        worksheet = workbook.add_worksheet()
        worksheet.write(0, 0, "Titel", bold)
        worksheet.write(0, 1, "Von", bold)
        worksheet.write(0, 2, "Bis", bold)
        worksheet.write(0, 3, "Gruppe", bold)
        worksheet.write(0, 4, "Organisator", bold)
        worksheet.write(0, 5, "Telefonnummer", bold)
        worksheet.write(0, 6, "Emailadresse", bold)
        worksheet.write(0, 7, "Tourenbeschreibung/Anforderung", bold)
        for row, termin in enumerate(queryset):
            worksheet.write(row+2, 0, termin.title)
            worksheet.write(row+2, 1, termin.start_date.strftime('%d.%m.%Y'))
            worksheet.write(row+2, 2, termin.end_date.strftime('%d.%m.%Y'))
            worksheet.write(row+2, 3, str(termin.group))
            worksheet.write(row+2, 4, termin.responsible)
            worksheet.write(row+2, 5, termin.phone)
            worksheet.write(row+2, 6, termin.email)
            worksheet.write(row+2, 7, termin.description)
        workbook.close()
        with open(media_path(filename), 'rb') as xls:
            response = HttpResponse(FileWrapper(xls))
            response['Content-Type'] = 'application/xlsx'
            response['Content-Disposition'] = 'attachment; filename='+filename

        return response
    make_overview.short_description = "Termine in Excel Liste überführen"

# Register your models here.
admin.site.register(Group, GroupAdmin)
admin.site.register(Termin, TerminAdmin)


def media_path(fp):
    return os.path.join(os.path.join(settings.MEDIA_MEMBERLISTS, "memberlists"), fp)
