from datetime import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.db import models
from django.utils.translation import gettext_lazy as _

from .member_on_list import NewMemberOnList


class MemberNoteList(models.Model):
    """
    A member list with a title and a bunch of members to take some notes.
    """

    title = models.CharField(verbose_name=_("Title"), default="", max_length=50)
    date = models.DateField(default=datetime.today, verbose_name=_("Date"), null=True, blank=True)
    membersonlist = GenericRelation(NewMemberOnList)

    def __str__(self):
        """String represenation"""
        return self.title

    class Meta:
        verbose_name = "Notizliste"
        verbose_name_plural = "Notizlisten"
