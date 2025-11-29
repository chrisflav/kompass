from django.contrib.auth.models import Group as BaseAuthGroup
from django.contrib.auth.models import User as BaseUser
from django.db import models
from django.utils.translation import gettext_lazy as _


class AuthGroup(BaseAuthGroup):
    class Meta:
        proxy = True
        verbose_name = _("Permission group")
        verbose_name_plural = _("Permission groups")


class LoginDatum(BaseUser):
    class Meta:
        proxy = True
        verbose_name = _("Login Datum")
        verbose_name_plural = _("Login Data")


class RegistrationPassword(models.Model):
    """
    A password that can be used to register after inviting a member.
    """

    password = models.CharField(max_length=100, verbose_name=_("Password"))

    def __str__(self):
        return self.password

    class Meta:
        verbose_name = _("Active registration password")
        verbose_name_plural = _("Active registration passwords")


def initial_user_setup(user, member):
    try:
        standard_group = AuthGroup.objects.get(name="Standard")
    except AuthGroup.DoesNotExist:
        return False

    user.is_staff = True
    user.save()
    user.groups.add(standard_group)
    member.user = user
    member.invite_as_user_key = ""
    member.save()
    return True
