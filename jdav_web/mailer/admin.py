from django.contrib import admin, messages
from django.contrib.admin import helpers
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import render
from django.db import models
from django import forms

from .models import Message, Attachment, MessageForm
from .mailutils import NOT_SENT, PARTLY_SENT


class AttachmentInline(admin.StackedInline):
    model = Attachment
    extra = 0


class MessageAdmin(admin.ModelAdmin):
    """Message creation view"""
    list_display = ('subject', 'from_addr', 'get_recipients', 'sent')
    change_form_template = "mailer/change_form.html"
    formfield_overrides = {
        models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    }

    inlines = [AttachmentInline]
    actions = ['send_message']
    form = MessageForm
    filter_horizontal = ('to_members',)

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


def submit_message(msg, request):
    success = msg.submit()
    if success == NOT_SENT:
        messages.error(request, _("Failed to send message"))
    elif success == PARTLY_SENT:
        messages.warning(request, _("Failed to send some messages"))
    else:
        messages.info(request, _("Successfully sent message"))


admin.site.register(Message, MessageAdmin)
