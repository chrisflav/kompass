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

from finance.parties import MEMBER
from finance.parties import PARTICIPANTS
from finance.parties import SECTION
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

from .answers import EMPTY
from .answers import no_longer_offered
from .answers import typed
from .declared import Asked
from .declared import asking
from .declared import unbounded
from .guard import no_queries

_PARTY_TYPES = (Member, Section, Participants)


def party_key(party: Party) -> tuple[str, int | None]:
    """What makes two parties the same party, for netting and for storage.

    By type and id rather than by equality. :class:`~kompass.rules.Member` is
    a frozen dataclass, so its generated ``__eq__`` is class-exact: a subclass
    a section wrote to carry one extra field would be a *different* party to
    every ``==`` comparison here while being the *same* party to the rows
    (:func:`finance.engine.statements._party_fields` resolves the kind with
    ``isinstance``). Money that nets against one key and is stored under
    another is the shape of the bug the first review round found in
    ``verify()``, so there is one key function and both sides call it — and the
    kinds come from :mod:`finance.parties`, the leaf module that exists so the
    engine and the store cannot drift apart by writing the same three strings
    twice.
    """
    if isinstance(party, Member):
        return (MEMBER, int(party.id))
    if isinstance(party, Participants):
        return (PARTICIPANTS, None)
    return (SECTION, None)


def party_label(party: Party) -> str:
    """A party as an error message names it."""
    if isinstance(party, Member):
        return f"member {int(party.id)}"
    if isinstance(party, Participants):
        return "the participants"
    return "the section"


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
        return _net_out(self.rule_transfers, party)

    def amount_for(self, member: Member) -> Decimal:
        """What ``member`` receives net, over every transfer."""
        return -_net_out(self.transfers, member)

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
    """The one transfer that closes the books, with the amount resolved here.

    What this guarantees, exactly: the party the declaration names as its
    *destination* nets to zero once this transfer is added, and every transfer
    has two ends, so nothing appears from nowhere. What it cannot guarantee is
    that a sensible ruleset was written — the two checks below are the two ways
    a declaration can be nonsense while still producing arithmetic that adds
    up, and both used to pass silently.
    """
    source, destination, category = ruleset.balance
    if not isinstance(source, _PARTY_TYPES) or not isinstance(destination, _PARTY_TYPES):
        raise TypeError(f"the ruleset's balance declaration names {source!r} and {destination!r}")
    if isinstance(source, Member) or isinstance(destination, Member):
        # A person is a payee, not a ledger. Balancing against a member makes
        # whoever it names the residue sink for everything the rules did not
        # account for: `(Member(999), SECTION, …)` resolves, writes a transfer,
        # and leaves that member out of pocket by the remainder with no error
        # at all — which is the one way a ruleset can hand somebody a bill
        # nobody wrote.
        raise TypeError(
            "the balance declaration names "
            f"{party_label(source)} and {party_label(destination)}: it must be "
            "between the section and the participants, because a person is a "
            "payee and not a ledger"
        )
    amount = _net_out(transfers, destination)
    if amount == 0 and _net_out(transfers, source) != 0:
        # The declaration is the wrong way round. The amount is resolved so
        # that the *destination* comes out at zero, so pointing it at a party
        # that is already square — while the source is out of pocket — closes
        # nothing and leaves books that do not add up with a `0.00` row to show
        # for it. The proposal's own §3 and §4.3 sketches are written this way,
        # which is why this is an error with a sentence rather than a silent
        # zero.
        raise TypeError(
            "the balance declaration brings its destination to zero, and this one "
            f"is already there while {source!r} is not: declare it the other way round"
        )
    # The declaration's own destination, before the swap below may exchange the
    # two: that is the party the amount was resolved for, and the only one the
    # engine promises anything about.
    declared = destination
    if amount < 0:
        source, destination, amount = destination, source, -amount
    balance = Transfer(
        source=source,
        destination=destination,
        amount=amount.quantize(CENT),
        category=category,
        rule_id="balance",
        label="",
        explanation="",
    )
    # Post hoc, because the claim is worth more than the derivation: the party
    # this was resolved for must come out at zero. Cheap, and it is the
    # assertion that would catch a future change to the arithmetic above.
    residue = _net_out(transfers + [balance], declared)
    if residue != 0:
        raise TypeError(f"the balancing transfer leaves {party_label(declared)} out by {residue}")
    return balance


def _net_out(transfers: Iterable[Transfer], party: Party) -> Decimal:
    """What ``party`` pays out net over ``transfers``."""
    key = party_key(party)
    total = Decimal("0.00")
    for transfer in transfers:
        if party_key(transfer.source) == key:
            total += transfer.amount
        if party_key(transfer.destination) == key:
            total -= transfer.amount
    return total


def _answered(asked: Asked, ctx: RuleContext) -> tuple[Inputs, list[str]]:
    """The answers a rule reads, and the keys whose answer was dropped.

    Two sets, because a ruleset answers two questions about its form.
    :attr:`~finance.engine.declared.Asked.vocabulary` is
    :meth:`~kompass.rules.Ruleset.inputs`, every key the ruleset may ever read,
    and it decides what is *readable*: a rule that reads a key it declared gets
    a value rather than a :class:`~kompass.rules.RuleError`.
    :attr:`~finance.engine.declared.Asked.form` is
    :meth:`~kompass.rules.Ruleset.relevant_inputs`, the questions still being
    asked, and it decides what is *answered*.

    So the rule for a question the ruleset has stopped asking is the rule for a
    question nobody has answered yet: it reads as that type's empty value. That
    is taxis #579, settled in the direction that costs nothing — **what the form
    does not ask, the rules read as unanswered.** The stored answer to a retired
    question no longer moves money, which was the bug; and reading one is not
    an error, which would have collapsed the whole evaluation into a traceback
    over a question a person cannot even see (the mistake ``EMPTY["choice"]``
    used to make, for the same reason).

    A key ``relevant_inputs`` names and ``inputs`` does not is *not* answered
    here, and is not quietly nothing either: it never reaches the vocabulary,
    so :func:`evaluate` reports it (:attr:`~finance.engine.declared.Asked.widened`).

    A **derived** declaration is resolved here rather than read, and that is
    deliberately the last word. ``build_context`` already resolved it, so for a
    real statement this agrees with what the form showed — but a context can
    also arrive from a case file, from the fuzzer or from a dry run against
    unsaved answers, and on those routes nothing else would. Both resolutions
    ask :mod:`finance.engine.declared` off ``inputs``, so "again" cannot mean
    "differently".

    An answer the declaration **no longer offers** is dropped here, and the key
    is handed back so that :func:`evaluate` can say so. Dropping it where
    nobody could be told — in ``coerce_input``, which has no way to report —
    produced the one state with no witness: a statement owing somebody money
    closing at ``0.00`` with the recipient still named on every page, no error,
    no failing check (the ruleset's own checks read the already-emptied value
    and go vacuous), and ``validity`` answering "everything is correct".
    Reported, it is simply a statement that does not resolve until somebody
    answers the question again.
    """
    # Everything declared reads as unanswered to begin with, so that a question
    # the form is not asking is readable but empty.
    answers: dict[str, object] = {
        declaration.key: EMPTY.get(declaration.type) for declaration in asked.vocabulary
    }
    stored: dict[str, object] = {}
    for declaration in asked.form:
        if declaration.key in asked.supplied:
            # `typed` and not `coerce_input`: a supplied value has no domain to
            # be re-checked against, and a bound it breaks is an error below
            # rather than a quietly empty reading.
            answers[declaration.key] = typed(declaration, asked.supplied[declaration.key])
            continue
        try:
            stored[declaration.key] = ctx.inputs.raw(declaration.key)
        except RuleError:
            answers[declaration.key] = EMPTY.get(declaration.type)
    asked_and_stored = [entry for entry in asked.form if entry.key in stored]
    dropped = no_longer_offered(asked_and_stored, stored)
    for declaration in asked_and_stored:
        answers[declaration.key] = (
            EMPTY.get(declaration.type) if declaration.key in dropped else stored[declaration.key]
        )
    return Inputs(answers), dropped


def evaluate(ruleset: Ruleset, ctx: RuleContext) -> Result:
    """Resolve ``ctx`` against ``ruleset``.

    Never raises: a ruleset that does lands in :attr:`Result.errors` with its
    traceback, pointing at the line in the section's own rules.
    """
    declarations: tuple[Input, ...] = ()
    try:
        with no_queries():
            # Both declaration methods at once, from one call, because the form
            # and the rules have to agree about which answers count (taxis
            # #579) and about where one key's value comes from: `inputs` is
            # what may be read, `relevant_inputs` is what is being asked.
            # Asking only `inputs` was the bug — a ruleset that retires a
            # question went on being paid from an answer the API offers no way
            # to see or change.
            asked = asking(ruleset, ctx)
            declarations = asked.form
            inputs, dropped = _answered(asked, ctx)
            answered = replace(ctx, inputs=inputs)
            returned, reported = ruleset.transfers(answered)
            checks = tuple(ruleset.checks(answered))
            transfers, problems = _validate(returned)
            balance = _balance_for(ruleset, transfers)
            # Three things that are wrong with the *answers or the
            # declarations* rather than with a transfer, reported the same way
            # and for the same reason: each of them leaves the books addable,
            # so nothing refuses on its own, and each of them would otherwise
            # be a figure nobody can account for. While `errors` is non-empty
            # nothing is persisted and no money moves.
            problems += [
                f"the answer to {key!r} is not one these rules offer any more; "
                "it is not read, so answer it again"
                for key in dropped
            ]
            # `asked.form` and not the vocabulary: a derived question the rules
            # have retired is one nobody is asked and no rule reads, so a bound
            # it breaks would be an error with nothing to do about it.
            problems += unbounded(asked.form, asked.supplied)
            problems += [
                f"relevant_inputs asks for {key!r}, which inputs does not declare; "
                "relevant_inputs narrows the questions, it does not add any"
                for key in asked.widened
            ]
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
