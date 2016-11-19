from django.contrib import admin
from django.contrib.admin import helpers
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import render

from .models import Message


class Button:
    short_description = ""
    view = ""


class ButtonableModelAdmin(admin.ModelAdmin):
    buttons = []

    def change_view(self, request, object_id, extra_context={}):
        extra_context['buttons'] = self.buttons
        if '/' in object_id:
            object_id = object_id[:object_id.find('/')]
        return super(
            ButtonableModelAdmin,
            self).change_view(
            request,
            object_id,
            extra_context=extra_context)


class MessageAdmin(ButtonableModelAdmin):
    """Message creation view"""
    list_display = ('subject', 'from_addr', 'to_group', 'sent')

    # TODO: get this working
    # can't find a good solution for this at the moment
    send_message = Button()
    send_message.short_description = _("Send")
    send_message.view = "mailer:send_mail"
    buttons = [send_message]
    actions = ['send_message']

    def send_message(self, request, queryset):
        print("calling send_message")
        if request.POST.get('confirmed'):
            for msg in queryset:
                msg.submit()
            self.message_user(request, _("Message sent"))
        else:
            context = {
                       'action_checkbox_name': helpers.ACTION_CHECKBOX_NAME,
                       'mails': queryset,
                       'ids': queryset.values_list("id"),
                       'some_sent': any(m.sent for m in queryset)}
            return render(request, 'mailer/confirm_send.html', context)
    send_message.short_description = _("Send message")


admin.site.register(Message, MessageAdmin)
