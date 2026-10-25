"""Who may hand out or take over which Django rights.

Shared by the logindata admin API and the classic admin, so that
``auth.change_user`` and ``auth.change_group`` are never a way to more rights
than the caller already holds: not by granting a permission, not by adding a
rights group, and not by taking over an account that holds more.

Taking over an account means deciding who can sign in as it: setting its
password, linking it to a member record, or changing the address its password
mails go to. For those, rights an account holds through its member record count
as well: the member access lists, and leading groups or excursions.
"""

from functools import reduce
from operator import or_

from django.contrib.auth.models import Permission
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from members.models import Freizeit
from members.models import PermissionGroup
from members.models import PermissionMember

SUPERUSER_ACCOUNT = _("Only a superuser may change a superuser account.")
STRONGER_ACCOUNT = _("You cannot change an account that has rights you do not hold yourself.")
MEMBER_RIGHTS = _(
    "Only a superuser may do this for an account or member record that has rights through "
    "the member access lists or by leading groups or excursions."
)
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


_ACL_FIELDS = (
    "list_members",
    "view_members",
    "change_members",
    "delete_members",
    "list_groups",
    "view_groups",
    "change_groups",
    "delete_groups",
)
# An access list row with at least one entry in any of its lists.
_GRANTS_SOMETHING = reduce(or_, (Q(**{"{}__isnull".format(f): False}) for f in _ACL_FIELDS))


def member_has_rights(member):
    """Whether ``member``'s record grants access to other members' data.

    That is an access list of its own, one of a group it belongs to, or leading
    a group or an excursion -- the rights the rules predicates hand its account.
    """
    return (
        PermissionMember.objects.filter(_GRANTS_SOMETHING, member=member).exists()
        or PermissionGroup.objects.filter(_GRANTS_SOMETHING, group__in=member.group.all()).exists()
        or member.leited_groups.exists()
        or Freizeit.objects.filter(jugendleiter=member).exists()
    )


def credential_refusal(actor, user):
    """Why ``actor`` may not take over ``user``'s sign-in, or ``None`` if they may.

    The account's Django rights as for :func:`account_refusal`, and, for anyone
    else's account, any rights it has through its member record.
    """
    refusal = account_refusal(actor, user)
    if refusal or actor.is_superuser or actor.pk == user.pk:
        return refusal
    member = getattr(user, "member", None)
    if member is not None and member_has_rights(member):
        return MEMBER_RIGHTS
    return None


def login_refusal(actor, member):
    """Why ``actor`` may not decide who signs in as ``member``, or ``None``.

    That is the member's linked account or, for a member without one, the
    account an invitation would create -- which gets the member's rights.
    """
    if member.user_id:
        return credential_refusal(actor, member.user)
    if not actor.is_superuser and member_has_rights(member):
        return MEMBER_RIGHTS
    return None


def member_change_refusal(actor, member, changes):
    """Why ``actor`` may not apply ``changes`` to ``member``, or ``None`` if they may.

    ``changes`` maps field names to new values; ``user`` is a ``User`` or
    ``None``. Unlinking frees the record for an invitation, linking hands the
    account the member's rights and its login mails, and the primary ``email``
    is where those mails go.
    """
    if actor.is_superuser:
        return None
    if "user" in changes:
        user = changes["user"]
        if (user.pk if user else None) != member.user_id:
            refusal = login_refusal(actor, member)
            if refusal:
                return refusal
            if user is not None:
                refusal = credential_refusal(actor, user)
                if refusal:
                    return refusal
                if member_has_rights(member):
                    return MEMBER_RIGHTS
    if changes.get("email", member.email) != member.email:
        return login_refusal(actor, member)
    return None
