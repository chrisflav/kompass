"""Inline-style CRUD routes for group / klettertreff / waiter related objects.

These reproduce the Django admin *inline* editing surface for objects that hang
off a parent record, so the SPA can add/list/edit/remove the parent's related
rows exactly like the admin inline does. Every write is gated on the PARENT
object's change permission (an inline is editable iff its parent is), reusing the
same predicates the admin enforces:

* ``RegistrationPassword`` (``RegistrationPasswordInline`` on ``GroupAdmin``) →
  ``members.change_group`` (``Group`` is a plain model with default perms).
* ``PermissionGroup`` (``PermissionOnGroupInline`` on ``GroupAdmin``) →
  ``members.change_group``. SENSITIVE: this is an object-level ACL — its M2M
  fields *grant* list/view/change/delete access to members and whole groups, so
  editing it hands out object permissions. It is deliberately gated on the same
  ``change_group`` permission the admin requires to open the group change view
  (only users who may change the group may edit its ACL).
* ``KlettertreffAttendee`` (``KlettertreffAttendeeInline`` on
  ``KlettertreffAdmin``) → ``members.change_klettertreff`` (plain model).
* ``InvitationToGroup`` (``InvitationToGroupAdmin`` inline on the waiting-list
  admin) is exposed read-only per waiter, gated on the object-level
  ``members.view_obj_memberwaitinglist`` permission.

Mounted at ``/api/members`` alongside the main members router. All routes here
use multi-segment paths (``/groups/{id}/...`` etc.) so they never collide with
that router's single-segment ``/{member_id}`` route.
"""

from contrib.api.perms import authorize
from contrib.api.perms import get_authorized
from contrib.api.perms import partial_clean
from django.shortcuts import get_object_or_404
from members.models import Group
from members.models import InvitationToGroup
from members.models import Klettertreff
from members.models import KlettertreffAttendee
from members.models import Member
from members.models import MemberWaitingList
from members.models import PermissionGroup
from members.models import RegistrationPassword
from ninja import ModelSchema
from ninja import Router
from ninja import Schema

from .schemas import GroupBrief
from .schemas import MemberBrief

router = Router()


# --- schemas: registration passwords --------------------------------------


class RegistrationPasswordOut(ModelSchema):
    """A group's registration password (admin ``RegistrationPasswordInline``)."""

    id: int
    group_id: int

    class Meta:
        model = RegistrationPassword
        fields = ["password"]


class RegistrationPasswordCreate(Schema):
    """Create payload for a registration password (group taken from the URL)."""

    password: str


class RegistrationPasswordUpdate(Schema):
    """Editable registration-password fields (all optional for PATCH)."""

    password: str | None = None
    group_id: int | None = None


# --- schemas: group permission ACL (SENSITIVE) ----------------------------


class PermissionGroupOut(Schema):
    """A group's object-level ACL (admin ``PermissionOnGroupInline``).

    SENSITIVE: every list exposed here is a set of grantees that the ACL confers
    list/view/change/delete access to.
    """

    id: int
    group_id: int
    list_member_ids: list[int]
    view_member_ids: list[int]
    change_member_ids: list[int]
    delete_member_ids: list[int]
    list_group_ids: list[int]
    view_group_ids: list[int]
    change_group_ids: list[int]
    delete_group_ids: list[int]

    @staticmethod
    def resolve_list_member_ids(obj) -> list[int]:
        return list(obj.list_members.values_list("id", flat=True))

    @staticmethod
    def resolve_view_member_ids(obj) -> list[int]:
        return list(obj.view_members.values_list("id", flat=True))

    @staticmethod
    def resolve_change_member_ids(obj) -> list[int]:
        return list(obj.change_members.values_list("id", flat=True))

    @staticmethod
    def resolve_delete_member_ids(obj) -> list[int]:
        return list(obj.delete_members.values_list("id", flat=True))

    @staticmethod
    def resolve_list_group_ids(obj) -> list[int]:
        return list(obj.list_groups.values_list("id", flat=True))

    @staticmethod
    def resolve_view_group_ids(obj) -> list[int]:
        return list(obj.view_groups.values_list("id", flat=True))

    @staticmethod
    def resolve_change_group_ids(obj) -> list[int]:
        return list(obj.change_groups.values_list("id", flat=True))

    @staticmethod
    def resolve_delete_group_ids(obj) -> list[int]:
        return list(obj.delete_groups.values_list("id", flat=True))


class PermissionGroupUpdate(Schema):
    """Editable ACL grantee sets (all optional; only supplied sets are applied).

    Each ``*_ids`` list replaces the corresponding M2M grantee set. SENSITIVE —
    these grant object permissions.
    """

    list_member_ids: list[int] | None = None
    view_member_ids: list[int] | None = None
    change_member_ids: list[int] | None = None
    delete_member_ids: list[int] | None = None
    list_group_ids: list[int] | None = None
    view_group_ids: list[int] | None = None
    change_group_ids: list[int] | None = None
    delete_group_ids: list[int] | None = None


# Maps the schema ``*_ids`` keys to the model's M2M attribute names.
PERMISSION_GROUP_M2M = {
    "list_member_ids": "list_members",
    "view_member_ids": "view_members",
    "change_member_ids": "change_members",
    "delete_member_ids": "delete_members",
    "list_group_ids": "list_groups",
    "view_group_ids": "view_groups",
    "change_group_ids": "change_groups",
    "delete_group_ids": "delete_groups",
}


def _apply_permission_group_m2m(permission_group, data):
    """Replace each supplied ACL grantee set on ``permission_group``."""
    for key, field in PERMISSION_GROUP_M2M.items():
        if data.get(key) is not None:
            getattr(permission_group, field).set(data[key])


# --- schemas: klettertreff attendees --------------------------------------


class KlettertreffAttendeeOut(Schema):
    """A klettertreff's attendee (admin ``KlettertreffAttendeeInline``)."""

    id: int
    klettertreff_id: int
    member: MemberBrief


class KlettertreffAttendeeCreate(Schema):
    """Add-attendee payload (klettertreff taken from the URL)."""

    member_id: int


# --- schemas: waiter invitations (read-only) ------------------------------


class WaiterInvitationOut(ModelSchema):
    """A waiter's group invitation (admin ``InvitationToGroupAdmin`` inline)."""

    id: int
    group: GroupBrief
    status: str

    class Meta:
        model = InvitationToGroup
        fields = ["date"]

    @staticmethod
    def resolve_status(obj) -> str:
        return str(obj.status())


# --- registration passwords -----------------------------------------------


@router.get(
    "/groups/{group_id}/registration-passwords",
    response=list[RegistrationPasswordOut],
)
def list_registration_passwords(request, group_id: int):
    """List a group's registration passwords (``members.view_group``)."""
    authorize(request, "members.view_group")
    group = get_object_or_404(Group, pk=group_id)
    return group.registrationpassword_set.all().order_by("id")


@router.post(
    "/groups/{group_id}/registration-passwords",
    response={201: RegistrationPasswordOut},
)
def create_registration_password(request, group_id: int, payload: RegistrationPasswordCreate):
    """Add a registration password to a group (``members.change_group``)."""
    authorize(request, "members.change_group")
    group = get_object_or_404(Group, pk=group_id)
    password = RegistrationPassword(group=group, password=payload.password)
    password.full_clean()
    password.save()
    return 201, password


@router.patch("/registration-passwords/{password_id}", response=RegistrationPasswordOut)
def update_registration_password(request, password_id: int, payload: RegistrationPasswordUpdate):
    """Update a registration password (``members.change_group``)."""
    authorize(request, "members.change_group")
    password = get_object_or_404(RegistrationPassword, pk=password_id)
    data = payload.dict(exclude_unset=True)
    changed = []
    if "password" in data:
        password.password = data["password"]
        changed.append("password")
    if "group_id" in data:
        password.group_id = data["group_id"]
        changed.append("group")
    partial_clean(password, changed)
    password.save()
    return password


@router.delete("/registration-passwords/{password_id}", response={204: None})
def delete_registration_password(request, password_id: int):
    """Delete a registration password (``members.change_group``)."""
    authorize(request, "members.change_group")
    get_object_or_404(RegistrationPassword, pk=password_id).delete()
    return 204, None


# --- group permission ACL (SENSITIVE) -------------------------------------


@router.get("/groups/{group_id}/permission-groups", response=list[PermissionGroupOut])
def list_permission_groups(request, group_id: int):
    """List a group's ACL records (0 or 1; ``members.change_group``).

    Gated on ``change_group`` (not the weaker ``view_group``): the ACL is
    sensitive, so it is only readable by users who may edit the group.
    """
    authorize(request, "members.change_group")
    group = get_object_or_404(Group, pk=group_id)
    return PermissionGroup.objects.filter(group=group).order_by("id")


@router.post(
    "/groups/{group_id}/permission-groups",
    response={201: PermissionGroupOut},
)
def create_permission_group(request, group_id: int, payload: PermissionGroupUpdate):
    """Create the group's ACL record and set its grantee sets (``members.change_group``).

    SENSITIVE: the supplied ``*_ids`` grant object permissions. ``PermissionGroup``
    has a one-to-one link to the group, so ``full_clean`` rejects a second record
    for a group that already has one (→ 422).
    """
    authorize(request, "members.change_group")
    group = get_object_or_404(Group, pk=group_id)
    permission_group = PermissionGroup(group=group)
    permission_group.full_clean()
    permission_group.save()
    _apply_permission_group_m2m(permission_group, payload.dict(exclude_unset=True))
    return 201, permission_group


@router.patch("/permission-groups/{permission_group_id}", response=PermissionGroupOut)
def update_permission_group(request, permission_group_id: int, payload: PermissionGroupUpdate):
    """Replace the supplied ACL grantee sets (``members.change_group``).

    SENSITIVE: the supplied ``*_ids`` grant object permissions.
    """
    authorize(request, "members.change_group")
    permission_group = get_object_or_404(PermissionGroup, pk=permission_group_id)
    _apply_permission_group_m2m(permission_group, payload.dict(exclude_unset=True))
    return permission_group


@router.delete("/permission-groups/{permission_group_id}", response={204: None})
def delete_permission_group(request, permission_group_id: int):
    """Delete the group's ACL record (``members.change_group``). SENSITIVE."""
    authorize(request, "members.change_group")
    get_object_or_404(PermissionGroup, pk=permission_group_id).delete()
    return 204, None


# --- klettertreff attendees -----------------------------------------------


@router.get(
    "/klettertreff/{klettertreff_id}/attendees",
    response=list[KlettertreffAttendeeOut],
)
def list_klettertreff_attendees(request, klettertreff_id: int):
    """List a klettertreff's attendees (``members.view_klettertreff``)."""
    authorize(request, "members.view_klettertreff")
    klettertreff = get_object_or_404(Klettertreff, pk=klettertreff_id)
    return klettertreff.klettertreffattendee_set.all().order_by("id")


@router.post(
    "/klettertreff/{klettertreff_id}/attendees",
    response={201: KlettertreffAttendeeOut},
)
def add_klettertreff_attendee(request, klettertreff_id: int, payload: KlettertreffAttendeeCreate):
    """Add a member as attendee of a klettertreff (``members.change_klettertreff``)."""
    authorize(request, "members.change_klettertreff")
    klettertreff = get_object_or_404(Klettertreff, pk=klettertreff_id)
    member = get_object_or_404(Member, pk=payload.member_id)
    attendee = KlettertreffAttendee(klettertreff=klettertreff, member=member)
    attendee.full_clean()
    attendee.save()
    return 201, attendee


@router.delete("/attendees/{attendee_id}", response={204: None})
def remove_klettertreff_attendee(request, attendee_id: int):
    """Remove a klettertreff attendee (``members.change_klettertreff``)."""
    authorize(request, "members.change_klettertreff")
    get_object_or_404(KlettertreffAttendee, pk=attendee_id).delete()
    return 204, None


# --- waiter invitations (read-only) ---------------------------------------


@router.get("/waiters/{waiter_id}/invitations", response=list[WaiterInvitationOut])
def list_waiter_invitations(request, waiter_id: int):
    """List a waiting-list applicant's group invitations, authorized per object.

    Read-only mirror of the admin's ``InvitationToGroup`` inline on the
    waiting-list detail; gated on the waiter's object-level
    ``members.view_obj_memberwaitinglist`` permission.
    """
    waiter = get_authorized(
        request, MemberWaitingList, waiter_id, "members.view_obj_memberwaitinglist"
    )
    return waiter.invitationtogroup_set.order_by("-pk")
