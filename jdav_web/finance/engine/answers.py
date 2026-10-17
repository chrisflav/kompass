"""Stored answers, as the types the rules that asked for them read.

An answer is kept as JSON — in ``Statement.inputs`` for a real statement, in a
case file for a worked example — and a rule reads it through a typed accessor
that raises on the wrong type. Which key is money and which is a person is the
*ruleset's declaration* and nothing else's, so this module takes the
declarations and the JSON and puts them together.

No Django here, deliberately. The statement path reaches this through
:mod:`finance.engine.context`, which does know Django; a case file's path
reaches it through :mod:`finance.engine.cases`, which knows none and must keep
not knowing any, because a section runs its cases in its own repository's CI.
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
    """
    if declaration.type == "member_set":
        return tuple(Member(MemberId(int(pk))) for pk in value or ())
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
