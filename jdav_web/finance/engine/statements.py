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

from .approval import resolve_eligibility
from .context import build_context
from .context import parameters
from .context import permission_holders
from .errors import RulesetInvalid
from .errors import RulesetRejected
from .evaluation import evaluate
from .evaluation import Result
from .guard import no_queries
from .loader import manifest
from .versions import active_version
from .versions import decimal_params
from .versions import ruleset_from_sources
from .versions import version_hash

logger = logging.getLogger(__name__)

#: How a party is written to a row, and read back from one.
_KIND_OF = {Section: SECTION, Participants: PARTICIPANTS, Member: MEMBER}


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
    """
    row = active_version()
    if row is not None:
        try:
            return ruleset_from_sources(row.sources)
        except (RulesetInvalid, RulesetRejected):
            logger.warning("the active ruleset %s cannot be loaded; using the reference", row)
    return reference_ruleset


def ruleset_for(statement: Any) -> Ruleset:
    """The ruleset ``statement`` is settled against.

    Its own snapshot where it has one, so that neither a new version nor a
    changed file can move an open statement; the active version otherwise.
    """
    sources = (statement.ruleset_snapshot or {}).get("sources")
    if sources:
        try:
            return ruleset_from_sources(sources)
        except (RulesetInvalid, RulesetRejected):
            logger.warning(
                "statement %s carries a snapshot that cannot be loaded; using the active ruleset",
                statement.pk,
            )
    return active_ruleset()


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
    return build_context(
        statement,
        permissions=ruleset.permissions if actors else (),
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
        statement.approval_constraint_set.all().delete()
        return ()
    members = MemberModel.objects.in_bulk([party.id for party in result.members()])
    names = {pk: member.name for pk, member in members.items()}
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


def _materialise_constraints(statement: Any, result: Result, *, version: str, frozen: Any) -> None:
    """Freeze the signatures the rules ask for, with the forbids applied.

    Routing runs on the *transfers*, after expansion, never on the raw
    statement — which is the ordering §7 of the proposal insists on, because
    "nobody who receives money from this statement" is a question about the
    payout rather than about the form somebody filled in.

    The forbids and the permission re-check are applied *here*, so the stored
    eligible set is already the set that may sign: a predicate cannot be
    persisted, and a statement's approval must not depend on re-running a
    section's Python years later.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset, actors=True)
    # Inside the guard, like `transfers` and `checks`: a rule that resolved its
    # eligible set with a query would freeze today's membership into rows that
    # replay differently in two years, and this is the call where that would
    # have gone unnoticed.
    with no_queries():
        constraints, forbids = ruleset.approval(context, list(result.transfers))
    permitted = {
        member.id
        for codename in (APPROVER_PERMISSION,)
        for member in permission_holders([codename])[codename]
    }
    statement.approval_constraint_set.all().delete()
    rows = []
    for position, constraint in enumerate(constraints):
        eligibility = resolve_eligibility(constraint, forbids, permitted=permitted)
        rows.append(
            ApprovalConstraint(
                statement=statement,
                position=position,
                name=constraint.name[:100],
                description=constraint.description,
                applicable=constraint.applicable,
                required=constraint.required,
                eligible_member_ids=list(eligibility.eligible),
                excluded=[
                    {"member": item.member, "forbid": item.forbid} for item in eligibility.excluded
                ],
                rule_version=version,
                frozen_at=frozen,
            )
        )
    ApprovalConstraint.objects.bulk_create(rows)


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
    """``(kind, member id)`` for a transfer's party, as a row stores it."""
    if isinstance(party, Member):
        return (MEMBER, int(party.id))
    return (_kind_of(party), None)


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
        except (RulesetInvalid, RulesetRejected) as refused:
            problems.append(f"statement {statement.pk}: {refused}")
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
