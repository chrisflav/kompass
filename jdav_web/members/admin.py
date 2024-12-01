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
from django.forms.models import BaseInlineFormSet

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
from django.forms import Textarea, RadioSelect, TypedChoiceField, CheckboxInput
from django.shortcuts import render
from django.core.exceptions import PermissionDenied
from .pdf import render_tex, fill_pdf_form, merge_pdfs, serve_pdf

from contrib.admin import CommonAdminInlineMixin, CommonAdminMixin

import nested_admin

from .models import (Member, Group, Freizeit, MemberNoteList, NewMemberOnList, Klettertreff,
                     MemberWaitingList, LJPProposal, Intervention, PermissionMember,
                     PermissionGroup, MemberTraining, TrainingCategory,
                     KlettertreffAttendee, ActivityCategory, EmergencyContact,
                     annotate_activity_score, RegistrationPassword, MemberUnconfirmedProxy,
                     InvitationToGroup)
from finance.models import Statement, BillOnExcursionProxy
from mailer.mailutils import send as send_mail, get_echo_link
from django.conf import settings
from utils import get_member
#from easy_select2 import apply_select2


class FilteredMemberFieldMixin:
    def formfield_for_foreignkey(self, db_field, request=None, **kwargs):
        """
        Override the queryset for member foreign key fields.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.related_model != Member:
            return field

        if request is None:
            field.queryset = Member.objects.none()
        elif request.user.has_perm('members.list_global_member'):
            field.queryset = Member.objects.all()
        elif not hasattr(request.user, 'member'):
            field.queryset = Member.objects.none()
        else:
            field.queryset = request.user.member.filter_queryset_by_permissions(model=Member)
        return field

    def formfield_for_manytomany(self, db_field, request=None, **kwargs):
        """
        Override the queryset for member many to many fields.
        """
        field = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.related_model != Member:
            return field

        if request is None:
            field.queryset = Member.objects.none()
        elif request.user.has_perm('members.list_global_member'):
            field.queryset = Member.objects.all()
        elif not hasattr(request.user, 'member'):
            field.queryset = Member.objects.none()
        else:
            field.queryset = request.user.member.filter_queryset_by_permissions(model=Member)
        return field


class InviteAsUserForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class PermissionOnGroupInline(admin.StackedInline):
    model = PermissionGroup
    extra = 1
    can_delete = False


class PermissionOnMemberInline(admin.StackedInline):
    model = PermissionMember
    extra = 1
    can_delete = False


class TrainingOnMemberInline(CommonAdminInlineMixin, admin.TabularInline):
    model = MemberTraining
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    ordering = ("date",)
    extra = 0


class EmergencyContactInline(CommonAdminInlineMixin, admin.TabularInline):
    model = EmergencyContact
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    fields = ['prename', 'lastname', 'email', 'phone_number']
    extra = 0


class TrainingCategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'permission_needed')
    ordering = ('name', )


class RegistrationFilter(admin.SimpleListFilter):
    title = _('Registration complete')
    parameter_name = 'registration_complete'
    default_value = ('All', None)

    def lookups(self, request, model_admin):
        return (
            ('True', _('True')),
            ('False', _('False')),
            ('All', _('All'))
        )

    def queryset(self, request, queryset):
        if self.value() == 'True':
            return queryset.filter(registration_complete=True)
        elif self.value() == 'False':
            return queryset.filter(registration_complete=False)
        elif self.value() is None:
            if self.default_value[1] is None:
                return queryset
            else:
                return queryset.filter(registration_complete=self.default_value[1])
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
class MemberAdmin(CommonAdminMixin, admin.ModelAdmin):
    fieldsets = [
        (None,
         {
             'fields': [('prename', 'lastname'),
                ('email', 'alternative_email'),
                'phone_number',
                'birth_date',
                'gender',
                'group', 'registration_form', 'image',
                ('join_date', 'leave_date'),
                'comments',
                'legal_guardians',
                'dav_badge_no',
                'active', 'echoed', 'gets_newsletter',
                'user',
             ]
         }
        ),
        (_("Contact information"),
         {
             'fields': ['street', 'plz', 'town', 'address_extra', 'country', 'iban']
         }
        ),
        (_("Skills"),
         {
             'fields': ['swimming_badge', 'climbing_badge', 'alpine_experience']
         }
        ),
        (_("Others"),
         {
             'fields': ['allergies', 'tetanus_vaccination', 'medication', 'photos_may_be_taken',
                        'may_cancel_appointment_independently']
         }
        ),
        (_("Organizational"),
         {
             'fields': [
                 ('good_conduct_certificate_presented_date',
                  'good_conduct_certificate_valid'),
                 'has_key', 'has_free_ticket_gym']
         }
        ),
    ]
    list_display = ('name_text_or_link', 'birth_date', 'age', 'get_group', 'gets_newsletter',
                    'registration_complete', 'active', 'echoed', 'comments', 'activity_score')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'gets_newsletter', RegistrationFilter, 'active')
    list_display_links = None
    readonly_fields = ['echoed', 'good_conduct_certificate_valid']
    inlines = [EmergencyContactInline, TrainingOnMemberInline, PermissionOnMemberInline]
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}
    change_form_template = "members/change_member.html"
    ordering = ('lastname',)
    actions = ['request_echo', 'invite_as_user_action']
    list_per_page = 25

    sensitive_fields = ['iban', 'registration_form', 'comments']

    field_view_permissions = {
        'user': 'members.may_set_auth_user',
        'good_conduct_certificate_presented_date': 'members.may_change_organizationals',
        'has_key': 'members.may_change_organizationals',
        'has_free_ticket_gym': 'members.may_change_organizationals',
    }

    field_change_permissions = {
        'user': 'members.may_set_auth_user',
        'group': 'members.may_change_group',
        'good_conduct_certificate_presented_date': 'members.may_change_organizationals',
        'has_key': 'members.may_change_organizationals',
        'has_free_ticket_gym': 'members.may_change_organizationals',
    }

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/inviteasuser/", wrap(self.invite_as_user_view),
                name="%s_%s_inviteasuser" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return annotate_activity_score(queryset.prefetch_related('group'))

    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            extra_context = extra_context or {}
            extra_context['qualities'] =\
                Member.objects.get(pk=object_id).get_skills()
            extra_context['activities'] =\
                Member.objects.get(pk=object_id).get_activities()
            return super(MemberAdmin, self).change_view(request, object_id,
                                                        form_url=form_url,
                                                        extra_context=extra_context)
        except Member.DoesNotExist:
            return super().change_view(request, object_id)

    def send_mail_to(self, request, queryset):
        member_pks = [m.pk for m in queryset]
        query = str(member_pks).replace(' ', '')
        return HttpResponseRedirect("/admin/mailer/message/add/?members={}".format(query))
    send_mail_to.short_description = _('Compose new mail to selected members')

    def request_echo(self, request, queryset):
        for member in queryset:
            if not member.gets_newsletter:
                continue
            member.send_mail(_("Echo required"),
                settings.ECHO_TEXT.format(name=member.prename, link=get_echo_link(member)))
        messages.success(request, _("Successfully requested echo from selected members."))
    request_echo.short_description = _('Request echo from selected members')

    def invite_as_user(self, request, queryset):
        failures = []
        for member in queryset:
            success = member.invite_as_user()
            if not success:
                failures.append(member)
                messages.error(request,
                               _('%(name)s does not have a DAV360 email address or is already registered.') % {'name': member.name})
        if queryset.count() == 1 and len(failures) == 0:
            messages.success(request, _('Successfully invited %(name)s as user.') % {'name': queryset[0].name})
        elif len(failures) == 0:
            messages.success(request, _('Successfully invited selected members to join as users.'))
        else:
            messages.warning(request, _('Some members have been invited, others could not be invited.'))

    def has_may_invite_as_user_permission(self, request):
        return request.user.has_perm('%s.%s' % (self.opts.app_label, 'may_invite_as_user'))

    def invite_as_user_action(self, request, queryset):
        if not request.user.has_perm('members.may_invite_as_user'):
            messages.error(request, _('Permission denied.'))
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))
        if "apply" in request.POST:
            self.invite_as_user(request, queryset)
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        context = dict(self.admin_site.each_context(request),
                       title=_('Invite as user'),
                       opts=self.opts,
                       members=queryset,
                       form=InviteAsUserForm(initial={'_selected_action': queryset.values_list('id', flat=True)}))
        return render(request, 'admin/invite_selected_as_user.html', context=context)
    invite_as_user_action.short_description = _('Invite selected members to join Kompass as users.')
    invite_as_user_action.allowed_permissions = ('may_invite_as_user',)

    def invite_as_user_view(self, request, object_id):
        if not request.user.has_perm('members.may_invite_as_user'):
            messages.error(request, _('Permission denied.'))
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                                args=(object_id,)))
        try:
            m = Member.objects.get(pk=object_id)
        except Member.DoesNotExist:
            messages.error(request, _("Member not found."))
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))
        if m.user:
            messages.error(request,
                _("%(name)s already has login data.") % {'name': str(m)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                                args=(object_id,)))
        if not m.has_internal_email():
            messages.error(request,
                _("The configured email address for %(name)s is not an internal one.") % {'name': str(m)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                                args=(object_id,)))
        if "apply" in request.POST:
            self.invite_as_user(request, Member.objects.filter(pk=object_id))
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                                args=(object_id,)))

        context = dict(self.admin_site.each_context(request),
                       title=_('Invite as user'),
                       opts=self.opts,
                       member=m,
                       object=m)
        if m.invite_as_user_key:
            messages.warning(request, _('%(name)s already has a pending invitation as user.' % {'name': str(m)}))
        return render(request, 'admin/invite_as_user.html', context=context)

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

    def name_text_or_link(self, obj):
        name = obj.name
        if not hasattr(obj, '_viewable') or obj._viewable:
            return format_html('<a href="{link}">{name}</a>'.format(
                link=reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(obj.pk,)),
                name=obj.name))
        else:
            return obj.name
    name_text_or_link.short_description = _('Name')
    name_text_or_link.admin_order_field = 'lastname'


class DemoteToWaiterForm(forms.Form):
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)


class MemberUnconfirmedAdmin(CommonAdminMixin, admin.ModelAdmin):
    fieldsets = [
        (None,
         {
             'fields': [('prename', 'lastname'),
                ('email', 'alternative_email'),
                'phone_number',
                'birth_date',
                'gender',
                'group', 'registration_form', 'image',
                ('join_date', 'leave_date'),
                'comments',
                'legal_guardians',
                'dav_badge_no',
                'active', 'echoed', 'gets_newsletter',
                'user',
             ]
         }
        ),
        (_("Contact information"),
         {
             'fields': ['street', 'plz', 'town', 'address_extra', 'country', 'iban']
         }
        ),
        (_("Skills"),
         {
             'fields': ['swimming_badge', 'climbing_badge', 'alpine_experience']
         }
        ),
        (_("Others"),
         {
             'fields': ['allergies', 'tetanus_vaccination', 'medication', 'photos_may_be_taken']
         }
        ),
        (_("Organizational"),
         {
             'fields': [
                 ('good_conduct_certificate_presented_date',
                  'good_conduct_certificate_valid'),
                 'has_key', 'has_free_ticket_gym']
         }
        ),
    ]
    list_display = ('name', 'birth_date', 'age', 'get_group', 'confirmed_mail', 'confirmed_alternative_mail')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('group', 'confirmed_mail', 'confirmed_alternative_mail')
    readonly_fields = ['confirmed_mail', 'confirmed_alternative_mail',
                       'good_conduct_certificate_valid']
    actions = ['request_mail_confirmation', 'confirm', 'demote_to_waiter_action']
    inlines = [EmergencyContactInline]
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

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/demote/",
                wrap(self.demote_to_waiter_view),
                name="%s_%s_demote" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    def demote_to_waiter_action(self, request, queryset):
        return self.demote_to_waiter_view(request, queryset)
    demote_to_waiter_action.short_description = _('Demote selected registrations to waiters.')

    def demote_to_waiter_view(self, request, object_id):
        if type(object_id) == str:
            member = MemberUnconfirmedProxy.objects.get(pk=object_id)
            queryset = [member]
            form = None
        else:
            queryset = object_id
            form = DemoteToWaiterForm(initial={'_selected_action': queryset.values_list('id', flat=True)})

        if "apply" in request.POST:
            self.demote_to_waiter(request, queryset)
            return HttpResponseRedirect(reverse('admin:members_memberunconfirmedproxy_changelist'))

        context = dict(self.admin_site.each_context(request),
                       title=_('Demote member to waiter'),
                       opts=self.opts,
                       queryset=queryset,
                       form=form)
        return render(request, 'admin/demote_to_waiter.html', context=context)

    def demote_to_waiter(self, request, queryset):
        for member in queryset:
            waiter = MemberWaitingList(prename=member.prename,
                                       lastname=member.lastname,
                                       email=member.email,
                                       birth_date=member.birth_date,
                                       gender=member.gender,
                                       comments=member.comments,
                                       confirmed_mail=member.confirmed_mail,
                                       confirm_mail_key=member.confirm_mail_key)
            waiter.save()
            member.delete()
            messages.success(request, _("Successfully demoted %(name)s to waiter.") % {'name': waiter.name})

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


class InvitationToGroupAdmin(CommonAdminInlineMixin, admin.TabularInline):
    model = InvitationToGroup
    fields = ['group', 'date', 'status']
    readonly_fields = ['group', 'date', 'status']
    extra = 0
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class MemberWaitingListAdmin(CommonAdminMixin, admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'birth_date', 'gender', 'application_text',
        'application_date', 'comments',
        'sent_reminders']
    list_display = ('name', 'birth_date', 'age', 'application_date', 'confirmed_mail',
                    'waiting_confirmed', 'sent_reminders')
    search_fields = ('prename', 'lastname', 'email')
    list_filter = ('confirmed_mail',)
    actions = ['ask_for_registration', 'ask_for_wait_confirmation']
    inlines = [InvitationToGroupAdmin]
    readonly_fields= ['application_date', 'sent_reminders']

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
            if not group.contact_email:
                messages.error(request,
                               _('The selected group does not have a contact email. Please first set a contact email and then try again.'))
                return HttpResponseRedirect(request.get_full_path())

            for waiter in queryset:
                waiter.invited_for_group = group
                waiter.save()
                waiter.invite_to_group(group)
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

            if not group.contact_email:
                messages.error(request,
                               _('The selected group does not have a contact email. Please first set a contact email and then try again.'))
                return HttpResponseRedirect(request.get_full_path())

            waiter.invited_for_group = group
            waiter.save()
            waiter.invite_to_group(group)
            messages.success(request,
                    _("Successfully invited %(name)s to %(group)s.") % {'name': waiter.name, 'group': waiter.invited_for_group.name})

            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (waiter._meta.app_label, waiter._meta.model_name),
                                                args=(object_id,)))

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
        if 'leiters' in self.fields:
            self.fields['leiters'].queryset = Member.objects.filter(group__name='Jugendleiter')


class GroupAdmin(CommonAdminMixin, admin.ModelAdmin):
    fields = ['name', 'description', 'year_from', 'year_to', 'leiters', 'contact_email', 'show_website',
        'weekday', ('start_time', 'end_time')]
    form = GroupAdminForm
    list_display = ('name', 'year_from', 'year_to')
    inlines = [RegistrationPasswordInline, PermissionOnGroupInline]
    search_fields = ('name',)


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
        if 'jugendleiter' in self.fields:
            q = self.fields['jugendleiter'].queryset
            self.fields['jugendleiter'].queryset = q.filter(group__name='Jugendleiter')


class BillOnExcursionInline(CommonAdminInlineMixin, admin.TabularInline):
    model = BillOnExcursionProxy
    extra = 0
    sortable_options = []
    fields = ['short_description', 'explanation', 'amount', 'paid_by', 'proof']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }


class StatementOnListInline(CommonAdminInlineMixin, nested_admin.NestedStackedInline):
    model = Statement
    extra = 1
    description = _('Please list here all expenses in relation with this excursion and upload relevant bills. These have to be permanently stored for the application of LJP contributions. The short descriptions are used in the seminar report cost overview (possible descriptions are e.g. food, material, etc.).')
    sortable_options = []
    fields = ['night_cost']
    inlines = [BillOnExcursionInline]


class InterventionOnLJPInline(CommonAdminInlineMixin, admin.TabularInline):
    model = Intervention
    extra = 0
    sortable_options = []
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 80})}
    }


class LJPOnListInline(CommonAdminInlineMixin, nested_admin.NestedStackedInline):
    model = LJPProposal
    extra = 1
    description = _('Here you can work on a seminar report for applying for financial contributions from Landesjugendplan (LJP). More information on creating a seminar report can be found in the wiki. The seminar report or only a participant list and cost overview can be consequently downloaded.')
    sortable_options = []
    inlines = [InterventionOnLJPInline]


class MemberOnListInline(CommonAdminInlineMixin, GenericTabularInline):
    model = NewMemberOnList
    extra = 0
    description = _('Please list all participants (also youth leaders) of this excursion. Here you can still make changes just before departure and hence generate the latest participant list for crisis intervention at all times.')
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    sortable_options = []


class MemberNoteListAdmin(admin.ModelAdmin):
    inlines = [MemberOnListInline]
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    ordering = ('-date',)
    actions = ['summary']

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
        if "summary" in request.POST:
            return self.summary(request, [MemberNoteList.objects.get(pk=object_id)])
        return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name),
                                            args=(object_id,)))

    def may_view_notelist(self, request, memberlist):
        return request.user.has_perm('members.view_global_member') or \
            ( hasattr(request.user, 'member') and \
              all([request.user.member.may_view(m.member) for m in memberlist.membersonlist.all()]) )

    def not_allowed_view(self, request, memberlist):
        messages.error(request,
                _("You are not allowed to view all members on note list %(name)s.") % {'name': memberlist.title})
        return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

    def summary(self, request, queryset):
        # this ensures legacy compatibilty
        memberlist = queryset[0]
        if not self.may_view_notelist(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        context = dict(memberlist=memberlist, settings=settings)
        return render_tex(memberlist.title + "_Zusammenfassung", 'members/notelist_summary.tex', context)
    summary.short_description = _('Generate PDF summary')


class GenerateSeminarReportForm(forms.Form):
    modes = (('full', _('Full report')),
             ('basic', _('Costs and participants only')))
    mode = forms.ChoiceField(choices=modes, label=_('Mode'))
    prepend_v32 = forms.BooleanField(label=_('Prepend V32'), initial=True,
                                     widget=CheckboxInput(attrs={'style': 'display: inherit'}),
                                     required=False)


class FreizeitAdmin(CommonAdminMixin, nested_admin.NestedModelAdmin):
    #inlines = [MemberOnListInline, LJPOnListInline, StatementOnListInline]
    form = FreizeitAdminForm
    list_display = ['__str__', 'date']
    search_fields = ('name',)
    ordering = ('-date',)
    view_on_site = False
    fieldsets = (
        (None, {
            'fields': ('name', 'place', 'destination', 'date', 'end', 'description', 'groups', 'jugendleiter',
                       'tour_type', 'tour_approach', 'kilometers_traveled', 'activity', 'difficulty'),
            'description': _('General information on your excursion. These are partly relevant for the amount of financial compensation (means of transport, travel distance, etc.).')
        }),
    )
    #formfield_overrides = {
    #    ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    def get_inlines(self, request, obj=None):
        if obj:
            return [MemberOnListInline, LJPOnListInline, StatementOnListInline]
        else:
            return [MemberOnListInline]

    def __init__(self, *args, **kwargs):
        super(FreizeitAdmin, self).__init__(*args, **kwargs)

    def save_model(self, request, obj, form, change):
        if not change and hasattr(request.user, 'member') and hasattr(obj, 'statement'):
            obj.statement.created_by = request.user.member
            obj.statement.save()
        super().save_model(request, obj, form, change)

    def may_view_excursion(self, request, memberlist):
        return request.user.has_perm('members.view_global_member') or \
            ( hasattr(request.user, 'member') and \
              all([request.user.member.may_view(m.member) for m in memberlist.membersonlist.all()]) )

    def not_allowed_view(self, request, memberlist):
        messages.error(request,
                _("You are not allowed to view all members on excursion %(name)s.") % {'name': memberlist.name})
        return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

    def crisis_intervention_list(self, request, memberlist):
        if not self.may_view_excursion(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        context = dict(memberlist=memberlist, settings=settings)
        return render_tex(memberlist.name + "_Krisenliste", 'members/crisis_intervention_list.tex', context)
    crisis_intervention_list.short_description = _('Generate crisis intervention list')

    def notes_list(self, request, memberlist):
        if not self.may_view_excursion(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        people, skills = memberlist.skill_summary
        context = dict(memberlist=memberlist, people=people, skills=skills, settings=settings)
        return render_tex(memberlist.name + "_Notizen", 'members/notes_list.tex', context)
    notes_list.short_description = _('Generate overview')

    def render_seminar_report_options(self, request, memberlist, form):
        context = dict(self.admin_site.each_context(request),
                       title=_('Generate seminar report'),
                       opts=self.opts,
                       memberlist=memberlist,
                       form=form,
                       object=memberlist)
        return render(request, 'admin/generate_seminar_report.html', context=context)

    def seminar_report(self, request, memberlist):
        if not self.may_view_excursion(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        if "apply" in request.POST:
            form = GenerateSeminarReportForm(request.POST)
            if not form.is_valid():
                messages.error(request, _('Please select a mode.'))
                return self.render_seminar_report_options(request, memberlist, form)
            mode = form.cleaned_data['mode']
            prepend_v32 = form.cleaned_data['prepend_v32']
            if mode == 'full' and not hasattr(memberlist, 'ljpproposal'):
                messages.error(request, _('Full mode is only available, if the seminar report section is filled out.'))
                return self.render_seminar_report_options(request, memberlist, form)
            title = memberlist.ljpproposal.title if hasattr(memberlist, 'ljpproposal') else memberlist.name
            context = dict(memberlist=memberlist, settings=settings, mode=mode)
            fp = render_tex(title + '_Seminarbericht', 'members/seminar_report.tex', context, save_only=True)
            if prepend_v32:
                context = memberlist.v32_fields()
                v32_fp = fill_pdf_form(title + "_LJP_V32",
                                       'members/V32-1_Themenorientierte_Bildungsmassnahmen.pdf',
                                       context,
                                       save_only=True)
                return merge_pdfs(title + 'LJP_Antrag', [v32_fp, fp])
            return serve_pdf(fp)
        return self.render_seminar_report_options(request, memberlist, GenerateSeminarReportForm())
    seminar_report.short_description = _('Generate seminar report')

    def sjr_application(self, request, memberlist):
        if not self.may_view_excursion(request, memberlist):
            return self.not_allowed_view(request, memberlist)
        context = memberlist.sjr_application_fields()
        if hasattr(memberlist, 'statement'):
            attachments = [b.proof.path for b in memberlist.statement.bill_set.all() if b.proof]
        else:
            attachments = []
        title = memberlist.ljpproposal.title if hasattr(memberlist, 'ljpproposal') else memberlist.name
        return fill_pdf_form(title + "_SJR_Antrag", 'members/sjr_template.pdf', context, attachments)
    sjr_application.short_description = _('Generate SJR application')

    def finance_overview(self, request, memberlist):
        if not memberlist.statement:
            messages.error(request, _("No statement found. Please add a statement and then retry."))
        if "apply" in request.POST:
            memberlist.statement.submit(get_member(request))
            messages.success(request,
                             _("Successfully submited statement. The finance department will notify you as soon as possible."))
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(memberlist.pk,)))
        context = dict(self.admin_site.each_context(request),
                       title=_('Finance overview'),
                       opts=self.opts,
                       memberlist=memberlist,
                       object=memberlist,
                       participant_count=memberlist.participant_count,
                       ljp_contributions=memberlist.potential_ljp_contributions,
                       total_relative_costs=memberlist.total_relative_costs,
                       **memberlist.statement.template_context())
        return render(request, 'admin/freizeit_finance_overview.html', context=context)

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
        if "sjr_application" in request.POST:
            return self.sjr_application(request, Freizeit.objects.get(pk=object_id))
        if "seminar_report" in request.POST:
            return self.seminar_report(request, Freizeit.objects.get(pk=object_id))
        if "notes_list" in request.POST:
            return self.notes_list(request, Freizeit.objects.get(pk=object_id))
        if "crisis_intervention_list" in request.POST:
            return self.crisis_intervention_list(request, Freizeit.objects.get(pk=object_id))
        if "finance_overview" in request.POST:
            return self.finance_overview(request, Freizeit.objects.get(pk=object_id))
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


admin.site.register(Member, MemberAdmin)
admin.site.register(MemberUnconfirmedProxy, MemberUnconfirmedAdmin)
admin.site.register(MemberWaitingList, MemberWaitingListAdmin)
admin.site.register(Group, GroupAdmin)
admin.site.register(Freizeit, FreizeitAdmin)
admin.site.register(MemberNoteList, MemberNoteListAdmin)
admin.site.register(Klettertreff, KlettertreffAdmin)
admin.site.register(ActivityCategory, ActivityCategoryAdmin)
admin.site.register(TrainingCategory, TrainingCategoryAdmin)
