from django.db import models


# Create your models here.
class Termin(models.Model):
    title = models.CharField('Titel', max_length=100)
    start_date = models.DateField('Von')
    end_date = models.DateField('Bis')
    group = models.CharField(verbose_name='Gruppe', max_length=100, default="", blank=True)
    responsible = models.CharField('Organisator', max_length=100, blank=True)
    phone = models.CharField(max_length=20, verbose_name='Telefonnumer', blank=True)
    email = models.EmailField(max_length=100, verbose_name='Email', blank=True)
    description = models.TextField('Tourenbeschreibung/Anforderung', blank=True)

    def __str__(self):
        return "{} {}".format(self.title, str(self.group))

    class Meta:
        verbose_name = 'Termin'
        verbose_name_plural = 'Termine'
