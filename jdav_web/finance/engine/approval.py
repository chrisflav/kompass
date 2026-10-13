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

**An empty eligible set means nobody, not anybody.** If the rules named people
and every one of them was removed — by a forbid, or because they do not hold
the capability — the constraint stands open and no signature satisfies it. The
opposite reading is the one bug that produces three: a forbid that excluded
everyone would disable itself, a permission check that rejected everyone would
grant the right to everyone, and the person the forbid was written for could
sign their own payout. The one case where the capability layer decides alone is
a constraint that named **nobody in the first place**, which is where Kompass
was before there were constraints at all; the exclusions recorded on the
constraint are what tells the two apart.

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

        Either its rules could not be resolved, or everybody they named was
        excluded. Both are states to be read and fixed, not states to be
        signed away — and this is what keeps "nobody is eligible" from
        meaning "anybody will do".
        """
        return bool(self.error) or (not self.eligible and bool(self.excluded))

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
    """
    excluded: list[Exclusion] = []
    eligible: list[int] = []
    allowed = None if permitted is None else set(permitted)
    for member in constraint.eligible:
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
) -> list[ConstraintState]:
    """The state of each constraint, given who has signed.

    ``rows`` are the constraints as mappings — name, description, applicable,
    required, eligible, excluded, overridden, error — so that this stays a pure
    function over data and the model layer owns the rows.

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
        if error or (not eligible and excluded):
            # Nobody. Either the rules could not be resolved at all, or they
            # named people and every one of them was removed — and in both
            # cases the constraint stands open rather than opening up.
            by: tuple[int, ...] = ()
            given = 0
        elif eligible:
            by = tuple(sorted(signed & set(eligible)))
            given = len(by) + len(anonymous)
        else:
            # The rules named nobody at all: the capability decides alone, as
            # it did before there were constraints.
            by = tuple(sorted(signed))
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
                satisfied=given >= required,
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
        if not state.eligible or member_id in state.eligible:
            return True
    return False
