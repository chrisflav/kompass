"""Building a :class:`~kompass.rules.RuleContext` out of the real models.

This is the only place in the engine that knows Django. Everything a rule may
read is copied out of the ORM here, eagerly and completely, into frozen values
— which is what makes the query guard (:mod:`finance.engine.guard`) possible at
all: by the time a ruleset runs there is nothing left to fetch.

Two things are deliberately translated rather than passed through:

*Money becomes* :class:`~decimal.Decimal` *via* ``str()``. The settings
snapshot on a statement stores JSON numbers, so ``0.15`` arrives as a binary
float; ``Decimal(str(0.15))`` is ``Decimal("0.15")`` and not
``0.1499999999999999944488848768742172978818416595458984375``, which is what
``Decimal(0.15)`` would be. The same trick is what migration ``0013`` used.

*Ages are resolved here*, because ``Member.age()`` reads the clock and a rule
may not. Both ages are offered — today's and the one on the first day of the
trip — and which one a regulation means is the ruleset's business.
"""

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.db.models import Q
from finance.rules_api import Bill
from finance.rules_api import CONTEXT_VERSION
from finance.rules_api import Excursion
from finance.rules_api import Inputs
from finance.rules_api import LJP
from finance.rules_api import LJPGoal
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Params
from finance.rules_api import Participant
from finance.rules_api import RuleContext
from finance.rules_api import StatementInfo
from finance.rules_api import TourApproach
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import LJPProposal
from members.models import Member as MemberModel
from members.models import MUSKELKRAFT_ANREISE
from members.models import OEFFENTLICHE_ANREISE

#: The settings a ruleset's parameters are taken from, until a ruleset brings
#: its own (step 2 of the refactor). These are exactly the keys
#: ``Statement._capture_settings_snapshot`` freezes.
PARAMETER_KEYS = (
    "ALLOWANCE_PER_DAY",
    "MAX_NIGHT_COST",
    "AID_PER_KM_TRAIN",
    "AID_PER_KM_CAR",
    "EXCURSION_ORG_FEE",
    "LJP_CONTRIBUTION_PER_DAY",
    "LJP_TAX",
)

_APPROACHES: dict[int, TourApproach] = {
    MUSKELKRAFT_ANREISE: "muscle",
    OEFFENTLICHE_ANREISE: "public",
    FAHRGEMEINSCHAFT_ANREISE: "car",
}

_GOALS: dict[int, LJPGoal] = {
    LJPProposal.LJP_QUALIFICATION: "qualification",
    LJPProposal.LJP_PARTICIPATION: "participation",
    LJPProposal.LJP_DEVELOPMENT: "development",
    LJPProposal.LJP_ENVIRONMENT: "environment",
}


def decimal(value: Any) -> Decimal:
    """``value`` as a :class:`~decimal.Decimal`, through its text form."""
    return Decimal(str(value))


def member_of(pk: int | None) -> Member | None:
    """``pk`` as a :class:`~kompass.rules.Member`, or ``None``."""
    if pk is None:
        return None
    return Member(MemberId(pk))


def parameters(statement: Any) -> dict[str, Decimal]:
    """The section's numbers as they apply to ``statement``.

    A submitted statement reads its own snapshot, a draft reads the live
    settings — the behaviour ``Statement._get_setting`` has today, minus its
    round trip through binary floats.
    """
    snapshot: Mapping[str, Any] = {}
    if statement.submitted and statement.settings_snapshot:
        snapshot = statement.settings_snapshot
    values: dict[str, Decimal] = {}
    for key in PARAMETER_KEYS:
        if key in snapshot:
            values[key] = decimal(snapshot[key])
        else:
            values[key] = decimal(getattr(settings, key, 0))
    return values


def permission_holders(codenames: Iterable[str]) -> dict[str, tuple[Member, ...]]:
    """Who holds each of ``codenames``, as ``"app_label.codename"``.

    Resolved against the real permission system — a user's own permissions, the
    permissions of their groups, and superusers, who hold everything. A ruleset
    names a recipient; whether that name may act is never the ruleset's word.
    """
    holders: dict[str, tuple[Member, ...]] = {}
    for full in codenames:
        app_label, separator, codename = full.partition(".")
        if not separator:
            # A bare codename, which every app that defines it answers for.
            app_label, codename = "", app_label
        direct = Q(user__user_permissions__codename=codename)
        through_groups = Q(user__groups__permissions__codename=codename)
        if app_label:
            direct &= Q(user__user_permissions__content_type__app_label=app_label)
            through_groups &= Q(user__groups__permissions__content_type__app_label=app_label)
        matches = MemberModel.objects.filter(
            direct | through_groups | Q(user__is_superuser=True)
        ).values_list("pk", flat=True)
        holders[full] = tuple(Member(MemberId(pk)) for pk in sorted(set(matches)))
    return holders


def _bills(statement: Any) -> tuple[Bill, ...]:
    return tuple(
        Bill(
            id=bill.pk,
            amount=decimal(bill.amount),
            covered=bool(bill.costs_covered),
            payer=member_of(bill.paid_by_id),
            has_proof=bool(bill.proof),
            description=bill.short_description,
        )
        for bill in statement.bill_set.all()
    )


def _ljp(excursion: Any) -> LJP | None:
    if not hasattr(excursion, "ljpproposal"):
        return None
    proposal = excursion.ljpproposal
    return LJP(
        goal=_GOALS.get(proposal.goal),
        participant_count=excursion.ljp_participant_count,
        theoretic_participant_count=excursion.theoretic_ljp_participant_count,
        duration=decimal(excursion.ljp_duration),
    )


def _participants(excursion: Any, leader_ids: set[int]) -> tuple[Participant, ...]:
    on_list: dict[int, Any] = {}
    # ``.all()`` on both relations, never ``.values_list`` or ``.distinct()``:
    # those build a new queryset and so bypass a prefetch, and the statement
    # list prefetches exactly these for its totals. A member listed twice is
    # deduplicated here rather than by the database.
    for entry in excursion.membersonlist.all():
        on_list.setdefault(entry.member.pk, entry.member)
    start = excursion.date
    return tuple(
        Participant(
            member=Member(MemberId(pk)),
            age=person.age() if person.birth_date else None,
            age_at_start=person.age_at(start) if person.birth_date else None,
            is_leader=pk in leader_ids,
        )
        for pk, person in sorted(on_list.items())
    )


def _excursion(excursion: Any) -> Excursion:
    leader_ids = sorted(leader.pk for leader in excursion.jugendleiter.all())
    return Excursion(
        duration=decimal(excursion.duration),
        nights=excursion.night_count,
        kilometers=excursion.kilometers_traveled,
        approach=_APPROACHES.get(excursion.tour_approach, "car"),
        leaders=tuple(Member(MemberId(pk)) for pk in leader_ids),
        # Not ``excursion.staff_count``, which counts in the database: the
        # leaders are already in hand.
        staff_count=len(leader_ids),
        approved_staff_count=excursion.approved_staff_count,
        participants=_participants(excursion, set(leader_ids)),
        ljp=_ljp(excursion),
    )


def statement_inputs(statement: Any) -> dict[str, object]:
    """The answers a statement carries today, by input key.

    Until the statement keeps its answers in one JSON field (step 3 of the
    refactor), they are four columns the Heidelberg rules happen to need. A
    ruleset that declares other keys reads them as empty; a column no ruleset
    declares is dropped before evaluation.
    """
    return {
        "night_cost": decimal(statement.night_cost),
        "allowance_to": tuple(
            Member(MemberId(pk))
            for pk in sorted(member.pk for member in statement.allowance_to.all())
        ),
        "subsidy_to": member_of(statement.subsidy_to_id),
        "ljp_to": member_of(statement.ljp_to_id),
    }


def build_context(
    statement: Any,
    *,
    permissions: Iterable[str] = (),
    inputs: Mapping[str, object] | None = None,
    params: Mapping[str, Decimal] | None = None,
    roles: Mapping[str, Iterable[int]] | None = None,
) -> RuleContext:
    """The context for ``statement``, read out of the database in one go.

    ``permissions`` are the codenames the ruleset declared
    (:attr:`kompass.rules.Ruleset.permissions`); they are resolved here because
    a rule cannot query for them itself. ``inputs`` overrides the answers the
    statement carries, which is what a dry run against unsaved answers needs.
    ``params`` and ``roles`` are passed in by
    :mod:`finance.engine.statements`, which reads them from the statement's own
    ruleset snapshot and from the dated role assignments; left out, the
    parameters fall back to the settings as they always did.
    """
    excursion = statement.excursion
    return RuleContext(
        version=CONTEXT_VERSION,
        params=Params(parameters(statement) if params is None else dict(params)),
        inputs=Inputs(statement_inputs(statement) if inputs is None else dict(inputs)),
        bills=_bills(statement),
        excursion=None if excursion is None else _excursion(excursion),
        statement=StatementInfo(
            id=statement.pk,
            creator=member_of(statement.created_by_id),
            submitter=member_of(statement.submitted_by_id),
        ),
        roles={
            role: tuple(Member(MemberId(pk)) for pk in sorted(ids))
            for role, ids in (roles or {}).items()
        },
        permissions=permission_holders(permissions),
    )
