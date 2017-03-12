from django.db import models
from django.core.exceptions import ValidationError
from django import forms
from django.utils.translation import ugettext_lazy as _
from .mailutils import send, get_content, SENT, PARTLY_SENT

import os


class RestrictedFileField(models.FileField):

    def __init__(self, *args, **kwargs):
        if "max_upload_size" in kwargs:
            self.max_upload_size = kwargs.pop("max_upload_size")

        super(RestrictedFileField, self).__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        data = super(RestrictedFileField, self).clean(*args, **kwargs)
        f = data.file
        try:
            if f._size > self.max_upload_size:
                raise forms.ValidationError('Please keep filesize under {}. '
                                            'Current filesize: '
                                            '{}'.format(self.max_upload_size,
                                                        f._size))
        except AttributeError as e:
            print(e)
        return data


# Create your models here.
class Message(models.Model):
    """Represents a message that can be sent to some members"""
    from_addr = models.EmailField(_('from email'))
    subject = models.CharField(_('subject'), max_length=50)
    content = models.TextField(_('content'))
    to_groups = models.ManyToManyField('members.Group',
                                       verbose_name=_('to group'),
                                       blank=True)
    to_memberlist = models.ForeignKey('members.MemberList',
                                      verbose_name=_('to member list'),
                                      blank=True,
                                      null=True)
    reply_to = models.ForeignKey('members.Member',
                                 verbose_name=_('reply to'),
                                 blank=True,
                                 null=True)
    sent = models.BooleanField(_('sent'), default=False)

    def __str__(self):
        return self.subject

    def get_recipients(self):
        recipients = [g.name for g in self.to_groups.all()]
        if self.to_memberlist is not None:
            recipients.append(self.to_memberlist.name)
        return ", ".join(recipients)
    get_recipients.short_description = _('recipients')

    def submit(self):
        """Sends the mail to the specified group of members"""
        members = set()
        groups = [gr.member_set.all() for gr in self.to_groups.all()]
        members.update([m for gr in groups for m in gr])
        if self.to_memberlist is not None:
            members.update([mol.member for mol in
                            self.to_memberlist.memberonlist_set.all()])
            members.update(self.to_memberlist.jugendleiter.all())
        filtered = [m for m in members if m.gets_newsletter]
        print("sending mail to", filtered)
        attach = [a.f.path for a in Attachment.objects.filter(msg__id=self.pk)
                  if a.f.name]
        success = send(self.subject, get_content(self.content),
                       self.from_addr,
                       [member.email for member in filtered],
                       attachments=attach,
                       reply_to=self.reply_to.email if self.reply_to else None)
        for a in Attachment.objects.filter(msg__id=self.pk):
            if a.f.name:
                os.remove(a.f.path)
            a.delete()
        if success == SENT or success == PARTLY_SENT:
            self.sent = True
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
        print("group", group, "memberlist", memberlist)
        if not group and memberlist is None:
            raise ValidationError(_('Either a group is required or a '
                                    'memberlist as recipient'))


class Attachment(models.Model):
    """Represents an attachment to an email"""
    msg = models.ForeignKey(Message, on_delete=models.CASCADE)
    print("attachment class")
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
