from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.db import models
from django.utils.translation import gettext_lazy as _
from members.rules import may_change
from members.rules import may_delete
from members.rules import may_view

from .base import ContactWithPhoneNumber
from .member import Member


class EmergencyContact(ContactWithPhoneNumber):
    """
    Emergency contact of a member
    """

    member = models.ForeignKey(Member, verbose_name=_("Member"), on_delete=models.CASCADE)
    email = models.EmailField(max_length=100, default="", blank=True)

    def __str__(self):
        return str(self.member)

    class Meta(CommonModel.Meta):
        verbose_name = _("Emergency contact")
        verbose_name_plural = _("Emergency contacts")
        rules_permissions = {
            "add_obj": may_change | has_global_perm("members.change_global_member"),
            "view_obj": may_view | has_global_perm("members.view_global_member"),
            "change_obj": may_change | has_global_perm("members.change_global_member"),
            "delete_obj": may_delete | has_global_perm("members.delete_global_member"),
        }
