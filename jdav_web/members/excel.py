from datetime import datetime
import os
import xlsxwriter
import openpyxl
from django.conf import settings
from contrib.media import media_path, find_template
from utils import normalize_filename
from .models import WEEKDAYS, LJPProposal

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


VBK_TEMPLATES = {
    LJPProposal.LJP_STAFF_TRAINING: 'members/LJP_VBK_3-1.xlsx',
    LJPProposal.LJP_EDUCATIONAL: 'members/LJP_VBK_3-2.xlsx',
}

NOT_BW_REASONS = {
    LJPProposal.NOT_BW_CONTENT: 'aufgrund der Lehrgangsinhalte',
    LJPProposal.NOT_BW_ROOMS: 'trägereigene Räumlichkeiten',
    LJPProposal.NOT_BW_CLOSE_BORDER: 'Grenznähe',
    LJPProposal.NOT_BW_ECONOMIC: 'wirtschaftliche Sparsamkeit',
}

LJP_GOALS = {
    LJPProposal.LJP_QUALIFICATION: 'Qualifizierung',
    LJPProposal.LJP_PARTICIPATION: 'Partizipation',
    LJPProposal.LJP_DEVELOPMENT: 'Persönlichkeitsentwicklung',
    LJPProposal.LJP_ENVIRONMENT: 'Umwelt',
}


def generate_ljp_vbk(excursion):
    """
    Generate the VBK forms for LJP given an excursion. Returns the filename to the filled excel file.
    """
    if not hasattr(excursion, 'ljpproposal'):
        raise ValueError(f"Excursion has no LJP proposal.")
    template_path = VBK_TEMPLATES[excursion.ljpproposal.category]
    path = find_template(template_path)
    workbook = openpyxl.load_workbook(path)

    sheet = workbook.active
    title = excursion.ljpproposal.title

    sheet['I6'] = settings.SEKTION_IBAN
    sheet['I8'] = settings.SEKTION_ACCOUNT_HOLDER
    sheet['P3'] = excursion.end.year
    sheet['B4'] = f"Sektion {settings.SEKTION}"
    sheet['B5'] = settings.SEKTION_STREET
    sheet['B6'] = settings.SEKTION_TOWN
    sheet['B7'] = settings.RESPONSIBLE_MAIL
    sheet['B36'] = f"{settings.SEKTION}, {datetime.today():%d.%m.%Y}"
    sheet['F19'] = excursion.code
    sheet['C19'] = LJP_GOALS[excursion.ljpproposal.goal] if excursion.ljpproposal.goal in LJP_GOALS else ""
    sheet['D19'] = settings.SEKTION
    sheet['G19'] = title
    sheet['I19'] = f"von {excursion.date:%d.%m.%y} bis {excursion.end:%d.%m.%y}"
    sheet['J19'] = excursion.ljp_duration
    sheet['L19'] = f"{excursion.ljp_participant_count}"
    sheet['H19'] = excursion.get_ljp_activity_category()
    sheet['M19'] = f"{excursion.postcode}, {excursion.place}"
    sheet['N19'] = f"{NOT_BW_REASONS[excursion.ljpproposal.not_bw_reason]}"\
        if not excursion.ljpproposal.not_bw_reason is None else ""

    if hasattr(excursion, 'statement'):
        sheet['Q19'] = f"{excursion.statement.total_theoretic}"

    name = normalize_filename(f"{excursion.code}_{title}_LJP_V-BK_3.{excursion.ljpproposal.category}",
                              date=excursion.date)
    filename = name + ".xlsx"
    workbook.save(media_path(filename))
    return filename
