from datetime import datetime, timedelta
import glob
import os
import subprocess
import shutil
import time
import unicodedata
import random
import string

from django.http import HttpResponse, HttpResponseRedirect
from wsgiref.util import FileWrapper
from django import forms
from django.contrib import admin, messages
from django.contrib.admin import DateFieldListFilter
from django.contrib.contenttypes.admin import GenericTabularInline
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from django.db.models import TextField, ManyToManyField, ForeignKey, Count,\
    Sum, Case, Q, F, When, Value, IntegerField, Subquery, OuterRef
from django.forms import Textarea, RadioSelect, TypedChoiceField
from django.shortcuts import render

from .models import (Member, Group, Freizeit, MemberNoteList, NewMemberOnList, Klettertreff,
                     KlettertreffAttendee, ActivityCategory, OldMemberOnList, MemberList,
                     annotate_activity_score, RegistrationPassword, MemberUnconfirmedProxy)
from mailer.mailutils import send as send_mail, get_echo_link, mail_root
from django.conf import settings
#from easy_select2 import apply_select2


class RegistrationFilter(admin.SimpleListFilter):
    title = _('Registration complete')
    parameter_name = 'registered'
    default_value = ('All', None)

    def lookups(self, request, model_admin):
        return (
            ('True', _('True')),
            ('False', _('False')),
            ('All', _('All'))
        )

    def queryset(self, request, queryset):
        if self.value() == 'True':
            return queryset.filter(registered=True)
        elif self.value() == 'False':
            return queryset.filter(registered=False)
        elif self.value() is None:
            if self.default_value[1] is None:
                return queryset
            else:
                return queryset.filter(registered=self.default_value[1])
        elif self.value() == 'All':
            return queryset

    def choices(self, cl):
        for lookup, title in self.lookup_choices:
            yield {
                'selected':
                    self.value() == lookup or
                    (self.value() is None and lookup == self.default_value[0]),
                'query_string': cl.get_query_string({
                                    self.parameter_name:
                                    lookup,
                                }, []),
                'display': title
            }


# Register your models here.
class MemberAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'email_parents', 'cc_email_parents', 'street', 'plz',
              'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group',
              'gets_newsletter', 'registered', 'registration_form', 'active',
              'not_waiting', 'echoed', 'comments']
    list_display = ('name', 'birth_date', 'age', 'get_group', 'gets_newsletter',
                    'registered', 'active', 'not_waiting', 'echoed', 'comments', 'activity_score')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'gets_newsletter', RegistrationFilter, 'active',
                   'not_waiting')
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}
    change_form_template = "members/change_member.html"
    #ordering = ('activity_score',)
    actions = ['send_mail_to', 'request_echo']

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return annotate_activity_score(queryset.filter(confirmed=True))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context['qualities'] =\
            Member.objects.get(pk=object_id).get_skills()
        extra_context['activities'] =\
            Member.objects.get(pk=object_id).get_activities()
        return super(MemberAdmin, self).change_view(request, object_id,
                                                    form_url=form_url,
                                                    extra_context=extra_context)

    def send_mail_to(self, request, queryset):
        member_pks = [m.pk for m in queryset]
        query = str(member_pks).replace(' ', '')
        return HttpResponseRedirect("/admin/mailer/message/add/?members={}".format(query))
    send_mail_to.short_description = _('Compose new mail to selected members')

    def request_echo(self, request, queryset):
        for member in queryset:
            if not member.gets_newsletter:
                continue
            send_mail("Wichtig: Rückmeldung erforderlich!",
                      """Hallo {name},

um unsere Daten auf dem aktuellen Stand zu halten, brauchen wir eine
kurze Bestätigung von dir. Dafür besuche einfach diesen Link:

{link}

Dort kannst du deine Daten überprüfen und ändern. Falls du nicht innerhalb von
30 Tagen deine Daten bestätigst, wirst du aus unserer Datenbank gelöscht und
erhälst in Zukunft keine Mails mehr von uns.

Bei Fragen, wende dich gerne an jugendreferent@jdav-ludwigsburg.de.

Viele Grüße
Deine JDAV Ludwigsburg""".format(name=member.prename, link=get_echo_link(member)),
                      mail_root,
                      [member.email, member.email_parents] if member.email_parents and member.cc_email_parents
                      else member.email)
        messages.success(request, _("Successfully requested echo from selected members."))
    request_echo.short_description = _('Request echo from selected members')

    def activity_score(self, obj):
        score = obj._activity_score
        # show 1 to 5 climbers based on activity in last year
        if score < 5:
            level = 1
        elif score >= 5 and score < 10:
            level = 2
        elif score >= 10 and score < 20:
            level = 3
        elif score >= 20 and score < 30:
            level = 4
        else:
            level = 5
        return format_html(level*'<img height=20px src="{}"/>&nbsp;'.format("/static/admin/images/climber.png"))
    activity_score.admin_order_field = '_activity_score'
    activity_score.short_description = _('activity')


class MemberUnconfirmedAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'email_parents', 'cc_email_parents', 'street', 'plz',
              'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group',
              'registered', 'registration_form', 'active',
              'not_waiting', 'comments']
    list_display = ('name', 'birth_date', 'age', 'get_group', 'confirmed_mail', 'confirmed_mail_parents')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'confirmed_mail', 'confirmed_mail_parents')
    actions = ['request_mail_confirmation', 'confirm']
    change_form_template = "members/change_member_unconfirmed.html"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.filter(confirmed=False)

    def request_mail_confirmation(self, request, queryset):
        for member in queryset:
            member.request_mail_confirmation()
        messages.success(request, _("Successfully requested mail confirmation from selected registrations."))
    request_mail_confirmation.short_description = _('Request mail confirmation from selected registrations')

    def confirm(self, request, queryset):
        notify_individual = len(queryset.all()) < 10
        success = True
        for member in queryset:
            if member.confirm() and notify_individual:
                messages.success(request, _("Successfully confirmed %(name)s.") % {'name': member.name})
            else:
                if notify_individual:
                    messages.error(request,
                            _("Can't confirm. %(name)s has unconfirmed email addresses.") % {'name': member.name})
                success = False
        if notify_individual:
            return
        if success:
            messages.success(request, _("Successfully confirmed multiple registrations."))
        else:
            messages.error(request, _("Failed to confirm some registrations because of unconfirmed email addresses."))
    confirm.short_description = _('Confirm selected registrations')

    def response_change(self, request, member):
        if "_confirm" in request.POST:
            if member.confirm():
                messages.success(request, _("Successfully confirmed %(name)s.") % {'name': member.name})
            else:
                messages.error(request,
                        _("Can't confirm. %(name)s has unconfirmed email addresses.") % {'name': member.name})
        return super(MemberUnconfirmedAdmin, self).response_change(request, member)


class RegistrationPasswordInline(admin.TabularInline):
    model = RegistrationPassword
    extra = 0


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'year_from', 'year_to']
    list_display = ('name', 'year_from', 'year_to')
    inlines = [RegistrationPasswordInline]


class ActivityCategoryAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


class FreizeitAdminForm(forms.ModelForm):
    difficulty = TypedChoiceField(choices=Freizeit.difficulty_choices,
                                  coerce=int,
                                  label=_('Difficulty'))
    tour_type = TypedChoiceField(choices=Freizeit.tour_type_choices,
                                 coerce=int,
                                 label=_('Tour type'))
    tour_approach = TypedChoiceField(choices=Freizeit.tour_approach_choices,
                                 coerce=int,
                                 label=_('Tour type'))

    class Meta:
        model = Freizeit
        exclude = ['add_member']

    def __init__(self, *args, **kwargs):
        super(FreizeitAdminForm, self).__init__(*args, **kwargs)
        self.fields['jugendleiter'].queryset = Member.objects.filter(group__name='Jugendleiter')
        #self.fields['add_member'].queryset = Member.objects.filter(prename__startswith='F')


class MemberOnListInline(GenericTabularInline):
    model = NewMemberOnList
    extra = 0
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1,
                                              'cols': 40})}
    }


class OldMemberOnListInline(admin.TabularInline):
    model = OldMemberOnList
    extra = 0


class MemberNoteListAdmin(admin.ModelAdmin):
    inlines = [MemberOnListInline]
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    ordering = ('-date',)
    actions = ['generate_summary']
    
    def generate_summary(self, request, queryset):
        """Generates a pdf summary of the given NoteMemberLists
        """
        for memberlist in queryset:
            # unique filename
            filename = memberlist.title + "_notes_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_').replace('&', '')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # generate table
            table = ""
            for memberonlist in memberlist.membersonlist.all():
                m = memberonlist.member
                comment = ". ".join(c for c
                                    in (m.comments,
                                        memberonlist.comments) if
                                    c).replace("..", ".")
                line = '{0} {1} & {2} \\\\'.format(
                    esc_ampersand(m.prename), esc_ampersand(m.lastname),
	            esc_ampersand(comment) or "---")
                table += esc_underscore(line)

            # copy template
            shutil.copy(media_path('memberlistnote_template.tex'),
                        media_path(filename_tex))

            # read in template
            with open(media_path(filename_tex), 'r', encoding='utf-8') as f:
                template_content = f.read()

            # adapt template
            title = esc_all(memberlist.title)
            template_content = template_content.replace('MEMBERLIST-TITLE', title)
            template_content = template_content.replace('MEMBERLIST-DATE',
                    datetime.today().strftime('%d.%m.%Y'))
            template_content = template_content.replace('TABLE', table)

            # write adapted template to file
            with open(media_path(filename_tex), 'w', encoding='utf-8') as f:
                f.write(template_content)

            # compile using pdflatex
            oldwd = os.getcwd()
            os.chdir(media_dir())
            subprocess.call(['pdflatex', filename_tex])
            time.sleep(1)

            # do some cleanup
            for f in glob.glob('*.log'):
                os.remove(f)
            for f in glob.glob('*.aux'):
                os.remove(f)
            os.remove(filename_tex)

            os.chdir(oldwd)

            # provide the user with the resulting pdf file
            with open(media_path(filename_pdf), 'rb') as pdf:
                response = HttpResponse(FileWrapper(pdf))
                response['Content-Type'] = 'application/pdf'
                response['Content-Disposition'] = 'attachment; filename=' + filename_pdf

            return response
    generate_summary.short_description = "PDF Übersicht erstellen"



class MemberListAdmin(admin.ModelAdmin):
    inlines = [OldMemberOnListInline]
    form = FreizeitAdminForm
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    actions = ['migrate_to_freizeit', 'migrate_to_notelist']
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}

    def __init__(self, *args, **kwargs):
        super(MemberListAdmin, self).__init__(*args, **kwargs)

    def migrate_to_freizeit(self, request, queryset):
        """Creates 'Freizeiten' from the given memberlists """
        for memberlist in queryset:
            freizeit = Freizeit(name=memberlist.name,
                                place=memberlist.place,
                                destination=memberlist.destination,
                                date=memberlist.date,
                                end=memberlist.end,
                                tour_type=memberlist.tour_type,
                                difficulty=memberlist.difficulty)
            freizeit.save()
            freizeit.jugendleiter = memberlist.jugendleiter.all()
            freizeit.groups = memberlist.groups.all()
            freizeit.activity = memberlist.activity.all()
            for memberonlist in memberlist.oldmemberonlist_set.all():
                newonlist = NewMemberOnList(member=memberonlist.member,
                                            comments=memberonlist.comments,
                                            memberlist=freizeit)
                newonlist.save()
        messages.info(request, "Freizeit(en) erfolgreich erstellt.")
    migrate_to_freizeit.short_description = "Aus Teilnehmerliste(n) Freizeit(en) erstellen"

    def migrate_to_notelist(self, request, queryset):
        """Creates 'MemberNoteList' from the given memberlists """
        for memberlist in queryset:
            notelist = MemberNoteList(title=memberlist.name,
                                      date=memberlist.date)
            notelist.save()
            for memberonlist in memberlist.oldmemberonlist_set.all():
                newonlist = NewMemberOnList(member=memberonlist.member,
                                            comments=memberonlist.comments,
                                            memberlist=notelist)
                newonlist.save()
        messages.info(request, "Teilnehmerlist(en) erfolgreich erstellt.")
    migrate_to_notelist.short_description = "Aus Teilnehmerliste(n) Notizliste erstellen"

class FreizeitAdmin(admin.ModelAdmin):
    inlines = [MemberOnListInline]
    form = FreizeitAdminForm
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    ordering = ('-date',)
    actions = ['convert_to_pdf', 'generate_notes', 'convert_to_ljp']
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}

    def __init__(self, *args, **kwargs):
        super(FreizeitAdmin, self).__init__(*args, **kwargs)

    def convert_to_pdf(self, request, queryset):
        """Converts a member list to pdf.
        """
        for memberlist in queryset:
            # create a unique filename
            filename = memberlist.name + "_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_').replace('&', '')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_table = 'table_' + filename
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # open temporary file for table
            with open(media_path(filename_table), 'w+', encoding='utf-8') as f:
                if memberlist.membersonlist.count() == 0:
                    f.write('{0} & {1} & {2} & {3} \\\\ \n'.format(
                        'keine Teilnehmer', '-', '-', '-'
                    ))
                for memberonlist in memberlist.membersonlist.all():
                    # write table of members in latex compatible format
                    member = memberonlist.member
                    # use parents phone number if available
                    phone_number = member.phone_number_parents if\
                        member.phone_number_parents else member.phone_number
                    # use parents email address if available
                    email = member.email_parents if\
                        member.email_parents else member.email
                    line = '{0} {1} & {2} & {3} & \\Email{{{4}}} \\\\ \n'.format(
                            esc_all(memberonlist.member.prename),
                            esc_all(memberonlist.member.lastname),
                            esc_all(memberonlist.member.address),
                            esc_all(memberonlist.member.contact_phone_number),
                            memberonlist.member.contact_email) # don't escape here, because url is used in tex
                    f.write(line)

            # copy and adapt latex memberlist template
            shutil.copy(media_path('memberlist_template.tex'),
                        media_path(filename_tex))

            # read in template
            with open(media_path(filename_tex), 'r', encoding='utf-8') as f:
                template_content = f.read()

            # adapt template
            name = esc_all(memberlist.name)
            template_content = template_content.replace('ACTIVITY', name)
            groups = ', '.join(g.name for g in
                               memberlist.groups.all())
            template_content = template_content.replace('GROUP',
                                                        esc_all(groups))
            destination = esc_all(memberlist.destination)
            template_content = template_content.replace('DESTINATION',
                                                        destination)
            place = esc_all(memberlist.place)
            template_content = template_content.replace('PLACE', place)
            template_content = template_content.replace('MEMBERLIST-DATE',
                                                        datetime.today().strftime('%d.%m.%Y'))
            time_period = memberlist.date.strftime('%d.%m.%Y')
            if memberlist.end != memberlist.date:
                time_period += " - " + memberlist.end.strftime('%d.%m.%Y')
            template_content = template_content.replace('TIME-PERIOD', time_period)
            jugendleiter = ', '.join(j.name for j in memberlist.jugendleiter.all())
            template_content = template_content.replace('JUGENDLEITER', jugendleiter)

            # create tickboxes for tour type
            tour_type = ''
            for tt in ['Gemeinschaftstour', 'Führungstour', 'Ausbildung']:
                print(memberlist.tour_type)
                if tt == memberlist.get_tour_type():
                    tour_type += '\\tickedbox ' + tt
                else:
                    tour_type += '\\checkbox'
                    tour_type += '\\enspace ' + tt

                tour_type += '\\qquad \\qquad '
            template_content = template_content.replace('TOUR-TYPE', tour_type)

            # create tickboxes for tour approach
            tour_approach = ''
            for tt in ['Muskelkraft', 'Öffentliche VM', 'Fahrgemeinschaften']:
                print(memberlist.tour_approach)
                if tt == memberlist.get_tour_approach():
                    tour_approach += '\\tickedbox ' + tt
                else:
                    tour_approach += '\\checkbox'
                    tour_approach += '\\enspace ' + tt

                tour_approach += '\\qquad \\qquad '
            template_content = template_content.replace('TOUR-APPROACH', tour_approach)


            template_content = template_content.replace('TABLE-NAME',
                    filename_table)

            # write adapted template to file
            with open(media_path(filename_tex), 'w', encoding='utf-8') as f:
                f.write(template_content)

            # compile using pdflatex
            oldwd = os.getcwd()
            os.chdir(media_dir())
            subprocess.call(['pdflatex', filename_tex])
            time.sleep(1)

            # do some cleanup
            for f in glob.glob('*.log'):
                os.remove(f)
            for f in glob.glob('*.aux'):
                os.remove(f)
            os.remove(filename_tex)
            os.remove(filename_table)

            os.chdir(oldwd)

            # provide the user with the resulting pdf file
            with open(media_path(filename_pdf), 'rb') as pdf:
                response = HttpResponse(FileWrapper(pdf))#, content='application/pdf')
                response['Content-Type'] = 'application/pdf'
                response['Content-Disposition'] = 'attachment; filename='+filename_pdf

            return response
    convert_to_pdf.short_description = _('Convert to PDF')

    def generate_notes(self, request, queryset):
        """Generates a short note for the jugendleiter"""
        for memberlist in queryset:
            # unique filename
            filename = memberlist.name + "_note_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_').replace('&', '')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # generate table
            table = ""
            activities = [a.name for a in memberlist.activity.all()]
            skills = {a: [] for a in activities}
            for memberonlist in memberlist.membersonlist.all():
                m = memberonlist.member
                qualities = []
                for activity, value in m.get_skills().items():
                    if activity not in activities:
                        continue
                    skills[activity].append(value)
                    qualities.append("\\textit{%s:} %s" % (activity, value))
                comment = ". ".join(c for c
                                    in (m.comments,
                                        memberonlist.comments) if
                                    c).replace("..", ".")
                line = '{0} {1} & {2} & {3} \\\\'.format(
                    esc_ampersand(m.prename), esc_ampersand(m.lastname),
                    esc_ampersand(", ".join(qualities)),
	            esc_ampersand(comment) or "---")
                table += esc_underscore(line)

            table_qualities = ""
            for activity in activities:
                skill_avg = 0 if len(skills[activity]) == 0 else\
                    sum(skills[activity]) / len(skills[activity])
                skill_min = 0 if len(skills[activity]) == 0 else\
                    min(skills[activity])
                skill_max = 0 if len(skills[activity]) == 0 else\
                    max(skills[activity])
                line = '{0} & {1} & {2} & {3} \\\\ \n'.format(
                    esc_ampersand(activity),
                    skill_avg,
                    skill_min,
                    skill_max
                    )
                table_qualities += esc_underscore(line)

            # copy template
            shutil.copy(media_path('membernote_template.tex'),
                        media_path(filename_tex))

            # read in template
            with open(media_path(filename_tex), 'r', encoding='utf-8') as f:
                template_content = f.read()

            # adapt template
            name = esc_all(memberlist.name)
            template_content = template_content.replace('ACTIVITY', name)
            groups = ', '.join(g.name for g in memberlist.groups.all())
            template_content = template_content.replace('GROUP',
                                                        esc_all(groups))
            destination = esc_all(memberlist.destination)
            template_content = template_content.replace('DESTINATION', destination)
            place = esc_all(memberlist.place)
            template_content = template_content.replace('PLACE', place)
            template_content = template_content.replace('MEMBERLIST-DATE',
                    datetime.today().strftime('%d.%m.%Y'))
            time_period = memberlist.date.strftime('%d.%m.%Y')
            if memberlist.end != memberlist.date:
                time_period += " - " + memberlist.end.strftime('%d.%m.%Y')
            template_content = template_content.replace('TIME-PERIOD', time_period)
            jugendleiter = ', '.join(j.name for j in memberlist.jugendleiter.all())
            template_content = template_content.replace('JUGENDLEITER', jugendleiter)

            template_content = template_content.replace('TABLE-QUALITIES',
                                                        table_qualities)
            template_content = template_content.replace('TABLE', table)

            # write adapted template to file
            with open(media_path(filename_tex), 'w', encoding='utf-8') as f:
                f.write(template_content)

            # compile using pdflatex
            oldwd = os.getcwd()
            os.chdir(media_dir())
            subprocess.call(['pdflatex', filename_tex])
            time.sleep(1)

            # do some cleanup
            for f in glob.glob('*.log'):
                os.remove(f)
            for f in glob.glob('*.aux'):
                os.remove(f)
            os.remove(filename_tex)

            os.chdir(oldwd)

            # provide the user with the resulting pdf file
            with open(media_path(filename_pdf), 'rb') as pdf:
                response = HttpResponse(FileWrapper(pdf))
                response['Content-Type'] = 'application/pdf'
                response['Content-Disposition'] = 'attachment; filename=' + filename_pdf

            return response
    generate_notes.short_description = _('Generate overview')

    def convert_to_ljp(self, request, queryset):
        """Converts a member list to pdf but without email and with birth date.
        Suitable for LJP lists.
        """
        for memberlist in queryset:
            # create a unique filename
            filename = memberlist.name + "_ljp_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_').replace('&', '')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_table = 'table_' + filename
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # open temporary file for table
            with open(media_path(filename_table), 'w+', encoding='utf-8') as f:
                if memberlist.membersonlist.count() == 0:
                    f.write('{0} & {1} & {2} & {3} \\\\ \n'.format(
                        'keine Teilnehmer', '-', '-', '-'
                    ))
                for memberonlist in memberlist.membersonlist.all():
                    # write table of members in latex compatible format
                    member = memberonlist.member
                    # use parents phone number if available
                    phone_number = member.phone_number_parents if\
                        member.phone_number_parents else member.phone_number
                    # use parents email address if available
                    email = member.email_parents if\
                        member.email_parents else member.email
                    line = '{0} {1} & {2} & {3} & & & \\\\ \\hline \n'.format(
                            esc_all(memberonlist.member.prename),
                            esc_all(memberonlist.member.lastname),
                            esc_all(memberonlist.member.address),
                            esc_all(memberonlist.member.birth_date.strftime("%d.%m.%Y")))
                    f.write(line)

            # copy and adapt latex memberlist template
            shutil.copy(media_path('memberlist_ljp_template.tex'),
                        media_path(filename_tex))

            # read in template
            with open(media_path(filename_tex), 'r', encoding='utf-8') as f:
                template_content = f.read()

            # adapt template
            name = esc_all(memberlist.name)
            template_content = template_content.replace('ACTIVITY', name)
            groups = ', '.join(g.name for g in
                               memberlist.groups.all())
            template_content = template_content.replace('GROUP',
                                                        esc_all(groups))
            destination = esc_all(memberlist.destination)
            template_content = template_content.replace('DESTINATION',
                                                        destination)
            place = esc_all(memberlist.place)
            template_content = template_content.replace('PLACE', place)
            template_content = template_content.replace('MEMBERLIST-DATE',
                                                        datetime.today().strftime('%d.%m.%Y'))
            time_period = memberlist.date.strftime('%d.%m.%Y')
            if memberlist.end != memberlist.date:
                time_period += " - " + memberlist.end.strftime('%d.%m.%Y')
            template_content = template_content.replace('TIME-PERIOD', time_period)
            jugendleiter = ', '.join(j.name for j in memberlist.jugendleiter.all())
            template_content = template_content.replace('JUGENDLEITER', jugendleiter)
            template_content = template_content.replace('TABLE-NAME',
                    filename_table)

            # write adapted template to file
            with open(media_path(filename_tex), 'w', encoding='utf-8') as f:
                f.write(template_content)

            # compile using pdflatex
            oldwd = os.getcwd()
            os.chdir(media_dir())
            subprocess.call(['pdflatex', filename_tex])
            time.sleep(1)

            # do some cleanup
            for f in glob.glob('*.log'):
                os.remove(f)
            for f in glob.glob('*.aux'):
                os.remove(f)
            os.remove(filename_tex)
            os.remove(filename_table)

            os.chdir(oldwd)

            # provide the user with the resulting pdf file
            with open(media_path(filename_pdf), 'rb') as pdf:
                response = HttpResponse(FileWrapper(pdf))#, content='application/pdf')
                response['Content-Type'] = 'application/pdf'
                response['Content-Disposition'] = 'attachment; filename='+filename_pdf

            return response
    convert_to_ljp.short_description = _('Generate list for LJP')


class KlettertreffAdminForm(forms.ModelForm):
    class Meta:
        model = Klettertreff
        exclude = []

    def __init__(self, *args, **kwargs):
        super(KlettertreffAdminForm, self).__init__(*args, **kwargs)
        self.fields['jugendleiter'].queryset = Member.objects.filter(group__name='Jugendleiter')


class KlettertreffAttendeeInlineForm(forms.ModelForm):
    class Meta:
        model = KlettertreffAttendee
        exclude = []

    """
    def __init__(self, *args, **kwargs):
        super(KlettertreffAttendeeInlineForm, self).__init__(*args, **kwargs)
        self.fields['member'].queryset = Member.objects.filter(group__name='J1')
    """

class KlettertreffAttendeeInline(admin.TabularInline):
    model = KlettertreffAttendee
    form = KlettertreffAttendeeInlineForm
    extra = 0
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}


class KlettertreffAdmin(admin.ModelAdmin):
    form = KlettertreffAdminForm
    exclude = []
    inlines = [KlettertreffAttendeeInline]
    list_display = ['__str__', 'date', 'get_jugendleiter']
    search_fields = ('date', 'location', 'topic')
    list_filter = [('date', DateFieldListFilter), 'group__name']
    actions = ['overview']

    def overview(self, request, queryset):
        group = request.GET.get('group__name')
        if group != None:
            members = Member.objects.filter(group__name__contains=group)
        else:
            members = Member.objects.all()
        context = {
                   'klettertreffs': queryset,
                   'members': members,
                   'attendees': KlettertreffAttendee.objects.all(),
                   'jugendleiters':
                   Member.objects.filter(group__name='Jugendleiter')
                   }

        return render(request, 'admin/klettertreff_overview.html',
                      context)

    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}


admin.site.register(Member, MemberAdmin)
admin.site.register(MemberUnconfirmedProxy, MemberUnconfirmedAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Freizeit, FreizeitAdmin)
admin.site.register(MemberNoteList, MemberNoteListAdmin)
admin.site.register(MemberList, MemberListAdmin)
admin.site.register(Klettertreff, KlettertreffAdmin)
admin.site.register(ActivityCategory, ActivityCategoryAdmin)


def media_path(fp):
    return os.path.join(os.path.join(settings.MEDIA_MEMBERLISTS, "memberlists"), fp)


def media_dir():
    return os.path.join(settings.MEDIA_MEMBERLISTS, "memberlists")


def esc_underscore(txt):
    return txt.replace('_', '\_')


def esc_ampersand(txt):
    return txt.replace('&', '\&')


def esc_all(txt):
    return esc_underscore(esc_ampersand(txt))
