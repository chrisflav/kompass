"""Asking a ruleset what to ask, and serving the parts it left to the engine.

Every caller comes through :func:`asking`, which calls a ruleset's two
declaration methods **once each, together**, inside the query guard. That is
not tidiness: the two used to be asked separately, and whether a question was
derived was then decided twice, from two different declaration lists. A ruleset
that named the same key in both with a different ``source`` got a form that
said the answer was its own to give while the engine supplied one anyway — a
``PATCH`` answered 200, the value was stored, and the rules read the trip's
figure. Deciding it once, from ``inputs``, is what makes that unsayable.

:class:`Asked` is the whole answer about one statement:

:attr:`~Asked.vocabulary`
    ``inputs`` — every key that may be read, every key an answer may be stored
    under, with the parts the engine serves filled in.
:attr:`~Asked.form`
    the questions actually being asked: the *same declarations*, filtered to the
    keys ``relevant_inputs`` returned and in its order. The same declaration
    object, so a key cannot be derived on one side and not on the other.
:attr:`~Asked.supplied`
    what the engine answers itself, by key.
:attr:`~Asked.widened`
    keys ``relevant_inputs`` named that ``inputs`` does not. ``relevant_inputs``
    narrows; a key only it names is readable nowhere and storable nowhere, so
    :func:`finance.engine.evaluation.evaluate` reports it rather than leaving a
    question whose answer silently never arrives.

Two parts of a declaration are the engine's rather than the ruleset's.

**The options of a party-valued question** (:attr:`kompass.rules.Input.options_source`).
A ruleset that names one gets them filled in from the statement, out of the
fixed vocabulary :data:`kompass.rules.OPTION_SOURCES`. It is a vocabulary and
not a path because this is the declaration where a mistake costs money: every
name in it is a set the statement already carries, so no spelling of it reaches
somebody the statement does not mention, and no spelling of it reaches the
member table.

**The value of a derived question** (:attr:`kompass.rules.Input.source`). The
engine resolves ``"excursion.kilometers"`` against the context it has already
built and supplies the answer, instead of asking a person for a figure the trip
already records. The declaration comes back
:attr:`~kompass.rules.Input.derived`, which is what makes
:func:`finance.inputs.clean` refuse a submitted value for it.

**A derived value is never stored.** It is resolved again on every context
build — twice, in fact: :func:`finance.engine.context.build_context` puts it in
so that ``relevant_inputs``, the form and ``clean`` see the same figure a rule
will, and :func:`finance.engine.evaluation.evaluate` resolves it again for the
routes that never go through ``build_context`` at all (a case file, the fuzzer,
a dry run against unsaved answers). Both ask *this* module, off ``inputs``, so
the two cannot disagree. Not storing it is the point of the feature: a second
copy in ``Statement.inputs`` would be one more thing to go stale when the
kilometres on the trip are corrected, and there would then be a question about
which of the two is right. There is nothing to re-seed and nothing to
reconcile — the excursion is the only record, and a wrong figure is fixed there.
"""

from collections.abc import Iterable
from collections.abc import Mapping
from dataclasses import dataclass
from dataclasses import replace
from typing import Any

from finance.rules_api import Input
from finance.rules_api import Member
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset

from .guard import no_queries


@dataclass(frozen=True)
class Asked:
    """What a ruleset asks about one statement, in one piece.

    Built by :func:`asking` and nothing else, so that the four answers below
    are always answers about the same two calls into the same ruleset.
    """

    #: ``inputs``: every key that may be read or stored, declarations served.
    vocabulary: tuple[Input, ...]
    #: The questions being asked — ``vocabulary`` filtered by ``relevant_inputs``.
    form: tuple[Input, ...]
    #: What the engine supplies itself, by key.
    supplied: Mapping[str, object]
    #: Keys ``relevant_inputs`` named that ``inputs`` does not.
    widened: tuple[str, ...]


def asking(ruleset: Ruleset, ctx: RuleContext) -> Asked:
    """``ruleset``'s declarations for ``ctx``, with the engine's parts filled in.

    Both declaration methods, once, inside the guard: declaring the form is as
    much the section's code as resolving the transfers, and a declaration that
    queried would be a question whose answer depended on the day it was
    rendered.
    """
    with no_queries():
        declared = list(ruleset.inputs(ctx))
        relevant = list(ruleset.relevant_inputs(ctx))
    values = supplied(declared, ctx)
    vocabulary = tuple(
        _served(declaration, ctx, declaration.key in values) for declaration in declared
    )
    by_key = {declaration.key: declaration for declaration in vocabulary}
    # `dict.fromkeys` keeps the order and drops a repeat, so a key named twice
    # is one question rather than two entries sharing a key.
    wanted = dict.fromkeys(declaration.key for declaration in relevant)
    return Asked(
        vocabulary=vocabulary,
        form=tuple(by_key[key] for key in wanted if key in by_key),
        supplied=values,
        widened=tuple(key for key in wanted if key not in by_key),
    )


def supplied(declarations: Iterable[Input], ctx: RuleContext) -> dict[str, object]:
    """The answer to every declaration the engine derives, by key.

    Only the ones that resolved: a source that comes to nothing leaves an
    ordinary question whose answer lives in ``Statement.inputs`` like any
    other, which is the half of the feature that lets one ruleset serve
    statements with and without an excursion.

    "Comes to nothing" means exactly ``None`` — the root is absent (no
    excursion) or the field itself is unset. A zero, an empty string and an
    empty set are values the statement *records*, so they are supplied like any
    other: a trip whose kilometres are still at the model's default of ``0``
    serves ``0`` and refuses a correction here, because the correction belongs
    on the trip. Only :class:`~kompass.rules.StatementInfo`'s people and
    :attr:`~kompass.rules.Excursion.ljp` are nullable fields at all.
    """
    values: dict[str, object] = {}
    for declaration in declarations:
        if not declaration.source:
            continue
        value = _at(ctx, declaration.source)
        if value is not None:
            values[declaration.key] = value
    return values


def unbounded(declarations: Iterable[Input], values: Mapping[str, object]) -> list[str]:
    """Every supplied value that breaks the bound its own declaration set.

    :attr:`~kompass.rules.Input.max` was enforced only against a *submitted*
    answer, so the one value a client cannot influence was the one value
    nothing bounded. The obvious use of the feature reaches it: a section
    writes ``source="excursion.leaders"`` so that nobody retypes who led the
    trip, and ``max=approved_staff_count`` was then never consulted — five
    leaders against three approved paid five allowances.

    Reported as an error rather than applied, and that is deliberate. Nobody
    can correct a supplied value through the form, so truncating it would pay a
    quietly smaller amount that no page explains; emptying it would pay
    nothing for the same reason. A trip with more leaders than the section
    approved is a statement somebody has to fix **on the excursion**, and while
    there is an error nothing is persisted and no money moves.

    The message is the engine's, in the engine's language, like every other
    thing :func:`finance.engine.evaluation.evaluate` reports. A section that
    wants the sentence in its own words says it in its own
    :meth:`~kompass.rules.Ruleset.checks`; what this guarantees is only that
    the figure is not paid.
    """
    problems: list[str] = []
    for declaration in declarations:
        if declaration.key not in values or declaration.max is None:
            continue
        value = values[declaration.key]
        if declaration.type == "member_set" and isinstance(value, tuple):
            if len(value) > declaration.max:
                problems.append(
                    f"{declaration.source} supplies {len(value)} people for "
                    f"{declaration.key!r}, which asks for at most {declaration.max}"
                )
        elif isinstance(value, int) and not isinstance(value, bool):
            if value > declaration.max:
                problems.append(
                    f"{declaration.source} supplies {value} for {declaration.key!r}, "
                    f"which asks for at most {declaration.max}"
                )
    return problems


def _served(declaration: Input, ctx: RuleContext, derived: bool) -> Input:
    """``declaration`` with the options filled in and the derivation marked.

    The option source is **spent**: it is cleared as it is resolved, so that a
    declaration never carries both an option source and options at once. That
    is the invariant :class:`kompass.rules.Input` refuses a ruleset for stating
    two ways, and it would be an odd thing to enforce against a rule author
    while the engine's own answer broke it — an option source is a request, the
    options are the answer, and once the answer is in the request is over.
    """
    changes: dict[str, Any] = {}
    if declaration.options_source:
        changes["options"] = options_from(ctx, declaration.options_source)
        changes["options_source"] = ""
    if derived:
        changes["derived"] = True
    return replace(declaration, **changes) if changes else declaration


def _at(ctx: RuleContext, source: str) -> object:
    """What ``source`` names in ``ctx``, or ``None`` when there is nothing there.

    The path was checked when the declaration was built
    (``kompass.rules._check_source``), so the root is one of
    :data:`kompass.rules.SOURCE_ROOTS` and the name is a field of the frozen
    dataclass that root holds. That is what keeps the one ``getattr`` below
    from being a reach into an arbitrary object: it cannot name a method, a
    dunder or anything the context did not put there, and a ruleset cannot
    hand the engine a callable to run instead.
    """
    root, _, name = source.partition(".")
    # Exhaustive over `SOURCE_ROOTS`; adding a root means adding it here.
    holder = ctx.excursion if root == "excursion" else ctx.statement
    if holder is None:
        return None
    return getattr(holder, name)


def options_from(ctx: RuleContext, source: str) -> tuple[Member, ...]:
    """Who a party-valued question may name, out of :data:`kompass.rules.OPTION_SOURCES`.

    Deduplicated and in id order, like every other set of people the engine
    hands round: :func:`finance.inputs._clean_members` and
    :func:`finance.engine.answers.coerce_input` canonicalise the *answer* the
    same way, and Heidelberg bills its organisation fee to the first element of
    one — so the order a set of people comes out in is never a client's click
    order.

    It is resolved on every context build, so it shrinks when the statement
    does: clearing a receipt's payer takes them out of a ``bills.payers`` set
    without anybody editing an answer. The answer that still names them then
    reads as unanswered (:func:`finance.engine.answers.within`), which is the
    only reading that cannot pay somebody the rules no longer offer.
    """
    people: tuple[Member | None, ...]
    if source == "excursion.leaders":
        people = () if ctx.excursion is None else ctx.excursion.leaders
    elif source == "excursion.participants":
        people = (
            ()
            if ctx.excursion is None
            else tuple(person.member for person in ctx.excursion.participants)
        )
    elif source == "bills.payers":
        people = tuple(bill.payer for bill in ctx.bills)
    elif source == "statement.creator":
        people = (ctx.statement.creator,)
    else:
        # `statement.submitter`, the last of `OPTION_SOURCES`.
        people = (ctx.statement.submitter,)
    named = {person for person in people if person is not None}
    return tuple(sorted(named, key=lambda person: int(person.id)))
