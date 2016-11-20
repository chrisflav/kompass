from datetime import datetime

from django.db import models
from django.utils import timezone
from django.utils.translation import ugettext_lazy as _

# maximum time in years of a material part until being replaced
MAX_TIME_MATERIAL = 5


# Create your models here.
class MaterialPart(models.Model):
    """
    Represents one part of material, which is owned (and stored) by different
    members of the association (Ownership)
    """
    name = models.CharField(_('name'), max_length=30)
    quantity = models.IntegerField(_('quantity'), default=0)
    buy_date = models.DateField(_('purchase date'), editable=True)
    lifetime = models.DecimalField(_('lifetime (years)'), decimal_places=0, max_digits=3)
    photo = models.ImageField(_('photo'), upload_to='images', blank=True)

    def __str__(self):
        """String representation"""
        return self.name

    def quantity_real(self):
        real = sum([o.count for o in Ownership.objects.filter(material__id = self.pk)])
        return str(real) + '/' + str(self.quantity)

    quantity_real.admin_order_field = 'quantity'
    quantity_real.short_description = _('Quantity')


    def not_too_old(self):
        """Returns wether the part should be replaced cause of age"""
        buy_time = timezone.make_aware(datetime.combine(self.buy_date,
                                                        datetime.min.time()))
        return yearsago(self.lifetime) < buy_time

    not_too_old.admin_order_field = 'buy_date'
    not_too_old.boolean = True
    not_too_old.short_description = _('Not too old?')

    class Meta:
        verbose_name = _('material part')
        verbose_name_plural = _('material parts')


class Ownership(models.Model):
    """Represents the connection between a MaterialPart and a Member"""
    material = models.ForeignKey(MaterialPart, on_delete=models.CASCADE)
    owner = models.ForeignKey('members.Member', verbose_name=_('owner'))
    count = models.IntegerField(_('count'), default=1)

    def __str__(self):
        """String representation"""
        return str(self.owner)

    class Meta:
        verbose_name = _('ownership')
        verbose_name_plural = _('ownerships')


def yearsago(years, from_date=None):
    """Function to return the date with a delta of years in the past"""
    if from_date is None:
        from_date = timezone.now()
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        # 29.02 -> use 28.02
        assert from_date.month == 2 and from_date.day == 29
        return from_date.replace(month=2, day=28, year=from_date.year - years)
