"""Stored answers, as the types the rules that asked for them read.

An answer is kept as JSON — in ``Statement.inputs`` for a real statement, in a
case file for a worked example — and a rule reads it through a typed accessor
that raises on the wrong type. Which key is money and which is a person is the
*ruleset's declaration* and nothing else's, so this module takes the
declarations and the JSON and puts them together.

Its own module so that the two paths into it share one implementation: a
statement's answers come through :mod:`finance.engine.context`, which reads the
ORM, and a case file's come through :mod:`finance.engine.cases`, which reads no
database at all. Nothing here imports anything but the typed API — though that
is not the same as being importable without Django, which neither this module
nor ``cases`` is: both live in :mod:`finance.engine`, whose package import
reaches the models.

**Two ways an answer can fail to fit, and they are treated differently.**

A *type* that does not fit is handed through untouched, so the rule's own
accessor raises and the evaluation reports it: that is a section retyping a key
whose old answers are still stored, and the loud reading is the right one.

A value *outside the domain its declaration offers* — a ``choice`` whose option
has been withdrawn, a person who is no longer among the people the rules offer,
a set larger than the bound — reads as **unanswered** instead
(:func:`within`). It is the same decision as a retired question (taxis #579):
what the form would not accept, the rules do not read. That matters because the
form validates an answer on the way *in* and nothing used to re-validate one on
the way *out*, so a withdrawn option went on paying, and ``/form`` served an
answer that the very same form would have refused — any client that round-tripped
what it was served got a 422 naming a value its own UI could not display.
"""

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from finance.rules_api import Input
from finance.rules_api import Member
from finance.rules_api import MemberId

#: What an unanswered declaration of each type reads as.
#:
#: ``choice`` is ``""`` and not ``None``, which is what makes the widget
#: readable at all (taxis #573): it is a named value out of a fixed list, a
#: rule reads it with :meth:`~kompass.rules.Inputs.text`, and that accessor
#: type-checks against ``str`` — so ``None`` here turned every unanswered
#: choice into a :class:`~kompass.rules.RuleError` that collapsed the whole
#: evaluation instead of reading as "nothing chosen yet".
#:
#: Here rather than in :mod:`finance.engine.evaluation` because it is now two
#: things' answer: what a question nobody asked reads as, and what an answer
#: outside its own domain falls back to.
EMPTY: dict[str, object] = {
    "money": Decimal("0.00"),
    "int": 0,
    "bool": False,
    "text": "",
    "choice": "",
    "member": None,
    "member_set": (),
}


def typed(declaration: Input, value: Any) -> object:
    """``value`` as the type ``declaration`` promises, whatever it is worth.

    The engine's own supplied values come through here and no further: they are
    read off the context rather than submitted, so there is no domain to
    re-check them against — ``options`` may not be stated beside a ``source``
    at all, and a ``max`` a supplied value breaks is reported as an error on the
    statement (:func:`finance.engine.declared.unbounded`) rather than quietly
    emptied, because nobody can correct it through the form.

    A value whose *type* does not fit is handed through untouched, not raised
    on. A section may change what a question asks for while statements still
    hold an answer under that key — which is the whole point of the feature —
    and ``inputs`` keeps a retired key rather than pruning it. Raising here
    would make every read of that statement a 500, including the ``/form``
    request that is the only way to put a new answer in. Handed through, the
    rule's own typed accessor raises :class:`kompass.rules.RuleError` instead,
    which :func:`finance.engine.evaluation.evaluate` reports as an error on the
    statement.
    """
    try:
        return _fitted(declaration, value)
    except (TypeError, ValueError, ArithmeticError):
        return value


def within(declaration: Input, value: Any) -> bool:
    """Whether a typed answer is still inside the domain ``declaration`` offers.

    The read side of :func:`finance.inputs.clean_value`, asked of an answer
    that was stored when the domain was wider: a ``choice`` whose option has
    since been withdrawn, a person the rules no longer offer — which happens
    without anybody editing the statement, since clearing a receipt's payer
    empties an ``options_source="bills.payers"`` set — or a set larger than a
    bound the section has since lowered.

    A value whose type does not fit is *not* judged here; it is outside every
    domain and has to stay loud rather than read as empty, so
    :func:`coerce_input` only asks this of a value :func:`typed` could fit.
    """
    if declaration.type == "choice":
        return value == "" or value in {choice.value for choice in declaration.choices}
    if declaration.type == "member":
        return value is None or value in declaration.options
    if declaration.type == "member_set":
        if declaration.max is not None and len(value) > declaration.max:
            return False
        return all(member in declaration.options for member in value)
    if declaration.type == "int":
        return declaration.max is None or value <= declaration.max
    return True


def offers(declaration: Input, value: Any) -> bool:
    """Whether the **stored** ``value`` is one ``declaration`` still offers.

    What :func:`coerce_input` decides with, exposed because ``/form`` needs the
    same answer: it serves what the rules read, so it may not hand back a value
    the rules have stopped reading.

    A value whose *type* does not fit is reported as offered, because it is not
    this question's business: it is outside every domain, and the loud reading
    belongs to the rule's own accessor rather than to a quiet emptying.
    """
    try:
        return within(declaration, _fitted(declaration, value))
    except (TypeError, ValueError, ArithmeticError):
        return True


def coerce_input(declaration: Input, value: Any) -> object:
    """One **stored** answer, as the type its declaration promises and no wider.

    The other half of :func:`finance.inputs.clean_value`: that one takes what a
    client sent and makes it storable, this one takes what was stored and makes
    it readable by a rule. The vocabulary is the same seven types, and an
    unanswered question reads as its type's empty value — ``0.00`` for money,
    ``None`` for a person, ``()`` for a set of them — because
    :class:`kompass.rules.Inputs` promises exactly that.

    Money goes through ``str`` on its way to :class:`~decimal.Decimal`, so a
    JSON number never arrives as its binary expansion.

    An answer the declaration no longer offers reads as that empty value too
    (:func:`within`), so that nothing is paid on a value the form would refuse.
    A *type* that does not fit is still handed through, unjudged, so that the
    rule's accessor raises on it: the two failures have to stay distinguishable,
    and only one of them is a thing a person can re-answer.
    """
    try:
        fitted = _fitted(declaration, value)
    except (TypeError, ValueError, ArithmeticError):
        return value
    return fitted if within(declaration, fitted) else EMPTY.get(declaration.type)


def _fitted(declaration: Input, value: Any) -> object:
    if declaration.type == "member_set":
        # A string is iterable and a dict iterates its keys, so without this
        # `"27"` would read back as two members and `{"3": 1}` as one — against
        # the promise above that a value which does not fit is handed through
        # untouched. Which is exactly the case the `except` above exists for: a
        # section retyping a key that already holds a text or whole-euro answer.
        if value is not None and not isinstance(value, list | tuple):
            raise TypeError(f"a set of members is not {type(value).__name__}")
        # Sorted and deduplicated, because a set is a set: this is what the
        # `ManyToManyField` it replaced guaranteed, and `statement_inputs`
        # sorted by primary key before the columns were dropped. The order
        # decides who a rule bills — Heidelberg's organisation fee goes to
        # `first_of(subsidy_to, *allowance_to)` — so it is canonical wherever
        # the answer is read, not only where it is written.
        return tuple(Member(MemberId(pk)) for pk in sorted({int(pk) for pk in value or ()}))
    if declaration.type == "member":
        return None if value is None else Member(MemberId(int(value)))
    if declaration.type == "money":
        return Decimal(str(value if value is not None else 0))
    if declaration.type == "int":
        return int(value if value is not None else 0)
    if declaration.type == "bool":
        return bool(value)
    return "" if value is None else str(value)


def typed_inputs(
    declarations: Iterable[Input],
    answers: Mapping[str, Any],
    derived: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """``answers`` restricted to ``declarations`` and typed by them.

    Restricted, because a key no declaration asks for is not an answer any
    more: the rules stopped asking, and :class:`kompass.rules.Inputs` would
    hand it to a rule that read it by mistake. Typed, because a rule reads
    ``ctx.inputs.money(...)`` and gets a :class:`~decimal.Decimal` or a
    :class:`kompass.rules.RuleError`, never a string that looks like one.

    ``derived`` are the answers the *engine* supplies, from
    :attr:`finance.engine.declared.Asked.supplied`. They win over anything
    stored under the same key, and that is the fail-closed half of the feature:
    a derived figure is never editable, so a value that reached
    ``Statement.inputs`` under its key — a leftover from before the question
    was derived, or a hand-crafted write — is shadowed rather than read. They
    go through :func:`typed` rather than :func:`coerce_input`, because a
    supplied value has no domain to be re-checked against and a bound it breaks
    is an error rather than an empty reading.
    """
    engine_supplied = {} if derived is None else derived
    return {
        declaration.key: (
            typed(declaration, engine_supplied[declaration.key])
            if declaration.key in engine_supplied
            else coerce_input(declaration, answers.get(declaration.key))
        )
        for declaration in declarations
    }
