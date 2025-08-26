from django.db import models
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext
from .mailutils import send, get_content, NOT_SENT, SENT, PARTLY_SENT,\
        addr_with_name
from utils import RestrictedFileField
from jdav_web.celery import app
from django.core.validators import RegexValidator
from django.conf import settings

from contrib.rules import has_global_perm
from contrib.models import CommonModel
from .rules import is_creator

import os


alphanumeric = RegexValidator(r'^[0-9a-zA-Z._-]*$',
                              _('Only alphanumeric characters, ., - and _ are allowed'))


class EmailAddress(models.Model):
    """Represents an email address, that is forwarded to specific members"""
    name = models.CharField(_('name'), max_length=50, validators=[alphanumeric],
                            unique=True)
    to_members = models.ManyToManyField('members.Member',
                                        verbose_name=_('Forward to participants'),
                                        blank=True)
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('Forward to group'),
                                       blank=True)
    internal_only = models.BooleanField(verbose_name=_('Restrict to internal email addresses'),
                                        help_text=_('Only allow forwarding to this e-mail address from one of the following domains: %(domains)s.') % {'domains': ", ".join(settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER)},
                                        default=False)
    allowed_senders = models.ManyToManyField('members.Group',
                                             verbose_name=_('Allowed sender'),
                                             help_text=_('Only forward e-mails of members of selected groups. Leave empty to allow all senders.'),
                                             blank=True,
                                             related_name='allowed_sender_on_emailaddresses')

    @property
    def email(self):
        return "{0}@{1}".format(self.name, settings.DOMAIN)

    @property
    def forwards(self):
        mails = set(member.email for member in self.to_members.all())
        mails.update([member.email for group in self.to_groups.all() for member in group.member_set.all()])
        return mails

    def __str__(self):
        return self.email

    class Meta:
        verbose_name = _('email address')
        verbose_name_plural = _('email addresses')


class EmailAddressForm(forms.ModelForm):

    class Meta:
        model = EmailAddress
        exclude = []

    def clean(self):
        super(EmailAddressForm, self).clean()
        group = self.cleaned_data.get('to_groups')
        members = self.cleaned_data.get('to_members')
        if not group and not members:
            raise ValidationError(_('Either a group or at least'
                                    ' one member is required as forward recipient.'))



# Create your models here.
class Message(CommonModel):
    """Represents a message that can be sent to some members"""
    subject = models.CharField(_('subject'), max_length=50)
    content = models.TextField(_('content'))
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('to group'),
                                       blank=True)
    to_freizeit = models.ForeignKey('members.Freizeit',
                                    verbose_name=_('to freizeit'),
                                    on_delete=models.CASCADE,
                                    blank=True,
                                    null=True)
    to_notelist = models.ForeignKey('members.MemberNoteList',
                                      verbose_name=_('to notes list'),
                                      on_delete=models.CASCADE,
                                      blank=True,
                                      null=True)
    to_members = models.ManyToManyField('members.Member',
                                        verbose_name=_('to member'),
                                        blank=True)
    reply_to = models.ManyToManyField('members.Member',
                                      verbose_name=_('reply to participant'),
                                      blank=True,
                                      related_name='reply_to')
    reply_to_email_address = models.ManyToManyField('mailer.EmailAddress',
                                                    verbose_name=_('reply to custom email address'),
                                                    blank=True,
                                                    related_name='reply_to_email_addr')
    sent = models.BooleanField(_('sent'), default=False)
    created_by = models.ForeignKey('members.Member', verbose_name=_('Created by'),
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL,
                                   related_name='created_messages')

    def __str__(self):
        return self.subject

    def get_recipients(self):
        recipients = [g.name for g in self.to_groups.all()]
        if self.to_freizeit is not None:
            recipients.append(self.to_freizeit.name)
        if self.to_notelist is not None:
            recipients.append(self.to_notelist.title)
        if 3 > self.to_members.count() > 0:
            recipients.extend([m.name for m in self.to_members.all()])
        elif self.to_members.count() > 2:
            recipients.append(gettext('Some other members'))
        return ", ".join(recipients)
    get_recipients.short_description = _('recipients')

    def submit(self, sender=None):
        """Sends the mail to the specified group of members"""
        # recipients
        members = set()
        # get all the members of the selected groups
        groups = [gr.member_set.all() for gr in self.to_groups.all()]
        members.update([m for gr in groups for m in gr])
        # get all the individually picked members
        members.update(self.to_members.all())
        # get all the members of the selected freizeit
        if self.to_freizeit is not None:
            members.update([mol.member for mol in
                            self.to_freizeit.membersonlist.all()])
            members.update(self.to_freizeit.jugendleiter.all())
        # get all the members of the selected notes list
        if self.to_notelist is not None:
            members.update([mol.member for mol in
                            self.to_notelist.membersonlist.all()])
        filtered = [m for m in members if m.gets_newsletter]
        print("sending mail to", filtered)

        attach = [a.f.path for a in Attachment.objects.filter(msg__id=self.pk)
                  if a.f.name]

        emails = [member.email for member in filtered]
        emails.extend([member.alternative_email for member in filtered if member.alternative_email])
        # remove any underscores from subject to prevent Arne from using
        # terrible looking underscores in subjects
        self.subject = self.subject.replace('_', ' ')
        # generate message id
        message_id = "<{pk}@{domain}>".format(pk=self.pk, domain=settings.DOMAIN)
        # reply to addresses
        reply_to = [jl.association_email for jl in self.reply_to.all()]
        reply_to.extend([ml.email for ml in self.reply_to_email_address.all()])
        # set correct from address
        # if the sender is none or if sending from association emails has been
        # disabled, use the default sending mail
        if sender is None:
            from_addr = addr_with_name(settings.DEFAULT_SENDING_MAIL, settings.DEFAULT_SENDING_NAME)
        elif sender and settings.SEND_FROM_ASSOCIATION_EMAIL:
            from_addr = addr_with_name(sender.association_email, sender.name)
        else:
            from_addr = addr_with_name(settings.DEFAULT_SENDING_MAIL, sender.name)
        # if sending from the association email has been disabled,
        # a sender was supplied and the reply to is empty, add the sender's
        # DAV360 email as reply to
        if sender and not settings.SEND_FROM_ASSOCIATION_EMAIL and sender.has_internal_email() and reply_to == []:
            reply_to.append(addr_with_name(sender.email, sender.name))
        try:
            success = send(self.subject, get_content(self.content, registration_complete=True),
                           from_addr,
                           emails,
                           message_id=message_id,
                           attachments=attach,
                           reply_to=reply_to)
            if success == SENT or success == PARTLY_SENT:
                self.sent = True
            for a in Attachment.objects.filter(msg__id=self.pk):
                if a.f.name:
                    os.remove(a.f.path)
                a.delete()
            success = SENT
        except Exception as e:
            print("Exception caught", e)
            success = NOT_SENT
        finally:
            self.save()
        return success

    class Meta(CommonModel.Meta):
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        permissions = (
            ("submit_mails", _("Can submit mails")),
        )
        rules_permissions = {
            "view_obj": is_creator | has_global_perm('mailer.view_global_message'),
            "change_obj": is_creator | has_global_perm('mailer.change_global_message'),
            "delete_obj": is_creator | has_global_perm('mailer.delete_global_message'),
        }


class MessageForm(forms.ModelForm):

    class Meta:
        model = Message
        exclude = []

    def clean(self):
        group = self.cleaned_data.get('to_groups')
        freizeit = self.cleaned_data.get('to_freizeit')
        notelist = self.cleaned_data.get('to_notelist')
        members = self.cleaned_data.get('to_members')
        if not group and freizeit is None and not members and notelist is None:
            raise ValidationError(_('Either a group, a memberlist or at least'
                                    ' one member is required as recipient'))

class Attachment(CommonModel):
    """Represents an attachment to an email"""
    msg = models.ForeignKey(Message, on_delete=models.CASCADE)
    # file (not naming it file because of builtin)
    f = RestrictedFileField(_('file'),
                            upload_to='attachments',
                            max_upload_size=10)

    def __str__(self):
        return os.path.basename(self.f.name) if self.f.name else str(_("Empty"))

    class Meta:
        verbose_name = _('attachment')
        verbose_name_plural = _('attachments')
        rules_permissions = {
            "add_obj": is_creator | has_global_perm('mailer.view_global_message'),
            "view_obj": is_creator | has_global_perm('mailer.view_global_message'),
            "change_obj": is_creator | has_global_perm('mailer.change_global_message'),
            "delete_obj": is_creator | has_global_perm('mailer.delete_global_message'),
        }

