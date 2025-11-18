from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class MailerConfig(AppConfig):
    name = "mailer"
    verbose_name = _("mailer")
