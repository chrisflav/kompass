from datetime import datetime
import glob
import os
import subprocess
import shutil
import time

from django.http import HttpResponse
from wsgiref.util import FileWrapper
from django import forms
from django.contrib import admin
from django.contrib.admin import DateFieldListFilter
from django.utils.translation import ugettext_lazy as translate
from django.db.models import TextField, ManyToManyField
from django.forms import Textarea
from django.shortcuts import render

from .models import (Member, Group, MemberList, MemberOnList, Klettertreff,
                     KlettertreffAttendee, ActivityCategory)


# Register your models here.
class MemberAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'street', 'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group',
              'gets_newsletter', 'queue', 'registration_form', 'comments']
    list_display = ('name', 'birth_date', 'gets_newsletter', 'get_group', 'queue', 'created', 'comments')
    list_filter = ('group', 'gets_newsletter', 'queue')
    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    }
    change_form_template = "members/change_member.html"

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        extra_context['qualities'] =\
            Member.objects.get(pk=object_id).get_skills()
        return super(MemberAdmin, self).change_view(request, object_id,
                                                    form_url=form_url,
                                                    extra_context=extra_context)


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'min_age']
    list_display = ('name', 'min_age')


class ActivityCategoryAdmin(admin.ModelAdmin):
    fields = ['name', 'description']


class MemberListAdminForm(forms.ModelForm):
    class Meta:
        model = MemberList
        exclude = ['add_member']

    def __init__(self, *args, **kwargs):
        super(MemberListAdminForm, self).__init__(*args, **kwargs)
        self.fields['jugendleiter'].queryset = Member.objects.filter(group__name='Jugendleiter')
        #self.fields['add_member'].queryset = Member.objects.filter(prename__startswith='F')
        

class MemberOnListInline(admin.StackedInline):
    model = MemberOnList
    extra = 0
    formfield_overrides = {
    TextField: {'widget': Textarea(
                           attrs={'rows': 1,
                                  'cols': 40})},
    }

class MemberListAdmin(admin.ModelAdmin):
    inlines = [MemberOnListInline]
    form = MemberListAdminForm
    list_display = ['__str__', 'date']
    actions = ['convert_to_pdf']
    formfield_overrides = {
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    }

    def __init__(self, *args, **kwargs):
        super(MemberListAdmin, self).__init__(*args, **kwargs)

    def convert_to_pdf(self, request, queryset):
        """Converts a member list to pdf.

        """
        for memberlist in queryset:
            # create a unique filename
            filename = memberlist.name + "_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_')
            filename_table = 'table_' + filename
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # open temporary file for table
            with open('media/memberlists/'+filename_table, 'w+') as f:
                for memberonlist in memberlist.memberonlist_set.all():
                    # write table of members in latex compatible format
                    line = '{0} {1} & {2}, {3} & {4} & {5} \\\\ \n'.format(memberonlist.member.prename,
                            memberonlist.member.lastname, memberonlist.member.street,
                            memberonlist.member.town, memberonlist.member.phone_number, memberonlist.member.email)
                    f.write(line) 
            
            # copy and adapt latex memberlist template
            shutil.copy('media/memberlists/memberlist_template.tex',
                        'media/memberlists/'+filename_tex)

            # read in template
            with open('media/memberlists/'+filename_tex, 'r') as f:
                template_content = f.read()
            
            # adapt template
            template_content = template_content.replace('ACTIVITY', memberlist.name)
            groups = ', '.join(g.name for g in memberlist.groups.all())
            template_content = template_content.replace('GROUP', groups)
            template_content = template_content.replace('DESTINATION', memberlist.destination)
            template_content = template_content.replace('PLACE', memberlist.place)
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
                if tt in memberlist.tour_type:
                    tour_type += '\\tickedbox ' + tt
                else:
                    tour_type += '\\checkbox'
                    tour_type += '\\enspace ' + tt

                tour_type += '\\qquad \\qquad '
            template_content = template_content.replace('TOUR-TYPE', tour_type)

            template_content = template_content.replace('TABLE-NAME',
                    filename_table)

            # write adapted template to file
            with open('media/memberlists/' + filename_tex, 'w') as f:
                f.write(template_content)

            # compile using pdflatex
            oldwd = os.getcwd()
            os.chdir('media/memberlists')
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
            with open('media/memberlists/'+filename_pdf, 'rb') as pdf:
                response = HttpResponse(FileWrapper(pdf))#, content='application/pdf')
                response['Content-Type'] = 'application/pdf'
                response['Content-Disposition'] = 'attachment; filename='+filename_pdf

            return response


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

class KlettertreffAttendeeInline(admin.StackedInline):
    model = KlettertreffAttendee
    form = KlettertreffAttendeeInlineForm
    extra = 0


class KlettertreffAdmin(admin.ModelAdmin):
    form = KlettertreffAdminForm
    exclude = []
    inlines = [KlettertreffAttendeeInline]
    list_display = ['__str__', 'date', 'get_jugendleiter']
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
        ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    }


admin.site.register(Member, MemberAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(MemberList, MemberListAdmin)
admin.site.register(Klettertreff, KlettertreffAdmin)
admin.site.register(ActivityCategory, ActivityCategoryAdmin)
