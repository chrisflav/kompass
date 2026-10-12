"""The form a statement asks for, derived from the rules that read it.

A section's rules declare every answer they need
(:meth:`~kompass.rules.Ruleset.inputs`), with a label, a widget type and — for
a party-valued answer — the domain of people who may be picked. This module is
the other side of that declaration: it renders it for a client, and it
validates what comes back.

Two things it deliberately does rather than trusts:

**The options are resolved here, from the rules' own declaration.** A ruleset
names candidates as ids; the names a person picks from are looked up at the
edge, so that the rules never see them.

**Every value is checked against its declaration**, not against a hand-written
list of the four columns Heidelberg happens to have. ``_resolve_recipient``
and ``_validate_allowance_count`` in the router were exactly that list; the
checks here are their generalisation, with the same two messages, so a section
whose rules ask for something else gets the same treatment without anybody
editing the API.

The validation is pessimistic on purpose — everything is checked before
anything is written — because approval must never fail on arithmetic that
could have been checked when the form was submitted.
"""

from decimal import Decimal
from decimal import InvalidOperation

from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from members.models import Member

from .engine import ruleset_for
from .engine import statement_context

#: The input types that name people, and whether more than one may be named.
MEMBER_TYPES = {"member": False, "member_set": True}


def declarations(statement):
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
    return list(ruleset.relevant_inputs(statement_context(statement, ruleset)))


def options_for(declaration):
    """``[{id, name}]`` for a declaration that names people.

    The rules offered ids; this is where they become something to show. A
    member the rules named who no longer exists simply drops out.
    """
    ids = [member.id for member in declaration.options]
    if not ids:
        return []
    by_id = Member.objects.in_bulk(ids)
    return [{"id": pk, "name": by_id[pk].name} for pk in ids if pk in by_id]


def rendered(statement):
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


def clean(statement, values):
    """Validate ``values`` against the declarations, or raise.

    Returns the cleaned answers, with members resolved to ids and money to
    ``Decimal``. Raises :class:`~django.core.exceptions.ValidationError` on the
    first problem, which is what the API turns into a 422.
    """
    by_key = {declaration.key: declaration for declaration in declarations(statement)}
    cleaned = {}
    for key, value in values.items():
        declaration = by_key.get(key)
        if declaration is None:
            raise ValidationError(_("These rules do not ask for %(key)s.") % {"key": key})
        cleaned[key] = clean_value(declaration, value)
    return cleaned


def clean_value(declaration, value):
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


def _clean_members(declaration, value):
    """Who may be named: exactly the people the rules offered, no more.

    This is ``_resolve_recipient`` and ``_validate_allowance_count``, both at
    once and for any declaration rather than for three columns. The messages
    are the ones the admin and the API have always given.
    """
    many = MEMBER_TYPES[declaration.type]
    if value is None:
        return [] if many else None
    picked = list(value) if many else [value]
    allowed = {member.id for member in declaration.options}
    for member_id in picked:
        if int(member_id) not in allowed:
            raise ValidationError(
                _("Only youth leaders of this excursion may receive contributions.")
            )
    if many and declaration.max is not None and len(picked) > declaration.max:
        raise ValidationError(
            _(
                "This excursion only has up to %(approved_count)s approved youth "
                "leaders, but you listed %(entered_count)s."
            )
            % {"approved_count": str(declaration.max), "entered_count": str(len(picked))}
        )
    resolved = [int(member_id) for member_id in picked]
    return resolved if many else resolved[0]


def _clean_money(declaration, value):
    try:
        amount = Decimal(str(value if value is not None else 0))
    except InvalidOperation:
        raise ValidationError(
            _("%(label)s is not an amount of money.") % {"label": str(declaration.label)}
        ) from None
    if amount < 0:
        raise ValidationError(
            _("%(label)s cannot be negative.") % {"label": str(declaration.label)}
        )
    return amount


def _clean_int(declaration, value):
    try:
        number = int(value if value is not None else 0)
    except (TypeError, ValueError):
        raise ValidationError(
            _("%(label)s is not a whole number.") % {"label": str(declaration.label)}
        ) from None
    if declaration.max is not None and number > declaration.max:
        raise ValidationError(
            _("%(label)s is at most %(max)s.")
            % {"label": str(declaration.label), "max": str(declaration.max)}
        )
    return number


def stored(values):
    """``values`` as the ``inputs`` column keeps them: JSON, money as text."""
    return {
        key: str(value) if isinstance(value, Decimal) else value for key, value in values.items()
    }
