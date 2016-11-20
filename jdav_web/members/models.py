from datetime import datetime
from django.db import models
from django.utils.translation import ugettext_lazy as _


class Group(models.Model):
    """
    Represents one group of the association
    e.g: J1, J2, Jugendleiter, etc.
    """
    name = models.CharField(max_length=20, verbose_name=_('name'))  # e.g: J1
    min_age = models.IntegerField(default=5,
                                  verbose_name=_('minimum age (years)'))

    def __str__(self):
        """String representation"""
        return self.name

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')


class Member(models.Model):
    """
    Represents a member of the association
    Might be a member of different groups: e.g. J1, J2, Jugendleiter, etc.
    """
    prename = models.CharField(max_length=20, verbose_name=_('prename'))
    lastname = models.CharField(max_length=20, verbose_name=_('last name'))
    street = models.CharField(max_length=30, verbose_name=_('street'), default='', blank=True)
    town = models.CharField(max_length=30, verbose_name=_('town'), default='', blank=True)
    phone_number = models.CharField(max_length=12, verbose_name=_('phone number'), default='', blank=True)
    phone_number_parents = models.CharField(max_length=12, verbose_name=_('parents phone number'), default='', blank=True)
    email = models.EmailField(max_length=100, default="")
    birth_date = models.DateField(_('birth date'))  # to determine the age
    group = models.ManyToManyField(Group)
    gets_newsletter = models.BooleanField(_('receives newsletter'),
                                          default=True)
    comments = models.TextField(_('comments'), default='', blank=True)

    def __str__(self):
        """String representation"""
        return self.name

    @property
    def name(self):
        """Returning whole name (prename + lastname)"""
        return "{0} {1}".format(self.prename, self.lastname)
    
    def get_group(self):
        """Returns a string of groups in which the member is."""
        groupstring = ''.join(g.name + ',\n' for g in self.group.all())
        groupstring = groupstring[:-2]
        return groupstring
    get_group.short_description = _('Group')

    class Meta:
        verbose_name = _('member')
        verbose_name_plural = _('members')


class MemberList(models.Model):
    """Lets the user create a list of members in pdf format. """
    name = models.CharField(verbose_name='List Name', default='',
                            max_length=50)
    date = models.DateField(default=datetime.today)
    comment = models.TextField(_('Comments'), default='')

    def __str__(self):
        """String represenation"""
        return self.name


class MemberOnList(models.Model):
    """
    Connects members to a list of members.
    """
    member = models.ForeignKey(Member)
    memberlist = models.ForeignKey(MemberList)
    comments = models.TextField(_('Comment'), default='')


class Klettertreff(models.Model):
    """ This model represents a Klettertreff event.

    A Klettertreff can take a date, location, Jugendleiter, attending members as
    input.
    """
    date = models.DateField(_('Date'), default=datetime.today)
    location = models.CharField(_('Location'), default='', max_length=60)
    jugendleiter = models.ManyToManyField(Member)
    
    def __str__(self):
        return self.location + ' ' + self.date.strftime('%d.%m.%Y')

    def get_jugendleiter(self):
        jl_string = ''.join(j.name + ',\n' for j in self.jugendleiter.all())
        jl_string = jl_string[:-2]
        return jl_string

    get_jugendleiter.short_description = _('Jugendleiter')

class KlettertreffAttendee(models.Model):
    """Connects members to Klettertreffs."""
    member = models.ForeignKey(Member)
    klettertreff = models.ForeignKey(Klettertreff)

