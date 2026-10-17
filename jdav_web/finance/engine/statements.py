"""What the engine does with one statement: bind it, resolve it, write it down.

Three things happen to a statement, and this module is all three.

**Binding** (:func:`bind`) copies the active ruleset version onto the statement
*when it is created* — the row, its hash, and the whole closure with its
parameters. From then on the statement is settled against the rules that were
in force the day it was opened, which is the requirement the old code missed:
it snapshotted the section's numbers at ``submit()``, so a draft quietly
followed whatever the settings said until somebody handed it in.

**Resolving** (:func:`evaluate_statement`) runs the statement's own ruleset
against a context built from its own parameters, so a draft from last year
evaluates against last year's rules.

**Materialising** (:func:`materialise`) writes the resulting transfers to
:class:`~finance.store.Obligation` rows: computed on every draft save, frozen
when the statement is handed in. After that the rows are the record — read, not
recomputed — which is what makes a settled statement legible without the code
that produced it, and what stops a page re-evaluating the rules a dozen times
to render one screen.

Nothing here imports ``finance.models``: statements arrive as arguments.
"""

import logging
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from django.utils import timezone
from finance.parties import MEMBER
from finance.parties import PARTICIPANTS
from finance.parties import SECTION
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Participants
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset
from finance.rules_api import Section
from finance.rules_api import Transfer
from finance.rulesets.heidelberg import APPROVER_PERMISSION
from finance.rulesets.heidelberg import ruleset as reference_ruleset
from finance.store import ApprovalConstraint
from finance.store import Obligation
from finance.store import RoleAssignment
from finance.store import RuleSet
from members.models import Member as MemberModel

from .approval import PERMISSION_EXCLUSION
from .approval import resolve_eligibility
from .context import build_context
from .context import parameters
from .context import permission_holders
from .evaluation import evaluate
from .evaluation import party_key
from .evaluation import Result
from .guard import no_queries
from .loader import manifest
from .versions import active_version
from .versions import decimal_params
from .versions import ruleset_from_sources
from .versions import version_hash

logger = logging.getLogger(__name__)

#: The name a constraint carries when the rules could not be resolved at all.
#: It is deliberately not a name a section can collide with by accident.
UNRESOLVED = "<unresolved>"


def _kind_of(party: Any) -> str:
    """Which kind of party this is, by type rather than by exact class."""
    if isinstance(party, Member):
        return MEMBER
    if isinstance(party, Participants):
        return PARTICIPANTS
    return SECTION


def active_ruleset() -> Ruleset:
    """The ruleset a new statement will be settled against.

    The active stored version, or — on an instance that has never imported one
    — the reference ruleset that ships in the image. A stored version that no
    longer loads is a loud warning and the same fallback: a section's broken
    rules must not take its finance pages down.

    *However* it fails to load, which is the whole of the promise and was not
    the whole of the code. Catching only the two exceptions a *refused*
    snapshot raises left every other way a module body can fail — a section's
    own ``ValueError``, and the realistic one, an ``ImportError`` from a
    Kompass upgrade that renamed something in ``kompass.rules`` — to propagate
    out of here and 500 the page that asked.
    """
    return _active_with_identity()[0]


def _active_with_identity() -> tuple[Ruleset, str]:
    """The ruleset in force, and the identity of what *actually* loaded.

    ``""`` whenever the answer comes from the reference ruleset — because
    nothing has been imported, **or** because the active version would not
    load and the fallback took over. One caller depends on telling those two
    apart from a version that loaded, and it depends on it for a right rather
    than for tidiness: :func:`_rows_from_the_same_rules` re-resolves a
    statement's eligibility only while the rules answering are the rules its
    rows were frozen under, and that check is a hash comparison. Reporting the
    active row's hash for an answer the *reference* ruleset gave passes it with
    the wrong rules — and the reference ruleset names ``Freigabe``, which is
    the step name every section that starts from it and narrows the group
    keeps, so the merge in :func:`current_constraint_rows` would take the
    reference ruleset's group for the section's own: a statement a section
    reserved for its treasurer, signable by everybody holding the capability.
    The frozen forbids stay sticky and the quorum stays frozen; it is exactly
    *who may sign* that would widen. Reported as ``""``, the bound fails, and
    the frozen rows stand — which is what degrading has to mean.

    The property this establishes is worth stating as one line, because it is
    stronger than the case it was written for: **a snapshot that will not load
    now means no re-resolution at all.** Either the active version loaded, and
    its hash differs from the hash the rows were frozen under — or it is the
    same ``(sources, params)`` as the snapshot, by construction, in which case
    it did not load either and the identity is ``""``. Both ways the bound in
    :func:`_rows_from_the_same_rules` fails, and no third way exists.
    """
    row = active_version()
    if row is not None:
        try:
            return ruleset_from_sources(row.sources), str(row.hash)
        except Exception as problem:
            # `error` rather than `warning`: the consequence is instance-wide
            # — every statement created from now on is settled against the
            # reference ruleset — and `tasks.import_ruleset` already shouts at
            # this level for a version that did not activate.
            logger.error(
                "the active ruleset %s cannot be loaded (%s: %s); the reference ruleset is "
                "answering for it",
                row,
                type(problem).__name__,
                problem,
                exc_info=True,
            )
    return reference_ruleset, ""


def ruleset_for(statement: Any) -> Ruleset:
    """The ruleset ``statement`` is settled against.

    Its own snapshot where it has one, so that neither a new version nor a
    changed file can move an open statement; the active version otherwise.
    """
    return loaded_ruleset(statement)[0]


def loaded_ruleset(statement: Any) -> tuple[Ruleset, str]:
    """The ruleset to use for ``statement``, and the version it came from.

    The second element is the identity of what was *actually loaded*: the
    snapshot's hash when the statement's own closure was used, the active
    version's hash when that answered instead, and ``""`` when neither could
    be loaded and the reference ruleset answered. Taking the last of those
    literally is what makes the sentence true, and
    :func:`_active_with_identity` says what it costs when it is not.

    The fallback is deliberate — a statement whose stored closure no longer
    loads must still render, generate transactions and print — but it means
    the rules that answer a question are not always the rules the statement was
    settled under, and anything that *compares* an answer to a stored record
    has to know which it got. :func:`current_constraint_rows` is that
    somebody: before this returned the identity, a fallback to the reference
    ruleset silently replaced a section's frozen forbids with the reference
    ruleset's constraints.
    """
    snapshot = statement.ruleset_snapshot or {}
    sources = snapshot.get("sources")
    if sources:
        try:
            return ruleset_from_sources(sources), str(snapshot.get("hash", ""))
        except Exception as problem:
            # Every way a stored closure can fail to load, not only the two a
            # refusal raises: a module body is a section's own code and may
            # raise anything, and an old snapshot meets a renamed
            # `kompass.rules` with an `ImportError`. Narrower, this function
            # was total on one path (`_rows_from_the_same_rules` wrapped it)
            # and a 500 on every other — the draft save, the form, the
            # printout — for the one kind of failure the fallback exists for.
            logger.warning(
                "statement %s carries a snapshot that cannot be loaded (%s: %s); "
                "using the version in force",
                statement.pk,
                type(problem).__name__,
                problem,
                exc_info=True,
            )
    return _active_with_identity()


def statement_params(statement: Any) -> dict[str, Decimal]:
    """The numbers ``statement`` is settled with.

    Its snapshot's parameters where it has them. Otherwise the legacy
    behaviour: the ``settings_snapshot`` of a submitted statement, else the
    live settings — which is what every statement created before this refactor
    has to keep reading.
    """
    snapshot = statement.ruleset_snapshot or {}
    stored = snapshot.get("params")
    if stored:
        return decimal_params(stored)
    return parameters(statement)


def statement_context(
    statement: Any,
    ruleset: Ruleset,
    *,
    inputs: Mapping[str, object] | None = None,
    actors: bool = False,
) -> RuleContext:
    """The context for ``statement`` under ``ruleset``.

    ``actors`` decides whether the people who may *act* on the statement are
    resolved into it: the holders of the permissions the ruleset declared, and
    who holds which role today. Those are two queries and the statement list
    builds a context per row, so they are fetched for the approval step — the
    only thing that reads them — and left out of the arithmetic.

    Neither is silently empty when left out. ``permission_holders`` raises for
    an undeclared codename and ``roles`` is :class:`~kompass.rules.Roles`
    *unresolved*, which raises as well; both land in ``Result.errors``, so a
    rule that routes money by who may sign it fails loudly instead of paying
    nothing and balancing the books around the hole.
    """
    # `ruleset.permissions` is read inside the guard: it is a class attribute
    # in every ruleset in tree, but nothing stops a section writing it as a
    # property, and a property is code — which would then be the one line of a
    # section's own that ran unguarded.
    with no_queries():
        declared = tuple(ruleset.permissions) if actors else ()
    return build_context(
        statement,
        permissions=declared,
        inputs=inputs,
        params=statement_params(statement),
        roles=RoleAssignment.roles_at() if actors else None,
    )


def evaluate_statement(
    statement: Any,
    *,
    ruleset: Ruleset | None = None,
    inputs: Mapping[str, object] | None = None,
) -> Result:
    """Resolve ``statement`` into transfers.

    ``ruleset`` and ``inputs`` are for a dry run — "what would this statement
    look like under that version, with those answers" — which is what the
    admin's test pages and the parity suite use.
    """
    rules = ruleset_for(statement) if ruleset is None else ruleset
    return evaluate(rules, statement_context(statement, rules, inputs=inputs))


def bind(statement: Any) -> bool:
    """Copy the active ruleset version onto a statement being created.

    Returns whether anything was bound: an instance that has imported no
    version yet leaves the statement unbound, and it then evaluates against the
    reference ruleset and the live settings, exactly as it did before there was
    a store.
    """
    row = active_version()
    if row is None:
        return False
    statement.ruleset = row
    statement.ruleset_hash = row.hash
    statement.ruleset_snapshot = row.snapshot()
    return True


def _party_fields(party: Any, prefix: str, names: Mapping[int, str]) -> dict[str, Any]:
    # `isinstance`, not `type(...)`: the validation that let this transfer
    # through used `isinstance`, so a `Member` subclass arrives here — and an
    # exact-type lookup would miss it and book the money as the section's.
    kind = _kind_of(party)
    if kind != MEMBER:
        return {f"{prefix}_kind": kind, f"{prefix}_member_id": None, f"{prefix}_name": ""}
    return {
        f"{prefix}_kind": MEMBER,
        f"{prefix}_member_id": party.id,
        # The name is copied beside the reference: an obligation is a record
        # of what was owed to whom, and it has to stay readable after the
        # member row is gone.
        f"{prefix}_name": names.get(party.id, ""),
    }


def cents_of(amount: Decimal) -> int:
    """``amount`` as whole cents, which is how an obligation stores money."""
    return int(amount.scaleb(2).to_integral_value())


def live_rows(statement: Any) -> list[Obligation]:
    """The statement's current obligation rows, superseded ones left out.

    Filtered in Python rather than in SQL on purpose: a list view that
    prefetched ``obligation_set`` answers this from the prefetch, and a
    statement has a handful of rows.
    """
    return [row for row in statement.obligation_set.all() if row.superseded_at is None]


def materialise(statement: Any, *, freeze: bool = False) -> tuple[Obligation, ...]:
    """Write the statement's transfers to rows, and return them.

    A draft is recomputed on every save. A submitted statement is *not*: its
    rows were frozen when it was handed in and they are the record from then
    on, so this returns them untouched unless it is the submission itself
    (``freeze=True``) that is asking.

    Where a frozen record *is* resolved again — the finance officer covering a
    bill after submission, which is the one edit that stays open — the old rows
    are **superseded, not deleted**. §6 of the proposal invokes the GoBD's
    *Unveränderbarkeit* as this design's regulatory justification, and deleting
    a settled row and writing a new one in its place is precisely the thing
    that asks for.
    """
    if statement.pk is None:
        return ()
    if statement.submitted and not freeze:
        return tuple(live_rows(statement))
    result = evaluate_statement(statement)
    if result.errors:
        # Nothing is persisted while the rules report a problem: a statement
        # that cannot be resolved has no record, and everything that reads one
        # falls back to resolving it live, where the problem is still visible.
        # Writing rows here would hide a payerless receipt behind a payout that
        # looks complete.
        _retire_rows(statement)
        _retire_constraint_rows(statement)
        return ()
    members = MemberModel.objects.in_bulk([party.id for party in result.members()])
    names = {pk: member.name for pk, member in members.items()}
    # The hash the statement was *asked* to settle under, which is not always
    # the hash of the rules that have just answered: a statement created while
    # the active version does not load gets its rows stamped with the section's
    # version and resolved by the reference ruleset. Inert where it would
    # matter — the identity `_active_with_identity` reports is then `""`, so
    # the bound in `_rows_from_the_same_rules` fails and these rows are read
    # rather than re-resolved for as long as the version stays unloadable —
    # logged at ERROR when it happens, and reported by `verify`, which replays
    # from the snapshot and says it cannot load it instead of dying on it. A
    # deliberate trade against the alternative, which is the outage this
    # fallback exists to prevent; recorded on #555 rather than changed here.
    version = (statement.ruleset_snapshot or {}).get("hash", "")
    frozen = timezone.now() if freeze else None
    rows = [
        Obligation(
            statement=statement,
            position=position,
            amount_cents=cents_of(transfer.amount),
            category=transfer.category,
            label=str(transfer.label)[:200],
            explanation=str(transfer.explanation),
            rule_id=transfer.rule_id,
            rule_version=version,
            frozen_at=frozen,
            **_party_fields(transfer.source, "source", names),
            **_party_fields(transfer.destination, "destination", names),
        )
        for position, transfer in enumerate(result.transfers)
    ]
    _retire_rows(statement)
    Obligation.objects.bulk_create(rows)
    _materialise_constraints(statement, result, version=version, frozen=frozen)
    return tuple(live_rows(statement))


def _retire_rows(statement: Any) -> None:
    """Clear the way for a new resolution, keeping what was settled.

    A draft's rows are a working copy and are simply dropped. A row that was
    frozen at submission is a record: it is marked superseded and stays.
    """
    rows = statement.obligation_set.all()
    rows.filter(frozen_at__isnull=True).delete()
    rows.filter(frozen_at__isnull=False, superseded_at__isnull=True).update(
        superseded_at=timezone.now()
    )


def _retire_constraint_rows(statement: Any) -> None:
    """Clear the way for a new resolution, keeping what was settled.

    The mirror of :func:`_retire_rows`, one model over, and for the same
    reason: a draft's constraint rows are a working copy and are dropped, a
    row frozen at submission is a record and is marked superseded.

    They were *deleted* until #555, and what the delete destroyed was the only
    record of who authorised a payout against a failing approval step and what
    reason they gave — to an unrelated receipt edit, through the one edit the
    finance officer's permission exists for. The decision the rows carried is
    read back by :func:`_decisions_so_far`.
    """
    rows = statement.approval_constraint_set.all()
    rows.filter(frozen_at__isnull=True).delete()
    rows.filter(frozen_at__isnull=False).update(superseded_at=timezone.now())


#: The fields of an :class:`~finance.store.ApprovalConstraint` that record a
#: *decision* about the step rather than a resolution of it: whether its
#: signatures came in, and who waived it with what reason.
DECISION_FIELDS = ("satisfied", "overridden_by_id", "overridden_at", "override_reason")

#: The three of them that are the waiver. They are the ones a new row may have
#: to refuse (:func:`_carried_decision`), because a waiver is a permission and
#: the other field is a count.
WAIVER_FIELDS = ("overridden_by_id", "overridden_at", "override_reason")


def latest_constraint_rows(statement: Any) -> list[ApprovalConstraint]:
    """The most recent row per step name, superseded rows included.

    Two callers need exactly this. :func:`_decisions_so_far` needs it because
    a re-resolution that happens while the rules report a problem persists
    nothing, so by the time the problem is fixed the row carrying a waiver is
    a superseded one; reading only live rows would carry a decision across an
    ordinary re-freeze and lose it across that pair of events, which is the
    same defect with one more step in it. And
    :func:`current_constraint_rows` needs it for the same state read from the
    other end: with no live rows at all the gate had nothing to answer with,
    and "no constraints" means *approved* (:func:`finance.engine.approval.
    fully_approved`), so a statement whose rules broke after submission read
    as signed off by nobody. The rows the record last asked for are a better
    answer than none, and supersession is what made them available.
    """
    latest: dict[str, ApprovalConstraint] = {}
    for row in ApprovalConstraint.all_objects.filter(statement=statement).order_by("pk"):
        latest[row.name] = row
    return list(latest.values())


def _decisions_so_far(statement: Any) -> dict[str, dict[str, Any]]:
    """Per step name, the decision its most recent row carries.

    A decision belongs to the **step**, not to the row. Resolving a statement
    again re-asks who may sign it; it does not re-ask whether the people who
    already signed did, nor withdraw an authorisation nobody withdrew —
    before #555 a covered receipt did exactly that, and put a payout the board
    had waived back in front of the board. The superseded row keeps its own
    copy of the decision beside the eligible set and the amounts it was taken
    against, so the chain reads as what happened rather than as the latest
    state alone.

    Carrying is not unconditional, and the two halves of a decision differ in
    *why*. ``satisfied`` is a count of what came in, read only for a statement
    that has settled or has not been handed in, and never by the gate, which
    counts signatures afresh every time (``recorded=False``) — so a step the
    rules ask for differently after a re-freeze, a quorum that grew with the
    payout say, carries it harmlessly. A **waiver is a permission**, and
    :attr:`~finance.engine.approval.ConstraintState.open` reads it on every
    call, gate included, so it is re-checked against the resolution that is
    taking over: see :func:`_carried_decision`.
    """
    return {
        row.name: {field: getattr(row, field) for field in DECISION_FIELDS}
        for row in latest_constraint_rows(statement)
    }


def _excluding_forbid(row: Mapping[str, Any], member_id: Any) -> str | None:
    """The name of the forbid that bars ``member_id`` from ``row``, or ``None``.

    The permission re-check is not a forbid, exactly as in
    :meth:`finance.models.Statement.forbids_approval_by`: somebody who did not
    hold the capability when the row was written may hold it now, and the
    capability is checked at the moment somebody acts.
    """
    if member_id is None:
        return None
    for item in row.get("excluded", ()) or ():
        if int(item["member"]) != int(member_id):
            continue
        forbid = str(item.get("forbid", ""))
        if forbid != PERMISSION_EXCLUSION:
            return forbid
    return None


def _carried_decision(decision: Mapping[str, Any], row: Mapping[str, Any]) -> dict[str, Any]:
    """What the new ``row`` takes over from the decision recorded before it.

    All of it, unless the decision is a **waiver** and this resolution
    excludes the person who gave it. Then the waiver stays behind, on the
    superseded row, and this row records that it did not carry.

    That exception is a control and not tidiness. An override is refused from
    somebody a ``Forbid`` excludes — "recording that they did it is a
    mitigation rather than a control"
    (:meth:`finance.models.Statement.override_approval`) — and
    :attr:`~finance.engine.approval.ConstraintState.open` reads ``overridden``
    on every call, the gate's included. So a carried waiver closes a step
    unconditionally, and carrying one the live path would now refuse is that
    control defeated after the fact: measured, the payee waives the board's
    signatures, the finance officer then covers a receipt *that payee* fronted,
    the new resolution excludes them under the section's conflict-of-interest
    forbid — and the waiver they may no longer give goes on paying them. The
    same shape as the hole a previous round's fix opened by dropping a frozen
    forbid.

    The alternative considered was to make
    :func:`finance.engine.approval.states` require the overrider to be in the
    eligible set before an override closes a step. It is the wrong rule: an
    override is *for* the person who may not sign — the chair waving through a
    step whose group is the treasurers — so requiring membership would refuse
    every legitimate waiver, and a waiver by an administrator with no member
    record (``overridden_by`` is nullable) could never be given at all. The
    forbid is the control that exists; this re-asks that control, and nothing
    else.
    """
    if not decision:
        return {}
    carried = dict(decision)
    if decision.get("overridden_at") is None:
        return carried
    forbid = _excluding_forbid(row, decision.get("overridden_by_id"))
    if forbid is None:
        return carried
    for field in WAIVER_FIELDS:
        carried.pop(field, None)
    waived_by = MemberModel.objects.filter(pk=decision["overridden_by_id"]).first()
    carried["override_withdrawn"] = (
        f"the override by {waived_by.name if waived_by else decision['overridden_by_id']} "
        f"({decision['override_reason']}) did not carry onto this row: {forbid}"
    )[:500]
    return carried


def _approver_ids() -> set[int]:
    """The members who hold the capability to sign anything off, today."""
    return {
        member.id
        for codename in (APPROVER_PERMISSION,)
        for member in permission_holders([codename])[codename]
    }


def resolve_constraints(statement: Any, result: Result) -> list[dict[str, Any]]:
    """What the rules ask for in the way of signatures, resolved against today.

    Returns one mapping per constraint in the shape
    :meth:`~finance.store.ApprovalConstraint.as_row` produces, which is what
    :mod:`finance.engine.approval` evaluates. Two callers:
    :func:`_materialise_constraints`, which writes these down at submission,
    and :func:`current_constraint_rows`, which asks the same question again at
    the moment somebody tries to sign.

    Routing runs on the *transfers*, after expansion, never on the raw
    statement — the ordering §7 of the proposal insists on, because "nobody who
    receives money from this statement" is a question about the payout rather
    than about the form somebody filled in.

    A ruleset that **fails** here — a forbid whose predicate raises, a rule
    that tries to query, a ``permissions`` declaration that does — yields
    constraints that carry the reason and name nobody. That is deliberate: the
    alternatives are to persist nothing, which would leave a statement with no
    constraints at all and therefore payable without a signature, or to
    resolve it permissively, which is the bug this whole module is written
    against. A broken rule makes a payout *stuck*, and stuck is the safe
    direction.

    The failure is recorded **per constraint**, and that matters: collapsing
    the whole list into one unresolved row turned a board's two signatures into
    one row that one override could clear. Each constraint keeps its own name,
    its own ``required`` and its own ``applicable``; only the group it could
    not resolve is replaced by the reason it could not.
    """
    ruleset = ruleset_for(statement)
    try:
        # Building the context is inside the `try` as well, because it is a
        # call into the section's rules too: it reads `ruleset.permissions` to
        # resolve who may act, and a `property` there is code, guarded like
        # the rest of it. Outside, one such property raised
        # `QueryDuringEvaluation` out of `materialise` and therefore out of
        # *every draft save* in the section — while the identical failure at
        # signing time already degraded, and while such a ruleset reaches
        # ACTIVE because nothing read `permissions` at import. Loud on one
        # path and silent on the other is the one answer that cannot be
        # right; the import says so now (`check_directory`) and the save ends
        # up where this docstring already promised.
        context = statement_context(statement, ruleset, actors=True)
        # Inside the guard, like `transfers` and `checks`: a rule that resolved
        # its eligible set with a query would freeze today's membership into
        # rows that replay differently in two years.
        with no_queries():
            constraints, forbids = ruleset.approval(context, list(result.transfers))
    except Exception as problem:
        logger.warning("the section's approval rules failed: %s", problem)
        return [
            {
                "name": UNRESOLVED,
                "description": "",
                "applicable": True,
                "required": 1,
                "eligible": [],
                "excluded": [],
                "error": f"{type(problem).__name__}: {problem}"[:500],
            }
        ]
    permitted = _approver_ids()
    rows: list[dict[str, Any]] = []
    for constraint in constraints:
        row: dict[str, Any] = {
            "name": str(constraint.name)[:100],
            "description": str(constraint.description),
            "applicable": bool(constraint.applicable),
            "required": int(constraint.required),
            "eligible": [],
            "excluded": [],
            "error": "",
        }
        try:
            eligibility = resolve_eligibility(constraint, forbids, permitted=permitted)
        except Exception as problem:
            logger.warning("the forbids of %s could not be resolved: %s", constraint.name, problem)
            row["error"] = f"{type(problem).__name__}: {problem}"[:500]
        else:
            row["eligible"] = list(eligibility.eligible)
            row["excluded"] = [
                {"member": item.member, "forbid": item.forbid} for item in eligibility.excluded
            ]
        rows.append(row)
    return rows


def _materialise_constraints(statement: Any, result: Result, *, version: str, frozen: Any) -> None:
    """Freeze the signatures the rules ask for, with the forbids applied.

    The forbids and the permission re-check are applied *here*, so the stored
    eligible set is the set that may sign: a predicate cannot be persisted, and
    an audit two years later must not depend on re-running a section's Python.
    Who may sign *now* is a different question, asked by
    :func:`current_constraint_rows` — see its docstring for why the two differ.

    Called again for a statement that is already submitted — the finance
    officer covering a receipt, which is the one edit that stays open — the
    rows it finds are **superseded rather than deleted**
    (:func:`_retire_constraint_rows`), and each new row carries the decision
    recorded about that step so far (:func:`_decisions_so_far`), as far as
    this resolution allows it to (:func:`_carried_decision`). Who overrode a
    step and why is the record the override mechanism exists to leave; losing
    it to an unrelated receipt edit was #555, and so was handing the payout
    back to the board that had already waived it.
    """
    decisions = _decisions_so_far(statement)
    _retire_constraint_rows(statement)
    ApprovalConstraint.objects.bulk_create(
        [
            ApprovalConstraint(
                statement=statement,
                position=position,
                name=row["name"],
                description=row["description"],
                applicable=row["applicable"],
                required=row["required"],
                eligible_member_ids=row["eligible"],
                excluded=row["excluded"],
                error=row["error"],
                rule_version=version,
                frozen_at=frozen,
                **_carried_decision(decisions.get(row["name"], {}), row),
            )
            for position, row in enumerate(resolve_constraints(statement, result))
        ]
    )


def current_constraint_rows(statement: Any) -> list[dict[str, Any]]:
    """The same question as at submission, asked again at signing time.

    The frozen :class:`~finance.store.ApprovalConstraint` rows are the record
    of *what the rules named when the statement was handed in*, and they stay
    exactly that. They are the wrong thing to **gate** on, though, and the
    reason is concrete: Heidelberg's one constraint names whoever holds
    ``process_statementsubmitted``, resolved at submission — so a treasurer
    appointed while statements are in flight held the capability, passed the
    permission check, and still could not sign the statements that were already
    waiting. Before the store they could. Freezing who *may act* is the wrong
    half to freeze.

    So eligibility is re-asked, under two bounds that make re-asking safe:

    **Only the same rules may answer.** A re-resolution is accepted only when
    the ruleset that produced it is the version the rows were frozen under
    (``ApprovalConstraint.rule_version``). The fallback in
    :func:`loaded_ruleset` is otherwise enough to replace a section's rules
    with the *reference* ruleset — on nothing worse than a Kompass upgrade that
    makes an old snapshot unloadable, or a statement created before the first
    import — and the reference ruleset has no forbids, so the conflict of
    interest the section wrote would quietly evaporate.

    **A frozen restriction is sticky.** The frozen rows are the spine: every
    one of them survives, with its own ``applicable`` and ``required``, and
    anybody a *forbid* excluded at submission stays excluded however today's
    resolution comes out. Only the permission exclusions are re-asked, because
    the capability is a question about now. So the appointed treasurer gets in
    and the excluded payee cannot, which is the whole point of asking again.

    The rows also carry the answer that was *reached* — a row's own
    ``satisfied`` — and these rows carry it through untouched, because whether
    to read it is not this function's call: the gate counts the signatures
    again, which is what :func:`finance.engine.approval.states` does unless a
    caller asks it for ``recorded=True``, and the record is the only caller
    that asks.
    """
    frozen = list(statement.approval_constraint_set.all())
    if not frozen:
        # Nothing live. Either this statement never had constraints — a
        # ruleset that asks for no signature, which is approved by the
        # capability alone — or its rules reported a problem after submission
        # and the rows were retired, where answering "no constraints" means
        # answering *approved* and a broken statement read as signed off by
        # nobody. The rows the record last asked for say what it still needs
        # (:func:`latest_constraint_rows`). The payout was refused either way,
        # by `_pay_out`'s own check on the problem, so this is what a person
        # is told rather than where the money stops.
        frozen = latest_constraint_rows(statement)
    if not frozen:
        return []
    rows = _rows_from_the_same_rules(statement, frozen)
    if rows is None:
        return [row.as_row() for row in frozen]
    today = {row["name"]: row for row in rows}
    merged = []
    for record in frozen:
        base = record.as_row()
        fresh = today.get(record.name)
        if fresh is None:
            # The same rules cannot stop naming a constraint they named — the
            # transfers are frozen too — so this is impossible rather than
            # merely unlikely. Keeping the row is what makes it harmless.
            merged.append(base)
            continue
        sticky = [
            item for item in base["excluded"] if str(item.get("forbid", "")) != PERMISSION_EXCLUSION
        ]
        barred = {int(item["member"]) for item in sticky}
        excluded = list(sticky) + [
            item for item in fresh["excluded"] if int(item["member"]) not in barred
        ]
        merged.append(
            {
                **base,
                "eligible": [member for member in fresh["eligible"] if int(member) not in barred],
                "excluded": excluded,
                "error": fresh["error"] or base["error"],
            }
        )
    return merged


def _rows_from_the_same_rules(
    statement: Any, frozen: list[ApprovalConstraint]
) -> list[dict[str, Any]] | None:
    """Today's resolution, or ``None`` if today's rules are not the same rules.

    "The same" is the version hash the rows carry. A row frozen before the
    store recorded one (``""``) is answered by the record alone: there is
    nothing to compare, and guessing in the permissive direction is what this
    function exists to prevent.
    """
    version = {row.rule_version for row in frozen}
    try:
        # `loaded_ruleset` is inside the `try` rather than above it, and stays
        # there now that it degrades on its own (#553): the reason it was
        # moved in was that it caught only the two exceptions a *refused*
        # snapshot raises, so a module body raising anything else came
        # straight out of it, through `live_approval_states`, and answered the
        # approval page and the `/approval` endpoint with a 500. That is fixed
        # at the source, where the other callers needed it too; keeping the
        # call in here is what makes this function's own promise — degrade to
        # the frozen rows, however re-resolving fails — not depend on which
        # of the two places the failure comes from.
        ruleset, loaded = loaded_ruleset(statement)
        if version != {loaded} or not loaded:
            logger.warning(
                "the approval of statement %s is not re-resolved: frozen under %s, loaded %r",
                statement.pk,
                ", ".join(sorted(version)) or "nothing",
                loaded,
            )
            return None
        result = (
            result_from_rows(statement) if rows_exist(statement) else evaluate_statement(statement)
        )
        return resolve_constraints(statement, result)
    except Exception as problem:  # the rules are there but will not run
        logger.warning("re-resolving the approval of %s failed: %s", statement.pk, problem)
        return None


def result_from_rows(statement: Any) -> Result:
    """The statement's frozen record, as a :class:`Result`.

    Reading rows rather than re-running the rules is the point of materialising
    them: a settled statement renders, generates its transactions and prints
    its summary from what was written down when it was handed in, and the code
    that produced it never runs again.
    """
    rows = live_rows(statement)
    transfers = tuple(row_as_transfer(row) for row in rows)
    balance = transfers[-1] if rows and rows[-1].rule_id == "balance" else None
    return Result(transfers=transfers, errors=(), checks=(), declarations=(), balance=balance)


def row_as_transfer(row: Obligation) -> Transfer:
    """One obligation row as the transfer it was written from."""
    return Transfer(
        source=_party_of(row.source_kind, row.source_member_id),
        destination=_party_of(row.destination_kind, row.destination_member_id),
        amount=row.amount,
        category=row.category,
        rule_id=row.rule_id,
        label=row.label,
        explanation=row.explanation,
    )


def _party_key(party: Any) -> tuple[str, int | None]:
    """``(kind, member id)`` for a transfer's party, as a row stores it.

    The engine's own key function, not a second one that agrees with it by
    coincidence: what `verify` compares has to be what the arithmetic netted.
    """
    return party_key(party)


def _party_of(kind: str, member_id: int | None) -> Any:
    if kind == MEMBER and member_id is not None:
        return Member(MemberId(member_id))
    if kind == PARTICIPANTS:
        return Participants()
    return Section()


def freeze(statement: Any) -> tuple[Obligation, ...]:
    """Freeze the statement's rows, because it has just been handed in."""
    return materialise(statement, freeze=True)


def rows_exist(statement: Any) -> bool:
    """Whether the statement has a materialised record to read.

    Counted off the prefetch rather than with ``.exists()``, so that a list
    view which prefetched the rows answers this without a query per statement —
    and :func:`result_from_rows` then reads the same cached list.
    """
    return statement.pk is not None and len(live_rows(statement)) > 0


def verify(statements: Any, *, sample: int = 10) -> list[str]:
    """Re-check what is stored against itself; one message per problem.

    Three things, and they are the three ways a stored version can stop meaning
    what it said: a row whose sources no longer hash to its manifest, a
    statement bound to a closure nobody imported, and a settled statement whose
    obligations no longer reproduce. The third is the real audit — it replays
    the rules from the statement's own snapshot and compares to the cent.

    ``statements`` is passed in rather than queried here, because the engine
    does not import the models that use it.
    """
    problems: list[str] = []
    known = set()
    for row in RuleSet.objects.all():
        known.add(row.hash)
        if manifest(row.sources) != row.manifest:
            problems.append(f"{row}: the stored sources do not match the stored manifest")
        if version_hash(row.sources, row.params) != row.hash:
            problems.append(f"{row}: the stored version does not hash to the stored hash")
    replayed = 0
    for statement in statements:
        digest = statement.ruleset_hash
        if digest and digest not in known:
            problems.append(
                f"statement {statement.pk} is bound to {digest[:12]}, which is not imported"
            )
        rows = live_rows(statement)
        if not rows or not statement.confirmed or replayed >= sample:
            continue
        if rows[0].rule_id == "legacy":
            # Back-filled from the transactions of a statement that was paid
            # out before there were rules to replay: there is nothing to
            # reproduce, and saying so is better than a false alarm.
            continue
        replayed += 1
        snapshot = statement.ruleset_snapshot or {}
        try:
            ruleset = ruleset_from_sources(snapshot.get("sources", {}))
        except Exception as refused:
            # A snapshot that will not load is a *finding*, however it fails.
            # Narrower, the two refusal types were reported and everything
            # else — a renamed `kompass.rules`, a section's own exception —
            # came out of this loop: the command died with a traceback instead
            # of the `CommandError` that lists what is wrong, and
            # `tasks.verify_rulesets`, which is this function and nothing
            # else, errored having audited nothing. Reporting keeps both: the
            # command is still loud, because a non-empty list raises there.
            problems.append(f"statement {statement.pk}: {type(refused).__name__}: {refused}")
            continue
        result = evaluate(ruleset, statement_context(statement, ruleset))
        # Who, as well as how much: rows naming member A against a replay
        # resolving member B is exactly the kind of drift this is for, and
        # comparing only the amounts reported it as agreement.
        now = [
            (
                t.category,
                t.rule_id,
                t.amount,
                _party_key(t.source),
                _party_key(t.destination),
            )
            for t in result.transfers
        ]
        then = [
            (
                row.category,
                row.rule_id,
                row.amount,
                (row.source_kind, row.source_member_id),
                (row.destination_kind, row.destination_member_id),
            )
            for row in rows
        ]
        if now != then:
            problems.append(
                f"statement {statement.pk} does not reproduce: {then} persisted, {now} replayed"
            )
    return problems
