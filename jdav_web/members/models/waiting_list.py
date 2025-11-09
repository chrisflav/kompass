from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from contrib.models import CommonModel
from members.rules import is_leader_of_relevant_invitation
from contrib.rules import has_global_perm
from mailer.mailutils import send as send_mail
from .base import Person, gen_key
from .invitation import InvitationToGroup
from mailer.mailutils import get_registration_link, get_wait_confirmation_link,\
    get_invitation_reject_link, get_leave_waitinglist_link,\
    get_invitation_confirm_link
import uuid


class MemberWaitingList(Person):
    """A participant on the waiting list"""
    WAITING_CONFIRMATION_SUCCESS = 0
    WAITING_CONFIRMATION_INVALID = 1
    WAITING_CONFIRMATION_EXPIRED = 1
    WAITING_CONFIRMED = 2

    application_text = models.TextField(_('Do you want to tell us something else?'), default='', blank=True)
    application_date = models.DateTimeField(verbose_name=_('application date'), default=timezone.now)
    last_wait_confirmation = models.DateField(default=timezone.now, verbose_name=_('Last wait confirmation'))
    wait_confirmation_key = models.CharField(max_length=32, default="")
    wait_confirmation_key_expire = models.DateTimeField(default=timezone.now)
    leave_key = models.CharField(max_length=32, default="")
    last_reminder = models.DateTimeField(default=timezone.now, verbose_name=_('Last reminder'))
    sent_reminders = models.IntegerField(default=0, verbose_name=_('Missed reminders'))
    registration_key = models.CharField(max_length=32, default="")
    registration_expire = models.DateTimeField(default=timezone.now)

    class Meta(CommonModel.Meta):
        verbose_name = _('Waiter')
        verbose_name_plural = _('Waiters')
        permissions = (('may_manage_waiting_list', 'Can view and manage the waiting list.'),)
        rules_permissions = {
            'add_obj': has_global_perm('members.add_global_memberwaitinglist'),
            'view_obj': is_leader_of_relevant_invitation | has_global_perm('members.view_global_memberwaitinglist'),
            'change_obj': has_global_perm('members.change_global_memberwaitinglist'),
            'delete_obj': has_global_perm('members.delete_global_memberwaitinglist'),
        }

    def latest_group_invitation(self):
        gi = self.invitationtogroup_set.order_by('-pk').first()
        return "{group}: {status}".format(group=gi.group.name, status=gi.status()) if gi else "-"
    latest_group_invitation.short_description = _('Latest group invitation')

    @property
    def waiting_confirmation_needed(self):
        return not self.wait_confirmation_key and \
            self.last_wait_confirmation < timezone.now() - \
            timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)

    def waiting_confirmed(self):
        if self.sent_reminders > 0:
            if timezone.now() < self.wait_confirmation_key_expire:
                return None
            return False
        return True
    waiting_confirmed.admin_order_field = 'last_wait_confirmation'
    waiting_confirmed.boolean = True
    waiting_confirmed.short_description = _('Waiting status confirmed')

    def confirm_waiting(self, key):
        if not self.wait_confirmation_key == key:
            return self.WAITING_CONFIRMATION_INVALID

        if timezone.now() < self.wait_confirmation_key_expire:
            self.last_wait_confirmation = timezone.now()
            self.wait_confirmation_key_expire = timezone.now()
            self.sent_reminders = 0
            self.leave_key = ''
            self.save()
            return self.WAITING_CONFIRMATION_SUCCESS

        if self.waiting_confirmed():
            return self.WAITING_CONFIRMED

        return self.WAITING_CONFIRMATION_EXPIRED

    def ask_for_wait_confirmation(self):
        self.last_reminder = timezone.now()
        self.sent_reminders += 1
        self.leave_key = gen_key()
        self.save()
        self.send_mail(_('Waiting confirmation needed'),
                       settings.WAIT_CONFIRMATION_TEXT.format(
                           name=self.prename,
                           link=get_wait_confirmation_link(self),
                           leave_link=get_leave_waitinglist_link(self.leave_key),
                           reminder=self.sent_reminders,
                           max_reminder_count=settings.MAX_REMINDER_COUNT))

    def generate_wait_confirmation_key(self):
        self.wait_confirmation_key = uuid.uuid4().hex
        self.wait_confirmation_key_expire = timezone.now() + \
            timezone.timedelta(days=settings.GRACE_PERIOD_WAITING_CONFIRMATION)
        self.save()
        return self.wait_confirmation_key

    def may_register(self, key):
        try:
            invitation = InvitationToGroup.objects.get(key=key)
            return self.pk == invitation.waiter.pk and \
                   timezone.now().date() < invitation.date + timezone.timedelta(days=30)
        except InvitationToGroup.DoesNotExist:
            return False

    def invite_to_group(self, group, text_template=None, creator=None):
        self.invited_for_group = group
        self.save()
        if not text_template:
            text_template = group.get_invitation_text_template()
        invitation = InvitationToGroup(group=group, waiter=self, created_by=creator)
        invitation.save()
        self.send_mail(_("Invitation to trial group meeting"),
            text_template.format(
                name=self.prename,
                link=get_registration_link(invitation.key),
                invitation_reject_link=get_invitation_reject_link(invitation.key),
                invitation_confirm_link=get_invitation_confirm_link(invitation.key)),
            cc=group.contact_email.email)

    def unregister(self):
        self.send_mail(_("Unregistered from waiting list"),
                       settings.LEAVE_WAITINGLIST_TEXT.format(name=self.prename))
        self.delete()

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if ret:
            self.send_mail(_("Successfully registered for the waitinglist"),
                           settings.JOIN_WAITINGLIST_CONFIRMATION_TEXT.format(name=self.prename))
        return ret
