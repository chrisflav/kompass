"""Inline CRUD routes for excursion / note-list participants and LJP proposals.

These mirror the Django admin *inlines* on the excursion (``Freizeit``) and
member-note-list (``MemberNoteList``) change views, letting the SPA add / list /
edit / remove the parent's related rows exactly like the admin:

* ``NewMemberOnList`` — the generic-FK "participants" inline shared by both
  ``Freizeit`` (``MemberOnListInline``) and ``MemberNoteList``. Writes are gated
  on the PARENT's change permission (an inline is editable iff the parent is):
  a ``Freizeit`` parent → object-level ``members.change_obj_freizeit``; a
  ``MemberNoteList`` parent → global ``members.change_membernotelist``.
* ``LJPProposal`` (``LJPOnListInline``) and its nested ``Intervention``
  (``InterventionOnLJPInline``) — the seminar-report inline of an excursion.
  Both are gated on the owning excursion's ``members.change_obj_freizeit`` (per
  the convention that an inline is editable iff the parent excursion is), which
  is equivalent to the models' own ``is_leader`` rules_permissions.

All routes are mounted under ``/api/members`` (a second router on that prefix).
Static path segments precede single-segment ``/{id}`` routes to avoid shadowing.
"""

from datetime import datetime
from decimal import Decimal

from contrib.api.perms import authorize
from contrib.api.perms import partial_clean
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from members.models import Freizeit
from members.models import Intervention
from members.models import LJPProposal
from members.models import Member
from members.models import MemberNoteList
from members.models import NewMemberOnList
from ninja import ModelSchema
from ninja import Router
from ninja import Schema

from .schemas import MemberBrief

router = Router()


# --- schemas: participants (NewMemberOnList) ------------------------------


class ExcursionParticipantOut(ModelSchema):
    """A member-on-list row (participant / note-list entry) with its member."""

    id: int
    member: MemberBrief

    class Meta:
        model = NewMemberOnList
        fields = ["comments"]


class ExcursionParticipantCreate(Schema):
    """Add a member to a participant / note list (optionally with a comment)."""

    member_id: int
    comments: str = ""


class ExcursionParticipantUpdate(Schema):
    """Edit a participant row; only the free-text comment is editable."""

    comments: str | None = None


# --- schemas: LJP proposal + interventions --------------------------------


class LJPInterventionOut(ModelSchema):
    id: int
    ljp_proposal_id: int

    class Meta:
        model = Intervention
        fields = ["date_start", "duration", "activity"]


class LJPInterventionCreate(Schema):
    date_start: datetime
    duration: Decimal
    activity: str


class LJPInterventionUpdate(Schema):
    date_start: datetime | None = None
    duration: Decimal | None = None
    activity: str | None = None


class LJPProposalOut(ModelSchema):
    id: int
    excursion_id: int | None = None
    category_display: str
    goal_display: str
    not_bw_reason_display: str | None = None
    interventions: list[LJPInterventionOut] = []

    class Meta:
        model = LJPProposal
        fields = ["title", "category", "goal", "goal_strategy", "not_bw_reason"]

    @staticmethod
    def resolve_category_display(obj) -> str:
        return str(obj.get_category_display())

    @staticmethod
    def resolve_goal_display(obj) -> str:
        return str(obj.get_goal_display())

    @staticmethod
    def resolve_not_bw_reason_display(obj) -> str | None:
        return str(obj.get_not_bw_reason_display()) if obj.not_bw_reason is not None else None

    @staticmethod
    def resolve_interventions(obj):
        return obj.intervention_set.all()


class LJPProposalCreate(Schema):
    """Create payload for an excursion's LJP proposal.

    Unspecified ``category`` / ``goal`` fall back to the model defaults. The
    ``goal`` / ``category`` combination is validated exactly like the admin's
    ``LJPProposalForm.clean`` (see :func:`_validate_ljp_combination`).
    """

    title: str = ""
    category: int | None = None
    goal: int | None = None
    goal_strategy: str = ""
    not_bw_reason: int | None = None


class LJPProposalUpdate(Schema):
    """Patch payload for an LJP proposal; only supplied fields are applied."""

    title: str | None = None
    category: int | None = None
    goal: int | None = None
    goal_strategy: str | None = None
    not_bw_reason: int | None = None


LJP_PROPOSAL_SCALAR_FIELDS = ("title", "category", "goal", "goal_strategy", "not_bw_reason")
INTERVENTION_SCALAR_FIELDS = ("date_start", "duration", "activity")


# --- permission helpers ---------------------------------------------------


def _authorize_participant_parent(request, parent, write):
    """Gate a participant row on its PARENT's view/change permission.

    ``Freizeit`` participants use the object-level ``*_obj_freizeit`` predicate;
    ``MemberNoteList`` entries use the global ``*_membernotelist`` permission
    (its admin is a plain ``ModelAdmin``). Any other parent type is a 404.
    """
    if isinstance(parent, Freizeit):
        authorize(
            request, "members.change_obj_freizeit" if write else "members.view_obj_freizeit", parent
        )
    elif isinstance(parent, MemberNoteList):
        authorize(
            request, "members.change_membernotelist" if write else "members.view_membernotelist"
        )
    else:
        raise Http404(_("Unknown participant list."))


def _authorize_ljp(request, proposal, write):
    """Gate an LJP proposal / intervention on its excursion's change permission.

    An LJP inline is editable iff its owning excursion is, so authorize
    ``members.change_obj_freizeit`` on the excursion. A proposal whose excursion
    was cleared (``SET_NULL``) falls back to the global excursion permission.
    """
    excursion = proposal.excursion
    if excursion is not None:
        authorize(
            request,
            "members.change_obj_freizeit" if write else "members.view_obj_freizeit",
            excursion,
        )
    else:
        authorize(
            request, "members.change_global_freizeit" if write else "members.view_global_freizeit"
        )


def _validate_ljp_combination(goal, category):
    """Replicate ``LJPProposalForm.clean``: goal/category must be compatible."""
    if goal is None or category is None:
        return
    if goal == LJPProposal.LJP_QUALIFICATION:
        if category != LJPProposal.LJP_STAFF_TRAINING:
            raise ValidationError(
                _(
                    "The learning goal 'Qualification' can only be combined with "
                    "the category 'Staff training'."
                )
            )
    elif category != LJPProposal.LJP_EDUCATIONAL:
        raise ValidationError(
            _(
                "The learning goals 'Participation', 'Personality development', and "
                "'Environment' can only be combined with the category 'Educational programme'."
            )
        )


# --- excursion participants ----------------------------------------------


@router.get("/excursions/{excursion_id}/participants", response=list[ExcursionParticipantOut])
def list_excursion_participants(request, excursion_id: int):
    """List an excursion's participants (gated on ``view_obj_freizeit``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_participant_parent(request, excursion, write=False)
    return excursion.membersonlist.all()


@router.post("/excursions/{excursion_id}/participants", response={201: ExcursionParticipantOut})
def add_excursion_participant(request, excursion_id: int, payload: ExcursionParticipantCreate):
    """Add a member to an excursion (gated on ``change_obj_freizeit``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_participant_parent(request, excursion, write=True)
    return 201, _create_participant(excursion, payload)


# --- note-list participants ----------------------------------------------


@router.get("/note-lists/{notelist_id}/participants", response=list[ExcursionParticipantOut])
def list_notelist_participants(request, notelist_id: int):
    """List a note list's members (gated on ``view_membernotelist``)."""
    notelist = get_object_or_404(MemberNoteList, pk=notelist_id)
    _authorize_participant_parent(request, notelist, write=False)
    return notelist.membersonlist.all()


@router.post("/note-lists/{notelist_id}/participants", response={201: ExcursionParticipantOut})
def add_notelist_participant(request, notelist_id: int, payload: ExcursionParticipantCreate):
    """Add a member to a note list (gated on ``change_membernotelist``)."""
    notelist = get_object_or_404(MemberNoteList, pk=notelist_id)
    _authorize_participant_parent(request, notelist, write=True)
    return 201, _create_participant(notelist, payload)


def _create_participant(parent, payload):
    """Create a ``NewMemberOnList`` row linking a member to ``parent``."""
    member = get_object_or_404(Member, pk=payload.member_id)
    content_type = ContentType.objects.get_for_model(type(parent))
    participant = NewMemberOnList(
        member=member,
        content_type=content_type,
        object_id=parent.pk,
        comments=payload.comments or "",
    )
    participant.full_clean()
    participant.save()
    return participant


# --- participant row edit / delete (shared, parent-typed) -----------------


@router.patch("/participants/{participant_id}", response=ExcursionParticipantOut)
def update_participant(request, participant_id: int, payload: ExcursionParticipantUpdate):
    """Edit a participant row's comment, gated on the parent's change permission."""
    participant = get_object_or_404(NewMemberOnList, pk=participant_id)
    _authorize_participant_parent(request, participant.memberlist, write=True)
    data = payload.dict(exclude_unset=True)
    if "comments" in data:
        participant.comments = data["comments"]
        partial_clean(participant, ["comments"])
        participant.save()
    return participant


@router.delete("/participants/{participant_id}", response={204: None})
def delete_participant(request, participant_id: int):
    """Remove a participant row, gated on the parent's change permission."""
    participant = get_object_or_404(NewMemberOnList, pk=participant_id)
    _authorize_participant_parent(request, participant.memberlist, write=True)
    participant.delete()
    return 204, None


# --- LJP proposal ---------------------------------------------------------


@router.get("/excursions/{excursion_id}/ljp-proposal", response=LJPProposalOut)
def retrieve_ljp_proposal(request, excursion_id: int):
    """Retrieve an excursion's LJP proposal (gated on ``view_obj_freizeit``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    authorize(request, "members.view_obj_freizeit", excursion)
    proposal = LJPProposal.objects.filter(excursion=excursion).first()
    if proposal is None:
        raise Http404(_("This excursion has no LJP proposal."))
    return proposal


@router.post("/excursions/{excursion_id}/ljp-proposal", response={201: LJPProposalOut})
def create_ljp_proposal(request, excursion_id: int, payload: LJPProposalCreate):
    """Create the LJP proposal for an excursion (gated on ``change_obj_freizeit``).

    ``excursion`` is a one-to-one relation, so ``full_clean`` yields 422 if a
    proposal already exists for this excursion.
    """
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    authorize(request, "members.change_obj_freizeit", excursion)
    data = payload.dict(exclude_unset=True)
    proposal = LJPProposal(excursion=excursion)
    for field in LJP_PROPOSAL_SCALAR_FIELDS:
        if field in data:
            setattr(proposal, field, data[field])
    _validate_ljp_combination(proposal.goal, proposal.category)
    proposal.full_clean()
    proposal.save()
    return 201, proposal


@router.patch("/ljp-proposals/{proposal_id}", response=LJPProposalOut)
def update_ljp_proposal(request, proposal_id: int, payload: LJPProposalUpdate):
    """Update an LJP proposal, gated on its excursion's change permission."""
    proposal = get_object_or_404(LJPProposal, pk=proposal_id)
    _authorize_ljp(request, proposal, write=True)
    data = payload.dict(exclude_unset=True)
    changed = [f for f in LJP_PROPOSAL_SCALAR_FIELDS if f in data]
    for field in changed:
        setattr(proposal, field, data[field])
    _validate_ljp_combination(proposal.goal, proposal.category)
    partial_clean(proposal, changed)
    proposal.save()
    return proposal


@router.delete("/ljp-proposals/{proposal_id}", response={204: None})
def delete_ljp_proposal(request, proposal_id: int):
    """Delete an LJP proposal, gated on its excursion's change permission."""
    proposal = get_object_or_404(LJPProposal, pk=proposal_id)
    _authorize_ljp(request, proposal, write=True)
    proposal.delete()
    return 204, None


# --- LJP interventions ----------------------------------------------------


@router.get("/ljp-proposals/{proposal_id}/interventions", response=list[LJPInterventionOut])
def list_interventions(request, proposal_id: int):
    """List an LJP proposal's interventions (gated on ``view_obj_freizeit``)."""
    proposal = get_object_or_404(LJPProposal, pk=proposal_id)
    _authorize_ljp(request, proposal, write=False)
    return proposal.intervention_set.all()


@router.post("/ljp-proposals/{proposal_id}/interventions", response={201: LJPInterventionOut})
def add_intervention(request, proposal_id: int, payload: LJPInterventionCreate):
    """Add an intervention to an LJP proposal (gated on ``change_obj_freizeit``)."""
    proposal = get_object_or_404(LJPProposal, pk=proposal_id)
    _authorize_ljp(request, proposal, write=True)
    intervention = Intervention(
        ljp_proposal=proposal,
        date_start=payload.date_start,
        duration=payload.duration,
        activity=payload.activity,
    )
    intervention.full_clean()
    intervention.save()
    return 201, intervention


@router.patch("/interventions/{intervention_id}", response=LJPInterventionOut)
def update_intervention(request, intervention_id: int, payload: LJPInterventionUpdate):
    """Update an intervention, gated on its proposal's excursion change permission."""
    intervention = get_object_or_404(Intervention, pk=intervention_id)
    _authorize_ljp(request, intervention.ljp_proposal, write=True)
    data = payload.dict(exclude_unset=True)
    changed = [f for f in INTERVENTION_SCALAR_FIELDS if f in data]
    for field in changed:
        setattr(intervention, field, data[field])
    partial_clean(intervention, changed)
    intervention.save()
    return intervention


@router.delete("/interventions/{intervention_id}", response={204: None})
def delete_intervention(request, intervention_id: int):
    """Delete an intervention, gated on its proposal's excursion change permission."""
    intervention = get_object_or_404(Intervention, pk=intervention_id)
    _authorize_ljp(request, intervention.ljp_proposal, write=True)
    intervention.delete()
    return 204, None
