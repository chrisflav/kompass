from django.contrib import admin
from django.utils.translation import ugettext_lazy as _

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
    list_display = ('subject', 'from_addr', 'to_group')

    # can't find a good solution for this at the moment
    # send_message = Button()
    # send_message.short_description = _("Send")
    # send_message.view = "mailer:index"
    # buttons = [send_message]
    actions = ['send_message']

    def send_message(self, request, queryset):
        for msg in queryset:
            msg.submit()
        self.message_user(request, _("Message sent"))

admin.site.register(Message, MessageAdmin)
