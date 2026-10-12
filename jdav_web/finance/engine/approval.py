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
did it and why; the constraint stays in the list, marked.

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
            excluded.append(Exclusion(member=int(member.id), forbid="permission"))
            continue
        eligible.append(int(member.id))
    return Eligibility(eligible=tuple(eligible), excluded=tuple(excluded))


def _first_forbid(member: Member, forbids: Iterable[Forbid]) -> str | None:
    for forbid in forbids:
        try:
            if forbid.applies_to(member):
                return forbid.name
        except Exception:
            # A section's predicate that raises excludes nobody; the engine
            # does not get to decide that it meant to.
            continue
    return None


def states(
    rows: Sequence[Mapping[str, Any]],
    signatures: Iterable[int],
    *,
    uncredited: int = 0,
) -> list[ConstraintState]:
    """The state of each persisted constraint, given who has signed.

    ``rows`` are the stored constraints as mappings — name, description,
    applicable, required, eligible, excluded, overridden — so that this stays a
    pure function over data and the model layer owns the rows.

    ``uncredited`` counts signatures whose signer the system cannot name: an
    admin account with no member record behind it, which the capability layer
    let in. They count towards every quorum, because refusing them would be a
    new rule — Kompass has always let whoever holds the permission confirm —
    and because an unattributable signature is still recorded as one.
    """
    signed = set(signatures)
    resolved: list[ConstraintState] = []
    for row in rows:
        eligible = tuple(int(member) for member in row.get("eligible", ()) or ())
        # An eligible set that came out empty is not a constraint nobody can
        # satisfy: it is a section that named nobody, which is where Kompass
        # was before there were constraints at all. The capability layer then
        # decides alone, as it always did, rather than making the statement
        # unpayable.
        by = tuple(sorted(signed & set(eligible))) if eligible else tuple(sorted(signed))
        required = int(row.get("required", 1) or 0)
        given = len(by) + uncredited
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
                excluded=tuple(
                    Exclusion(member=int(item["member"]), forbid=str(item["forbid"]))
                    for item in row.get("excluded", ()) or ()
                ),
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
        if not state.open:
            continue
        if not state.eligible or member_id in state.eligible:
            return True
    return False
