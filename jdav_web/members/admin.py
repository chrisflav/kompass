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
from django.db.models import TextField
from django.forms import Textarea

from .models import (Member, Group, MemberList, MemberOnList, Klettertreff,
        KlettertreffAttendee)


# Register your models here.
class MemberAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'street', 'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group',
              'gets_newsletter', 'comments']
    list_display = ('name', 'street', 'town', 'phone_number',
            'phone_number_parents', 'birth_date', 'gets_newsletter', 'get_group', 'comments')
    list_filter = ('group', 'gets_newsletter')


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'min_age']
    list_display = ('name', 'min_age')

class MemberListAdminForm(forms.ModelForm):
    class Meta:
        model = MemberList
        exclude = ['add_member']

    def __init__(self, *args, **kwargs):
        super(MemberListAdminForm, self).__init__(*args, **kwargs)
        if self.instance.pk:
            pass
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
    form = MemberListAdminForm
    actions = ['convert_to_pdf']
    inlines = [MemberOnListInline]

    def __init__(self, *args, **kwargs):
        super(MemberListAdmin, self).__init__(*args, **kwargs)

    def convert_to_pdf(self, request, queryset):
        """Converts a member list to pdf.

        """
        for memberlist in queryset:
            # build a unique filename
            filename = memberlist.name + "_" + datetime.today().strftime("%d_%m_%Y")
            filename = filename.replace(' ', '_')
 
            filename_table = 'table_' + filename
            filename_tex = filename + '.tex'
            filename_pdf = filename + '.pdf'

            # open temporary file for table
            with open('media/memberlists/'+filename_table, 'w+') as f:
                for memberonlist in memberlist.memberonlist_set.all():
                    # write table of members in latex compatible format
                    line = '{0} & {1} & {2} & {3} \\\\ \n'.format(memberonlist.member.prename,
                            memberonlist.member.lastname,
                            memberonlist.member.birth_date.strftime('%d.%m.%Y'), memberonlist.comments)
                    f.write(line) 
            
            # copy and adapt latex memberlist template
            shutil.copy('media/memberlists/memberlist_template.tex',
                        'media/memberlists/'+filename_tex)

            # read in template
            with open('media/memberlists/'+filename_tex, 'r') as f:
                template_content = f.read()
            
            # adapt template
            template_content = template_content.replace('MEMBERLIST-TITLE', memberlist.name)
            template_content = template_content.replace('MEMBERLIST-DATE',
                    memberlist.date.strftime('%d.%m.%Y'))
            template_content = template_content.replace('MEMBERLIST-COMMENTS',
                    memberlist.comment)
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

class KlettertreffAttendeeInline(admin.StackedInline):

    model = KlettertreffAttendee
    extra = 0

class KlettertreffAdmin(admin.ModelAdmin):
    form = KlettertreffAdminForm
    exclude = []
    inlines = [KlettertreffAttendeeInline]
    list_display = ['__str__', 'date', 'get_jugendleiter']
    list_filter = [('date', DateFieldListFilter)]

admin.site.register(Member, MemberAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(MemberList, MemberListAdmin)
admin.site.register(Klettertreff, KlettertreffAdmin)
