from datetime import datetime
import glob
import os
import subprocess
import shutil
import time
import unicodedata

from django.http import HttpResponse, HttpResponseRedirect
from wsgiref.util import FileWrapper
from django import forms
from django.contrib import admin
from django.contrib.admin import DateFieldListFilter
from django.utils.translation import ugettext_lazy as _
from django.db.models import TextField, ManyToManyField, ForeignKey
from django.forms import Textarea, RadioSelect, TypedChoiceField
from django.shortcuts import render

from .models import (Member, Group, MemberList, MemberOnList, Klettertreff,
                     KlettertreffAttendee, ActivityCategory)
from django.conf import settings
from easy_select2 import apply_select2


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
    fields = ['prename', 'lastname', 'email', 'email_parents', 'street', 'plz',
              'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group',
              'gets_newsletter', 'registered', 'registration_form', 'comments']
    list_display = ('name', 'birth_date', 'get_group', 'gets_newsletter',
                    'registered', 'created', 'comments')
    search_fields = ('prename', 'lastname')
    list_filter = ('group', 'gets_newsletter', RegistrationFilter)
    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        ForeignKey: {'widget': apply_select2(forms.Select)}
    }
    change_form_template = "members/change_member.html"
    actions = ['send_mail_to']

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context['qualities'] =\
            Member.objects.get(pk=object_id).get_skills()
        return super(MemberAdmin, self).change_view(request, object_id,
                                                    form_url=form_url,
                                                    extra_context=extra_context)

    def send_mail_to(self, request, queryset):
        member_pks = [m.pk for m in queryset]
        query = str(member_pks).replace(' ', '')
        return HttpResponseRedirect("/admin/mailer/message/add/?members={}".format(query))
    send_mail_to.short_description = _('Compose new mail to selected members')


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'min_age']
    list_display = ('name', 'min_age')


class ActivityCategoryAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


class MemberListAdminForm(forms.ModelForm):
    difficulty = TypedChoiceField(MemberList.difficulty_choices,
                                  widget=RadioSelect,
                                  coerce=int,
                                  label=_('Difficulty'))
    tour_type = TypedChoiceField(MemberList.tour_type_choices,
                                 widget=RadioSelect,
                                 coerce=int,
                                 label=_('Tour type'))

    class Meta:
        model = MemberList
        exclude = ['add_member']

    def __init__(self, *args, **kwargs):
        super(MemberListAdminForm, self).__init__(*args, **kwargs)
        self.fields['jugendleiter'].queryset = Member.objects.filter(group__name='Jugendleiter')
        #self.fields['add_member'].queryset = Member.objects.filter(prename__startswith='F')


class MemberOnListInline(admin.TabularInline):
    model = MemberOnList
    extra = 0
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1,
                                              'cols': 40})},
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        ForeignKey: {'widget': apply_select2(forms.Select)}
    }


class MemberListAdmin(admin.ModelAdmin):
    inlines = [MemberOnListInline]
    form = MemberListAdminForm
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    actions = ['convert_to_pdf', 'generate_notes']
    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        ForeignKey: {'widget': apply_select2(forms.Select)}
    }

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}

    def __init__(self, *args, **kwargs):
        super(MemberListAdmin, self).__init__(*args, **kwargs)

    def convert_to_pdf(self, request, queryset):
        """Converts a member list to pdf.
        """
        for memberlist in queryset:
            # create a unique filename
            filename = memberlist.name + "_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_table = 'table_' + filename
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # open temporary file for table
            with open(media_path(filename_table), 'w+', encoding='utf-8') as f:
                if memberlist.memberonlist_set.count() == 0:
                    f.write('{0} & {1} & {2} & {3} \\\\ \n'.format(
                        'keine Teilnehmer', '-', '-', '-'
                    ))
                for memberonlist in memberlist.memberonlist_set.all():
                    # write table of members in latex compatible format
                    line = '{0} {1} & {2}, {3} & {4} & {5} \\\\ \n'.format(
                            esc_ampersand(memberonlist.member.prename),
                            esc_ampersand(memberonlist.member.lastname),
                            esc_ampersand(memberonlist.member.street),
                            esc_ampersand(memberonlist.member.place),
                            esc_ampersand(memberonlist.member.phone_number),
                            esc_ampersand(memberonlist.member.email))
                    f.write(esc_underscore(line))

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
            filename = filename.replace(' ', '_')
            # drop umlauts, accents etc.
            filename = unicodedata.normalize('NFKD', filename).\
                encode('ASCII', 'ignore').decode()
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # generate table
            table = ""
            activities = [a.name for a in memberlist.activity.all()]
            skills = {a: [] for a in activities}
            for memberonlist in memberlist.memberonlist_set.all():
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
    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        ForeignKey: {'widget': apply_select2(forms.Select)}
    }


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

    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        ForeignKey: {'widget': apply_select2(forms.Select)}
    }

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}


admin.site.register(Member, MemberAdmin)
admin.site.register(Group, GroupAdmin)
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
    esc_underscore(esc_ampersand(txt))
