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

from .answers import coerce_input
from .declared import ask
from .declared import supplied
from .guard import no_queries

#: What an unanswered declaration of each type reads as.
#:
#: ``choice`` is ``""`` and not ``None``, which is what makes the widget
#: readable at all (taxis #573): it is a named value out of a fixed list, a
#: rule reads it with :meth:`~kompass.rules.Inputs.text`, and that accessor
#: type-checks against ``str`` — so ``None`` here turned every unanswered
#: choice into a :class:`~kompass.rules.RuleError` that collapsed the whole
#: evaluation instead of reading as "nothing chosen yet".
_EMPTY: dict[str, object] = {
    "money": Decimal("0.00"),
    "int": 0,
    "bool": False,
    "text": "",
    "choice": "",
    "member": None,
    "member_set": (),
}

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


def _answered(vocabulary: Iterable[Input], asked: Iterable[Input], ctx: RuleContext) -> Inputs:
    """The answers a rule reads: what is *asked*, over the whole vocabulary.

    Two sets, because a ruleset answers two questions about its form.
    ``vocabulary`` is :meth:`~kompass.rules.Ruleset.inputs`, every key the
    ruleset may ever read, and it decides what is *readable*: a rule that reads
    a key it declared gets a value rather than a
    :class:`~kompass.rules.RuleError`. ``asked`` is
    :meth:`~kompass.rules.Ruleset.relevant_inputs`, the questions still on the
    form, and it decides what is *answered*.

    So the rule for a question the ruleset has stopped asking is the rule for a
    question nobody has answered yet: it reads as that type's empty value. That
    is taxis #579, settled in the direction that costs nothing — **what the form
    does not ask, the rules read as unanswered.** The stored answer to a retired
    question no longer moves money, which was the bug; and reading one is not
    an error, which would have collapsed the whole evaluation into a traceback
    over a question a person cannot even see (the mistake ``_EMPTY["choice"]``
    used to make, for the same reason).

    A **derived** declaration is resolved here rather than read, and that is
    deliberately the last word. ``build_context`` already resolved it, so for a
    real statement this agrees with what the form showed — but a context can
    also arrive from a case file, from the fuzzer or from a dry run against
    unsaved answers, and on those routes nothing else would. Resolving again
    costs two attribute reads and makes one sentence true on every route: what
    a rule reads for a derived key is what the statement's own data says, and
    not what anybody submitted under it.
    """
    asked = list(asked)
    engine_supplied = supplied(asked, ctx)
    # Everything declared reads as unanswered to begin with, so that a question
    # the form is not asking is readable but empty — and so that a
    # `relevant_inputs` which somehow names a key `inputs` does not is still
    # resolved below rather than silently dropped.
    answers: dict[str, object] = {
        declaration.key: _EMPTY.get(declaration.type) for declaration in vocabulary
    }
    for declaration in asked:
        if declaration.key in engine_supplied:
            answers[declaration.key] = coerce_input(declaration, engine_supplied[declaration.key])
            continue
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
            # Both questions, because the form and the rules have to agree
            # about which answers count (taxis #579): `inputs` is what may be
            # read, `relevant_inputs` is what is being asked, and `_answered`
            # puts the two together. Asking only `inputs` is the bug — a
            # ruleset that retires a question would go on being paid from an
            # answer the API offers no way to see or change.
            vocabulary = ask(ruleset, ctx)
            declarations = tuple(ask(ruleset, ctx, relevant=True))
            answered = replace(ctx, inputs=_answered(vocabulary, declarations, ctx))
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
