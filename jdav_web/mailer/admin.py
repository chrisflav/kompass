from django.contrib import admin
from django.contrib.admin import helpers
from django.utils.translation import ugettext_lazy as _
from django.shortcuts import render

from .models import Message


class MessageAdmin(admin.ModelAdmin):
    """Message creation view"""
    list_display = ('subject', 'from_addr', 'to_group', 'sent')
    change_form_template = "mailer/change_form.html"

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

    def response_change(self, request, obj):
        if "_send" in request.POST:
            obj.submit()
        return super(MessageAdmin, self).response_change(request, obj)

    def response_add(self, request, obj):
        if "_send" in request.POST:
            obj.submit()
        return super(MessageAdmin, self).response_change(request, obj)


admin.site.register(Message, MessageAdmin)
