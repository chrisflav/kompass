"""Asking a ruleset what to ask, and serving the parts it left to the engine.

A declaration is mostly the ruleset's own words — a key, a label, a widget. Two
parts of it are not, and both are here:

**The options of a party-valued question** (:attr:`kompass.rules.Input.options_source`).
A ruleset that names one gets them filled in from the statement, out of the
fixed vocabulary :data:`kompass.rules.OPTION_SOURCES`. It is a vocabulary and
not a path because this is the declaration where a mistake costs money: every
name in it is a set the statement already carries, so no spelling of it reaches
somebody the statement does not mention, and no spelling of it reaches the
member table.

**The value of a derived question** (:attr:`kompass.rules.Input.source`). The
engine resolves ``"excursion.kilometers"`` against the context it has already
built and supplies the answer, instead of asking a person for a figure the
trip already records. The declaration comes back
:attr:`~kompass.rules.Input.derived`, which is what makes
:func:`finance.inputs.clean` refuse a submitted value for it.

**A derived value is never stored.** It is resolved again on every context
build — twice, in fact: :func:`finance.engine.context.build_context` puts it in
so that ``relevant_inputs``, the form and ``clean`` see the same figure a rule
will, and :func:`finance.engine.evaluation.evaluate` resolves it again as the
last word, so that *no* route to the rules can substitute something else. Not
storing it is the point of the feature: a second copy in
``Statement.inputs`` would be one more thing to go stale when the kilometres
on the trip are corrected, and there would then be a question about which of
the two is right. There is nothing to re-seed and nothing to reconcile — the
excursion is the only record, and a wrong figure is fixed there.

Everything a ruleset is asked happens inside the query guard, which is why
every caller comes through :func:`ask` rather than calling
``ruleset.inputs`` itself: declaring the form is as much the section's code as
resolving the transfers, and a declaration that queried would be a question
whose answer depended on the day it was rendered.
"""

from collections.abc import Iterable
from dataclasses import replace
from typing import Any

from finance.rules_api import Input
from finance.rules_api import Member
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset

from .guard import no_queries


def ask(ruleset: Ruleset, ctx: RuleContext, *, relevant: bool = False) -> list[Input]:
    """``ruleset``'s declarations for ``ctx``, with the engine's parts filled in.

    ``relevant`` asks :meth:`~kompass.rules.Ruleset.relevant_inputs` — the
    questions still worth asking given the answers so far — rather than
    :meth:`~kompass.rules.Ruleset.inputs`. The two have to agree about which
    answers a rule reads (taxis #579), so the callers that decide *that* pass
    it and the ones that only want the full vocabulary do not; see
    :func:`finance.inputs.party_keys` for the one place the wider set is
    deliberately the right question.
    """
    with no_queries():
        declared = list(ruleset.relevant_inputs(ctx) if relevant else ruleset.inputs(ctx))
    supplied_keys = supplied(declared, ctx)
    return [_served(declaration, ctx, declaration.key in supplied_keys) for declaration in declared]


def supplied(declarations: Iterable[Input], ctx: RuleContext) -> dict[str, object]:
    """The answer to every declaration the engine derives, by key.

    Only the ones that resolved: a source that comes to nothing — no trip, or
    a figure nobody recorded — leaves an ordinary question whose answer lives
    in ``Statement.inputs`` like any other, which is the half of the feature
    that lets one ruleset serve statements with and without an excursion.
    """
    values: dict[str, object] = {}
    for declaration in declarations:
        if not declaration.source:
            continue
        value = _at(ctx, declaration.source)
        if value is not None:
            values[declaration.key] = value
    return values


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
