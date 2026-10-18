"""Cases: a ruleset's own tests, as data beside it.

A case is one JSON file holding a whole context — parameters, answers, bills, a
trip — and what the rules are expected to make of it. It needs no database and
no fixtures, which is the point: a section can run its cases in its own
repository's CI against the image it deploys, and Kompass runs the reference
ruleset's cases in its suite. It is run *inside* that image rather than beside
it: this module reaches Django through the query guard and through
:mod:`finance.engine`'s package import, so "no fixtures" is the claim and "no
Django" is not.

JSON rather than YAML because Kompass has no YAML library and this refactor
adds no dependency. Money is written as a string (``"42.69"``) so that a case
file never carries a binary float. Parties are written as ``"SECTION"``,
``"PARTICIPANTS"`` or a member id. An answer in ``inputs`` is written as JSON
and typed by the declaration that asks for it when the case runs
(:func:`answered`), so a case can answer any input a ruleset declares and not
only the four the reference ruleset happens to.

A case file::

    {
      "name": "allowance only",
      "params": {"ALLOWANCE_PER_DAY": "22"},
      "inputs": {"allowance_to": [7]},
      "excursion": {"duration": "2.0", "leaders": [7], "staff_count": 1,
                    "approved_staff_count": 2},
      "expect": {
        "transfers": [
          ["SECTION", "7", "44.00", "allowance"],
          ["PARTICIPANTS", "SECTION", "44.00", "participant_contribution"]
        ],
        "errors": []
      }
    }

Each expected transfer is ``[source, destination, amount, category]``, in the
order the rules produced them, and the engine's balancing transfer is the last
one — a case that leaves it out fails, which is the point: it says out loud
what the participants end up contributing. ``checks`` may list the expected
state of each check; leaving it out means the case does not look at them.

Only the keys a case cares about have to be there; everything else takes a
quiet default — no bills, no trip, no answers, every parameter unset.
"""

import json
from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from finance.rules_api import Bill
from finance.rules_api import CONTEXT_VERSION
from finance.rules_api import Excursion
from finance.rules_api import Inputs
from finance.rules_api import LJP
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Params
from finance.rules_api import Participant
from finance.rules_api import PARTICIPANTS
from finance.rules_api import Party
from finance.rules_api import Roles
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset
from finance.rules_api import SECTION
from finance.rules_api import StatementInfo
from finance.rules_api import Transfer

from .answers import typed_inputs
from .declared import ask
from .declared import supplied
from .evaluation import evaluate


def party(value: Any) -> Party:
    """A party as a case file writes it: ``"SECTION"``, ``"PARTICIPANTS"``, id."""
    if value == "SECTION":
        return SECTION
    if value == "PARTICIPANTS":
        return PARTICIPANTS
    return Member(MemberId(int(value)))


def party_name(value: Party) -> str:
    """The inverse of :func:`party`, for a legible failure message."""
    if isinstance(value, Member):
        return str(value.id)
    return "SECTION" if value == SECTION else "PARTICIPANTS"


def _members(values: Iterable[Any]) -> tuple[Member, ...]:
    return tuple(Member(MemberId(int(value))) for value in values)


def _maybe_member(value: Any) -> Member | None:
    return None if value is None else Member(MemberId(int(value)))


def _bills(entries: Iterable[Mapping[str, Any]]) -> tuple[Bill, ...]:
    return tuple(
        Bill(
            id=int(entry.get("id", index + 1)),
            amount=Decimal(str(entry["amount"])),
            covered=bool(entry.get("covered", False)),
            payer=_maybe_member(entry.get("payer")),
            has_proof=bool(entry.get("has_proof", True)),
            description=str(entry.get("description", "")),
        )
        for index, entry in enumerate(entries)
    )


def _ljp(entry: Mapping[str, Any] | None) -> LJP | None:
    if entry is None:
        return None
    return LJP(
        goal=entry.get("goal"),
        participant_count=int(entry.get("participant_count", 0)),
        theoretic_participant_count=int(entry.get("theoretic_participant_count", 0)),
        duration=Decimal(str(entry.get("duration", "0"))),
    )


def _excursion(entry: Mapping[str, Any] | None) -> Excursion | None:
    if entry is None:
        return None
    return Excursion(
        duration=Decimal(str(entry.get("duration", "0"))),
        nights=int(entry.get("nights", 0)),
        kilometers=int(entry.get("kilometers", 0)),
        approach=entry.get("approach", "muscle"),
        leaders=_members(entry.get("leaders", ())),
        staff_count=int(entry.get("staff_count", 0)),
        approved_staff_count=int(entry.get("approved_staff_count", 0)),
        participants=tuple(
            Participant(
                member=Member(MemberId(int(person["member"]))),
                age=person.get("age"),
                age_at_start=person.get("age_at_start", person.get("age")),
                is_leader=bool(person.get("is_leader", False)),
            )
            for person in entry.get("participants", ())
        ),
        ljp=_ljp(entry.get("ljp")),
    )


@dataclass(frozen=True)
class Case:
    """One case file, parsed."""

    name: str
    context: RuleContext
    #: The answers as the file wrote them, untyped. They are typed by the
    #: ruleset's own declarations when the case is run, not when it is parsed:
    #: which key is money and which is a person is the ruleset's to say, and a
    #: case file is parsed without one.
    answers: Mapping[str, Any]
    transfers: tuple[tuple[str, str, str, str], ...]
    errors: tuple[str, ...]
    checks: tuple[bool, ...] | None


def parse_case(data: Mapping[str, Any], *, name: str) -> Case:
    """A case from the mapping a case file holds."""
    expected = data.get("expect", {})
    answers: Mapping[str, Any] = data.get("inputs", {})
    context = RuleContext(
        version=CONTEXT_VERSION,
        params=Params({key: Decimal(str(value)) for key, value in data.get("params", {}).items()}),
        inputs=Inputs(dict(answers)),
        bills=_bills(data.get("bills", ())),
        excursion=_excursion(data.get("excursion")),
        statement=StatementInfo(
            id=data.get("statement", {}).get("id", 1),
            creator=_maybe_member(data.get("statement", {}).get("creator")),
            submitter=_maybe_member(data.get("statement", {}).get("submitter")),
        ),
        # A case says what it says: an empty-but-resolved mapping, so a rule
        # reading a role from one gets "nobody holds it" rather than the
        # refusal an unresolved context would give.
        roles=Roles({}),
        permissions={key: _members(value) for key, value in data.get("permissions", {}).items()},
    )
    checks = expected.get("checks")
    return Case(
        name=str(data.get("name", name)),
        context=context,
        answers=answers,
        transfers=tuple(
            (str(row[0]), str(row[1]), str(row[2]), str(row[3]))
            for row in expected.get("transfers", ())
        ),
        errors=tuple(str(message) for message in expected.get("errors", ())),
        checks=None if checks is None else tuple(bool(value) for value in checks),
    )


def load_cases(directory: Path) -> list[Case]:
    """Every case in ``directory``, in file-name order."""
    return [
        parse_case(json.loads(path.read_text(encoding="utf-8")), name=path.stem)
        for path in sorted(directory.glob("*.json"))
    ]


def _rendered(transfer: Transfer) -> tuple[str, str, str, str]:
    return (
        party_name(transfer.source),
        party_name(transfer.destination),
        str(transfer.amount),
        transfer.category,
    )


def answered(ruleset: Ruleset, case: Case) -> RuleContext:
    """``case``'s context with its answers typed by ``ruleset``'s declarations.

    A case file is JSON, so every answer in it arrives as JSON: money as text,
    a person as an id. This used to be coerced by *name* — four keys the
    Heidelberg rules happen to declare, and everything else passed through — so
    a case answering any other ``money`` input handed the rules a ``str`` and
    ``ctx.inputs.money()`` raised, and a ``member`` input arrived as a bare
    ``int``. Which only ever worked because the reference ruleset's cases use
    exactly those four keys.

    It matters more than it looks: cases gate activation, so until a case can
    express a custom input, the one mechanism that would catch a custom input
    being mishandled is the one that cannot.
    """
    # Inside the guard like every other call into a section's own code, and
    # before `evaluate` opens its own: declaring the form is as much the
    # ruleset's code as resolving the transfers. `ask` is what opens it, and
    # what fills in the parts of a declaration the engine serves — so a case
    # answering a question whose options come from the trip is checked against
    # the people the engine would really have offered.
    declarations = ask(ruleset, case.context)
    return replace(
        case.context,
        inputs=Inputs(
            typed_inputs(declarations, case.answers, supplied(declarations, case.context))
        ),
    )


def run_case(ruleset: Ruleset, case: Case) -> list[str]:
    """What ``case`` got wrong, as one message per difference.

    An empty list is a passing case.
    """
    result = evaluate(ruleset, answered(ruleset, case))
    failures: list[str] = []
    produced = tuple(_rendered(transfer) for transfer in result.transfers)
    if produced != case.transfers:
        failures.append(f"transfers\n  expected {case.transfers}\n  got      {produced}")
    if tuple(result.errors) != case.errors:
        failures.append(f"errors\n  expected {case.errors}\n  got      {tuple(result.errors)}")
    if case.checks is not None:
        states = tuple(check.ok for check in result.checks)
        if states != case.checks:
            failures.append(f"checks\n  expected {case.checks}\n  got      {states}")
    return failures


def run_cases(ruleset: Ruleset, directory: Path) -> dict[str, list[str]]:
    """Every case in ``directory`` that failed, by name."""
    failed: dict[str, list[str]] = {}
    for case in load_cases(directory):
        failures = run_case(ruleset, case)
        if failures:
            failed[case.name] = failures
    return failed
