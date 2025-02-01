import os

from django.contrib import admin
from wsgiref.util import FileWrapper
from django.http import HttpResponse
from django.conf import settings
from .models import Termin
from contrib.media import media_path, serve_media, ensure_media_dir

import xlsxwriter


class TerminAdmin(admin.ModelAdmin):
    list_display = ('title','start_date', 'end_date', 'group', 'category', 'responsible')
    list_filter = ('group',)
    ordering = ('start_date','end_date')
    actions = ['make_overview']

    def make_overview(self, request, queryset):
        ensure_media_dir()
        filename = 'termine.xlsx'
        workbook = xlsxwriter.Workbook(media_path(filename))
        bold = workbook.add_format({'bold': True})
        worksheet = workbook.add_worksheet()
        worksheet.write(0, 0, "Titel", bold)
        worksheet.write(0, 1, "Untertitel", bold)
        worksheet.write(0, 2, "Von", bold)
        worksheet.write(0, 3, "Bis", bold)
        worksheet.write(0, 4, "Gruppe", bold)
        worksheet.write(0, 5, "Kategorie", bold)
        worksheet.write(0, 6, "Technik", bold)
        worksheet.write(0, 7, "Kondition", bold)
        worksheet.write(0, 8, "Saison", bold)
        worksheet.write(0, 9, "Eventart", bold)
        worksheet.write(0, 10, "Klassifizierung", bold)
        worksheet.write(0, 11, "Höhenmeter (Meter)", bold)
        worksheet.write(0, 12, "Strecke (Kilometer)", bold)
        worksheet.write(0, 13, "Etappendauer (Stunden)", bold)
        worksheet.write(0, 14, "Voraussetzungen", bold)
        worksheet.write(0, 15, "Beschreibung", bold)
        worksheet.write(0, 16, "Ausrüstung", bold)
        worksheet.write(0, 17, "Max. Teilnehmerzahl", bold)
        worksheet.write(0, 18, "Organisator", bold)
        worksheet.write(0, 19, "Telefonnummer", bold)
        worksheet.write(0, 20, "Emailadresse", bold)
        for row, termin in enumerate(queryset):
            worksheet.write(row+2, 0, termin.title)
            worksheet.write(row+2, 1, termin.subtitle)
            worksheet.write(row+2, 2, termin.start_date.strftime('%d.%m.%Y'))
            worksheet.write(row+2, 3, termin.end_date.strftime('%d.%m.%Y'))
            worksheet.write(row+2, 4, termin.group)
            worksheet.write(row+2, 5, termin.category)
            worksheet.write(row+2, 6, termin.technik)
            worksheet.write(row+2, 7, termin.condition)
            worksheet.write(row+2, 8, termin.saison)
            worksheet.write(row+2, 9, termin.eventart)
            worksheet.write(row+2, 10, termin.klassifizierung)
            worksheet.write(row+2, 11, termin.anforderung_hoehe)
            worksheet.write(row+2, 12, termin.anforderung_strecke)
            worksheet.write(row+2, 13, termin.anforderung_dauer)
            worksheet.write(row+2, 14, termin.voraussetzungen)
            worksheet.write(row+2, 15, termin.description)
            worksheet.write(row+2, 16, termin.equipment)
            worksheet.write(row+2, 17, termin.max_participants)
            worksheet.write(row+2, 18, termin.responsible)
            worksheet.write(row+2, 19, termin.phone)
            worksheet.write(row+2, 20, termin.email)
        workbook.close()
        return serve_media(filename, 'application/xlsx')
    make_overview.short_description = "Termine in Excel Liste überführen"

# Register your models here.
admin.site.register(Termin, TerminAdmin)
