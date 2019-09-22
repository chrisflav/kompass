from django.db import models


class Group(models.Model):
    name = models.CharField('Name', max_length=50)

    class Meta:
        verbose_name = 'Gruppe'
        verbose_name_plural = 'Gruppen'

    def __str__(self):
        return self.name


# Create your models here.
class Termin(models.Model):
    title = models.CharField('Titel', max_length=100)
    start_date = models.DateField('Von')
    end_date = models.DateField('Bis')
    group = models.ForeignKey('ludwigsburgalpin.Group',
                              verbose_name='Gruppe')

    def __str__(self):
        return "{} {}".format(self.title, str(self.group))

    class Meta:
        verbose_name = 'Termin'
        verbose_name_plural = 'Termine'
