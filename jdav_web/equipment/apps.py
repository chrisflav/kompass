from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class EquipmentConfig(AppConfig):
    """The material management of the SPA, apart from the old ``material`` app."""

    name = "equipment"
    verbose_name = _("material management")
