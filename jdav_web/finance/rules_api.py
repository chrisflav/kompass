"""``kompass.rules`` — the API a section's finance rules are written against.

A *ruleset* is an ordinary Python package. It subclasses :class:`Ruleset`, it
imports nothing from Kompass but this module, and it answers four questions
about one statement:

``inputs``
    Which extra data does a person have to supply? Every answer the rules read
    is declared here, which is what lets the form be derived from the rules
    instead of hand-written beside them.
``transfers``
    Who owes whom how much? The answer is a list of :class:`Transfer`\\ s plus a
    list of error messages. Nothing is persisted while there are errors.
``checks``
    What must hold before the statement may be handed in?
``approval``
    Who has to sign it off?

A minimal ruleset::

    from decimal import Decimal

    from kompass.rules import Input, Ruleset, RuleContext, SECTION, PARTICIPANTS, Transfer

    class FlatRate(Ruleset):
        name = "flat-rate"
        context_version = 1
        balance = (PARTICIPANTS, SECTION, "participant_contribution")

        def inputs(self, ctx: RuleContext) -> list[Input]:
            return [Input("leader", "Zuschuss an", "member",
                          options=ctx.excursion.leaders if ctx.excursion else ())]

        def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
            leader = ctx.inputs.member("leader")
            if leader is None:
                return [], []
            return [Transfer(SECTION, leader, ctx.params.FLAT_RATE, "subsidy",
                             rule_id="flat_rate")], []

Three properties of this API are worth knowing before writing a rule.

**Everything is a frozen value.** The context holds no model instances, no
relations to follow, no names, no bank details, no other statements and no
balances. What a rule cannot reach it cannot accidentally depend on, and what
it cannot depend on cannot change the answer for a statement that was settled
years ago.

**Money is :class:`~decimal.Decimal`, in whole cents.** Every amount a rule
returns must have at most two decimal places; the engine rejects anything
finer rather than rounding it silently, because a rounding rule belongs to the
section, not to the engine. :func:`split` and :func:`pct` are the two
roundings most rules need.

**A rule must not be able to tell when it runs.** There is no clock in the
context and no way to query the database — the engine blocks that during
evaluation — so evaluating an old statement again gives the old answer. The
one deliberate exception is :attr:`Participant.age`, which the engine resolves
when it builds the context (see its documentation).

The engine, not the ruleset, appends the transfer that makes the set add up:
see :attr:`Ruleset.balance`.
"""

from abc import ABC
from abc import abstractmethod
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import field
from dataclasses import fields
from decimal import Decimal
from decimal import ROUND_FLOOR
from typing import Any
from typing import Final
from typing import Literal
from typing import NewType

#: The version of the context shape this module describes.
#:
#: A ruleset declares the version it was written against in
#: :attr:`Ruleset.context_version`, and Kompass refuses to load a ruleset
#: written for a newer one. Changes are additive: a field is added, never
#: renamed or removed, so a ruleset written against version 1 keeps working.
CONTEXT_VERSION: Final = 1

#: One cent — the resolution of every amount in a transfer.
CENT: Final = Decimal("0.01")

MemberId = NewType("MemberId", int)
"""A member's primary key.

The only identity a rule ever sees. Names, addresses and bank details are
resolved by the engine after evaluation, so that a ruleset cannot leak them.
"""

InputType = Literal["money", "int", "bool", "text", "choice", "member", "member_set"]
"""The widget vocabulary an :class:`Input` is rendered with.

This is presentation, not rule structure: ``money`` and ``int`` are both
numbers, and the difference is the field the person is shown.
"""


class RuleError(Exception):
    """Raised when a ruleset asks the engine for something it may not have.

    Rule authors do not raise this. Problems with a *statement* are reported by
    returning a message from :meth:`Ruleset.transfers`; this exception is for
    problems with the *ruleset* — an input it never declared, a permission it
    never asked for — which are programming errors and should fail a case in
    the section's own CI.
    """


@dataclass(frozen=True, slots=True)
class Member:
    """A person, by id.

    Members compare and hash by id, so a rule may use them in sets and as
    dictionary keys (``{t.destination for t in transfers}``).
    """

    id: MemberId


@dataclass(frozen=True, slots=True)
class Section:
    """The section itself: the party whose money is being spent.

    There is one instance, :data:`SECTION`.
    """


@dataclass(frozen=True, slots=True)
class Participants:
    """The excursion's participants, as one party.

    There is one instance, :data:`PARTICIPANTS`. It is the usual counterparty
    for :attr:`Ruleset.balance`: whatever the section pays out net is what the
    participants' contributions have to cover. It is a lump sum — no individual
    participant's bank details are in scope.
    """


#: The section (see :class:`Section`).
SECTION: Final = Section()
#: The participants as one party (see :class:`Participants`).
PARTICIPANTS: Final = Participants()

Party = Member | Section | Participants
"""Anything that can be one end of a :class:`Transfer`."""


@dataclass(frozen=True, slots=True)
class Bill:
    """One receipt handed in with the statement.

    A bill is a *fact*, not a transfer: it says that money was spent, not that
    anybody is owed it. Whether the section reimburses it is
    :attr:`covered`, which the finance officer decides — and a bill that is not
    covered is still in the context, because it may well count towards a
    subsidy that is computed from the trip's total cost.
    """

    #: The bill's primary key, for error messages that name a row.
    id: int
    #: What the receipt says, cent-exact.
    amount: Decimal
    #: Whether the section reimburses this bill.
    covered: bool
    #: Who paid, if anybody was named. ``None`` is a common, reportable state.
    payer: Member | None
    #: Whether a scan of the receipt is attached.
    has_proof: bool
    #: The short description its author gave it.
    description: str


@dataclass(frozen=True, slots=True)
class Participant:
    """Somebody on the excursion's member list.

    Youth leaders who are also on the list appear here with
    :attr:`is_leader` set, so a rule that counts "participants" has to say
    whether it means the leaders too.
    """

    member: Member
    #: Age today, or ``None`` when the birth date is unknown.
    #:
    #: This is the one value in the context that depends on when the engine
    #: ran, and it exists because the rules it was ported from use it. A rule
    #: that must stay reproducible should prefer :attr:`age_at_start`.
    age: int | None
    #: Age on the excursion's first day, or ``None`` when the birth date is
    #: unknown. Reproducible, and usually what a regulation means.
    age_at_start: int | None
    #: Whether this person is also a youth leader of the excursion.
    is_leader: bool


LJPGoal = Literal["qualification", "participation", "development", "environment"]
"""The learning goal of a Landesjugendplan proposal."""


@dataclass(frozen=True, slots=True)
class LJP:
    """The excursion's Landesjugendplan proposal, if it has one.

    The counts are the ones the state's regulations define, computed by the
    engine: a participant is counted when they are at least 6 and under 27 on
    the first day, up to a fifth of the participants may fall outside that
    band, and youth leaders always count.
    """

    #: The declared learning goal, or ``None`` when none was picked yet.
    goal: LJPGoal | None
    #: The participant count under the regulations, ``0`` below the cutoff.
    participant_count: int
    #: The same count without the cutoff — what the cutoff is applied to.
    theoretic_participant_count: int
    #: The number of days that count as seminar days, at most the trip's
    #: duration.
    duration: Decimal


TourApproach = Literal["muscle", "public", "car"]
"""How the group travelled: on muscle power, by public transport, or by car."""


@dataclass(frozen=True, slots=True)
class Excursion:
    """The trip a statement settles, when there is one.

    A statement without an excursion (a purchase, a repair) has
    ``ctx.excursion is None``, and every rule has to say what it does then.
    """

    #: Days, in half-day steps: a long single day is ``1.0``, a short one
    #: ``0.5``.
    duration: Decimal
    #: Nights away.
    nights: int
    #: Kilometres travelled there and back.
    kilometers: int
    #: How the group travelled.
    approach: TourApproach
    #: The excursion's youth leaders — the people who may be named as
    #: recipients. Re-validated by the engine, so a rule cannot widen it.
    leaders: tuple[Member, ...]
    #: How many youth leaders led the trip.
    staff_count: int
    #: How many of them the section's regulations refinance.
    approved_staff_count: int
    #: Everybody on the member list, leaders included (see
    #: :class:`Participant`).
    participants: tuple[Participant, ...]
    #: The Landesjugendplan proposal, or ``None`` when the trip has none.
    ljp: LJP | None


@dataclass(frozen=True, slots=True)
class StatementInfo:
    """The statement being evaluated, stripped to what a rule may know."""

    #: The statement's primary key, or ``None`` before it is first saved.
    id: int | None
    #: Who created it.
    creator: Member | None
    #: Who handed it in, once somebody has.
    submitter: Member | None


class Inputs:
    """The answers to :meth:`Ruleset.inputs`, by key.

    Reading a key the ruleset did not declare raises :class:`RuleError` rather
    than returning ``None``: a typo in a rule is a bug the section's own cases
    should catch, not a silent zero in somebody's reimbursement. A key that was
    declared but never answered reads as that type's empty value — ``0.00`` for
    money, ``None`` for a member, ``()`` for a member set.

    The accessors are typed, so ``mypy`` checks the arithmetic a rule does with
    an answer::

        nights = ctx.excursion.nights * ctx.inputs.money("night_cost")

    ``ctx.inputs.night_cost`` reads the same answer untyped, for a quick look.
    A key that happens to be named like one of the accessors — ``money``,
    ``member``, ``members``, ``number``, ``flag``, ``text``, ``raw``,
    ``declared`` — is readable through those and through :meth:`raw`, but not
    as an attribute, where the method wins.
    """

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, object]) -> None:
        self._values = dict(values)

    def __repr__(self) -> str:
        return f"Inputs({self._values!r})"

    def declared(self) -> tuple[str, ...]:
        """The keys that are readable, in declaration order."""
        return tuple(self._values)

    def raw(self, key: str) -> object:
        """The answer to ``key``, untyped.

        Prefer :meth:`money`, :meth:`member`, :meth:`members`, :meth:`number`,
        :meth:`flag` or :meth:`text`, which say what they expect.
        """
        try:
            return self._values[key]
        except KeyError:
            raise RuleError(
                f"undeclared input {key!r}; this ruleset declares "
                f"{', '.join(self._values) or 'nothing'}"
            ) from None

    def __getattr__(self, key: str) -> object:
        if key.startswith("_"):
            raise AttributeError(key)
        return self.raw(key)

    def _typed(self, key: str, expected: type | tuple[type, ...], what: str) -> object:
        value = self.raw(key)
        if not isinstance(value, expected):
            raise RuleError(f"input {key!r} is not {what}, but {type(value).__name__}")
        return value

    def money(self, key: str) -> Decimal:
        """A money answer, as a :class:`~decimal.Decimal`."""
        value = self._typed(key, Decimal, "a money value")
        assert isinstance(value, Decimal)
        return value

    def number(self, key: str) -> int:
        """A whole-number answer."""
        value = self._typed(key, int, "a whole number")
        assert isinstance(value, int)
        return value

    def flag(self, key: str) -> bool:
        """A yes/no answer."""
        value = self._typed(key, bool, "a yes/no value")
        assert isinstance(value, bool)
        return value

    def text(self, key: str) -> str:
        """A free-text answer."""
        value = self._typed(key, str, "a text value")
        assert isinstance(value, str)
        return value

    def member(self, key: str) -> Member | None:
        """A single person, or ``None`` when nobody was picked."""
        value = self.raw(key)
        if value is None or isinstance(value, Member):
            return value
        raise RuleError(f"input {key!r} is not a member, but {type(value).__name__}")

    def members(self, key: str) -> tuple[Member, ...]:
        """A set of people, possibly empty, in the order they were picked."""
        value = self.raw(key)
        if isinstance(value, tuple) and all(isinstance(item, Member) for item in value):
            return value
        raise RuleError(f"input {key!r} is not a set of members")


class Params:
    """The section's numbers, as :class:`~decimal.Decimal`\\ s.

    A ruleset's parameters are data, versioned with it, so that changing the
    allowance per day is a parameter change and not a rule change. Reading one
    that does not exist raises :class:`RuleError`.
    """

    __slots__ = ("_values",)

    def __init__(self, values: Mapping[str, Decimal]) -> None:
        self._values = dict(values)

    def __repr__(self) -> str:
        return f"Params({self._values!r})"

    def __getattr__(self, key: str) -> Decimal:
        if key.startswith("_"):
            raise AttributeError(key)
        try:
            return self._values[key]
        except KeyError:
            raise RuleError(
                f"unknown parameter {key!r}; this ruleset has "
                f"{', '.join(sorted(self._values)) or 'none'}"
            ) from None

    def get(self, key: str, default: Decimal) -> Decimal:
        """The parameter ``key``, or ``default`` when it is not set."""
        return self._values.get(key, default)

    def as_dict(self) -> dict[str, Decimal]:
        """A copy of every parameter."""
        return dict(self._values)


class Roles(Mapping[str, tuple[Member, ...]]):
    """Who holds which section role — or a refusal to guess.

    A mapping, so ``ctx.roles["kassenwart"]`` reads as one, with one
    difference that matters: a context built for the *arithmetic* does not
    resolve the role assignments, and reading them from there raises
    :class:`RuleError` instead of answering ``()``.

    That asymmetry is deliberate. An empty mapping cannot distinguish "nobody
    holds this role" from "nobody asked the database", and the second one,
    silently, pays a treasurer nothing and balances the books around the hole.
    Roles are resolved for :meth:`Ruleset.approval`, which is what they are
    for; a rule that routes *money* by a role has to say so, and until the
    engine offers that it says so by failing loudly.
    """

    __slots__ = ("_values", "_resolved")

    def __init__(self, values: Mapping[str, tuple[Member, ...]] | None = None) -> None:
        self._resolved = values is not None
        self._values = dict(values or {})

    @classmethod
    def unresolved(cls) -> "Roles":
        """The roles of a context that did not ask for them."""
        return cls(None)

    @property
    def resolved(self) -> bool:
        """Whether the role assignments were read at all."""
        return self._resolved

    def _check(self) -> None:
        if not self._resolved:
            raise RuleError(
                "the role assignments were not resolved for this context; roles are "
                "resolved for `approval`, so a rule that routes money by a role has "
                "to be asked for differently"
            )

    def __getitem__(self, role: str) -> tuple[Member, ...]:
        self._check()
        return self._values[role]

    def get(self, role: str, default: Any = ()) -> Any:
        self._check()
        return self._values.get(role, default)

    def __iter__(self) -> Iterator[str]:
        self._check()
        return iter(self._values)

    def __len__(self) -> int:
        self._check()
        return len(self._values)

    def __repr__(self) -> str:
        return f"Roles({self._values!r})" if self._resolved else "Roles(unresolved)"


@dataclass(frozen=True, slots=True)
class RuleContext:
    """Everything a rule may know about one statement.

    Built by the engine, never by a ruleset. Each field is documented on the
    type it holds.
    """

    #: The context shape this instance was built to; compare with
    #: :data:`CONTEXT_VERSION`.
    version: int
    #: The section's numbers (see :class:`Params`).
    params: Params
    #: The answers to :meth:`Ruleset.inputs` (see :class:`Inputs`).
    inputs: Inputs
    #: Every receipt handed in, covered or not, in the order they were added.
    bills: tuple[Bill, ...]
    #: The trip, or ``None`` for a statement that settles something else.
    excursion: Excursion | None
    #: The statement itself (see :class:`StatementInfo`).
    statement: StatementInfo
    #: Who holds which section role (see :class:`Roles`). Resolved for
    #: :meth:`Ruleset.approval`; reading it elsewhere raises rather than
    #: answering "nobody".
    roles: Roles = field(default_factory=Roles.unresolved)
    #: Who holds which permission, for the codenames the ruleset declared in
    #: :attr:`Ruleset.permissions`. Read it through
    #: :meth:`permission_holders`.
    permissions: Mapping[str, tuple[Member, ...]] = field(default_factory=dict)

    def role_holders(self, role: str) -> tuple[Member, ...]:
        """Everybody who holds ``role``, or ``()`` if the role is unknown.

        Raises :class:`RuleError` when this context did not resolve the role
        assignments — see :class:`Roles` for why that is not silently empty.
        """
        return tuple(self.roles.get(role, ()))

    def permission_holders(self, codename: str) -> tuple[Member, ...]:
        """Everybody who holds ``codename``, as of this evaluation.

        The codename has to be listed in :attr:`Ruleset.permissions`; the
        engine resolves those before evaluation, because a rule cannot query
        the database itself. Reading an undeclared one raises
        :class:`RuleError`.
        """
        try:
            return self.permissions[codename]
        except KeyError:
            raise RuleError(
                f"undeclared permission {codename!r}; list it in the ruleset's "
                "`permissions` so the engine resolves it"
            ) from None


@dataclass(frozen=True, slots=True)
class Transfer:
    """Money owed by one party to another, because of one rule.

    A transfer is the whole output of a ruleset. Expressing a payout as a
    movement between two parties rather than as a number on a member makes the
    books add up by construction: there is no such thing as money that appears
    from nowhere, and the engine's balancing transfer (see
    :attr:`Ruleset.balance`) closes whatever is left.

    Signs do not appear here. A deduction — an organisation fee charged against
    somebody's reimbursement — is a transfer *to* the section, not a negative
    transfer from it.
    """

    #: Who owes the money.
    source: Party
    #: Who receives it.
    destination: Party
    #: How much, with at most two decimal places. The engine rejects anything
    #: finer: how to round is the section's decision, and :func:`split` and
    #: :func:`pct` are there to make it.
    amount: Decimal
    #: What kind of money this is — ``"allowance"``, ``"ljp"``, whatever the
    #: ruleset wants to group and label by. Free text to the engine.
    category: str
    #: Which rule produced it, for provenance: the stamp that answers "which
    #: statements paid a subsidy under which version of the rule".
    rule_id: str
    #: A short label for a person reading the payout, e.g. the bill's own
    #: description.
    label: str = ""
    #: Room for the arithmetic, if it is worth showing: "4 Tage × 22 €".
    explanation: str = ""


@dataclass(frozen=True, slots=True)
class Choice:
    """One alternative a ``choice`` question offers.

    The value is what is stored and what a rule reads back
    (:meth:`Inputs.text`); the label is what the person picking it is shown.
    Keeping the two apart is what lets a section reword a question without
    touching the rules that read its answer.
    """

    #: What the answer reads as — the rules' own vocabulary, and stable.
    value: str
    #: What the person choosing it is shown, in the section's language.
    label: str


#: The context fields a derived input's :attr:`Input.source` may start at.
#:
#: A source is ``"<root>.<field>"``, one field deep, and the field has to be a
#: real field of what that root holds. Both are checked where the declaration
#: is written, so a typo is a refusal that lists the fields rather than a
#: question that silently becomes one nobody can answer. The list is
#: deliberately short: a derived input is a figure the statement *already*
#: knows, and these are the two places it keeps one.
SOURCE_ROOTS: Final = ("excursion", "statement")

#: What each root holds, for checking a :attr:`Input.source` against its fields.
_SOURCE_TYPES: Final = {"excursion": Excursion, "statement": StatementInfo}

#: Where a party-valued question's :attr:`Input.options` may be taken from.
#:
#: A fixed vocabulary rather than a path, because "who may be paid" is the one
#: declaration where a mistake costs money. Every name here is a set the
#: *statement itself* carries, so no spelling of
#: :attr:`Input.options_source` reaches somebody the statement does not already
#: mention, and "every member in the section" is not reachable at all.
#:
#: ``excursion.leaders`` is what a trip-shaped ruleset writes by hand today.
#: The rest is what a statement settling something else has instead: the people
#: on the trip's list, whoever paid one of its receipts, and the two people the
#: statement names itself.
OPTION_SOURCES: Final = (
    "excursion.leaders",
    "excursion.participants",
    "bills.payers",
    "statement.creator",
    "statement.submitter",
)

#: The widget types whose answer names people, and so the only ones an option
#: source means anything for.
_PARTY_INPUT_TYPES: Final = ("member", "member_set")


def _check_source(source: str) -> None:
    """Refuse ``source`` unless the engine will resolve it (:data:`SOURCE_ROOTS`)."""
    root, dot, name = source.partition(".")
    holder = _SOURCE_TYPES.get(root)
    if holder is None:
        raise RuleError(
            f"a derived input's source starts at one of {', '.join(SOURCE_ROOTS)}, not at {root!r}"
        )
    if not dot or not name or "." in name:
        raise RuleError(
            f"{source!r} is not a source: write it as <root>.<field>, one field deep. "
            "A figure further in than that is read off the context by the rule that "
            "wants it."
        )
    known = tuple(declared.name for declared in fields(holder))
    if name not in known:
        raise RuleError(f"{root} has no field {name!r}; it has {', '.join(known)}")


@dataclass(frozen=True, slots=True)
class Input:
    """One question the statement's form has to ask.

    Declaring the question beside the rule that reads the answer is what keeps
    the two from drifting apart: the form is generated from these, and a rule
    that reads an undeclared key fails loudly (see :class:`Inputs`).

    A declaration the engine cannot serve is refused where it is written, with
    :class:`RuleError`: a ``choice`` with nothing to choose from, a
    :attr:`source` that names no context field, an :attr:`options_source` on a
    question that names no people. The engine refuses a nonsense
    :attr:`Ruleset.balance` for the same reason — it is a bug in the rules, and
    a case in the section's own CI should fail on it rather than a person's
    form quietly losing a question.
    """

    #: The key the answer is read back under.
    key: str
    #: What the person is asked, in the section's language.
    label: str
    #: Which widget to render (see :data:`InputType`).
    type: InputType
    #: Whether the statement may be handed in without an answer.
    required: bool = True
    #: A sentence of help under the field.
    help: str = ""
    #: For ``member`` and ``member_set``: who may be picked. The engine
    #: re-validates a submitted answer against this, so an answer can never
    #: name somebody the rule did not offer.
    #:
    #: A ruleset either lists the people itself, out of the context it was
    #: given, or names an :attr:`options_source` and lets the engine fill this
    #: in. Not both.
    options: tuple[Member, ...] = ()
    #: For ``member_set`` and ``int``, and for **those two only**: the largest
    #: acceptable count or value. It is ignored on every other type —
    #: ``money`` included, which is worth knowing because an amount is the
    #: other thing one would expect a ceiling on. A money answer is bounded by
    #: the resolution and ceiling of the field itself
    #: (``finance.inputs.MONEY_MAX``) and not by this; a section wanting its
    #: own maximum writes a :class:`Check`.
    #:
    #: It bounds a *submitted* answer, which is refused on the way in, and an
    #: answer the engine supplies from a :attr:`source`, which cannot be —
    #: nobody can correct that one through the form. A supplied value that
    #: breaks this is therefore an **error on the statement**, naming the
    #: source and the bound, rather than a truncation: five youth leaders
    #: against three the section approved is something to fix on the
    #: excursion, and while there is an error nothing is persisted and no
    #: money moves.
    max: int | None = None
    #: For ``choice``: the alternatives, which a ``choice`` has to have. A
    #: submitted answer is re-validated against them, exactly as a person is
    #: re-validated against :attr:`options`.
    choices: tuple[Choice, ...] = ()
    #: Where the engine takes this answer *from* instead of asking for it:
    #: ``"excursion.kilometers"`` (see :data:`SOURCE_ROOTS`).
    #:
    #: When the source resolves, the engine supplies the value, the declaration
    #: comes back :attr:`derived`, and the form **refuses** a submitted answer
    #: for the key — the figure is corrected where it lives, not here. When it
    #: does not, this is an ordinary question whose answer is stored like any
    #: other. Either way a rule reads it the same way, which is the whole
    #: point: one ``ctx.inputs.number("kilometers")`` and no branch on where it
    #: came from.
    #:
    #: A source resolves to nothing in exactly two cases: the root is absent
    #: (a statement with no excursion) or the field itself is ``None``. A
    #: ``0``, an empty string and an empty set are values the statement
    #: *records*, so they are supplied like any other — a trip whose kilometres
    #: are still at the model's default of ``0`` serves ``0`` and refuses a
    #: correction here, because the correction belongs on the trip. The
    #: nullable fields are :class:`StatementInfo`'s two people and
    #: :attr:`Excursion.ljp`; every other field of :class:`Excursion` always
    #: has a value.
    #:
    #: Derivation is decided by :meth:`Ruleset.inputs` and nothing else. A key
    #: :meth:`Ruleset.relevant_inputs` names is served with the declaration
    #: ``inputs`` gave it, so the form and the rules cannot disagree about
    #: where one key's value comes from.
    #:
    #: For a ``member`` or ``member_set`` it should be stated *with*
    #: :attr:`options` or an :attr:`options_source`, and the two never both
    #: apply: when the source resolves the engine supplies the answer and the
    #: options go unread; when it does not, the options are who may be picked.
    #: ``source="excursion.leaders"`` with ``options_source="bills.payers"`` is
    #: the whole of "the people who led the trip, or whoever paid a receipt
    #: when there was no trip" — and **without the second half the question
    #: cannot be answered at all** on a statement with no excursion, because a
    #: party-valued declaration offering nobody offers nobody.
    #:
    #: So: who may be picked bounds the answer when it is *asked for*, and says
    #: nothing about one the engine supplies. A supplied one comes out of the
    #: statement's own data, which is what makes it safe without a domain, and
    #: what bounds it is :attr:`max`.
    #:
    #: A derived value is **not stored**. It is resolved again every time a
    #: context is built, so there is no second copy to go stale when the trip
    #: changes.
    source: str = ""
    #: Where the engine takes :attr:`options` from, for a ``member`` or
    #: ``member_set`` question: one of :data:`OPTION_SOURCES`.
    #:
    #: It is a request, and the engine's answer is :attr:`options`. A
    #: declaration that comes back from the engine therefore carries one or the
    #: other and never both — which is also what a ruleset stating both is
    #: refused for.
    options_source: str = ""
    #: The step this question belongs to, as a short label. Questions that
    #: share one are presented together, in the order the labels are first
    #: declared, and ``GET …/form`` serves that grouping. Empty is the unnamed
    #: step, which is what a form without steps is.
    step: str = ""
    #: Whether the engine supplies this answer itself. The *engine* sets it; a
    #: ruleset declares :attr:`source` and reads this back, and setting it
    #: without a source is refused — it would be a question nobody can ever
    #: answer, refused with a message that is not true of it.
    derived: bool = False

    def __post_init__(self) -> None:
        if self.derived and not self.source:
            raise RuleError(
                f"{self.key!r} is marked derived with nothing to derive it from; the "
                "engine sets that itself, from `source`"
            )
        # A `source` beside `options` or an `options_source` is *not* refused,
        # and the rule that makes it unambiguous is one sentence: who may be
        # picked bounds the answer when it is asked for, and says nothing about
        # one the engine supplies. The two arms never both apply — see
        # `source` — so for a `member` or `member_set` this is the pairing that
        # makes one question answerable with a trip and without one.
        if self.type == "choice" and not self.choices:
            raise RuleError(
                f"the choice {self.key!r} offers no choices, which is a text field that "
                "validates nothing; list them in `choices`"
            )
        if self.choices and self.type != "choice":
            raise RuleError(f"{self.key!r} is a {self.type} input, so its choices are never shown")
        if self.source:
            _check_source(self.source)
        if not self.options_source:
            return
        if self.options_source not in OPTION_SOURCES:
            raise RuleError(
                f"{self.options_source!r} is not an option source; the engine serves "
                f"{', '.join(OPTION_SOURCES)}"
            )
        if self.type not in _PARTY_INPUT_TYPES:
            raise RuleError(f"{self.key!r} is a {self.type} input, so it names no people")
        if self.options:
            raise RuleError(
                f"{self.key!r} both lists its options and names {self.options_source!r} to "
                "take them from; say it once"
            )


@dataclass(frozen=True, slots=True)
class Check:
    """A precondition for handing the statement in.

    Both states are worth showing, so a check carries its message whether or
    not it holds: "Für den LJP-Beitrag braucht jeder Beleg ein Bild" is the
    rule either way, and whether it is satisfied is :attr:`ok`.
    """

    #: Whether the precondition holds.
    ok: bool
    #: What has to be true, phrased for the person who has to fix it.
    message: str


@dataclass(frozen=True, slots=True)
class Constraint:
    """A signature the statement needs before the money moves.

    Constraints are an unordered set: no priorities, no workflow. Each one asks
    for :attr:`required` signatures out of :attr:`eligible`, one signature
    counts against every constraint it satisfies, and
    :attr:`applicable` and *satisfied* are separate states — a constraint that
    does not apply is shown as such rather than hidden.
    """

    #: A short name, shown in the approval list.
    name: str
    #: Why this signature is needed, in the section's words.
    description: str
    #: Whether it applies to this statement at all.
    applicable: bool
    #: How many signatures from :attr:`eligible` are needed.
    required: int
    #: Who may sign. Re-checked against the real permission system, so naming
    #: somebody here cannot grant them a right they do not have.
    eligible: tuple[Member, ...]
    #: What it means for :attr:`eligible` to come out **empty**.
    #:
    #: Left ``False``, an empty group means *nobody*: the constraint stands
    #: open and no signature satisfies it. That is the safe reading, and it is
    #: the one an empty group usually deserves — a role nobody holds, a filter
    #: that matched nobody, a query that returned nothing — because the
    #: alternative lets a statement pay itself out precisely when the rules
    #: could not say who should allow it.
    #:
    #: Set ``True``, the engine fills the group from the holders of the
    #: section's approval capability instead, which is what Kompass did before
    #: there were constraints at all. The forbids still apply to the group it
    #: fills in, so "whoever may act, except whoever is paid" is sayable. An
    #: empty group *then* still means nobody — there is no reading under which
    #: "we could not work out who" means "anyone will do".
    anyone_permitted: bool = False


@dataclass(frozen=True)
class Forbid:
    """Somebody who may not sign, whatever permits them.

    Forbids are subtracted from every constraint's eligible set before quorum
    is counted, and they win unconditionally: this is how a conflict of
    interest is expressed ("nobody who receives money from this statement").
    """

    #: A short name, shown when a signature is refused.
    name: str
    #: Whether this forbid catches a given candidate.
    applies_to: Callable[[Member], bool]


class Ruleset(ABC):
    """What a section's finance rules have to implement.

    Subclass it in the section's ruleset package and export one instance as
    ``ruleset``::

        ruleset = HeidelbergRules()

    Everything the engine fixes is here; everything else — how many rules there
    are, what the categories mean, who a recipient is, whether an amount is per
    person or per statement — is the author's Python.
    """

    #: A short name for this ruleset, used in logs and in the admin.
    name: str = "unnamed"
    #: The :data:`CONTEXT_VERSION` this ruleset was written against. Kompass
    #: refuses to load a ruleset written against a newer context.
    context_version: int = CONTEXT_VERSION
    #: The date these rules were **in force** from, ISO 8601
    #: (``"2026-03-01"``), empty for "from the moment Kompass is told".
    #:
    #: It is valid time, and it may be in the past: a section that resolved
    #: new rates in March and imports them in May says ``"2026-03-01"``, and
    #: the record then carries both when the rules applied and when Kompass
    #: learned of them. A date in the future stages a change that is already
    #: agreed. This declaration is the *authority* for either, which is why it
    #: lives in the ruleset package rather than in a command-line flag: the
    #: package is reviewed and committed, and it is the versioned
    #: documentation of the procedure an auditor asks for.
    #:
    #: Backdating records; it does not re-settle. A statement is bound to the
    #: rules it was created under, and no version imported afterwards — with
    #: whatever date — changes what it settled under; settling one again under
    #: a correction is a separate, deliberate act (#561).
    valid_from: str = ""
    #: Permission codenames the rules read with
    #: :meth:`RuleContext.permission_holders`. The engine resolves these before
    #: evaluation, because the rules cannot query the database themselves.
    permissions: tuple[str, ...] = ()
    #: ``(source, destination, category)`` of the one transfer the *engine*
    #: appends, with the amount it resolves itself: the amount that brings
    #: ``destination``'s net position to zero. Declaring the parties and
    #: letting the engine do the arithmetic is what makes "the statement adds
    #: up" unfalsifiable rather than asserted. When the resolved amount comes
    #: out negative the engine runs the transfer the other way round, so the
    #: direction declared here is the one that is usual for the section.
    balance: tuple[Party, Party, str] = (PARTICIPANTS, SECTION, "balance")

    @abstractmethod
    def inputs(self, ctx: RuleContext) -> list[Input]:
        """Declare every answer the rules read, in the order to ask for them."""

    @abstractmethod
    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        """Resolve the statement into transfers, plus anything wrong with it.

        Return ``(transfers, errors)``. An error is a sentence for the person
        who has to fix the statement — a covered bill with nobody to pay back —
        and while there is one, nothing is persisted and no money moves. Do not
        raise for a problem with the statement; raising is for a broken
        *ruleset*, and the engine turns it into an error with a traceback.
        """

    def checks(self, ctx: RuleContext) -> list[Check]:
        """Preconditions for handing the statement in. Default: none."""
        return []

    def relevant_inputs(self, ctx: RuleContext) -> list[Input]:
        """The questions still worth asking, given the answers so far.

        The default re-runs :meth:`inputs` against the answers known so far,
        which is enough for a ruleset whose ``inputs`` branches on them — drop
        the question about the price per night once "no subsidy" has been
        answered, and it stops being asked.

        This and :meth:`inputs` have different jobs, and overriding this one
        overrides only the second of them. ``inputs`` says what may be
        **read**: the whole vocabulary, every key an answer may be stored
        under, and the list that reading a key is checked against. This says
        what is being **asked**: the form, and the set an answer has to be in
        to count. A question this leaves out is off the form, the API refuses
        an answer for it, and the rules read it as *unanswered* — the type's
        empty value, whatever is still stored under the key.

        So what the form does not ask, the rules read as unanswered, and
        retiring a question stops it moving money. Reading a retired key is
        not an error; it reads empty, because a question nobody can see is not
        something a rule should fail on.

        **Narrow, do not widen.** A key only this names is not in the
        vocabulary, so it has nowhere to be stored and nowhere to be read: the
        engine reports it as an error on the statement rather than serving a
        question whose answer would silently never arrive. And a key this
        names is served with the declaration ``inputs`` gave it — same label,
        same type, same bound, same :attr:`Input.source` — so the two methods
        cannot disagree about one key.
        """
        return self.inputs(ctx)

    def approval(
        self, ctx: RuleContext, transfers: list[Transfer]
    ) -> tuple[list[Constraint], list[Forbid]]:
        """Who has to sign this statement off, and who may not.

        Routing runs on the *transfers*, after expansion, so a rule can say
        "nobody who receives money from this statement" (see :class:`Forbid`)
        or "over 1.000 € it takes the board" without re-deriving either from
        the raw statement. Default: nobody, which the engine reads as "the
        capability check alone decides".
        """
        return [], []


def quantize(amount: Decimal) -> Decimal:
    """``amount`` floored to whole cents.

    The rounding :func:`split` and :func:`pct` are built on: towards minus
    infinity, never away from zero, so repeatedly splitting an amount can
    never create money.
    """
    return amount.quantize(CENT, rounding=ROUND_FLOOR)


def split(amount: Decimal, n: int) -> list[Decimal]:
    """``amount`` divided ``n`` ways, to the cent, adding back up exactly.

    Each share is floored to the cent and the leftover cents are handed out one
    each from the top, in declaration order, so 99 cents five ways is 20, 20,
    20, 20, 19 — every time, which is what makes a statement reproducible.
    Raises :class:`ValueError` for ``n <= 0``.
    """
    if n <= 0:
        raise ValueError(f"cannot split into {n} shares")
    total = int(quantize(amount).scaleb(2).to_integral_value())
    base, remainder = divmod(total, n)
    return [Decimal(base + (1 if index < remainder else 0)).scaleb(-2) for index in range(n)]


def pct(amount: Decimal, basis_points: int) -> Decimal:
    """``basis_points`` ten-thousandths of ``amount``, floored to the cent.

    Basis points rather than a percentage because they are exact integers:
    ``pct(x, 9000)`` is 90 % of ``x``, ``pct(x, 1990)`` is 19,9 %.
    """
    return quantize(amount * Decimal(basis_points) / Decimal(10000))


def first_of(*parties: Party | None) -> Party | None:
    """The first party that is not ``None``, or ``None``.

    The fallback chain a rule needs when a deduction has to be charged to
    somebody and there is more than one candidate: ``first_of(subsidy_to,
    *allowance_to)``.
    """
    for party in parties:
        if party is not None:
            return party
    return None


__all__ = [
    "CENT",
    "CONTEXT_VERSION",
    "Bill",
    "Check",
    "Choice",
    "Constraint",
    "Excursion",
    "Forbid",
    "Input",
    "InputType",
    "Inputs",
    "LJP",
    "LJPGoal",
    "Member",
    "MemberId",
    "OPTION_SOURCES",
    "PARTICIPANTS",
    "Params",
    "Participant",
    "Participants",
    "Party",
    "RuleContext",
    "RuleError",
    "Roles",
    "Ruleset",
    "SECTION",
    "SOURCE_ROOTS",
    "Section",
    "StatementInfo",
    "TourApproach",
    "Transfer",
    "first_of",
    "pct",
    "quantize",
    "split",
]
