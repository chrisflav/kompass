from django.contrib import admin, messages
from django.conf import settings
from django.contrib.admin import helpers
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render
from django.db import models
from django import forms
#from easy_select2 import apply_select2
import json

from rules.contrib.admin import ObjectPermissionsModelAdmin

from .models import Message, Attachment, MessageForm, EmailAddress, EmailAddressForm
from .mailutils import NOT_SENT, PARTLY_SENT
from members.models import Member
from members.admin import FilteredMemberFieldMixin
from contrib.admin import CommonAdminMixin, CommonAdminInlineMixin


class AttachmentInline(CommonAdminInlineMixin, admin.TabularInline):
    model = Attachment
    extra = 0


class EmailAddressAdmin(FilteredMemberFieldMixin, admin.ModelAdmin):
    list_display = ('email', 'internal_only')
    fields = ('name', 'to_members', 'to_groups', 'internal_only')
    #formfield_overrides = {
    #    models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    models.ForeignKey: {'widget': apply_select2(forms.Select)}
    #}
    filter_horizontal = ('to_members',)
    form = EmailAddressForm


class MessageAdmin(FilteredMemberFieldMixin, CommonAdminMixin, ObjectPermissionsModelAdmin):
    """Message creation view"""
    exclude = ('created_by', 'to_notelist')
    list_display = ('subject', 'get_recipients', 'sent')
    search_fields = ('subject',)
    list_filter = ('sent',)
    change_form_template = "mailer/change_form.html"
    readonly_fields = ('sent',)
    #formfield_overrides = {
    #    models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
    #    models.ForeignKey: {'widget': apply_select2(forms.Select)}
    #}

    inlines = [AttachmentInline]
    actions = ['send_message']
    form = MessageForm
    filter_horizontal = ('to_members','reply_to')

    def save_model(self, request, obj, form, change):
        if not change and hasattr(request.user, 'member'):
            obj.created_by = request.user.member
        super().save_model(request, obj, form, change)

    def send_message(self, request, queryset):
        if request.POST.get('confirmed'):
            for msg in queryset:
                submit_message(msg, request)
        else:
            context = {
                       'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
                       'mails': queryset,
                       'ids': queryset.values_list("id"),
                       'some_sent': any(m.sent for m in queryset)}
            return render(request, 'mailer/confirm_send.html', context)
    send_message.short_description = _("Send message")

    def response_change(self, request, obj):
        if "_send" in request.POST:
            submit_message(obj, request)
        return super(MessageAdmin, self).response_change(request, obj)

    def response_add(self, request, obj):
        if "_send" in request.POST:
            submit_message(obj, request)
        return super(MessageAdmin, self).response_add(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        form = super(MessageAdmin, self).get_form(request, obj, **kwargs)
        raw_members = request.GET.get('members', None)
        if raw_members is not None:
            m_ids = json.loads(raw_members)
            if type(m_ids) != list:
                return form
            members = Member.objects.filter(pk__in=m_ids)
            form.base_fields['to_members'].initial = members
        return form


def submit_message(msg, request):
    sender = None
    if not hasattr(request.user, 'member'):
        messages.error(request, _("Your account is not connected to a member. Please contact your system administrator."))
        return
    sender = request.user.member
    if not sender.has_internal_email():
        messages.error(request,
                       _("Your email address is not an internal email address. Please use an email address with one of the following domains: %(domains)s.") % {'domains': ", ".join(settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER)})
        return
    success = msg.submit(sender)
    if success == NOT_SENT:
        messages.error(request, _("Failed to send message"))
    elif success == PARTLY_SENT:
        messages.warning(request, _("Failed to send some messages"))
    else:
        messages.success(request, _("Successfully sent message"))


admin.site.register(Message, MessageAdmin)
admin.site.register(EmailAddress, EmailAddressAdmin)
