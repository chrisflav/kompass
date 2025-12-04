from django.db import models
from django.utils.translation import gettext_lazy as _


from .member import Member
from .group import Group

class PermissionMember(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name='permissions')
    # every member of view_members may view this member
    list_members = models.ManyToManyField(Member, related_name='listable_by', blank=True,
                                          verbose_name=_('May list members'))
    view_members = models.ManyToManyField(Member, related_name='viewable_by', blank=True,
                                          verbose_name=_('May view members'))
    change_members = models.ManyToManyField(Member, related_name='changeable_by', blank=True,
                                            verbose_name=_('May change members'))
    delete_members = models.ManyToManyField(Member, related_name='deletable_by', blank=True,
                                            verbose_name=_('May delete members'))

    # every member in any view_group may view this member
    list_groups = models.ManyToManyField(Group, related_name='listable_by', blank=True,
                                         verbose_name=_('May list members of groups'))
    view_groups = models.ManyToManyField(Group, related_name='viewable_by', blank=True,
                                         verbose_name=_('May view members of groups'))
    change_groups = models.ManyToManyField(Group, related_name='changeable_by', blank=True,
                                           verbose_name=_('May change members of groups'))
    delete_groups = models.ManyToManyField(Group, related_name='deletable_by', blank=True,
                                           verbose_name=_('May delete members of groups'))

    class Meta:
        verbose_name = _('Permissions')
        verbose_name_plural = _('Permissions')

    def __str__(self):
        return str(_('Permissions'))


class PermissionGroup(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='permissions')
    # every member of view_members may view all members of group
    list_members = models.ManyToManyField(Member, related_name='group_members_listable_by', blank=True,
                                          verbose_name=_('May list members'))
    view_members = models.ManyToManyField(Member, related_name='group_members_viewable_by', blank=True,
                                          verbose_name=_('May view members'))
    change_members = models.ManyToManyField(Member, related_name='group_members_changeable_by_group', blank=True,
                                            verbose_name=_('May change members'))
    delete_members = models.ManyToManyField(Member, related_name='group_members_deletable_by', blank=True,
                                            verbose_name=_('May delete members'))

    # every member in any view_group may view all members of group
    list_groups = models.ManyToManyField(Group, related_name='group_members_listable_by', blank=True,
                                         verbose_name=_('May list members of groups'))
    view_groups = models.ManyToManyField(Group, related_name='group_members_viewable_by', blank=True,
                                         verbose_name=_('May view members of groups'))
    change_groups = models.ManyToManyField(Group, related_name='group_members_changeable_by', blank=True,
                                           verbose_name=_('May change members of groups'))
    delete_groups = models.ManyToManyField(Group, related_name='group_members_deletable_by', blank=True,
                                           verbose_name=_('May delete members of groups'))

    class Meta:
        verbose_name = _('Group permissions')
        verbose_name_plural = _('Group permissions')

    def __str__(self):
        return str(_('Group permissions'))
