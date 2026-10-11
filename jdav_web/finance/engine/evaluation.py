"""Running a ruleset against a context, and closing the books afterwards.

:func:`evaluate` is the whole of the engine's arithmetic. It calls into the
ruleset three times — ``inputs``, ``transfers``, ``checks`` — and everything it
gets back it distrusts: an amount finer than a cent, a transfer with nobody at
one end, an exception out of a section's own Python. None of those may take a
finance page down, so each one comes back as a message in
:attr:`Result.errors`, and while that list is non-empty nothing is persisted
and no money moves.

The one amount the engine computes itself is the balancing transfer. A ruleset
declares the two parties and the category (:attr:`kompass.rules.Ruleset.balance`)
and the engine resolves the amount that brings one of them to zero, so "the
statement adds up" is not an assertion anybody can forget to make.
"""

import traceback
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import replace
from decimal import Decimal

from finance.rules_api import CENT
from finance.rules_api import Check
from finance.rules_api import Input
from finance.rules_api import Inputs
from finance.rules_api import Member
from finance.rules_api import Participants
from finance.rules_api import Party
from finance.rules_api import RuleContext
from finance.rules_api import RuleError
from finance.rules_api import Ruleset
from finance.rules_api import Section
from finance.rules_api import Transfer

from .guard import no_queries

#: What an unanswered declaration of each type reads as.
_EMPTY: dict[str, object] = {
    "money": Decimal("0.00"),
    "int": 0,
    "bool": False,
    "text": "",
    "choice": None,
    "member": None,
    "member_set": (),
}

_PARTY_TYPES = (Member, Section, Participants)


@dataclass(frozen=True)
class Result:
    """What one evaluation produced.

    :attr:`transfers` is the whole answer, balancing transfer included, in the
    order the rules declared it. The rest is what a person needs to act on the
    statement: the questions it should have asked, the preconditions for
    handing it in, and what is wrong with it.
    """

    #: Every transfer, the engine's balancing one last (see :attr:`balance`).
    transfers: tuple[Transfer, ...]
    #: One sentence per problem; while this is non-empty, nothing is persisted.
    errors: tuple[str, ...]
    #: The preconditions, satisfied or not.
    checks: tuple[Check, ...]
    #: The input declarations this context produced.
    declarations: tuple[Input, ...]
    #: The engine-built balancing transfer, or ``None`` when evaluation failed
    #: outright.
    balance: Transfer | None

    @property
    def rule_transfers(self) -> tuple[Transfer, ...]:
        """The transfers the ruleset itself returned, without the balance."""
        if self.balance is None:
            return self.transfers
        return self.transfers[:-1]

    @property
    def ok(self) -> bool:
        """Whether the statement resolved without a problem."""
        return not self.errors

    def of_category(self, category: str) -> tuple[Transfer, ...]:
        """Every rule transfer in ``category``, in declaration order."""
        return tuple(t for t in self.rule_transfers if t.category == category)

    def total_of(self, category: str) -> Decimal:
        """The sum of ``category``, to the cent (``0.00`` when there is none)."""
        return sum_amounts(self.of_category(category))

    def net_out(self, party: Party) -> Decimal:
        """What ``party`` pays out net over the rule transfers.

        Positive when the party is out of pocket. The balancing transfer is
        left out, because it is defined as the amount that makes this zero.
        """
        total = Decimal("0.00")
        for transfer in self.rule_transfers:
            if transfer.source == party:
                total += transfer.amount
            if transfer.destination == party:
                total -= transfer.amount
        return total

    def amount_for(self, member: Member) -> Decimal:
        """What ``member`` receives net, over every transfer."""
        total = Decimal("0.00")
        for transfer in self.transfers:
            if transfer.destination == member:
                total += transfer.amount
            if transfer.source == member:
                total -= transfer.amount
        return total

    def members(self) -> tuple[Member, ...]:
        """Every member a transfer touches, in the order they first appear."""
        seen: list[Member] = []
        for transfer in self.transfers:
            for party in (transfer.destination, transfer.source):
                if isinstance(party, Member) and party not in seen:
                    seen.append(party)
        return tuple(seen)


def sum_amounts(transfers: Iterable[Transfer]) -> Decimal:
    """The cent-exact sum of ``transfers``' amounts, ``0.00`` when empty."""
    total = Decimal("0.00")
    for transfer in transfers:
        total += transfer.amount
    return total


def _is_cent_exact(amount: Decimal) -> bool:
    if not amount.is_finite():
        return False
    exponent = amount.as_tuple().exponent
    return isinstance(exponent, int) and exponent >= -2


def _validate(transfers: Iterable[object]) -> tuple[list[Transfer], list[str]]:
    """Accept what is a transfer of whole cents, and report the rest."""
    accepted: list[Transfer] = []
    problems: list[str] = []
    for index, candidate in enumerate(transfers):
        if not isinstance(candidate, Transfer):
            problems.append(f"rule returned {type(candidate).__name__} instead of a Transfer")
            continue
        where = f"transfer {candidate.rule_id}" if candidate.rule_id else f"transfer #{index}"
        if not isinstance(candidate.source, _PARTY_TYPES):
            problems.append(f"{where} has no source party")
            continue
        if not isinstance(candidate.destination, _PARTY_TYPES):
            problems.append(f"{where} has no destination party")
            continue
        if not isinstance(candidate.amount, Decimal):
            problems.append(
                f"{where} has a {type(candidate.amount).__name__} amount, not a Decimal"
            )
            continue
        if not _is_cent_exact(candidate.amount):
            problems.append(f"{where} has the amount {candidate.amount}, which is not whole cents")
            continue
        accepted.append(replace(candidate, amount=candidate.amount.quantize(CENT)))
    return accepted, problems


def _balance_for(ruleset: Ruleset, transfers: list[Transfer]) -> Transfer:
    """The one transfer that closes the books, with the amount resolved here."""
    source, destination, category = ruleset.balance
    if not isinstance(source, _PARTY_TYPES) or not isinstance(destination, _PARTY_TYPES):
        raise TypeError(f"the ruleset's balance declaration names {source!r} and {destination!r}")
    amount = Decimal("0.00")
    for transfer in transfers:
        if transfer.source == destination:
            amount += transfer.amount
        if transfer.destination == destination:
            amount -= transfer.amount
    if amount < 0:
        source, destination, amount = destination, source, -amount
    return Transfer(
        source=source,
        destination=destination,
        amount=amount.quantize(CENT),
        category=category,
        rule_id="balance",
        label="",
        explanation="",
    )


def _answered(declarations: Iterable[Input], ctx: RuleContext) -> Inputs:
    """The answers to ``declarations``, with an empty value for the unanswered.

    The declarations are the authority: an answer to a question the ruleset
    stopped asking is dropped, and a question nobody answered reads as that
    type's empty value rather than raising.
    """
    answers: dict[str, object] = {}
    for declaration in declarations:
        try:
            answers[declaration.key] = ctx.inputs.raw(declaration.key)
        except RuleError:
            answers[declaration.key] = _EMPTY.get(declaration.type)
    return Inputs(answers)


def evaluate(ruleset: Ruleset, ctx: RuleContext) -> Result:
    """Resolve ``ctx`` against ``ruleset``.

    Never raises: a ruleset that does lands in :attr:`Result.errors` with its
    traceback, pointing at the line in the section's own rules.
    """
    declarations: tuple[Input, ...] = ()
    try:
        with no_queries():
            declarations = tuple(ruleset.inputs(ctx))
            answered = replace(ctx, inputs=_answered(declarations, ctx))
            returned, reported = ruleset.transfers(answered)
            checks = tuple(ruleset.checks(answered))
            transfers, problems = _validate(returned)
            balance = _balance_for(ruleset, transfers)
    except Exception as exception:
        return Result(
            transfers=(),
            errors=(_traceback_error(exception),),
            checks=(),
            declarations=declarations,
            balance=None,
        )
    errors = [str(message) for message in reported] + problems
    return Result(
        transfers=tuple(transfers) + (balance,),
        errors=tuple(errors),
        checks=checks,
        declarations=declarations,
        balance=balance,
    )


def _traceback_error(exception: BaseException) -> str:
    """The message a person sees when a section's rules break.

    The traceback is part of it on purpose: the rules are the section's own
    code, in the section's own repository, and the line number is the fastest
    route to the fix. Nothing in it is data about anybody.
    """
    formatted = "".join(
        traceback.format_exception(type(exception), exception, exception.__traceback__)
    )
    return f"the section's rules failed: {exception}\n{formatted}"
