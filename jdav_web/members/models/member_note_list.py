from datetime import datetime

from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
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

    def get_dropdown_display(self):
        """Return a string suitable for display in admin dropdown menus."""
        if self.date:
            return f"{self.title} - {self.date.strftime('%d.%m.%Y')}"
        return self.title

    @staticmethod
    def filter_queryset_by_change_permissions(user, queryset=None):
        if queryset is None:
            queryset = MemberNoteList.objects.all()
        if user.has_perm("members.change_membernotelist"):
            return queryset
        else:
            return MemberNoteList.objects.none()

    def add_members(self, queryset):
        content_type = ContentType.objects.get_for_model(MemberNoteList)

        # Add selected members to the note list
        for member in queryset:
            NewMemberOnList.objects.get_or_create(
                member=member, content_type=content_type, object_id=self.pk
            )

    class Meta:
        verbose_name = "Notizliste"
        verbose_name_plural = "Notizlisten"
