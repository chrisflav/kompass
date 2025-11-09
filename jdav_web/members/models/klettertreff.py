from django.db import models
from django.utils.translation import gettext_lazy as _
from datetime import datetime

class Klettertreff(models.Model):
    """This model represents a Klettertreff event."""
    date = models.DateField(_('Date'), default=datetime.today)
    location = models.CharField(_('Location'), default='', max_length=60)
    topic = models.CharField(_('Topic'), default='', max_length=60)
    jugendleiter = models.ManyToManyField('Member')
    group = models.ForeignKey('Group', default='', verbose_name=_('Group'), on_delete=models.CASCADE)

    def __str__(self):
        return f"{self.location} {self.date:%d.%m.%Y}"

    def get_jugendleiter(self):
        return ', '.join(j.name for j in self.jugendleiter.all())
    get_jugendleiter.short_description = _('Jugendleiter')

    def has_attendee(self, member):
        return KlettertreffAttendee.objects.filter(
            member__id__contains=member.id,
            klettertreff__id__contains=self.id).exists()

    def has_jugendleiter(self, jugendleiter):
        return jugendleiter in self.jugendleiter.all()

    class Meta:
        verbose_name = _('Klettertreff')
        verbose_name_plural = _('Klettertreffs')

class KlettertreffAttendee(models.Model):
    """Connects members to Klettertreffs."""
    member = models.ForeignKey('Member', verbose_name=_('Member'), on_delete=models.CASCADE)
    klettertreff = models.ForeignKey(Klettertreff, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.member)

    class Meta:
        verbose_name = _('Member')
        verbose_name_plural = _('Members')
