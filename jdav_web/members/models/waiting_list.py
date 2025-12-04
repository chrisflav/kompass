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
        if gi:
            return "{group}: {status}".format(group=gi.group.name, status=gi.status())
        else:
            return "-"
    latest_group_invitation.short_description = _('Latest group invitation')

    @property
    def waiting_confirmation_needed(self):
        """Returns if person should be asked to confirm waiting status."""
        return not self.wait_confirmation_key \
            and self.last_wait_confirmation < timezone.now() -\
                timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)

    def waiting_confirmed(self):
        """Returns if the persons waiting status is considered to be confirmed."""
        if self.sent_reminders > 0:
            # there was sent at least one wait confirmation request
            if timezone.now() < self.wait_confirmation_key_expire:
                # the request has not expired yet
                return None
            else:
                # we sent a request that has expired
                return False
        else:
            # if there exist no pending or expired reminders, the waiter remains confirmed
            return True
    waiting_confirmed.admin_order_field = 'last_wait_confirmation'
    waiting_confirmed.boolean = True
    waiting_confirmed.short_description = _('Waiting status confirmed')

    def ask_for_wait_confirmation(self):
        """Sends an email to the person asking them to confirm their intention to wait."""
        self.last_reminder = timezone.now()
        self.sent_reminders += 1
        self.leave_key = gen_key()
        self.save()
        self.send_mail(_('Waiting confirmation needed'),
                       settings.WAIT_CONFIRMATION_TEXT.format(name=self.prename,
                                                              link=get_wait_confirmation_link(self),
                                                              leave_link=get_leave_waitinglist_link(self.leave_key),
                                                              reminder=self.sent_reminders,
                                                              max_reminder_count=settings.MAX_REMINDER_COUNT))

    def confirm_waiting(self, key):
        # if a wrong key is supplied, we return invalid
        if not self.wait_confirmation_key == key:
            return self.WAITING_CONFIRMATION_INVALID

        # if the current wait confirmation key is not expired, return sucess
        if timezone.now() < self.wait_confirmation_key_expire:
            self.last_wait_confirmation = timezone.now()
            self.wait_confirmation_key_expire = timezone.now()
            self.sent_reminders = 0
            self.leave_key = ''
            self.save()
            return self.WAITING_CONFIRMATION_SUCCESS

        # if the waiting is already confirmed, return success
        # this might happen if both parents and member mail are used for communication
        if self.waiting_confirmed():
            return self.WAITING_CONFIRMED

        # otherwise the link is too old and the person was not confirmed in time
        return self.WAITING_CONFIRMATION_EXPIRED

    def generate_wait_confirmation_key(self):
        self.wait_confirmation_key = uuid.uuid4().hex
        self.wait_confirmation_key_expire = timezone.now() \
            + timezone.timedelta(days=settings.GRACE_PERIOD_WAITING_CONFIRMATION)
        self.save()
        return self.wait_confirmation_key

    def may_register(self, key):
        try:
            invitation = InvitationToGroup.objects.get(key=key)
            return self.pk == invitation.waiter.pk and timezone.now().date() < invitation.date + timezone.timedelta(days=30)
        except InvitationToGroup.DoesNotExist:
            return False

    def invite_to_group(self, group, text_template=None, creator=None):
        """
        Invite waiter to given group. Stores a new group invitation
        and sends a personalized e-mail based on the passed template.
        """
        self.invited_for_group = group
        self.save()
        if not text_template:
            text_template = group.get_invitation_text_template()
        invitation = InvitationToGroup(group=group, waiter=self, created_by=creator)
        invitation.save()
        self.send_mail(_("Invitation to trial group meeting"),
            text_template.format(name=self.prename,
                                 link=get_registration_link(invitation.key),
                                 invitation_reject_link=get_invitation_reject_link(invitation.key),
                                 invitation_confirm_link=get_invitation_confirm_link(invitation.key)),
            cc=group.contact_email.email)

    def unregister(self):
        """Delete the waiter and inform them about the deletion via email."""
        self.send_mail(_("Unregistered from waiting list"),
                       settings.LEAVE_WAITINGLIST_TEXT.format(name=self.prename))
        self.delete()

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if ret:
            self.send_mail(_("Successfully registered for the waitinglist"),
                           settings.JOIN_WAITINGLIST_CONFIRMATION_TEXT.format(name=self.prename))
        return ret
