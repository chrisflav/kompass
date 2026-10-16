"""Who has to sign a statement off, and whether they have.

The rules answer the first half: :meth:`~kompass.rules.Ruleset.approval`
returns an unordered set of :class:`~kompass.rules.Constraint`\\ s (who *may*
sign, and how many signatures that constraint needs) and an unordered set of
:class:`~kompass.rules.Forbid`\\ s (who *may not*, whatever permits them). This
module is the second half: the arithmetic over those two sets.

Four rules, each taken from a system that has had to get it right:

**Forbid trumps permit, and default is deny** (Cedar's precedence). A forbid is
subtracted from every constraint's eligible set before anything is counted, and
no amount of permitting puts somebody back.

**One signature counts against every constraint it satisfies** (GitLab's
approval rules). Signing once as a member of two eligible sets advances both,
because the person signed the statement, not the rule.

**Applicable and satisfied are separate states** (Gerrit's ``applicableIf``
versus ``submittableIf``). A constraint that does not apply is reported as not
applying, rather than vanishing: "no signature was needed" and "a signature was
given" are different things to read in an audit trail two years later.

**An override is a state, not an absence.** Overriding a constraint records who
did it and why; the constraint stays in the list, marked. An override is itself
subject to the forbids: somebody a forbid excluded may not override the
constraint it excluded them from, because recording that they did is a
mitigation and not a control.

**An empty eligible set means nobody, not anybody.** Whatever made it empty —
a forbid that caught everyone, a permission check that rejected everyone, a
role nobody holds, a filter that matched nobody — the constraint stands open
and no signature satisfies it. The opposite reading is one bug that produces
four: a forbid that excluded everyone disables itself, a permission check that
rejected everyone grants the right to everyone, a vacant role lets the payee
sign their own payout past a forbid written for them, and all three are
reported as *satisfied*.

An earlier version of this module read "nobody was excluded" as "the rules
named nobody on purpose", which is a proxy for intent and fails whenever a
restriction is empty for an innocent reason. A section that wants the
capability to decide now says so, on the constraint
(:attr:`kompass.rules.Constraint.anyone_permitted`), and the engine fills the
group in from the permission holders — so the forbids apply to it and nothing
has to be inferred.

What this module does *not* decide is whether somebody may sign at all. That is
the capability layer — a global permission, checked by the view — and the
eligible set the rules name is re-checked against it, so that a section's
configuration repository can never hand anybody a right they do not have
(CODEOWNERS' rule, that a named owner must actually have write access).
"""

from collections.abc import Iterable
from collections.abc import Mapping
from collections.abc import Sequence
from dataclasses import dataclass
from dataclasses import field
from typing import Any

from finance.rules_api import Constraint
from finance.rules_api import Forbid
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import RuleError

#: The ``forbid`` name an exclusion carries when it was the permission system
#: and not a section's rule that removed somebody. It is the one exclusion that
#: is re-asked rather than respected: the capability is checked at the moment
#: somebody acts, so losing it at submission time is not a verdict for ever.
PERMISSION_EXCLUSION = "permission"


@dataclass(frozen=True)
class Exclusion:
    """One person a forbid removed from one constraint, and which forbid."""

    member: int
    forbid: str


@dataclass(frozen=True)
class Eligibility:
    """Who may sign one constraint, once the forbids have been applied."""

    #: Who the rules named and nothing excluded, by member id.
    eligible: tuple[int, ...]
    #: Who was removed, and by which forbid.
    excluded: tuple[Exclusion, ...]


@dataclass(frozen=True)
class ConstraintState:
    """One constraint, as a person reading the statement sees it."""

    name: str
    description: str
    applicable: bool
    required: int
    #: Who may sign, after forbids and the permission re-check.
    eligible: tuple[int, ...]
    #: Who signed, of those.
    signed_by: tuple[int, ...]
    #: Whether the quorum is in.
    satisfied: bool
    #: Whether somebody overrode it instead.
    overridden: bool = False
    #: Who overrode it, and why.
    overridden_by: int | None = None
    override_reason: str = ""
    #: Who was removed from the eligible set, and by which forbid.
    excluded: tuple[Exclusion, ...] = field(default_factory=tuple)
    #: Why this constraint could not be resolved at all, if it could not. A
    #: constraint with an error names nobody and is satisfied by nobody.
    error: str = ""

    @property
    def unsatisfiable(self) -> bool:
        """Whether no signature can satisfy this constraint as it stands.

        Either its rules could not be resolved, or there is nobody left in the
        group. Both are states to be read and fixed, not states to be signed
        away — and this is what keeps "nobody is eligible" from meaning
        "anybody will do".
        """
        return bool(self.error) or not self.eligible

    @property
    def open(self) -> bool:
        """Whether this constraint still stands in the way of a payout."""
        return self.applicable and not (self.satisfied or self.overridden)

    @property
    def missing(self) -> int:
        """How many more signatures it needs."""
        if not self.applicable or self.satisfied or self.overridden:
            return 0
        return max(self.required - len(self.signed_by), 0)


def resolve_eligibility(
    constraint: Constraint, forbids: Iterable[Forbid], permitted: Iterable[int] | None = None
) -> Eligibility:
    """Who may sign ``constraint``: named, minus forbidden, minus unpermitted.

    ``permitted`` is the set of member ids that hold the capability to sign at
    all. ``None`` means "do not re-check", which is for a dry run; the real
    flow always passes it, because the rules' word about who may act is never
    the last word.

    A constraint that names nobody and sets
    :attr:`~kompass.rules.Constraint.anyone_permitted` has its group *filled
    in* from ``permitted`` here, before the forbids run — so a section can say
    "whoever may act on statements, except whoever this one pays" without
    naming anybody, and the exception still bites.
    """
    excluded: list[Exclusion] = []
    eligible: list[int] = []
    allowed = None if permitted is None else set(permitted)
    candidates = constraint.eligible
    if not candidates and constraint.anyone_permitted and allowed is not None:
        candidates = tuple(Member(MemberId(member_id)) for member_id in sorted(allowed))
    for member in candidates:
        forbid = _first_forbid(member, forbids)
        if forbid is not None:
            excluded.append(Exclusion(member=int(member.id), forbid=forbid))
            continue
        if allowed is not None and int(member.id) not in allowed:
            excluded.append(Exclusion(member=int(member.id), forbid=PERMISSION_EXCLUSION))
            continue
        eligible.append(int(member.id))
    return Eligibility(eligible=tuple(eligible), excluded=tuple(excluded))


def _first_forbid(member: Member, forbids: Iterable[Forbid]) -> str | None:
    """The name of the first forbid that applies to ``member``, or ``None``.

    A predicate that raises is a :class:`~kompass.rules.RuleError`, not a
    shrug. Deciding that a broken forbid excludes nobody is deciding, against
    the section's intent, that its most restrictive rule does not apply —
    which is the one direction this code may never fail in.
    """
    for forbid in forbids:
        try:
            applies = forbid.applies_to(member)
        except Exception as problem:
            raise RuleError(
                f"the forbid {forbid.name!r} failed on member {int(member.id)}: {problem}"
            ) from problem
        if applies:
            return forbid.name
    return None


def states(
    rows: Sequence[Mapping[str, Any]],
    signatures: Iterable[int],
    *,
    uncredited: Iterable[Any] = (),
    recorded: bool = False,
) -> list[ConstraintState]:
    """The state of each constraint, given who has signed.

    ``rows`` are the constraints as mappings — name, description, applicable,
    required, eligible, excluded, overridden, error — so that this stays a pure
    function over data and the model layer owns the rows.

    ``recorded`` says which question is being asked, and the two answers are
    meant to differ. Left ``False`` — the **gate** — ``satisfied`` is counted
    from ``signatures`` against ``eligible``, every time. Passed ``True`` — the
    **record** — it is read from the row's own ``satisfied``, because the row
    holds what was true when the statement was signed and the *frozen*
    eligible set it would otherwise be recounted against cannot contain
    somebody who was appointed after submission: recounting reported an
    ordinary signature as no signature at all.

    It is an argument rather than "the row carries the key": presence as the
    signal meant a row builder that happened to include ``satisfied: False``
    froze the gate at *unsatisfied*, and nothing could ever be signed again —
    with no type error to say so, and no caller having asked for anything.

    ``uncredited`` are the *signers* whose signature cannot be attributed to a
    member: an admin account with no member record, which the capability layer
    let in. They are a set rather than a count, and that is the whole of the
    point — counting them let one unlinked account satisfy a quorum of two by
    pressing the button twice, which is how a four-eyes rule is defeated by a
    single pair. They still count towards a quorum, because Kompass has always
    let whoever holds the permission confirm, but only ever as one signature
    each, and never towards a constraint whose eligible set was emptied by a
    forbid.
    """
    signed = set(signatures)
    anonymous = set(uncredited)
    resolved: list[ConstraintState] = []
    for row in rows:
        eligible = tuple(int(member) for member in row.get("eligible", ()) or ())
        excluded = tuple(
            Exclusion(member=int(item["member"]), forbid=str(item["forbid"]))
            for item in row.get("excluded", ()) or ()
        )
        error = str(row.get("error", "") or "")
        required = int(row.get("required", 1) or 0)
        if error or not eligible:
            # Nobody. Either the rules could not be resolved at all, or there
            # is no group left to sign — and in both cases the constraint
            # stands open rather than opening up. A section that wants the
            # capability to decide says so on the constraint, and the engine
            # fills the group in (`resolve_eligibility`), so by the time a row
            # is written an empty group is an empty group.
            by: tuple[int, ...] = ()
            given = 0
        else:
            by = tuple(sorted(signed & set(eligible)))
            given = len(by) + len(anonymous)
        overridden = bool(row.get("overridden", False))
        resolved.append(
            ConstraintState(
                name=str(row.get("name", "")),
                description=str(row.get("description", "")),
                applicable=bool(row.get("applicable", True)),
                required=required,
                eligible=eligible,
                signed_by=by,
                satisfied=bool(row.get("satisfied", False)) if recorded else given >= required,
                overridden=overridden,
                overridden_by=row.get("overridden_by"),
                override_reason=str(row.get("override_reason", "")),
                excluded=excluded,
                error=error,
            )
        )
    return resolved


def fully_approved(constraint_states: Iterable[ConstraintState]) -> bool:
    """Whether every constraint that applies has its quorum or an override.

    No constraints at all means yes: a ruleset that asks for no signature is a
    ruleset that is happy with the capability check, which is what Heidelberg's
    predecessor did.
    """
    return not any(state.open for state in constraint_states)


def may_sign(constraint_states: Iterable[ConstraintState], member_id: int) -> bool:
    """Whether ``member_id`` can still advance any open constraint.

    Used by the object permission: somebody who is not named by any open
    constraint has nothing to sign, and the button is not offered.
    """
    for state in constraint_states:
        if not state.open or state.unsatisfiable:
            continue
        if member_id in state.eligible:
            return True
    return False
