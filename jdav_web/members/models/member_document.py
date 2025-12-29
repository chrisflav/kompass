import os

from contrib.models import CommonModel
from django.db import models
from django.utils.translation import gettext_lazy as _
from utils import RestrictedFileField


class MemberDocument(CommonModel):
    """Represents an additional document attached to a member profile"""

    member = models.ForeignKey("Member", on_delete=models.CASCADE)
    # file (not naming it file because of builtin)
    f = RestrictedFileField(_("file"), upload_to="member_documents", max_upload_size=10)

    def __str__(self):
        return os.path.basename(self.f.name) if self.f.name else str(_("Empty"))

    class Meta:
        verbose_name = _("Extra document")
        verbose_name_plural = _("Extra documents")
