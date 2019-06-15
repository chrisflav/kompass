from django.db import models
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext
from .mailutils import send, get_content, NOT_SENT, SENT, PARTLY_SENT, mail_root
from utils import RestrictedFileField
from jdav_web.celery import app

import os

# this is the mail address that is used to send mails
SENDING_ADDRESS = mail_root


# Create your models here.
class Message(models.Model):
    """Represents a message that can be sent to some members"""
    subject = models.CharField(_('subject'), max_length=50)
    content = models.TextField(_('content'))
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('to group'),
                                       blank=True)
    to_memberlist = models.ForeignKey('members.MemberList',
                                      verbose_name=_('to member list'),
                                      blank=True,
                                      null=True)
    to_members = models.ManyToManyField('members.Member',
                                        verbose_name=_('to member'),
                                        blank=True)
    reply_to = models.ManyToManyField('members.Member',
                                      verbose_name=_('reply to'),
                                      blank=True,
                                      related_name='reply_to')
    sent = models.BooleanField(_('sent'), default=False)

    def __str__(self):
        return self.subject

    def get_recipients(self):
        recipients = [g.name for g in self.to_groups.all()]
        if self.to_memberlist is not None:
            recipients.append(self.to_memberlist.name)
        if 3 > self.to_members.count() > 0:
            recipients.extend([m.name for m in self.to_members.all()])
        elif self.to_members.count() > 2:
            recipients.append(ugettext('Some other members'))
        return ", ".join(recipients)
    get_recipients.short_description = _('recipients')

    def submit(self):
        """Sends the mail to the specified group of members"""
        # recipients
        members = set()
        # get all the members of the selected groups
        groups = [gr.member_set.all() for gr in self.to_groups.all()]
        members.update([m for gr in groups for m in gr])
        # get all the individually picked members
        members.update(self.to_members.all())
        # get all the members of the selected member list
        if self.to_memberlist is not None:
            members.update([mol.member for mol in
                            self.to_memberlist.memberonlist_set.all()])
            members.update(self.to_memberlist.jugendleiter.all())
        filtered = [m for m in members if m.gets_newsletter]
        print("sending mail to", filtered)
        attach = [a.f.path for a in Attachment.objects.filter(msg__id=self.pk)
                  if a.f.name]
        emails = [member.email for member in filtered]
        emails.extend([member.email_parents for member in filtered
                       if member.email_parents])
        # remove any underscores from subject to prevent Arne from using
        # terrible looking underscores in subjects
        self.subject = self.subject.replace('_', ' ')
        if len(self.reply_to.all()) > 0:
            temporary_reply_to = [r.email for r in self.reply_to.all()]
        else:
            temporary_reply_to = None
        try:
            success = send(self.subject, get_content(self.content),
                           SENDING_ADDRESS,
                           emails,
                           reply_to=temporary_reply_to,
                           message_id=self.pk,
                           attachments=attach)
            if success == SENT or success == PARTLY_SENT:
                self.sent = True
            for a in Attachment.objects.filter(msg__id=self.pk):
                if a.f.name:
                    os.remove(a.f.path)
                a.delete()
        except Exception as e:
            print("Exception catched", e)
            success = NOT_SENT
        finally:
            self.save()
        return success

    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        permissions = (
            ("submit_mails", _("Can submit mails")),
        )


class MessageForm(forms.ModelForm):

    class Meta:
        model = Message
        exclude = []

    def clean(self):
        group = self.cleaned_data.get('to_groups')
        memberlist = self.cleaned_data.get('to_memberlist')
        members = self.cleaned_data.get('to_members')
        if not group and memberlist is None and not members:
            raise ValidationError(_('Either a group, a memberlist or at least'
                                    ' one member is required as recipient'))


class Attachment(models.Model):
    """Represents an attachment to an email"""
    msg = models.ForeignKey(Message, on_delete=models.CASCADE)
    # file (not naming it file because of builtin)
    f = RestrictedFileField(_('file'),
                            upload_to='attachments',
                            blank=True,
                            max_upload_size=10485760)

    def __str__(self):
        return os.path.basename(self.f.name) if self.f.name else _("Empty")

    class Meta:
        verbose_name = _('attachment')
        verbose_name_plural = _('attachments')
