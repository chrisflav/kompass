from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import render
from django.db import models
from django import forms
from easy_select2 import apply_select2
import json

from .models import Message, Attachment, MessageForm, EmailAddress
from .mailutils import NOT_SENT, PARTLY_SENT
from members.models import Member


class AttachmentInline(admin.TabularInline):
    model = Attachment
    extra = 0


class EmailAddressAdmin(admin.ModelAdmin):
    list_display = ('email', )
    formfield_overrides = {
        models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        models.ForeignKey: {'widget': apply_select2(forms.Select)}
    }
    filter_horizontal = ('to_members',)


class MessageAdmin(admin.ModelAdmin):
    """Message creation view"""
    list_display = ('subject', 'get_recipients', 'sent')
    search_fields = ('subject',)
    change_form_template = "mailer/change_form.html"
    formfield_overrides = {
        models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple},
        models.ForeignKey: {'widget': apply_select2(forms.Select)}
    }

    inlines = [AttachmentInline]
    actions = ['send_message']
    form = MessageForm
    filter_horizontal = ('to_members','reply_to')

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

    class Media:
        css = {'all': ('admin/css/tabular_hide_original.css',)}


def submit_message(msg, request):
    success = msg.submit()
    if success == NOT_SENT:
        messages.error(request, _("Failed to send message"))
    elif success == PARTLY_SENT:
        messages.warning(request, _("Failed to send some messages"))
    else:
        messages.info(request, _("Successfully sent message"))


admin.site.register(Message, MessageAdmin)
admin.site.register(EmailAddress, EmailAddressAdmin)
