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
"""

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from finance.rules_api import Input
from finance.rules_api import Member
from finance.rules_api import MemberId


def coerce_input(declaration: Input, value: Any) -> object:
    """One stored answer, as the type its declaration promises.

    The other half of :func:`finance.inputs.clean_value`: that one takes what a
    client sent and makes it storable, this one takes what was stored and makes
    it readable by a rule. The vocabulary is the same seven types, and an
    unanswered question reads as its type's empty value — ``0.00`` for money,
    ``None`` for a person, ``()`` for a set of them — because
    :class:`kompass.rules.Inputs` promises exactly that.

    Money goes through ``str`` on its way to :class:`~decimal.Decimal`, so a
    JSON number never arrives as its binary expansion.

    **A value that does not fit is handed through untouched**, not raised on.
    A section may change what a question asks for while statements still hold
    an answer under that key — which is the whole point of the feature — and
    ``inputs`` keeps a retired key rather than pruning it. Raising here would
    make every read of that statement a 500, including the ``/form`` request
    that is the only way to put a new answer in. Handed through, the rule's own
    typed accessor raises :class:`kompass.rules.RuleError` instead, which
    :func:`finance.engine.evaluation.evaluate` reports as an error on the
    statement.
    """
    try:
        return _fitted(declaration, value)
    except (TypeError, ValueError, ArithmeticError):
        return value


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


def typed_inputs(declarations: Iterable[Input], answers: Mapping[str, Any]) -> dict[str, object]:
    """``answers`` restricted to ``declarations`` and typed by them.

    Restricted, because a key no declaration asks for is not an answer any
    more: the rules stopped asking, and :class:`kompass.rules.Inputs` would
    hand it to a rule that read it by mistake. Typed, because a rule reads
    ``ctx.inputs.money(...)`` and gets a :class:`~decimal.Decimal` or a
    :class:`kompass.rules.RuleError`, never a string that looks like one.
    """
    return {
        declaration.key: coerce_input(declaration, answers.get(declaration.key))
        for declaration in declarations
    }
