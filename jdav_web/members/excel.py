from datetime import datetime
import os
import xlsxwriter
from django.conf import settings
from contrib.media import media_path
from .models import WEEKDAYS

def generate_group_overview(all_groups, limit_to_public = True):
    """
    Creates an Excel Sheet with an overview of all the groups, their dates, times, age range and
    number of members, etc.

    arguments:
    limit_to_public (optional, default is True): If False, all groups are returned in the overview,
    including technical ones. If True, only groups with the flag "show_on_website" are returned.

    """
    today = f"{datetime.today():%d.%m.%Y}"
    filename = f"gruppenuebersicht_jdav_{settings.SEKTION}_{today}.xlsx"
    workbook = xlsxwriter.Workbook(media_path(filename))
    default = workbook.add_format({'text_wrap' : True, 'border': 1})
    bold = workbook.add_format({'bold': True, 'border': 1})
    title = workbook.add_format({'bold': True, 'font_size': 16, 'align': 'center'})
    right = workbook.add_format({'bold': True, 'align': 'right'})
    worksheet = workbook.add_worksheet()

    worksheet.merge_range(0, 0, 0, 6, f"Gruppenübersicht JDAV {settings.SEKTION}", title)
    row = 1
    worksheet.write(row, 0, "Gruppe", bold)
    worksheet.write(row, 1, "Wochentag", bold)
    worksheet.write(row, 2, "Uhrzeit", bold)
    worksheet.write(row, 3, "Altersgruppe", bold)
    worksheet.write(row, 4, "TN", bold)
    worksheet.write(row, 5, "JL", bold)
    worksheet.write(row, 6, "Jugendleiter*innen", bold)

    for group in all_groups:
        # choose if only official youth groups on the website are shown
        if limit_to_public and not group.show_website:
            continue

        row = row + 1
        wd = f"{WEEKDAYS[group.weekday][1]}" if group.weekday else 'kein Wochentag'
        times = f"{group.start_time:%H:%M} - {group.end_time:%H:%M}" if group.start_time and group.end_time else 'keine Zeiten'
        yl_count = len([member for member in group.member_set.all() if member in group.leiters.all()])
        tn_count = group.member_set.count() - yl_count
        members = f"JG {group.year_from} - {group.year_to}"
        leaders = f"{', '.join([yl.name for yl in group.leiters.all()])}"

        worksheet.write(row, 0, group.name, default)
        worksheet.write(row, 1, wd, default)
        worksheet.write(row, 2, times, default)
        worksheet.write(row, 3, members, default)
        worksheet.write(row, 4, tn_count, default)
        worksheet.write(row, 5, yl_count, default)
        worksheet.write(row, 6, leaders, default)

    worksheet.write(row+2, 6, f"Stand: {today}", right)
    # set column width
    worksheet.set_column_pixels(0, 0, 100)
    worksheet.set_column_pixels(1, 1, 80)
    worksheet.set_column_pixels(2, 2, 90)
    worksheet.set_column_pixels(3, 3, 120)
    worksheet.set_column_pixels(4, 4, 20)
    worksheet.set_column_pixels(5, 5, 20)
    worksheet.set_column_pixels(6, 6, 140)
    workbook.close()

    return filename
