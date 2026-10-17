from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class FinanceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "finance"
    verbose_name = _("Finance")

    def ready(self):
        # Connects the receiver that takes a deleted member out of the answers
        # that named them — the cleanup the four dropped columns used to get
        # from `SET_NULL` and from cascading through rows. Imported here rather
        # than at module scope because it reaches the models.
        from . import signals  # noqa: F401
