from django.db import models
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import ugettext_lazy as _
from django.utils.translation import ugettext
from .mailutils import send, get_content, NOT_SENT, SENT, PARTLY_SENT, mail_root
from utils import RestrictedFileField
from jdav_web.celery import app
from django.core.validators import RegexValidator

import os

# this is the mail address that is used to send mails
SENDING_ADDRESS = mail_root
HOST = os.environ.get('DJANGO_ALLOWED_HOST', 'localhost:8000').split(",")[0]


alphanumeric = RegexValidator(r'^[0-9a-zA-Z]*$', _('Only alphanumeric characters are allowed'))


class EmailAddress(models.Model):
    """Represents an email address, that is forwarded to specific members"""
    name = models.CharField(_('name'), max_length=50, validators=[alphanumeric])
    to_members = models.ManyToManyField('members.Member',
                                        verbose_name=_('Forward to participants'),
                                        blank=True)
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('Forward to group'),
                                       blank=True)

    @property
    def email(self):
        return "{0}@{1}".format(self.name, HOST)

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
        group = self.cleaned_data.get('to_groups')
        members = self.cleaned_data.get('to_members')
        if not group and not members:
            raise ValidationError(_('Either a group or at least'
                                    ' one member is required as forward recipient.'))



# Create your models here.
class Message(models.Model):
    """Represents a message that can be sent to some members"""
    subject = models.CharField(_('subject'), max_length=50)
    content = models.TextField(_('content'))
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('to group'),
                                       blank=True)
    to_freizeit = models.ForeignKey('members.Freizeit',
                                    verbose_name=_('to freizeit'),
                                    blank=True,
                                    null=True)
    to_notelist = models.ForeignKey('members.MemberNoteList',
                                      verbose_name=_('to notes list'),
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
        emails.extend([member.email_parents for member in filtered
                       if member.email_parents])
        # remove any underscores from subject to prevent Arne from using
        # terrible looking underscores in subjects
        self.subject = self.subject.replace('_', ' ')
        # generate message id
        message_id = "<{}@jdav-ludwigsburg.de>".format(self.pk)
        # reply to addresses
        reply_to_unfiltered = [jl.association_email for jl in self.reply_to.all()]
        reply_to_unfiltered.extend([ml.email for ml in self.reply_to_email_address.all()])
        # remove sending address from reply-to field (probably unnecessary since it's removed by
        # the mail provider anyways)
        reply_to = [mail for mail in reply_to_unfiltered if mail != SENDING_ADDRESS ]
        try:
            success = send(self.subject, get_content(self.content),
                           SENDING_ADDRESS,
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
        except Exception as e:
            print("Exception caught", e)
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
        freizeit = self.cleaned_data.get('to_freizeit')
        notelist = self.cleaned_data.get('to_notelist')
        members = self.cleaned_data.get('to_members')
        if not group and freizeit is None and not members and notelist is None:
            raise ValidationError(_('Either a group, a memberlist or at least'
                                    ' one member is required as recipient'))
        reply_to = self.cleaned_data.get('reply_to')
        reply_to_email_address = self.cleaned_data.get('reply_to_email_address')
        if not reply_to and not reply_to_email_address:
            raise ValidationError(_('At least one reply-to recipient is required. '
                                    'Use the info mail if you really want no reply-to recipient.'))

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
