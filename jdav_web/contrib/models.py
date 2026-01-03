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

    @classmethod
    def filter_queryset_by_change_permissions_member(cls, member, queryset):
        """
        Keep objects in queryset that the given `Member` may change. This
        is an internal method used to implement `filter_queryset_by_change_permissions`.
        The default implementation is a no-op.
        """
        return queryset

    @classmethod
    def filter_queryset_by_change_permissions(cls, user, queryset=None):
        """
        Keep objects in queryset that the given `User` may change.
        """
        if queryset is None:
            queryset = cls.objects.all()
        permission = f"{cls._meta.app_label}.change_global_{cls._meta.model_name}"
        if user.has_perm(permission):
            return queryset
        if not hasattr(user, "member"):
            return cls.objects.none()
        return cls.filter_queryset_by_change_permissions_member(user.member, queryset)
