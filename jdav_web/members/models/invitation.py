import uuid
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from contrib.models import CommonModel
from members.rules import is_leader_of_relevant_invitation
from contrib.rules import has_global_perm
from mailer.mailutils import send as send_mail
from django.conf import settings
from .base import gen_key
from .group import Group

class InvitationToGroup(CommonModel):
    """An invitation of a waiter to a group."""
    waiter = models.ForeignKey('MemberWaitingList', verbose_name=_('Waiter'), on_delete=models.CASCADE)
    group = models.ForeignKey(Group, verbose_name=_('Group'), on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now, verbose_name=_('Invitation date'))
    rejected = models.BooleanField(verbose_name=_('Invitation rejected'), default=False)
    key = models.CharField(max_length=32, default=gen_key)
    created_by = models.ForeignKey('Member', verbose_name=_('Created by'),
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL,
                                   related_name='created_group_invitations')

    class Meta(CommonModel.Meta):
        verbose_name = _('Invitation to group')
        verbose_name_plural = _('Invitations to groups')
        rules_permissions = {
            'add_obj': has_global_perm('members.add_global_memberwaitinglist'),
            'view_obj': is_leader_of_relevant_invitation | has_global_perm('members.view_global_memberwaitinglist'),
            'change_obj': has_global_perm('members.change_global_memberwaitinglist'),
            'delete_obj': has_global_perm('members.delete_global_memberwaitinglist'),
        }

    def is_expired(self):
        return self.date < (timezone.now() - timezone.timedelta(days=30)).date()

    def status(self):
        if self.rejected:
            return _('Rejected')
        elif self.is_expired():
            return _('Expired')
        return _('Undecided')
    status.short_description = _('Status')

    def send_left_waitinglist_notification_to(self, recipient):
        send_mail(_('%(waiter)s left the waiting list') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_LEFT_WAITINGLIST.format(name=recipient.prename,
                                                                    waiter=self.waiter,
                                                                    group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_reject_notification_to(self, recipient):
        send_mail(_('Group invitation rejected by %(waiter)s') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_REJECTED.format(name=recipient.prename,
                                                            waiter=self.waiter,
                                                            group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_confirm_notification_to(self, recipient):
        send_mail(_('Group invitation confirmed by %(waiter)s') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_CONFIRMED_TEXT.format(name=recipient.prename,
                                                                  waiter=self.waiter,
                                                                  group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_confirm_confirmation(self):
        self.waiter.send_mail(_('Trial group meeting confirmed'),
                              settings.TRIAL_GROUP_MEETING_CONFIRMED_TEXT.format(name=self.waiter.prename,
                                                                                 group=self.group,
                                                                                 contact_email=self.group.contact_email,
                                                                                 timeinfo=self.group.get_time_info()))

    def notify_left_waitinglist(self):
        """
        Inform youth leaders of the group and the inviter that the waiter left the waitinglist,
        prompted by this group invitation.
        """
        if self.created_by:
            self.send_left_waitinglist_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_left_waitinglist_notification_to(jl)

    def reject(self):
        """Reject this invitation. Informs the youth leaders of the group of the rejection."""
        self.rejected = True
        self.save()
        # send notifications
        if self.created_by:
            self.send_reject_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_reject_notification_to(jl)

    def confirm(self):
        """Confirm this invitation. Informs the youth leaders of the group of the invitation."""
        self.rejected = False
        self.save()
        # confirm the confirmation
        self.send_confirm_confirmation()
        # send notifications
        if self.created_by:
            self.send_confirm_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_confirm_notification_to(jl)

