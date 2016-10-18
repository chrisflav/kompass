from datetime import datetime

from django.db import models
from django.utils import timezone

# maximum time in years of a material part until being replaced
MAX_TIME_MATERIAL = 5


# Create your models here.
class MaterialPart(models.Model):
    """
    Represents one part of material, which is owned (and stored) by different
    members of the association (Ownership)
    """
    name = models.CharField(max_length=30)
    buy_date = models.DateField('purchase date')

    def __str__(self):
        """String representation"""
        return self.name

    def should_be_replaced(self):
        """Returns wether the part should be replaced cause of age"""
        buy_time = timezone.make_aware(datetime.combine(self.buy_date,
                                                        datetime.min.time()))
        return yearsago(MAX_TIME_MATERIAL) >= buy_time

    should_be_replaced.admin_order_field = 'buy_date'
    should_be_replaced.boolean = True
    should_be_replaced.short_description = 'Should be replaced?'


class Ownership(models.Model):
    """Represents the connection between a MaterialPart and a Member"""
    material = models.ForeignKey(MaterialPart, on_delete=models.CASCADE)
    owner = models.ForeignKey('members.Member')
    count = models.IntegerField(default=1)

    def __str__(self):
        """String representation"""
        return str(self.owner)


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
