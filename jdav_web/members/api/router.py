"""Members API routes."""

from contrib.api.perms import authorize
from contrib.api.perms import get_authorized
from contrib.api.perms import partial_clean
from contrib.api.perms import set_scalar_fields
from contrib.permissions import scope_queryset
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from members.models import ActivityCategory
from members.models import annotate_activity_score
from members.models import Freizeit
from members.models import Group
from members.models import Klettertreff
from members.models import Member
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberUnconfirmedProxy
from members.models import MemberWaitingList
from members.models import TrainingCategory
from ninja import Router

from .schemas import ActivityCategoryOut
from .schemas import ActivityCategoryUpdate
from .schemas import AuthUserBrief
from .schemas import EXCURSION_APPROVAL_FIELDS
from .schemas import EXCURSION_UPDATE_SCALAR_FIELDS
from .schemas import ExcursionBrief
from .schemas import ExcursionCreate
from .schemas import ExcursionOut
from .schemas import ExcursionUpdate
from .schemas import GROUP_UPDATE_SCALAR_FIELDS
from .schemas import GroupCreate
from .schemas import GroupOut
from .schemas import GroupUpdate
from .schemas import KlettertreffBrief
from .schemas import KlettertreffCreate
from .schemas import KlettertreffOut
from .schemas import KlettertreffUpdate
from .schemas import MEMBER_ORGANIZATIONAL_FIELDS
from .schemas import MEMBER_UPDATE_SCALAR_FIELDS
from .schemas import MemberBrief
from .schemas import MemberCreate
from .schemas import MemberEnumChoice
from .schemas import MemberNoteListBrief
from .schemas import MemberNoteListCreate
from .schemas import MemberNoteListOut
from .schemas import MemberNoteListUpdate
from .schemas import MemberOut
from .schemas import MemberTrainingCreate
from .schemas import MemberTrainingUpdate
from .schemas import MemberUpdate
from .schemas import MeOut
from .schemas import RegistrationBrief
from .schemas import TrainingBrief
from .schemas import TrainingCategoryOut
from .schemas import TrainingCategoryUpdate
from .schemas import TrainingOut
from .schemas import WaiterBrief
from .schemas import WaiterInviteIn
from .schemas import WaiterOut
from .schemas import WaiterUpdate

router = Router()


def _create_instance(model, scalars, fk_ids=None, m2m=None):
    """Build, validate and save ``model`` from a create payload.

    ``scalars`` maps field name → value (only the fields the client supplied),
    ``fk_ids`` maps FK field name → id (or ``None`` to leave unset), and ``m2m``
    maps M2M accessor → list of ids, applied after ``save()``. Only the supplied
    scalar/FK fields are validated (via :func:`partial_clean`), so unrelated
    ``default="" blank=False`` fields don't spuriously fail like they would under
    a full ``full_clean``.
    """
    instance = model()
    changed = []
    for name, value in scalars.items():
        setattr(instance, name, value)
        changed.append(name)
    for name, value in (fk_ids or {}).items():
        setattr(instance, f"{name}_id", value)
        changed.append(name)
    partial_clean(instance, changed)
    instance.save()
    # Reload so callable defaults are normalised to their stored form before the
    # response schema serialises them (e.g. a ``DateField`` whose default is
    # ``datetime.today`` holds a ``datetime`` in memory until re-read as a date).
    instance.refresh_from_db()
    for accessor, ids in (m2m or {}).items():
        getattr(instance, accessor).set(ids)
    return instance


def _apply_member_update(request, member, payload):
    """Apply a ``MemberUpdate`` payload with the admin's per-field permissions.

    Shared by the member and the unconfirmed-registration change endpoints;
    the caller has already resolved and authorized the object.
    """
    data = payload.dict(exclude_unset=True)
    if "group_ids" in data:
        authorize(request, "members.may_change_member_group")
    if "user_id" in data:
        authorize(request, "members.may_set_auth_user")
    if any(field in data for field in MEMBER_ORGANIZATIONAL_FIELDS):
        authorize(request, "members.may_change_organizationals")
    changed = set_scalar_fields(
        member, data, MEMBER_UPDATE_SCALAR_FIELDS + MEMBER_ORGANIZATIONAL_FIELDS
    )
    if "user_id" in data:
        member.user_id = data["user_id"]
        changed.append("user")
    partial_clean(member, changed)
    member.save()
    if data.get("group_ids") is not None:
        member.group.set(data["group_ids"])
    return member


# --- groups ---------------------------------------------------------------


@router.get("/groups", response=list[GroupOut])
def list_groups(request):
    """Groups the user may view, scoped like ``list_registrations``.

    Holders of ``members.view_group`` see every group. Everyone else sees the
    groups they lead (``member.leited_groups``): a Jugendleiter needs their own
    groups without holding the site-wide permission, since the dashboard's
    "Meine Gruppen" panel and the group pickers are built from this list. A
    plain 403 here surfaced as "Du leitest aktuell keine Gruppe." rather than as
    an error. Callers without a linked member see nothing.
    """
    queryset = Group.objects.all().order_by("name")
    if request.user.has_perm("members.view_group"):
        return queryset
    member = getattr(request.user, "member", None)
    if member is None:
        return Group.objects.none()
    return queryset.filter(pk__in=member.leited_groups.values("pk"))


@router.post("/groups", response={201: GroupOut})
def create_group(request, payload: GroupCreate):
    """Create a group (``members.add_group``; matches ``GroupAdmin``)."""
    authorize(request, "members.add_group")
    data = payload.dict(exclude_unset=True)
    leiter_ids = data.pop("leiter_ids", [])
    contact_email_id = data.pop("contact_email_id", None)
    group = _create_instance(
        Group,
        data,
        fk_ids={"contact_email": contact_email_id},
        m2m={"leiters": leiter_ids},
    )
    return 201, group


@router.get("/groups/{group_id}", response=GroupOut)
def retrieve_group(request, group_id: int):
    """Full group detail (plain Django ``members.view_group`` perm).

    ``GroupAdmin`` is a plain ``admin.ModelAdmin``, so it uses the default
    Django ``view_group`` permission checked globally.
    """
    authorize(request, "members.view_group")
    return get_object_or_404(Group, pk=group_id)


@router.patch("/groups/{group_id}", response=GroupOut)
def update_group(request, group_id: int, payload: GroupUpdate):
    """Update the editable change-view fields of a group (``members.change_group``).

    Scalar fields are validated with ``full_clean`` (→ 422 on error). ``leiters``
    (M2M) and ``contact_email`` (FK) are applied by id.
    """
    authorize(request, "members.change_group")
    group = get_object_or_404(Group, pk=group_id)
    data = payload.dict(exclude_unset=True)
    changed = set_scalar_fields(group, data, GROUP_UPDATE_SCALAR_FIELDS)
    if "contact_email_id" in data:
        group.contact_email_id = data["contact_email_id"]
        changed.append("contact_email")
    partial_clean(group, changed)
    group.save()
    if "leiter_ids" in data and data["leiter_ids"] is not None:
        group.leiters.set(data["leiter_ids"])
    return group


@router.delete("/groups/{group_id}", response={204: None})
def delete_group(request, group_id: int):
    """Delete a group (``members.delete_group``; matches ``GroupAdmin``)."""
    authorize(request, "members.delete_group")
    get_object_or_404(Group, pk=group_id).delete()
    return 204, None


# --- excursions -----------------------------------------------------------


@router.get("/excursions", response=list[ExcursionBrief])
def list_excursions(request):
    """Excursions the user may list (led groups / own leadership)."""
    # Prefetch the relations the Brief resolves (groups + participants) so the
    # list doesn't fan out into per-row queries for the filter data.
    qs = (
        Freizeit.objects.all()
        .order_by("-date")
        .prefetch_related("groups", "jugendleiter", "membersonlist")
    )
    return scope_queryset(request.user, qs, model=Freizeit)


@router.post("/excursions", response={201: ExcursionOut})
def create_excursion(request, payload: ExcursionCreate):
    """Create an excursion (``members.add_global_freizeit``; matches ``FreizeitAdmin``).

    Approval fields are not settable here (they mirror the admin's
    permission-gated Approval fieldset, edited afterwards).
    """
    authorize(request, "members.add_global_freizeit")
    data = payload.dict(exclude_unset=True)
    group_ids = data.pop("group_ids", [])
    jugendleiter_ids = data.pop("jugendleiter_ids", [])
    activity_ids = data.pop("activity_ids", [])
    excursion = _create_instance(
        Freizeit,
        data,
        m2m={"groups": group_ids, "jugendleiter": jugendleiter_ids, "activity": activity_ids},
    )
    return 201, excursion


@router.get("/excursions/{excursion_id}", response=ExcursionOut)
def retrieve_excursion(request, excursion_id: int):
    """Full excursion detail with computed figures, authorized per object."""
    return get_authorized(request, Freizeit, excursion_id, "members.view_obj_freizeit")


@router.patch("/excursions/{excursion_id}", response=ExcursionOut)
def update_excursion(request, excursion_id: int, payload: ExcursionUpdate):
    """Update the editable change-view fields of an excursion, authorized per object.

    The base fields are gated on ``members.change_obj_freizeit`` (leader / global).
    The Approval fieldset (``approved``, ``approval_comments``,
    ``approved_extra_youth_leader_count``) is additionally gated on
    ``members.manage_approval_excursion``; supplying any approval field without
    that permission raises 403. Scalars are validated with ``full_clean``.
    """
    excursion = get_authorized(request, Freizeit, excursion_id, "members.change_obj_freizeit")
    data = payload.dict(exclude_unset=True)
    if any(field in data for field in EXCURSION_APPROVAL_FIELDS):
        authorize(request, "members.manage_approval_excursion")
    changed = set_scalar_fields(
        excursion, data, EXCURSION_UPDATE_SCALAR_FIELDS + EXCURSION_APPROVAL_FIELDS
    )
    partial_clean(excursion, changed)
    excursion.save()
    if data.get("group_ids") is not None:
        excursion.groups.set(data["group_ids"])
    if data.get("jugendleiter_ids") is not None:
        excursion.jugendleiter.set(data["jugendleiter_ids"])
    if data.get("activity_ids") is not None:
        excursion.activity.set(data["activity_ids"])
    return excursion


@router.delete("/excursions/{excursion_id}", response={204: None})
def delete_excursion(request, excursion_id: int):
    """Delete an excursion, authorized per object (``delete_obj_freizeit``)."""
    excursion = get_authorized(request, Freizeit, excursion_id, "members.delete_obj_freizeit")
    excursion.delete()
    return 204, None


# --- members --------------------------------------------------------------


@router.get("/", response=list[MemberBrief])
def list_members(request):
    """Members the user may list, scoped by the shared permission filter.

    Returns the brief identity representation only; full detail is available
    via the retrieve endpoint, which is gated on ``view_obj_member``. The
    queryset is annotated with ``_activity_score`` so the brief can expose the
    admin's activity column value.
    """
    queryset = annotate_activity_score(Member.objects.all()).order_by("lastname")
    return scope_queryset(request.user, queryset, model=Member)


@router.post("/", response={201: MemberOut})
def create_member(request, payload: MemberCreate):
    """Create a member (``members.add_global_member``; matches ``MemberAdmin``).

    Collects the admin add form's required subset (name, gender, email, groups);
    the remaining fields default per the model and are edited afterwards.
    """
    authorize(request, "members.add_global_member")
    data = payload.dict(exclude_unset=True)
    group_ids = data.pop("group_ids", [])
    member = _create_instance(Member, data, m2m={"group": group_ids})
    return 201, member


@router.get("/registrations", response=list[RegistrationBrief])
def list_registrations(request):
    """Unconfirmed registrations, scoped exactly like ``MemberUnconfirmedAdmin``.

    Holders of ``members.may_manage_all_registrations`` see every registration;
    otherwise the list is restricted to registrations in the caller's led
    groups (``member.leited_groups``), and callers without a linked member see
    nothing. This replaces the SPA's previous client-side ``confirmed === false``
    filter over ``GET /api/members/`` (which bypassed server-side scoping).
    """
    queryset = MemberUnconfirmedProxy.objects.all().order_by("lastname")
    if request.user.has_perm("members.may_manage_all_registrations"):
        return queryset
    member = getattr(request.user, "member", None)
    if member is None:
        return MemberUnconfirmedProxy.objects.none()
    return queryset.filter(group__in=member.leited_groups.all()).distinct()


@router.get("/registrations/{registration_id}", response=MemberOut)
def retrieve_registration(request, registration_id: int):
    """Full detail of an unconfirmed registration, authorized per object.

    Fetched via ``MemberUnconfirmedProxy`` (which the default ``Member.objects``
    manager excludes, since it filters ``confirmed=True``) so clicking an
    unconfirmed registration no longer 404s. Gated on the proxy's view rule
    (``view_obj_memberunconfirmedproxy`` = may_view | may_manage_all_registrations).
    """
    return get_authorized(
        request,
        MemberUnconfirmedProxy,
        registration_id,
        "members.view_obj_memberunconfirmedproxy",
    )


@router.patch("/registrations/{registration_id}", response=MemberOut)
def update_registration(request, registration_id: int, payload: MemberUpdate):
    """Update an unconfirmed registration (``MemberUnconfirmedAdmin``'s change form).

    Same field handling as :func:`update_member`, but resolved through
    ``MemberUnconfirmedProxy`` (the default manager filters ``confirmed=True``)
    and gated on the proxy's ``change_obj`` rule.
    """
    registration = get_authorized(
        request,
        MemberUnconfirmedProxy,
        registration_id,
        "members.change_obj_memberunconfirmedproxy",
    )
    return _apply_member_update(request, registration, payload)


@router.delete("/registrations/{registration_id}", response={204: None})
def delete_registration(request, registration_id: int):
    """Delete an unconfirmed registration, authorized per object."""
    registration = get_authorized(
        request,
        MemberUnconfirmedProxy,
        registration_id,
        "members.delete_obj_memberunconfirmedproxy",
    )
    registration.delete()
    return 204, None


@router.get("/me", response=MeOut)
def retrieve_me(request):
    """The authenticated user's own identity (name + linked member, if any).

    Any authenticated user may read their own identity — no object permission is
    involved. Declared before the greedy single-segment ``/{member_id}`` route so
    it is matched first. ``member_id`` is null when the account has no linked
    ``Member`` (e.g. a pure administrator login).
    """
    user = request.user
    member = getattr(user, "member", None)
    return {
        "user_id": user.pk,
        "username": user.get_username(),
        "name": member.name if member is not None else user.get_username(),
        "member_id": member.pk if member is not None else None,
        "is_staff": bool(getattr(user, "is_staff", False)),
        "is_superuser": bool(getattr(user, "is_superuser", False)),
        # A superuser holds every permission, so sending the full list would be
        # ~300 strings the client would never consult — `is_superuser` already
        # short-circuits its checks.
        "permissions": [] if user.is_superuser else sorted(user.get_all_permissions()),
    }


# NOTE: the single-segment ``/{member_id}`` GET/PATCH routes are declared at the
# END of this module. django-ninja resolves ``{member_id}`` with a string
# converter (validating the ``int`` via pydantic), so it greedily captures any
# single path segment — declaring it here would shadow the static single-segment
# routes below (``/trainings``, ``/waiters``, ``/klettertreff``, ``/note-lists``)
# and make them return 422. Static routes must be registered first.


# --- trainings ------------------------------------------------------------


@router.get("/trainings", response=list[TrainingBrief])
def list_trainings(request):
    """Trainings the user may list, scoped by the shared permission filter."""
    return scope_queryset(
        request.user, MemberTraining.objects.all().order_by("-date"), model=MemberTraining
    )


@router.post("/trainings", response={201: TrainingOut})
def create_training(request, payload: MemberTrainingCreate):
    """Create a training record (``members.add_global_membertraining``)."""
    authorize(request, "members.add_global_membertraining")
    data = payload.dict(exclude_unset=True)
    member_id = data.pop("member_id")
    category_id = data.pop("category_id")
    activity_ids = data.pop("activity_ids", [])
    training = _create_instance(
        MemberTraining,
        data,
        fk_ids={"member": member_id, "category": category_id},
        m2m={"activity": activity_ids},
    )
    return 201, training


@router.get("/trainings/{training_id}", response=TrainingOut)
def retrieve_training(request, training_id: int):
    """Full training detail, authorized per object.

    ``MemberTraining``'s rules_permissions are evaluated against the owning
    ``Member`` (the model is used as an admin inline, so the parent member — not
    the training — is passed to the predicate), so authorize against
    ``training.member``.
    """
    training = get_object_or_404(MemberTraining, pk=training_id)
    authorize(request, "members.view_obj_membertraining", training.member)
    return training


@router.patch("/trainings/{training_id}", response=TrainingOut)
def update_training(request, training_id: int, payload: MemberTrainingUpdate):
    """Update the editable subset of a training, authorized per owning member.

    Like :func:`retrieve_training`, ``MemberTraining``'s rules_permissions are
    evaluated against the owning ``Member``, so authorize ``change`` against
    ``training.member``.
    """
    training = get_object_or_404(MemberTraining, pk=training_id)
    authorize(request, "members.change_obj_membertraining", training.member)
    data = payload.dict(exclude_unset=True)
    changed = set_scalar_fields(
        training, data, ("title", "comments", "participated", "passed", "date")
    )
    if "member_id" in data:
        training.member_id = data["member_id"]
        changed.append("member")
    if "category_id" in data:
        training.category_id = data["category_id"]
        changed.append("category")
    partial_clean(training, changed)
    training.save()
    if data.get("activity_ids") is not None:
        training.activity.set(data["activity_ids"])
    return training


@router.delete("/trainings/{training_id}", response={204: None})
def delete_training(request, training_id: int):
    """Delete a training, authorized against its owning member.

    Like retrieve/update, ``MemberTraining``'s rules_permissions are evaluated
    against the parent ``Member`` (the model is used as an admin inline).
    """
    training = get_object_or_404(MemberTraining, pk=training_id)
    authorize(request, "members.delete_obj_membertraining", training.member)
    training.delete()
    return 204, None


# --- klettertreff ---------------------------------------------------------


@router.get("/klettertreff", response=list[KlettertreffBrief])
def list_klettertreff(request):
    """Klettertreff events the user may view.

    ``KlettertreffAdmin`` is a plain ``admin.ModelAdmin``, so it uses the
    default Django ``view_klettertreff`` permission checked globally.
    """
    authorize(request, "members.view_klettertreff")
    return Klettertreff.objects.all().order_by("-date")


@router.post("/klettertreff", response={201: KlettertreffOut})
def create_klettertreff(request, payload: KlettertreffCreate):
    """Create a Klettertreff event (``members.add_klettertreff``)."""
    authorize(request, "members.add_klettertreff")
    data = payload.dict(exclude_unset=True)
    group_id = data.pop("group_id")
    jugendleiter_ids = data.pop("jugendleiter_ids", [])
    klettertreff = _create_instance(
        Klettertreff,
        data,
        fk_ids={"group": group_id},
        m2m={"jugendleiter": jugendleiter_ids},
    )
    return 201, klettertreff


@router.get("/klettertreff/{klettertreff_id}", response=KlettertreffOut)
def retrieve_klettertreff(request, klettertreff_id: int):
    """Full Klettertreff detail (plain Django ``members.view_klettertreff`` perm)."""
    authorize(request, "members.view_klettertreff")
    return get_object_or_404(Klettertreff, pk=klettertreff_id)


@router.patch("/klettertreff/{klettertreff_id}", response=KlettertreffOut)
def update_klettertreff(request, klettertreff_id: int, payload: KlettertreffUpdate):
    """Update the editable Klettertreff fields (plain ``members.change_klettertreff``).

    ``group`` (FK) and ``jugendleiter`` (M2M) are applied by id; scalars are
    validated with ``full_clean`` (→ 422 on error).
    """
    authorize(request, "members.change_klettertreff")
    klettertreff = get_object_or_404(Klettertreff, pk=klettertreff_id)
    data = payload.dict(exclude_unset=True)
    changed = set_scalar_fields(klettertreff, data, ("date", "location", "topic"))
    if "group_id" in data:
        klettertreff.group_id = data["group_id"]
        changed.append("group")
    partial_clean(klettertreff, changed)
    klettertreff.save()
    if data.get("jugendleiter_ids") is not None:
        klettertreff.jugendleiter.set(data["jugendleiter_ids"])
    return klettertreff


@router.delete("/klettertreff/{klettertreff_id}", response={204: None})
def delete_klettertreff(request, klettertreff_id: int):
    """Delete a Klettertreff (``members.delete_klettertreff``)."""
    authorize(request, "members.delete_klettertreff")
    get_object_or_404(Klettertreff, pk=klettertreff_id).delete()
    return 204, None


# --- note lists -----------------------------------------------------------


@router.get("/note-lists", response=list[MemberNoteListBrief])
def list_note_lists(request):
    """Member note lists the user may view.

    ``MemberNoteListAdmin`` is a plain ``admin.ModelAdmin``, so it uses the
    default Django ``view_membernotelist`` permission checked globally.
    """
    authorize(request, "members.view_membernotelist")
    return MemberNoteList.objects.all().order_by("-date")


@router.post("/note-lists", response={201: MemberNoteListOut})
def create_note_list(request, payload: MemberNoteListCreate):
    """Create a member note list (``members.add_membernotelist``)."""
    authorize(request, "members.add_membernotelist")
    data = payload.dict(exclude_unset=True)
    note_list = _create_instance(MemberNoteList, data)
    return 201, note_list


@router.get("/note-lists/{notelist_id}", response=MemberNoteListOut)
def retrieve_note_list(request, notelist_id: int):
    """Full member note-list detail (plain ``members.view_membernotelist`` perm)."""
    authorize(request, "members.view_membernotelist")
    return get_object_or_404(MemberNoteList, pk=notelist_id)


@router.patch("/note-lists/{notelist_id}", response=MemberNoteListOut)
def update_note_list(request, notelist_id: int, payload: MemberNoteListUpdate):
    """Update a member note list's title/date (plain ``members.change_membernotelist``)."""
    authorize(request, "members.change_membernotelist")
    notelist = get_object_or_404(MemberNoteList, pk=notelist_id)
    data = payload.dict(exclude_unset=True)
    changed = set_scalar_fields(notelist, data, ("title", "date"))
    partial_clean(notelist, changed)
    notelist.save()
    return notelist


@router.delete("/note-lists/{notelist_id}", response={204: None})
def delete_note_list(request, notelist_id: int):
    """Delete a note list (``members.delete_membernotelist``)."""
    authorize(request, "members.delete_membernotelist")
    get_object_or_404(MemberNoteList, pk=notelist_id).delete()
    return 204, None


# --- waiting list ---------------------------------------------------------


@router.get("/waiters", response=list[WaiterBrief])
def list_waiters(request):
    """Waiting-list applicants the user may list (leader of a relevant invitation)."""
    return scope_queryset(
        request.user,
        MemberWaitingList.objects.all().order_by("application_date"),
        model=MemberWaitingList,
    )


@router.get("/waiters/{waiter_id}", response=WaiterOut)
def retrieve_waiter(request, waiter_id: int):
    """Full waiting-list applicant detail, authorized per object."""
    return get_authorized(
        request, MemberWaitingList, waiter_id, "members.view_obj_memberwaitinglist"
    )


@router.patch("/waiters/{waiter_id}", response=WaiterOut)
def update_waiter(request, waiter_id: int, payload: WaiterUpdate):
    """Update the editable fields of a waiting-list applicant, authorized per object.

    ``MemberWaitingList``'s ``change_obj`` resolves to the global
    ``members.change_global_memberwaitinglist`` permission. Fields are validated
    with ``full_clean`` (→ 422 on error).
    """
    waiter = get_authorized(
        request, MemberWaitingList, waiter_id, "members.change_obj_memberwaitinglist"
    )
    data = payload.dict(exclude_unset=True)
    changed = set_scalar_fields(waiter, data, list(data.keys()))
    partial_clean(waiter, changed)
    waiter.save()
    return waiter


@router.post("/waiters/{waiter_id}/invite", response=WaiterOut)
def invite_waiter_to_group(request, waiter_id: int, payload: WaiterInviteIn):
    """Invite a waiting-list applicant to a group.

    Mirrors ``MemberWaitingListAdmin.invite_view`` (the "Invite to group" extra
    button): gated on the global ``members.change_global_memberwaitinglist``
    permission, requires the target group to have a contact email, and delegates
    to the authoritative ``MemberWaitingList.invite_to_group`` model method
    (which creates the ``InvitationToGroup`` and sends the invitation mail using
    the group's default text template).

    Like the admin's two-step form, an optional ``text`` overrides the group's
    default invitation template (``group.get_invitation_text_template()``, which
    is what the SPA prefills the editable text with); when omitted, the model
    falls back to that default.
    """
    authorize(request, "members.change_global_memberwaitinglist")
    waiter = get_object_or_404(MemberWaitingList, pk=waiter_id)
    group = get_object_or_404(Group, pk=payload.group_id)
    if not group.contact_email:
        raise ValidationError(
            _(
                "The selected group does not have a contact email. Please first set a "
                "contact email and then try again."
            )
        )
    creator = request.user.member if hasattr(request.user, "member") else None
    waiter.invite_to_group(group, text_template=payload.text or None, creator=creator)
    return waiter


@router.post("/waiters/{waiter_id}/request-wait-confirmation", response=WaiterOut)
def request_wait_confirmation(request, waiter_id: int):
    """Ask an applicant to confirm they still want to wait.

    Mirrors ``MemberWaitingListAdmin.ask_for_wait_confirmation``: generates a
    fresh confirmation key and sends the reminder mail (which also carries the
    "leave the waiting list" link).
    """
    authorize(request, "members.change_global_memberwaitinglist")
    waiter = get_object_or_404(MemberWaitingList, pk=waiter_id)
    waiter.generate_wait_confirmation_key()
    waiter.ask_for_wait_confirmation()
    waiter.refresh_from_db()
    return waiter


@router.post("/waiters/{waiter_id}/request-mail-confirmation", response=WaiterOut)
def request_waiter_mail_confirmation(request, waiter_id: int, rerequest: bool = True):
    """Ask an applicant to confirm their e-mail address.

    Mirrors ``MemberWaitingListAdmin.request_mail_confirmation`` (``rerequest``
    true) and ``request_required_mail_confirmation`` (``rerequest`` false, which
    only mails addresses that are still unconfirmed).
    """
    authorize(request, "members.change_global_memberwaitinglist")
    waiter = get_object_or_404(MemberWaitingList, pk=waiter_id)
    waiter.request_mail_confirmation(rerequest=rerequest)
    waiter.refresh_from_db()
    return waiter


@router.delete("/waiters/{waiter_id}", response={204: None})
def delete_waiter(request, waiter_id: int):
    """Remove an applicant from the waiting list, authorized per object."""
    waiter = get_authorized(
        request, MemberWaitingList, waiter_id, "members.delete_obj_memberwaitinglist"
    )
    waiter.delete()
    return 204, None


# --- member workflow actions ---------------------------------------------
#
# These mirror the custom admin actions (``members/admin.py``). Each reuses the
# authoritative model method and the same object-level permission the admin
# enforces, so the API cannot bypass any workflow guard. Actions on *confirmed*
# members are gated on ``change_obj_member``; actions that manage *unconfirmed*
# registrations are gated on ``change_obj_memberunconfirmedproxy`` (the proxy
# permission the admin's registration views use, which additionally admits
# holders of ``may_manage_all_registrations``).


@router.post("/{member_id}/request-echo", response=MemberOut)
def request_echo(request, member_id: int):
    """Send an echo (address-confirmation) request to the member.

    Mirrors ``MemberAdmin.request_echo``: the member must receive the newsletter
    and have a birth date (both mandatory for the echo mail).
    """
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    if not member.gets_newsletter:
        raise ValidationError(_("Member does not receive the newsletter."))
    if not member.birth_date:
        raise ValidationError(
            _("Member has no birth date set, which is mandatory for echo requests.")
        )
    member.request_echo()
    return member


@router.post("/{member_id}/invite-as-user", response=MemberOut)
def invite_as_user(request, member_id: int):
    """Invite the member to create Kompass login data.

    Gated on the global ``may_invite_as_user`` permission (the admin action's
    ``allowed_permissions``). Fails if the member has no internal email address
    or already has a linked account.
    """
    authorize(request, "members.may_invite_as_user")
    member = get_object_or_404(Member, pk=member_id)
    if not member.invite_as_user():
        raise ValidationError(_("Member has no internal email address or is already registered."))
    return member


@router.post("/{member_id}/request-password-reset", response=MemberOut)
def request_password_reset(request, member_id: int):
    """Send a password-reset mail to a member who already has login data."""
    authorize(request, "members.may_invite_as_user")
    member = get_object_or_404(Member, pk=member_id)
    if not member.request_password_reset():
        raise ValidationError(_("Member has no linked account or no internal email address."))
    return member


@router.post("/{member_id}/unconfirm", response=MemberOut)
def unconfirm(request, member_id: int):
    """Revoke a member's confirmed status."""
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    member.unconfirm()
    return member


@router.post("/{member_id}/confirm", response=MemberOut)
def confirm(request, member_id: int):
    """Confirm an unconfirmed registration.

    Fails while any of the member's email addresses is still unconfirmed, just
    like ``MemberUnconfirmedAdmin.confirm``.
    """
    member = get_authorized(
        request,
        MemberUnconfirmedProxy,
        member_id,
        "members.change_obj_memberunconfirmedproxy",
    )
    if not member.confirm():
        raise ValidationError(_("Member has unconfirmed email addresses."))
    return member


@router.post("/{member_id}/request-mail-confirmation", response=MemberOut)
def request_mail_confirmation(request, member_id: int, rerequest: bool = True):
    """Ask an unconfirmed registration to confirm its email address(es).

    With ``rerequest=false`` only addresses that were never asked are contacted
    (the admin's "re-request missing confirmations" variant).
    """
    member = get_authorized(
        request,
        MemberUnconfirmedProxy,
        member_id,
        "members.change_obj_memberunconfirmedproxy",
    )
    member.request_mail_confirmation(rerequest=rerequest)
    return member


@router.post("/{member_id}/request-registration-form", response=MemberOut)
def request_registration_form(request, member_id: int):
    """Ask a member to (re-)upload their signed registration form.

    Mirrors ``MemberUnconfirmedAdmin.request_registration_form_view``: generates
    the upload key and mails the person the link to the upload page.
    """
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    member.request_registration_form()
    member.refresh_from_db()
    return member


@router.post("/{member_id}/demote-to-waiter", response={204: None})
def demote_to_waiter(request, member_id: int):
    """Demote an unconfirmed registration back to a waiting-list applicant.

    The member record is replaced by a ``MemberWaitingList`` entry carrying over
    its data, so there is no member resource left to return.
    """
    member = get_authorized(
        request,
        MemberUnconfirmedProxy,
        member_id,
        "members.change_obj_memberunconfirmedproxy",
    )
    member.demote_to_waiter()
    return 204, None


# --- selector categories (ActivityCategory / TrainingCategory) ------------
#
# Simple CRUD so the SPA can populate the FK/M2M selects used by trainings
# (category / activity) and excursions (activity). Both admins are plain
# ``admin.ModelAdmin`` → default Django model permissions apply. These static
# single-segment list routes are declared BEFORE the ``/{member_id}`` route
# (which greedily captures any single segment) so they are not shadowed.


@router.get("/activity-categories", response=list[ActivityCategoryOut])
def list_activity_categories(request):
    """Activity categories (``members.view_activitycategory``)."""
    authorize(request, "members.view_activitycategory")
    return ActivityCategory.objects.all().order_by("name")


@router.post("/activity-categories", response={201: ActivityCategoryOut})
def create_activity_category(request, payload: ActivityCategoryUpdate):
    """Create an activity category (``members.add_activitycategory``)."""
    authorize(request, "members.add_activitycategory")
    category = ActivityCategory(**payload.dict(exclude_unset=True))
    category.full_clean()
    category.save()
    return 201, category


@router.get("/activity-categories/{category_id}", response=ActivityCategoryOut)
def retrieve_activity_category(request, category_id: int):
    """Activity category detail (``members.view_activitycategory``)."""
    authorize(request, "members.view_activitycategory")
    return get_object_or_404(ActivityCategory, pk=category_id)


@router.patch("/activity-categories/{category_id}", response=ActivityCategoryOut)
def update_activity_category(request, category_id: int, payload: ActivityCategoryUpdate):
    """Update an activity category (``members.change_activitycategory``)."""
    authorize(request, "members.change_activitycategory")
    category = get_object_or_404(ActivityCategory, pk=category_id)
    data = payload.dict(exclude_unset=True)
    set_scalar_fields(category, data, list(data.keys()))
    category.full_clean()
    category.save()
    return category


@router.delete("/activity-categories/{category_id}", response={204: None})
def delete_activity_category(request, category_id: int):
    """Delete an activity category (``members.delete_activitycategory``)."""
    authorize(request, "members.delete_activitycategory")
    get_object_or_404(ActivityCategory, pk=category_id).delete()
    return 204, None


@router.get("/training-categories", response=list[TrainingCategoryOut])
def list_training_categories(request):
    """Training categories (``members.view_trainingcategory``)."""
    authorize(request, "members.view_trainingcategory")
    return TrainingCategory.objects.all().order_by("name")


@router.post("/training-categories", response={201: TrainingCategoryOut})
def create_training_category(request, payload: TrainingCategoryUpdate):
    """Create a training category (``members.add_trainingcategory``)."""
    authorize(request, "members.add_trainingcategory")
    category = TrainingCategory(**payload.dict(exclude_unset=True))
    category.full_clean()
    category.save()
    return 201, category


@router.get("/training-categories/{category_id}", response=TrainingCategoryOut)
def retrieve_training_category(request, category_id: int):
    """Training category detail (``members.view_trainingcategory``)."""
    authorize(request, "members.view_trainingcategory")
    return get_object_or_404(TrainingCategory, pk=category_id)


@router.patch("/training-categories/{category_id}", response=TrainingCategoryOut)
def update_training_category(request, category_id: int, payload: TrainingCategoryUpdate):
    """Update a training category (``members.change_trainingcategory``)."""
    authorize(request, "members.change_trainingcategory")
    category = get_object_or_404(TrainingCategory, pk=category_id)
    data = payload.dict(exclude_unset=True)
    set_scalar_fields(category, data, list(data.keys()))
    category.full_clean()
    category.save()
    return category


@router.delete("/training-categories/{category_id}", response={204: None})
def delete_training_category(request, category_id: int):
    """Delete a training category (``members.delete_trainingcategory``)."""
    authorize(request, "members.delete_trainingcategory")
    get_object_or_404(TrainingCategory, pk=category_id).delete()
    return 204, None


# --- choice enums ---------------------------------------------------------


@router.get("/enums", response=dict[str, list[MemberEnumChoice]])
def member_enums(request):
    """The choice fields of the ``Member`` model as ``{field: [{value, label}]}``.

    Lets the SPA render labelled ``<select>``s for member choice fields (e.g.
    ``gender``). Any authenticated user may read this static metadata.
    """
    result = {}
    for field in Member._meta.get_fields():
        choices = getattr(field, "choices", None)
        if choices:
            result[field.name] = [{"value": value, "label": str(label)} for value, label in choices]
    return result


# --- login accounts (options for the member's "Nutzer" field) -------------


@router.get("/auth-users", response=list[AuthUserBrief])
def list_auth_users(request):
    """Login accounts offered by the member change view's ``Nutzer`` picker.

    Gated on ``members.may_set_auth_user`` — the same permission
    :func:`update_member` enforces for ``user_id`` — rather than on
    ``auth.view_user``, which it does not imply: in the admin the select is
    rendered for exactly the users who may change the field.

    That permission covers *writing* the link and nothing else, so no member is
    named here — an account already spoken for is reported as ``taken``, no more.
    Naming its member would disclose an identity that ``Member.may_view``, and
    with it both :func:`list_members` and :func:`retrieve_member`, refuses this
    caller; the admin's select shows usernames only for the same reason. See
    ``GET /api/logindata/users`` for the account administration surface proper,
    which does carry ``member_name`` — behind ``auth.view_user``.
    """
    authorize(request, "members.may_set_auth_user")
    # ``all_objects``: an unconfirmed registration holds an account just as
    # firmly as a confirmed member does, so leaving those out would report a
    # taken account free. Only the ids are read — names must not travel.
    taken = set(Member.all_objects.exclude(user=None).values_list("user_id", flat=True))
    return [
        {"id": user.pk, "username": user.username, "taken": user.pk in taken}
        for user in User.objects.all().only("username").order_by("username")
    ]


# --- member detail (single-segment {member_id}) ---------------------------
#
# Declared LAST so the static single-segment routes above are matched first
# (see the note near ``list_members``). The two-segment ``/{member_id}/...``
# workflow-action routes above are unaffected by ordering (different arity).


@router.get("/{member_id}", response=MemberOut)
def retrieve_member(request, member_id: int):
    """Full member detail, authorized per object."""
    return get_authorized(request, Member, member_id, "members.view_obj_member")


@router.patch("/{member_id}", response=MemberOut)
def update_member(request, member_id: int, payload: MemberUpdate):
    """Update the editable change-view fields of a member, authorized per object.

    In addition to the object-level ``change_obj_member`` gate, the admin's
    per-field permissions are enforced: supplying ``group_ids`` requires
    ``members.may_change_member_group``; ``user_id`` requires
    ``members.may_set_auth_user``; and the organizational fields
    (``good_conduct_certificate_presented_date``, ``has_key``,
    ``has_free_ticket_gym``) require ``members.may_change_organizationals``.
    Supplying a gated field without its permission raises 403. Scalars are
    validated with ``full_clean`` (→ 422 on error).
    """
    member = get_authorized(request, Member, member_id, "members.change_obj_member")
    return _apply_member_update(request, member, payload)


@router.delete("/{member_id}", response={204: None})
def delete_member(request, member_id: int):
    """Delete a member, authorized per object (``delete_obj_member``)."""
    member = get_authorized(request, Member, member_id, "members.delete_obj_member")
    member.delete()
    return 204, None
