from datetime import datetime
import uuid
from django.db import models
from django.utils.translation import ugettext_lazy as _
from django.utils import timezone


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
    unsubscribe_key = models.CharField(max_length=32, default="")
    unsubscribe_expire = models.DateTimeField(default=timezone.now)

    def __str__(self):
        """String representation"""
        return self.name

    def generate_key(self):
        self.unsubscribe_key = uuid.uuid4().hex
        self.unsubscribe_expire = timezone.now() + timezone.timedelta(days=1)
        self.save()
        return self.unsubscribe_key

    def unsubscribe(self, key):
        if self.unsubscribe_key == key and timezone.now() <\
                self.unsubscribe_expire:
            for member in Member.objects.filter(email=self.email):
                member.gets_newsletter = False
                member.save()
            self.unsubscribe_key, self.unsubscribe_expire = "", timezone.now()
            return True
        else:
            return False

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
