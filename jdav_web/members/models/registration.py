from django.db import models
from django.utils.translation import gettext_lazy as _

from .group import Group


class RegistrationPassword(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    password = models.CharField(_("Password"), default="", max_length=20, unique=True)

    class Meta:
        verbose_name = _("registration password")
        verbose_name_plural = _("registration passwords")
