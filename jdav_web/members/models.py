from datetime import datetime
import hashlib
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
    email = models.EmailField(max_length=100, default="")
    birth_date = models.DateField(_('birth date'))  # to determine the age
    group = models.ManyToManyField(Group)
    gets_newsletter = models.BooleanField(_('receives newsletter'),
                                          default=True)
    key = models.CharField(max_length=32, default="")

    def __str__(self):
        """String representation"""
        return self.name

    def save(self, *args, **kwargs):
        if len(self.key) == 0:
            self.key = hashlib.md5((self.prename + self.lastname +
                                    self.email).encode()).hexdigest()
        super(Member, self).save(*args, **kwargs)

    @property
    def name(self):
        """Returning whole name (prename + lastname)"""
        return "{0} {1}".format(self.prename, self.lastname)

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
