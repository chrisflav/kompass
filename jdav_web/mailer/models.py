from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.core.mail import send_mass_mail


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
    get_groups.short_description = _('recipicients')

    def submit(self):
        """Sends the mail to the specified group of members"""
        members = set()
        for group in self.to_groups.all():
            group_members = group.member_set.all()
            for member in group_members:
                members.add(member)
        data = [
            (self.subject, self.content, self.from_addr, [member.email])
            for member in members
        ]
        send_mass_mail(data)
        self.sent = True
        self.save()

    class Meta:
        verbose_name = _('message')
        verbose_name_plural = _('messages')
        permissions = (
            ("submit_mails", _("Can submit mails")),
        )
