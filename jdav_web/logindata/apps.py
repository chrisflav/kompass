from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class LoginDataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'logindata'
    verbose_name = _('Authentication')
