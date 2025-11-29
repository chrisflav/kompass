from django.db import models
from rules.contrib.models import RulesModelBase
from rules.contrib.models import RulesModelMixin


# Create your models here.
class CommonModel(models.Model, RulesModelMixin, metaclass=RulesModelBase):
    class Meta:
        abstract = True
        default_permissions = (
            "add_global",
            "change_global",
            "view_global",
            "delete_global",
            "list_global",
            "view",
        )
