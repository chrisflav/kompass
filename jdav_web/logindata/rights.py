"""Who may hand out or take over which Django rights.

Shared by the logindata admin API and the classic admin, so that
``auth.change_user`` and ``auth.change_group`` are never a way to more rights
than the caller already holds: not by granting a permission, not by adding a
rights group, and not by taking over an account that holds more.
"""

from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

SUPERUSER_ACCOUNT = _("Only a superuser may change a superuser account.")
STRONGER_ACCOUNT = _("You cannot change an account that has rights you do not hold yourself.")
MISSING_PERMISSIONS = _("You cannot grant permissions you do not hold yourself: %(permissions)s")


def _codenames(permissions):
    return {
        "{}.{}".format(p.content_type.app_label, p.codename)
        for p in permissions.select_related("content_type")
    }


def missing_permissions(actor, permissions):
    """The codenames among ``permissions`` that ``actor`` does not hold, sorted."""
    if actor.is_superuser:
        return []
    return sorted(_codenames(permissions) - actor.get_all_permissions())


def account_refusal(actor, user):
    """Why ``actor`` may not change ``user``'s account, or ``None`` if they may.

    The account's permissions are read from the database rather than through
    ``get_all_permissions``, which reports none for an inactive account: one
    that is reactivated after its password was set would otherwise be a way in.
    """
    if actor.is_superuser:
        return None
    if user.is_superuser:
        return SUPERUSER_ACCOUNT
    if user.is_staff and not actor.is_staff:
        return STRONGER_ACCOUNT
    held = Permission.objects.filter(Q(user=user) | Q(group__user=user)).distinct()
    if _codenames(held) - actor.get_all_permissions():
        return STRONGER_ACCOUNT
    return None
