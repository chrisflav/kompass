from django.db import models
from django.utils.translation import ugettext_lazy as _


# Create your models here.
class Message(models.Model):
    """Represents a message that can be sent to some members"""
    from_addr = models.EmailField('email')
    subject = models.CharField(_('subject'), max_length=50)
    content = models.TextField(_('content'))
    to_group = models.ForeignKey('members.Group', verbose_name=_('group'))

    def submit(self):
        print("Sending message")
