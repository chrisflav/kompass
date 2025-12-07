from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.utils.translation import gettext_lazy as _
from members.rules import is_leader


class NewMemberOnList(CommonModel):
    """
    Connects members to a list of members.
    """

    member = models.ForeignKey("Member", verbose_name=_("Member"), on_delete=models.CASCADE)
    content_type = models.ForeignKey(
        ContentType, on_delete=models.CASCADE, default=ContentType("members", "Freizeit").pk
    )
    object_id = models.PositiveIntegerField()
    memberlist = GenericForeignKey("content_type", "object_id")
    comments = models.TextField(_("Comment"), default="", blank=True)

    def __str__(self):
        return str(self.member)

    class Meta(CommonModel.Meta):
        verbose_name = _("Member")
        verbose_name_plural = _("Members")
        rules_permissions = {
            "add_obj": is_leader,
            "view_obj": is_leader | has_global_perm("members.view_global_freizeit"),
            "change_obj": is_leader,
            "delete_obj": is_leader,
        }

    @property
    def comments_tex(self):
        raw = ". ".join(c for c in (self.member.comments, self.comments) if c).replace("..", ".")
        return raw if raw else "---"

    @property
    def skills(self):
        activities = [a.name for a in self.memberlist.activity.all()]
        return {k: v for k, v in self.member.get_skills().items() if k in activities}

    @property
    def qualities_tex(self):
        qualities = []
        for activity, value in self.skills.items():
            qualities.append("\\textit{{{}:}} {}".format(activity, value))
        return ", ".join(qualities)
