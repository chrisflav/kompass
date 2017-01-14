from django.db import models
from django.forms import forms
from django.utils.translation import ugettext_lazy as _
from .mailutils import send, get_content

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
                                       verbose_name=_('to group'))
    sent = models.BooleanField(_('sent'), default=False)

    def __str__(self):
        return self.subject

    def get_groups(self):
        return ", ".join([g.name for g in self.to_groups.all()])
    get_groups.short_description = _('recipients')

    def submit(self):
        """Sends the mail to the specified group of members"""
        members = set()
        for group in self.to_groups.all():
            group_members = group.member_set.all()
            for member in group_members:
                if not member.gets_newsletter:
                    continue
                members.add(member)
        attach = [a.f.path for a in Attachment.objects.filter(msg__id=self.pk)
                  if a.f.name]
        success = send(self.subject, get_content(self.content),
                       self.from_addr, [member.email for member in members],
                       attachments=attach)
        for a in Attachment.objects.filter(msg__id=self.pk):
            if a.f.name:
                os.remove(a.f.path)
            a.delete()
        if success:
            self.sent = True
            self.save()
            return True
        else:
            return False

    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        permissions = (
            ("submit_mails", _("Can submit mails")),
        )


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
