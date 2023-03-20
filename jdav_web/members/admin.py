from datetime import datetime, timedelta
import glob
import os
import subprocess
import shutil
import time
import unicodedata
import random
import string
from functools import partial, update_wrapper

from django.contrib.admin.templatetags.admin_urls import add_preserved_filters
from django.template.loader import get_template
from django.urls import path, reverse
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
from .pdf import render_tex

import nested_admin

from .models import (Member, Group, Freizeit, MemberNoteList, NewMemberOnList, Klettertreff,
                     MemberWaitingList, LJPProposal, Intervention,
                     KlettertreffAttendee, ActivityCategory, OldMemberOnList, MemberList,
                     annotate_activity_score, RegistrationPassword, MemberUnconfirmedProxy)
from finance.models import Statement, Bill
from mailer.mailutils import send as send_mail, get_echo_link
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
              'town', 'phone_number', 'phone_number_parents', 'birth_date', 'group', 'iban',
              'gets_newsletter', 'registered', 'registration_form', 'active', 'echoed', 'comments']
    list_display = ('name', 'birth_date', 'age', 'get_group', 'gets_newsletter',
                    'registered', 'active', 'echoed', 'comments', 'activity_score')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'gets_newsletter', RegistrationFilter, 'active')
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}
    change_form_template = "members/change_member.html"
    #ordering = ('activity_score',)
    actions = ['send_mail_to', 'request_echo']

    def get_fields(self, request, obj=None):
        if request.user.has_perm('members.may_set_auth_user'):
            if 'user' not in self.fields:
                self.fields.append('user')
        else:
            if 'user' in self.fields:
                self.fields.remove('user')
        return super(MemberAdmin, self).get_fields(request, obj)

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return annotate_activity_score(queryset)

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
            send_mail(_("Echo required"),
                      settings.ECHO_TEXT.format(name=member.prename, link=get_echo_link(member)),
                      settings.DEFAULT_SENDING_MAIL,
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
              'registered', 'registration_form', 'active', 'comments']
    list_display = ('name', 'birth_date', 'age', 'get_group', 'confirmed_mail', 'confirmed_mail_parents')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'confirmed_mail', 'confirmed_mail_parents')
    actions = ['request_mail_confirmation', 'confirm', 'demote_to_waiter']
    change_form_template = "members/change_member_unconfirmed.html"

    def has_add_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        if request.user.has_perm('members.may_manage_all_registrations'):
            return queryset
        if not hasattr(request.user, 'member'):
            return MemberUnconfirmedProxy.objects.none()
        groups = request.user.member.leited_groups.all()
        # this is magic (the first part, group is a manytomanyfield) but seems to work
        return queryset.filter(group__in=groups).distinct()

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

    def demote_to_waiter(self, request, queryset):
        for member in queryset:
            #mem_as_dict = member.__dict__
            #del mem_as_dict['_state']
            #del mem_as_dict['id']
            waiter = MemberWaitingList(prename=member.prename,
                                       lastname=member.lastname,
                                       email=member.email,
                                       email_parents=member.email_parents,
                                       cc_email_parents=member.cc_email_parents,
                                       birth_date=member.birth_date,
                                       comments=member.comments,
                                       confirmed_mail=member.confirmed_mail,
                                       confirmed_mail_parents=member.confirmed_mail_parents,
                                       confirm_mail_key=member.confirm_mail_key,
                                       confirm_mail_parents_key=member.confirm_mail_parents_key)
            waiter.save()
            member.delete()
            messages.success(request, _("Successfully demoted %(name)s to waiter.") % {'name': waiter.name})
    demote_to_waiter.short_description = _('Demote selected registrations to waiters.')

    def response_change(self, request, member):
        if "_confirm" in request.POST:
            if member.confirm():
                messages.success(request, _("Successfully confirmed %(name)s.") % {'name': member.name})
            else:
                messages.error(request,
                        _("Can't confirm. %(name)s has unconfirmed email addresses.") % {'name': member.name})
        return super(MemberUnconfirmedAdmin, self).response_change(request, member)


class WaiterInviteForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    group = forms.ModelChoiceField(queryset=Group.objects.all(),
                                   label=_('Group'))


class MemberWaitingListAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'email_parents', 'birth_date',  'comments', 'invited_for_group']
    list_display = ('name', 'birth_date', 'age', 'confirmed_mail', 'confirmed_mail_parents',
                    'waiting_confirmed')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('confirmed_mail', 'confirmed_mail_parents')
    actions = ['ask_for_registration', 'ask_for_wait_confirmation']
    readonly_fields= ('invited_for_group',)

    def has_add_permission(self, request, obj=None):
        return False

    def ask_for_wait_confirmation(self, request, queryset):
        """Asks the waiting person to confirm their waiting status."""
        for waiter in queryset:
            waiter.ask_for_wait_confirmation()
            messages.success(request,
                    _("Successfully asked %(name)s to confirm their waiting status.") % {'name': waiter.name})
    ask_for_wait_confirmation.short_description = _('Ask selected waiters to confirm their waiting status')

    def ask_for_registration(self, request, queryset):
        """Asks the waiting person to register with all required data."""
        if "apply" in request.POST:
            try:
                group = Group.objects.get(pk=request.POST['group'])
            except Group.DoesNotExist:
                messages.error(request,
                               _("An error occurred while trying to invite said members. Please try again."))
                return HttpResponseRedirect(request.get_full_path())

            for waiter in queryset:
                waiter.invited_for_group = group
                waiter.save()
                waiter.invite_to_group()
                messages.success(request, 
                        _("Successfully invited %(name)s to %(group)s.") % {'name': waiter.name, 'group': waiter.invited_for_group.name})

            return HttpResponseRedirect(request.get_full_path())
        context = dict(self.admin_site.each_context(request),
                       title=_('Select group for invitation'),
                       opts=self.opts,
                       waiters=queryset.all(),
                       form=WaiterInviteForm(initial={'_selected_action': queryset.values_list('id', flat=True)}))
        return render(request,
                      'admin/invite_selected_for_group.html',
                      context=context)
    ask_for_registration.short_description = _('Offer waiter a place in a group.')

    def response_change(self, request, waiter):
        ret = super(MemberWaitingListAdmin, self).response_change(request, waiter)
        if "_invite" in request.POST:
            return HttpResponseRedirect(
                        reverse('admin:%s_%s_invite' % (waiter._meta.app_label, waiter._meta.model_name),
                                args=(waiter.pk,)))
        return ret

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/invite/",
                wrap(self.invite_view),
                name="%s_%s_invite" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    def invite_view(self, request, object_id):
        waiter = MemberWaitingList.objects.get(pk=object_id)

        if "apply" in request.POST:
            try:
                group = Group.objects.get(pk=request.POST['group'])
            except Group.DoesNotExist:
                messages.error(request,
                               _("An error occurred while trying to invite said members. Please try again."))
                return HttpResponseRedirect(request.get_full_path())

            waiter.invited_for_group = group
            waiter.save()
            waiter.invite_to_group()
            messages.success(request, 
                    _("Successfully invited %(name)s to %(group)s.") % {'name': waiter.name, 'group': waiter.invited_for_group.name})

            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (waiter._meta.app_label, waiter._meta.model_name)))

        context = dict(self.admin_site.each_context(request),
                       title=_('Select group for invitation'),
                       opts=self.opts,
                       object=waiter,
                       waiter=waiter,
                       form=WaiterInviteForm(initial={'_selected_action': [waiter.pk]}))
        return render(request,
                      'admin/invite_for_group.html',
                      context=context)

class RegistrationPasswordInline(admin.TabularInline):
    model = RegistrationPassword
    extra = 0


class GroupAdminForm(forms.ModelForm):
    class Meta:
        model = Freizeit
        exclude = ['add_member']


    def __init__(self, *args, **kwargs):
        super(GroupAdminForm, self).__init__(*args, **kwargs)
        self.fields['leiters'].queryset = Member.objects.filter(group__name='Jugendleiter')


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'year_from', 'year_to', 'leiters']
    form = GroupAdminForm
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
                                 label=_('Means of transportation'))

    class Meta:
        model = Freizeit
        exclude = ['add_member']

    def __init__(self, *args, **kwargs):
        super(FreizeitAdminForm, self).__init__(*args, **kwargs)
        self.fields['jugendleiter'].queryset = Member.objects.filter(group__name='Jugendleiter')
        #self.fields['add_member'].queryset = Member.objects.filter(prename__startswith='F')


class BillOnStatementInline(admin.TabularInline):
    model = Bill
    extra = 0
    sortable_options = []
    fields = ['short_description', 'explanation', 'amount', 'paid_by', 'proof']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.submitted:
            return self.fields
        return super(BillOnStatementInline, self).get_readonly_fields(request, obj)


class StatementOnListInline(nested_admin.NestedStackedInline):
    model = Statement
    extra = 1
    sortable_options = []
    fields = ['night_cost']
    inlines = [BillOnStatementInline]

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and hasattr(obj, 'statement') and obj.statement.submitted:
            return self.fields
        return super(StatementOnListInline, self).get_readonly_fields(request, obj)


class InterventionOnLJPInline(admin.TabularInline):
    model = Intervention
    extra = 0
    sortable_options = []
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 80})}
    }


class LJPOnListInline(nested_admin.NestedStackedInline):
    model = LJPProposal
    extra = 1
    sortable_options = []
    inlines = [InterventionOnLJPInline]


class MemberOnListInline(GenericTabularInline):
    model = NewMemberOnList
    extra = 0
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    sortable_options = []


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
            filename = filename.replace(' ', '_').replace('&', '').replace('/', '_')
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

class FreizeitAdmin(nested_admin.NestedModelAdmin):
    inlines = [MemberOnListInline, LJPOnListInline, StatementOnListInline]
    form = FreizeitAdminForm
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    ordering = ('-date',)
    actions = ['crisis_intervention_list', 'notes_list', 'seminar_report']
    view_on_site = False
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}

    def __init__(self, *args, **kwargs):
        super(FreizeitAdmin, self).__init__(*args, **kwargs)

    def crisis_intervention_list(self, request, queryset):
        for memberlist in queryset:
            context = dict(memberlist=memberlist)
            return render_tex(memberlist.name + "_Krisenliste", 'members/crisis_intervention_list.tex', context)
    crisis_intervention_list.short_description = _('Generate crisis intervention list')

    def notes_list(self, request, queryset):
        for memberlist in queryset:
            people, skills = memberlist.skill_summary
            context = dict(memberlist=memberlist, people=people, skills=skills)
            return render_tex(memberlist.name + "_Notizen", 'members/notes_list.tex', context)
    notes_list.short_description = _('Generate overview')

    def seminar_report(self, request, queryset):
        for memberlist in queryset:
            context = dict(memberlist=memberlist)
            title = memberlist.ljpproposal.title if hasattr(memberlist, 'ljpproposal') else memberlist.name
            return render_tex(title + "_Seminarbericht", 'members/seminar_report.tex', context)
    seminar_report.short_description = _('Generate seminar report')

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/action/",
                wrap(self.action_view),
                name="%s_%s_action" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    def action_view(self, request, object_id):
        if "seminar_report" in request.POST:
            return self.seminar_report(request, [Freizeit.objects.get(pk=object_id)])
        if "notes_list" in request.POST:
            return self.notes_list(request, [Freizeit.objects.get(pk=object_id)])
        if "crisis_intervention_list" in request.POST:
            return self.crisis_intervention_list(request, [Freizeit.objects.get(pk=object_id)])
        return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                            args=(object_id,)))

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
admin.site.register(MemberWaitingList, MemberWaitingListAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Freizeit, FreizeitAdmin)
admin.site.register(MemberNoteList, MemberNoteListAdmin)
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
