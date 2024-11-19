from django.utils.translation import gettext_lazy as _
from django.db import models
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseAuthGroupAdmin
from django.contrib.auth.models import User as BaseUser, Group as BaseAuthGroup


class AuthGroup(BaseAuthGroup):
    class Meta:
        proxy = True
        verbose_name = _('Permission group')
        verbose_name_plural = _('Permission groups')
        app_label = "auth"


class LoginDatum(BaseUser):
    class Meta:
        proxy = True
        verbose_name = _('Login Datum')
        verbose_name_plural = _('Login Data')
        app_label = "auth"
