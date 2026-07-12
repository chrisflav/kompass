"""REST endpoints for the admin inlines nested under a ``Member``.

These reproduce the add / list / edit / remove behaviour of the change-view
inlines on ``MemberAdmin`` (``EmergencyContactInline``, ``MemberDocumentInline``
and ``PermissionOnMemberInline``) so the SPA can manage a member's related rows
exactly like the admin.

Permission model reuse
----------------------

An admin inline is editable iff its parent object is, so every write is gated on
the parent member's object-level change permission
(``members.change_obj_member``) — the same predicate ``MemberAdmin`` enforces.

* ``EmergencyContact`` additionally carries its own ``Meta.rules_permissions``
  (``add_obj`` / ``view_obj`` / ``change_obj`` / ``delete_obj``). The admin
  evaluates those predicates against the *parent member* (see
  ``CommonAdminInlineMixin.has_*_permission``, which passes the parent object),
  so they are re-checked here with the member as the object — respecting the
  model's own rules on top of the parent gate.
* ``MemberDocument`` is a plain ``CommonModel`` with no object-level rules, so it
  is gated purely on the parent member's change permission.
* ``PermissionMember`` is an **ACL** inline: its rows grant per-object
  permissions (``may_view`` / ``may_change`` / … over other members and groups).
  Being able to edit it is an escalation vector — a user who can change these
  rows can widen who may see/modify members — so every operation, *including
  listing*, is gated strictly on ``members.change_obj_member`` of the owning
  member (not merely ``view``), matching the sensitivity of the data it exposes.
"""

import os

from contrib.api.perms import authorize
from contrib.api.perms import get_authorized
from contrib.api.perms import partial_clean
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from members.models import EmergencyContact
from members.models import Member
from members.models import MemberDocument
from members.models import PermissionMember
from ninja import File
from ninja import ModelSchema
from ninja import Router
from ninja import Schema
from ninja.files import UploadedFile

router = Router()

# Mirror the ``RestrictedFileField`` on ``MemberDocument.f`` (max_upload_size=10
# MB) plus the content types the admin widget advertises via its ``accept``
# attribute (``application/pdf,image/jpeg,image/png``).
DOCUMENT_CONTENT_TYPES = ["application/pdf", "image/jpeg", "image/png"]
DOCUMENT_MAX_UPLOAD_SIZE_MB = 10

# (payload key -> M2M field) for the PermissionMember ACL relations.
PERMISSION_MEMBER_M2M = (
    ("list_member_ids", "list_members"),
    ("view_member_ids", "view_members"),
    ("change_member_ids", "change_members"),
    ("delete_member_ids", "delete_members"),
    ("list_group_ids", "list_groups"),
    ("view_group_ids", "view_groups"),
    ("change_group_ids", "change_groups"),
    ("delete_group_ids", "delete_groups"),
)


def _validate_document(upload):
    """Enforce the ``MemberDocument.f`` upload constraints (content type + size)."""
    if upload.content_type not in DOCUMENT_CONTENT_TYPES:
        raise ValidationError(_("Filetype not supported."))
    limit = DOCUMENT_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > limit:
        raise ValidationError(
            _("Please keep filesize under %(mb)s MiB.") % {"mb": DOCUMENT_MAX_UPLOAD_SIZE_MB}
        )


# --- schemas --------------------------------------------------------------


class MemberEmergencyContactOut(ModelSchema):
    id: int
    member_id: int

    class Meta:
        model = EmergencyContact
        fields = ["prename", "lastname", "email", "phone_number"]


class MemberEmergencyContactCreate(Schema):
    """Create payload for an emergency contact (mirrors the admin inline fields)."""

    prename: str
    lastname: str
    email: str = ""
    phone_number: str = ""


class MemberEmergencyContactUpdate(Schema):
    """PATCH payload; only supplied fields are applied and validated."""

    prename: str | None = None
    lastname: str | None = None
    email: str | None = None
    phone_number: str | None = None


class MemberInlineDocumentOut(Schema):
    """Read representation of a member's extra document."""

    id: int
    member_id: int
    filename: str
    file_url: str | None = None

    @staticmethod
    def resolve_filename(obj) -> str:
        return os.path.basename(obj.f.name) if obj.f and obj.f.name else ""

    @staticmethod
    def resolve_file_url(obj) -> str | None:
        return obj.f.url if obj.f else None


class MemberPermissionOut(Schema):
    """Read representation of a member's ACL row (``PermissionMember``).

    Exposes only the ids of the granted relations; the SPA renders them against
    the member/group selectors it already loads.
    """

    id: int
    member_id: int
    list_member_ids: list[int] = []
    view_member_ids: list[int] = []
    change_member_ids: list[int] = []
    delete_member_ids: list[int] = []
    list_group_ids: list[int] = []
    view_group_ids: list[int] = []
    change_group_ids: list[int] = []
    delete_group_ids: list[int] = []

    @staticmethod
    def resolve_list_member_ids(obj) -> list[int]:
        return [m.pk for m in obj.list_members.all()]

    @staticmethod
    def resolve_view_member_ids(obj) -> list[int]:
        return [m.pk for m in obj.view_members.all()]

    @staticmethod
    def resolve_change_member_ids(obj) -> list[int]:
        return [m.pk for m in obj.change_members.all()]

    @staticmethod
    def resolve_delete_member_ids(obj) -> list[int]:
        return [m.pk for m in obj.delete_members.all()]

    @staticmethod
    def resolve_list_group_ids(obj) -> list[int]:
        return [g.pk for g in obj.list_groups.all()]

    @staticmethod
    def resolve_view_group_ids(obj) -> list[int]:
        return [g.pk for g in obj.view_groups.all()]

    @staticmethod
    def resolve_change_group_ids(obj) -> list[int]:
        return [g.pk for g in obj.change_groups.all()]

    @staticmethod
    def resolve_delete_group_ids(obj) -> list[int]:
        return [g.pk for g in obj.delete_groups.all()]


class MemberPermissionIn(Schema):
    """Create/patch payload for a member ACL row; only supplied relations set."""

    list_member_ids: list[int] | None = None
    view_member_ids: list[int] | None = None
    change_member_ids: list[int] | None = None
    delete_member_ids: list[int] | None = None
    list_group_ids: list[int] | None = None
    view_group_ids: list[int] | None = None
    change_group_ids: list[int] | None = None
    delete_group_ids: list[int] | None = None


# --- emergency contacts ---------------------------------------------------
#
# Routes are ordered so the parent-scoped ``/{member_id}/...`` collection routes
# and the static ``/emergency-contacts/{id}`` item routes never shadow one
# another (their discriminating segment differs), and neither is a bare
# single-segment ``/{id}`` that could shadow the sibling members routes.


@router.get("/{member_id}/emergency-contacts", response=list[MemberEmergencyContactOut])
def list_emergency_contacts(request, member_id: int):
    """List a member's emergency contacts (parent ``view`` + model ``view_obj``)."""
    member = get_authorized(request, Member, member_id, "members.view_obj_member")
    authorize(request, "members.view_obj_emergencycontact", member)
    return member.emergencycontact_set.all().order_by("pk")


@router.post("/{member_id}/emergency-contacts", response={201: MemberEmergencyContactOut})
def create_emergency_contact(request, member_id: int, payload: MemberEmergencyContactCreate):
    """Add an emergency contact to a member (parent ``change`` + model ``add_obj``)."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    authorize(request, "members.add_obj_emergencycontact", member)
    data = payload.dict()
    contact = EmergencyContact(member=member, **data)
    # Validate only the fields actually provided (+ member). full_clean() would
    # otherwise reject the inherited confirm_mail_key (default="" but blank=False,
    # a field the admin inline form never exposes).
    partial_clean(contact, [*data.keys(), "member"])
    contact.save()
    return 201, contact


@router.patch("/emergency-contacts/{contact_id}", response=MemberEmergencyContactOut)
def update_emergency_contact(request, contact_id: int, payload: MemberEmergencyContactUpdate):
    """Edit an emergency contact (parent ``change`` + model ``change_obj``)."""
    contact = get_object_or_404(EmergencyContact, pk=contact_id)
    authorize(request, "members.change_obj_member", contact.member)
    authorize(request, "members.change_obj_emergencycontact", contact.member)
    data = payload.dict(exclude_unset=True)
    for field, value in data.items():
        setattr(contact, field, value)
    partial_clean(contact, list(data.keys()))
    contact.save()
    return contact


@router.delete("/emergency-contacts/{contact_id}", response={204: None})
def delete_emergency_contact(request, contact_id: int):
    """Remove an emergency contact (parent ``change`` + model ``delete_obj``)."""
    contact = get_object_or_404(EmergencyContact, pk=contact_id)
    authorize(request, "members.change_obj_member", contact.member)
    authorize(request, "members.delete_obj_emergencycontact", contact.member)
    contact.delete()
    return 204, None


# --- member documents -----------------------------------------------------
#
# The item route uses ``/member-documents/{id}`` (not ``/documents/{id}``) so it
# never overlaps the reserved ``/members/documents`` router prefix mounted
# alongside this one.


@router.get("/{member_id}/documents", response=list[MemberInlineDocumentOut])
def list_member_documents(request, member_id: int):
    """List a member's extra documents (gated on the parent member's ``view``)."""
    member = get_authorized(request, Member, member_id, "members.view_obj_member")
    return member.memberdocument_set.all().order_by("pk")


@router.post("/{member_id}/documents", response={201: MemberInlineDocumentOut})
def create_member_document(request, member_id: int, f: UploadedFile = File(...)):
    """Upload an extra document to a member (multipart; parent ``change`` gate)."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    _validate_document(f)
    document = MemberDocument(member=member, f=f)
    # The upload constraints are enforced by ``_validate_document`` above:
    # ``RestrictedFileField.clean`` compares the size against ``max_upload_size``
    # as raw *bytes* (while its own validator treats it as MB), so running it via
    # ``full_clean`` would reject any real file. Validate the rest of the model
    # but skip that field's buggy ``clean``.
    document.full_clean(exclude=["f"])
    document.save()
    return 201, document


@router.delete("/member-documents/{document_id}", response={204: None})
def delete_member_document(request, document_id: int):
    """Delete a member's extra document (gated on the parent member's ``change``)."""
    document = get_object_or_404(MemberDocument, pk=document_id)
    authorize(request, "members.change_obj_member", document.member)
    document.delete()
    return 204, None


# --- registration form (Member.registration_form file) --------------------

REGISTRATION_FORM_CONTENT_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/gif"]
REGISTRATION_FORM_MAX_MB = 5


class MemberRegistrationFormOut(Schema):
    """The member's registration-form file url after upload/clear."""

    registration_form: str | None = None


@router.post("/{member_id}/registration-form", response=MemberRegistrationFormOut)
def upload_registration_form(request, member_id: int, f: UploadedFile = File(...)):
    """Upload/replace a member's registration form (multipart; parent ``change`` gate)."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    if f.content_type not in REGISTRATION_FORM_CONTENT_TYPES:
        raise ValidationError(_("Filetype not supported."))
    if f.size > REGISTRATION_FORM_MAX_MB * 1024 * 1024:
        raise ValidationError(
            _("Please keep filesize under %(mb)s MiB.") % {"mb": REGISTRATION_FORM_MAX_MB}
        )
    member.registration_form = f
    member.save()
    return {"registration_form": member.registration_form.url if member.registration_form else None}


@router.delete("/{member_id}/registration-form", response=MemberRegistrationFormOut)
def clear_registration_form(request, member_id: int):
    """Remove a member's registration form (parent ``change`` gate)."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    member.registration_form = None
    member.save()
    return {"registration_form": None}


# --- permission (ACL) rows ------------------------------------------------
#
# SENSITIVE: these grant object permissions. Every operation is gated on the
# owning member's ``change_obj_member`` (escalation guard). The item route uses
# ``/permission-members/{id}`` so it does not shadow the collection routes.


def _apply_permission_m2m(permission, data):
    """Set only the ACL relations present in ``data`` (ids -> M2M ``.set``)."""
    for payload_key, field_name in PERMISSION_MEMBER_M2M:
        if data.get(payload_key) is not None:
            getattr(permission, field_name).set(data[payload_key])


@router.get("/{member_id}/permission-members", response=list[MemberPermissionOut])
def list_permission_members(request, member_id: int):
    """List a member's ACL row(s) (SENSITIVE → gated on parent ``change``)."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    return PermissionMember.objects.filter(member=member).order_by("pk")


@router.post("/{member_id}/permission-members", response={201: MemberPermissionOut})
def create_permission_member(request, member_id: int, payload: MemberPermissionIn):
    """Create a member's ACL row (SENSITIVE → gated on parent ``change``).

    ``PermissionMember`` is a ``OneToOneField`` to the member, so ``full_clean``
    rejects a second row for the same member (→ 422).
    """
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    permission = PermissionMember(member=member)
    permission.full_clean()
    permission.save()
    _apply_permission_m2m(permission, payload.dict(exclude_unset=True))
    return 201, permission


@router.patch("/permission-members/{permission_id}", response=MemberPermissionOut)
def update_permission_member(request, permission_id: int, payload: MemberPermissionIn):
    """Edit a member's ACL row (SENSITIVE → gated on parent ``change``)."""
    permission = get_object_or_404(PermissionMember, pk=permission_id)
    authorize(request, "members.change_obj_member", permission.member)
    _apply_permission_m2m(permission, payload.dict(exclude_unset=True))
    return permission


@router.delete("/permission-members/{permission_id}", response={204: None})
def delete_permission_member(request, permission_id: int):
    """Delete a member's ACL row (SENSITIVE → gated on parent ``change``)."""
    permission = get_object_or_404(PermissionMember, pk=permission_id)
    authorize(request, "members.change_obj_member", permission.member)
    permission.delete()
    return 204, None
