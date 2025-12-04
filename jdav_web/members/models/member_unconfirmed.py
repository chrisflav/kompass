from django.db import models 
from django.utils.translation import gettext_lazy as _
from members.rules import may_view, may_change, may_delete
from contrib.rules import has_global_perm
from .member import Member

class MemberUnconfirmedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=False)

class MemberUnconfirmedProxy(Member):
    """Proxy to show unconfirmed members seperately in admin"""
    objects = MemberUnconfirmedManager()

    class Meta:
        proxy = True
        verbose_name = _('Unconfirmed registration')
        verbose_name_plural = _('Unconfirmed registrations')
        permissions = (('may_manage_all_registrations', 'Can view and manage all unconfirmed registrations.'),)
        rules_permissions = {
            'view_obj': may_view | has_global_perm('members.may_manage_all_registrations'),
            'change_obj': may_change | has_global_perm('members.may_manage_all_registrations'),
            'delete_obj': may_delete | has_global_perm('members.may_manage_all_registrations'),
        }

    def __str__(self):
        """String representation"""
        return self.name
