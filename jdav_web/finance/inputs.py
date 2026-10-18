"""The form a statement asks for, derived from the rules that read it.

A section's rules declare every answer they need
(:meth:`~kompass.rules.Ruleset.inputs`), with a label, a widget type and — for
a party-valued answer — the domain of people who may be picked. This module is
the other side of that declaration: it renders it for a client — the SPA
through ``GET …/form``, the admin's excursion inline through
:func:`form_field` — and it validates what comes back.

Two things it deliberately does rather than trusts:

**The options are resolved here, from the rules' own declaration.** A ruleset
names candidates as ids; the names a person picks from are looked up at the
edge, so that the rules never see them.

**Every value is checked against its declaration**, not against a hand-written
list of the four columns Heidelberg used to have. ``_resolve_recipient`` and
``_validate_allowance_count`` in the router were exactly that list, and
``StatementOnListForm`` was the same list as three querysets; the checks here
are their generalisation, with the same two messages, so a section whose rules
ask for something else gets the same treatment without anybody editing the API
or the admin.

The validation is pessimistic on purpose — everything is checked before
anything is written — because approval must never fail on arithmetic that
could have been checked when the form was submitted.
"""

from collections.abc import Mapping
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from finance.rules_api import Input
from members.models import Member

from .engine import no_queries
from .engine import ruleset_for
from .engine import statement_context

#: The input types that name people, and whether more than one may be named.
MEMBER_TYPES = {"member": False, "member_set": True}

#: The resolution and the ceiling an answer in money has to fit.
#:
#: Cents because that is what the engine computes in — ``quantize`` floors to
#: them, so a third decimal place is silently dropped rather than paid.
#:
#: The ceiling is ``max_digits=7``, which is :func:`form_field`'s own money
#: field: the admin and the API check the same declaration, so they have to
#: refuse the same answers, and a ceiling the admin's widget would reject
#: anyway is the one place the two can be made to agree. It is deliberately
#: *not* the ``max_digits=5`` of the column ``night_cost`` came from — a
#: section may reimburse more than 999.99 a night and nothing should stop it —
#: which is why ``0021``'s reverse lists an amount too wide for that column
#: among the things reversing cannot do.
MONEY_PLACES = 2
MONEY_DIGITS = 7
MONEY_MAX = Decimal(10 ** (MONEY_DIGITS - MONEY_PLACES)) - Decimal("0.01")


def declarations(statement: Any) -> list[Input]:
    """The questions ``statement`` still has to ask, in order.

    Asked through ``relevant_inputs`` rather than ``inputs``, against the
    answers the statement already carries, which is what lets a ruleset retire
    a question: once "no subsidy" is saved, the price per night comes off the
    form rather than staying on it to be ignored. The answers it re-runs
    against are the *saved* ones — the ones the engine holds in its own shapes
    — so a client that wants the form to change asks for it again after the
    ``PATCH``.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset)
    # Inside the guard, like `transfers`, `checks` and `approval`: this is the
    # `/form` endpoint's entry into a section's own code, and a declaration
    # that queried would make the form depend on the day it was rendered.
    with no_queries():
        return list(ruleset.relevant_inputs(context))


def options_for(declaration: Input) -> list[dict[str, Any]]:
    """``[{id, name}]`` for a declaration that names people.

    The rules offered ids; this is where they become something to show. A
    member the rules named who no longer exists simply drops out.
    """
    ids = [member.id for member in declaration.options]
    if not ids:
        return []
    by_id = Member.objects.in_bulk(ids)
    return [{"id": pk, "name": by_id[pk].name} for pk in ids if pk in by_id]


def rendered(statement: Any) -> list[dict[str, Any]]:
    """The whole form as a client needs it: declarations with resolved options."""
    return [
        {
            "key": declaration.key,
            "label": str(declaration.label),
            "type": declaration.type,
            "required": declaration.required,
            "help": str(declaration.help),
            "max": declaration.max,
            "options": options_for(declaration),
        }
        for declaration in declarations(statement)
    ]


def party_keys(statement: Any) -> set[str]:
    """Every key that names people, asked of ``inputs`` and not of the form.

    An answer naming somebody is only admissible against the trip it was given
    for: swap the excursion and last week's youth leaders are no longer
    eligible for anything, and a deleted member has to come out of every answer
    that still names them. Callers drop these rather than the four columns they
    used to know by name.

    Asked of :meth:`~kompass.rules.Ruleset.inputs` rather than through
    :func:`declarations`, which asks ``relevant_inputs``: the question this has
    to match is the one :func:`finance.engine.context.build_context` asks, so
    that a ruleset narrowing only ``relevant_inputs`` cannot put a key out of
    reach here while the engine goes on reading it. The two questions
    disagreeing at all is taxis #579; what this guarantees is that *this* set is
    never the smaller of the two.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset)
    with no_queries():
        declared = ruleset.inputs(context)
    return {declaration.key for declaration in declared if declaration.type in MEMBER_TYPES}


def form_field(declaration: Input) -> Any:
    """``declaration`` as a Django form field, for a server-rendered form.

    The admin's excursion inline is a client of the declarations like the SPA
    is, and it used to be a ``ModelForm`` over the four columns with the
    eligible youth leaders assigned into three querysets by hand. This is that
    form's field list, derived: the domain of a party-valued answer becomes the
    field's choices, so the admin cannot offer somebody the rules did not.

    The values that come back are ids and numbers, never model instances, so
    that :func:`clean_value` can check them against the same declaration the
    API checks against and give the same message.
    """
    common = {
        "label": declaration.label,
        "required": declaration.required,
        "help_text": declaration.help,
    }
    if declaration.type in MEMBER_TYPES:
        choices = [(option["id"], option["name"]) for option in options_for(declaration)]
        if MEMBER_TYPES[declaration.type]:
            return forms.TypedMultipleChoiceField(choices=choices, coerce=int, **common)
        return forms.TypedChoiceField(
            choices=[("", "---------"), *choices], coerce=int, empty_value=None, **common
        )
    if declaration.type == "money":
        # The same bound `_clean_money` enforces, so the widget refuses exactly
        # what the declaration does rather than its own narrower range.
        return forms.DecimalField(
            decimal_places=MONEY_PLACES, max_digits=MONEY_DIGITS, min_value=0, **common
        )
    if declaration.type == "int":
        return forms.IntegerField(max_value=declaration.max, **common)
    if declaration.type == "bool":
        return forms.BooleanField(**common)
    return forms.CharField(**common)


def clean(statement: Any, values: Mapping[str, Any]) -> dict[str, Any]:
    """Validate ``values`` against the declarations, or raise.

    Returns the cleaned answers, with members resolved to ids and money to
    ``Decimal``. Raises :class:`~django.core.exceptions.ValidationError` on the
    first problem, which is what the API turns into a 422.

    A problem with one answer is raised **keyed by that answer**, so the 422
    carries an ``errors`` map and a client can print "this trip only has two
    approved youth leaders" under the question it is about rather than as a
    toast over the whole form. The admin's form did that when it was a
    ``ModelForm`` over four columns; the API did not.
    """
    by_key = {declaration.key: declaration for declaration in declarations(statement)}
    cleaned = {}
    for key, value in values.items():
        declaration = by_key.get(key)
        if declaration is None:
            raise ValidationError(_("These rules do not ask for %(key)s.") % {"key": key})
        try:
            cleaned[key] = clean_value(declaration, value)
        except ValidationError as problem:
            raise ValidationError({key: problem.messages}) from None
    return cleaned


def clean_value(declaration: Input, value: Any) -> Any:
    """One answer, checked against one declaration and converted.

    Public because it is the whole of the widget vocabulary in one place:
    ``money`` becomes a non-negative ``Decimal``, ``int`` a bounded whole
    number, ``member`` and ``member_set`` ids from the declaration's own
    options, ``bool`` a flag, and anything else text.
    """
    if declaration.type in MEMBER_TYPES:
        return _clean_members(declaration, value)
    if declaration.type == "money":
        return _clean_money(declaration, value)
    if declaration.type == "int":
        return _clean_int(declaration, value)
    if declaration.type == "bool":
        return bool(value)
    return "" if value is None else str(value)


def _as_member(value: Any) -> int:
    """``value`` as a member id, or a refusal the client can read.

    Whatever a client sends for a party-valued answer, this has to come back as
    a 422 and not as a 500. ``main`` got that from pydantic, which typed
    ``subsidy_to_id`` as an ``int``; now the answers arrive as a free-form
    ``dict`` and the only thing that looks at them is here. The message is the
    one the admin and the API have always given, which is also true of a value
    that is not a person at all: it is not one of the people the rules offered.

    ``OverflowError`` is in the list because ``1e400`` is an ordinary JSON
    number that arrives as ``float('inf')``, and ``int()`` of that overflows
    rather than failing to parse.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(
            _("Only youth leaders of this excursion may receive contributions.")
        ) from None


def _clean_members(declaration: Input, value: Any) -> Any:
    """Who may be named: exactly the people the rules offered, each once.

    This is ``_resolve_recipient`` and ``_validate_allowance_count``, both at
    once and for any declaration rather than for three columns. The messages
    are the ones the admin and the API have always given.

    A ``member_set`` comes back **deduplicated and in id order**, because it is
    a set: that is what the ``ManyToManyField`` it replaced guaranteed, and
    both halves of the guarantee move money. Without the deduplication,
    ``{"allowance_to": [1, 1]}`` passed a bound of two and froze two obligation
    rows paying member 1, so a youth leader could double their own allowance
    with one ``PATCH``; the count the bound is checked against is therefore the
    deduplicated one, since one person named twice is one recipient. Without
    the ordering, the client's click order decided who the organisation fee was
    charged against — Heidelberg's ``first_of(subsidy_to, *allowance_to)`` bills
    the first element, and the SPA appends in click order while the admin sends
    option order.
    """
    many = MEMBER_TYPES[declaration.type]
    if value is None:
        return [] if many else None
    picked = list(value) if many and isinstance(value, list) else [value]
    allowed = {member.id for member in declaration.options}
    ids = [_as_member(member_id) for member_id in picked]
    for member_id in ids:
        if member_id not in allowed:
            raise ValidationError(
                _("Only youth leaders of this excursion may receive contributions.")
            )
    if not many:
        return ids[0]
    resolved = sorted(set(ids))
    if declaration.max is not None and len(resolved) > declaration.max:
        raise ValidationError(
            _(
                "This excursion only has up to %(approved_count)s approved youth "
                "leaders, but you listed %(entered_count)s."
            )
            % {"approved_count": str(declaration.max), "entered_count": str(len(resolved))}
        )
    return resolved


def _clean_money(declaration: Input, value: Any) -> Decimal:
    try:
        amount = Decimal(str(value if value is not None else 0))
    except InvalidOperation:
        raise ValidationError(
            _("%(label)s is not an amount of money.") % {"label": str(declaration.label)}
        ) from None
    # `Decimal` accepts "nan" and "inf", and comparing either raises rather
    # than answering — so they are refused as what they are, not an amount.
    if not amount.is_finite():
        raise ValidationError(
            _("%(label)s is not an amount of money.") % {"label": str(declaration.label)}
        )
    if amount < 0:
        raise ValidationError(
            _("%(label)s cannot be negative.") % {"label": str(declaration.label)}
        )
    # `as_tuple()` and not `normalize()`: normalising applies the decimal
    # context, and `Decimal("1E+1000000").normalize()` raises `Overflow` — an
    # `ArithmeticError` that is not an `InvalidOperation`, so that string in a
    # money answer was a 500 rather than this function's 422. Money arrives as
    # text on this API, so nothing exotic is needed to send it. The exponent is
    # all the question needs, and reading it uses no context. The `int()` is
    # for the type checker: typeshed allows an exponent of 'n', 'N' or 'F',
    # which only a NaN or an infinity carries and `is_finite()` has refused.
    places = max(0, -int(amount.as_tuple().exponent))
    if places > MONEY_PLACES or amount > MONEY_MAX:
        raise ValidationError(
            _("%(label)s has to be an amount in whole cents, at most %(max)s.")
            % {"label": str(declaration.label), "max": str(MONEY_MAX)}
        )
    return amount


def _clean_int(declaration: Input, value: Any) -> int:
    try:
        number = int(value if value is not None else 0)
    except (TypeError, ValueError, OverflowError):
        raise ValidationError(
            _("%(label)s is not a whole number.") % {"label": str(declaration.label)}
        ) from None
    if declaration.max is not None and number > declaration.max:
        raise ValidationError(
            _("%(label)s may be at most %(max)s.")
            % {"label": str(declaration.label), "max": str(declaration.max)}
        )
    return number


def stored(values: Mapping[str, Any]) -> dict[str, Any]:
    """``values`` as the ``inputs`` column keeps them: JSON, money as text.

    This is now the whole record: the four Heidelberg columns it used to be
    written beside were migrated into it by ``0021`` — which read **the
    columns**, because by then this field had been written and never read for
    three releases and had drifted from them. Nothing writes here except
    through :func:`clean`, so an answer in it has been checked against the
    declaration it belongs to.
    """
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()
    }
