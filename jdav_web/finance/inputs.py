"""The form a statement asks for, derived from the rules that read it.

A section's rules declare every answer they need
(:meth:`~kompass.rules.Ruleset.inputs`), with a label, a widget type and — for
a party-valued answer — the domain of people who may be picked. This module is
the other side of that declaration: it renders it for a client — the SPA
through ``GET …/form``, which is :func:`form`, and the admin's excursion inline
through :func:`form_field` — and it validates what comes back.

Three things it deliberately does rather than trusts:

**The options are resolved here, from the rules' own declaration.** A ruleset
names candidates as ids — itself, or through
:attr:`~kompass.rules.Input.options_source`, which the engine fills in from a
fixed vocabulary of sets the statement already carries. The names a person
picks from are looked up at the edge, so that the rules never see them.

**A derived answer is refused, not ignored.** A declaration with a
:attr:`~kompass.rules.Input.source` the engine resolved comes back
:attr:`~kompass.rules.Input.derived`, and :func:`clean` raises for it: the
value is a reading of the excursion, resolved again on every evaluation, so a
value submitted under its key would be stored where nothing reads it. Refusing
says so, where ignoring would let a hand-crafted ``PATCH`` believe it had
changed a payout.

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

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from finance.rules_api import Input
from finance.rules_api import Member as RuleMember
from finance.rules_api import RuleContext
from members.models import Member

from .engine import Asked
from .engine import asking
from .engine import offers
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


def asked(statement: Any) -> tuple[Asked, RuleContext]:
    """What ``statement``'s rules ask of it, and the context they were asked about.

    The form is :attr:`~finance.engine.declared.Asked.form`, which is
    ``relevant_inputs`` — against the answers the statement already carries,
    which is what lets a ruleset retire a question: once "no subsidy" is saved,
    the price per night comes off the form rather than staying on it to be
    ignored. The answers it re-runs against are the *saved* ones, so a client
    that wants the form to change asks for it again after the ``PATCH``.

    ``relevant_inputs`` is the authoritative question about what is *asked*,
    and since taxis #579 it is the one the rules are asked too: a question it
    does not return is one :func:`finance.engine.evaluation.evaluate` does not
    read either. So the answer :func:`clean` refuses is also an answer that
    moves no money, which is what it means for the two sides to agree.

    Everything comes out of one :func:`~finance.engine.declared.asking` call,
    and the whole of it is returned rather than just the form: the declarations
    are only half of a form, a derived question's *value* comes from the same
    call, and resolving either from a second context is how the form and the
    rules would come apart.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset)
    # Inside the guard, like `transfers`, `checks` and `approval` — `asking`
    # opens it: this is the `/form` endpoint's entry into a section's own code,
    # and a declaration that queried would make the form depend on the day it
    # was rendered.
    return asking(ruleset, context), context


def declarations(statement: Any) -> list[Input]:
    """The questions ``statement`` still has to ask, in order (see :func:`asked`)."""
    return list(asked(statement)[0].form)


def answerable(statement: Any) -> list[Input]:
    """The questions a person may answer: the declarations, minus the derived ones.

    What a server-rendered form is given. The admin's excursion inline writes
    every field it renders and has nowhere to put a figure it must show but not
    accept, so it is handed the questions it can honour and the derived ones
    are left to the engine — which resolves them on every evaluation regardless
    of what any form did. The SPA gets the whole list and the ``derived`` flag
    with it, because it can render a figure as a figure.
    """
    return [declaration for declaration in declarations(statement) if not declaration.derived]


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


def _declaration(declaration: Input) -> dict[str, Any]:
    """One declaration as a client needs it, with its options resolved."""
    return {
        "key": declaration.key,
        "label": str(declaration.label),
        "type": declaration.type,
        "required": declaration.required,
        "help": str(declaration.help),
        "max": declaration.max,
        "options": options_for(declaration),
        "choices": [
            {"value": choice.value, "label": str(choice.label)} for choice in declaration.choices
        ],
        "step": str(declaration.step),
        "derived": declaration.derived,
    }


def steps(declarations_: Iterable[Input]) -> list[dict[str, Any]]:
    """``declarations_`` grouped into the steps the ruleset named, in order.

    A step is a label and the keys that belong to it, in declaration order; the
    steps come in the order their labels are first declared. A declaration with
    no ``step`` belongs to the unnamed one (``""``), so this is always the whole
    form and a client can lay it out from here rather than from the flat list.

    That is all it is. There is no page state, no "next", no notion of a step
    being complete: which questions belong together is the section's business
    and how to present them is the client's, and a wizard in between would be
    the backend deciding both.
    """
    grouped: dict[str, list[str]] = {}
    for declaration in declarations_:
        grouped.setdefault(str(declaration.step), []).append(declaration.key)
    return [{"label": label, "keys": keys} for label, keys in grouped.items()]


def _as_json(value: Any) -> Any:
    """A derived value the way ``Statement.inputs`` would have held it.

    So that one client-side code path reads a derived answer and a stored one:
    money as text, a person as an id, a set of people as a list of ids. A value
    that is none of those — a source naming a nested structure rather than a
    figure, which is a ruleset's mistake — comes back as text rather than as a
    500 on the one endpoint that would say what is wrong.
    """
    if isinstance(value, RuleMember):
        return int(value.id)
    if isinstance(value, tuple):
        return [_as_json(item) for item in value]
    if value is None or isinstance(value, bool | int | str):
        return value
    return str(value)


def form(statement: Any) -> dict[str, Any]:
    """The whole form: the questions, how they group, and the answers they are about.

    ``answers`` is restricted to the keys this form asks for, so an answer the
    rules have stopped asking for is not handed back to be re-submitted. Two
    kinds of answer are **not** read out of ``Statement.inputs``:

    A *derived* answer is resolved here, from the same call the declarations
    came from, which is why a stale value stored under its key cannot be shown:
    there is one figure, it lives on the excursion, and this is a reading of it.

    An answer the declaration no longer *offers* comes back empty — a
    ``choice`` whose option has been withdrawn, a person who is no longer
    among the people the rules offer. It is the answer the rules read
    (:func:`finance.engine.answers.within`), and serving anything else would
    hand a client a value its own UI cannot display and the very same form
    would refuse: round-tripping what ``/form`` served used to answer 422 on a
    question nobody had touched.

    So **a client may send back everything here except the keys marked
    derived**, which are served to be shown and refused to be changed.

    One exception, and it is deliberate: an answer whose stored *type* no
    longer fits its declaration — a section retyped the key — is served as it
    stands and refused on the way back. :func:`finance.engine.answers.offers`
    reports it as offered on purpose, because it is not a withdrawn option but
    a broken one, and the rules report it loudly rather than reading it as
    unanswered. Echoing it back is a 422 naming that key; answering the
    question properly clears it.
    """
    served, context = asked(statement)
    carried = statement.answers
    return {
        "inputs": [_declaration(declaration) for declaration in served.form],
        "steps": steps(served.form),
        "answers": {
            declaration.key: _answer(declaration, served, carried) for declaration in served.form
        },
    }


def _answer(declaration: Input, served: Asked, carried: Mapping[str, Any]) -> Any:
    """What ``/form`` hands back for one question: what the rules will read."""
    if declaration.key in served.supplied:
        return _as_json(served.supplied[declaration.key])
    stored = carried.get(declaration.key)
    if stored is None:
        return None
    # `None` rather than the type's empty value, so that an answer nobody has
    # given and one nobody may give any more look the same to a client: both
    # are a question still to be answered, and both come back through `clean`
    # as the empty answer if a client sends them straight back.
    return stored if offers(declaration, stored) else None


def party_keys(statement: Any) -> set[str]:
    """Every key that names people, asked of ``inputs`` and not of the form.

    An answer naming somebody is only admissible against the trip it was given
    for: swap the excursion and last week's youth leaders are no longer
    eligible for anything, and a deleted member has to come out of every answer
    that still names them. Callers drop these rather than the four columns they
    used to know by name.

    Asked of :meth:`~kompass.rules.Ruleset.inputs` rather than through
    :func:`declarations`, which asks ``relevant_inputs``, and that stays true
    now that ``relevant_inputs`` is what the rules are asked (taxis #579):
    ``inputs`` is the whole vocabulary a ruleset may put in
    ``Statement.inputs``, ``relevant_inputs`` narrows it, and what has to be
    cleaned of a deleted member is every key an answer could be *stored* under.
    Over-eager by design — pruning a key the rules are not currently reading
    costs nothing, and missing one leaves a dangling id in a column with a real
    foreign key behind it.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset)
    declared = asking(ruleset, context, form=False).vocabulary
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
    if declaration.type == "choice":
        # A select, with the same alternatives `_clean_choice` validates
        # against, so the admin cannot offer what the API would refuse.
        return forms.ChoiceField(
            choices=[("", "---------"), *((c.value, str(c.label)) for c in declaration.choices)],
            **common,
        )
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

    A **derived** answer is refused rather than ignored. The engine resolves
    it from the statement's own data on every evaluation, so a value submitted
    for it would be written to a key nothing reads — and the person who sent it
    would have no way of knowing. Refusing fails closed in the direction that
    matters: a hand-crafted ``PATCH`` cannot put a figure of its own where the
    excursion's kilometres belong, and nor can a client that simply echoed back
    the whole form it was served.
    """
    by_key = {declaration.key: declaration for declaration in declarations(statement)}
    cleaned = {}
    for key, value in values.items():
        declaration = by_key.get(key)
        if declaration is None:
            raise ValidationError(_("These rules do not ask for %(key)s.") % {"key": key})
        if declaration.derived:
            raise ValidationError(
                {
                    key: [
                        _(
                            "%(label)s is taken from the statement's own data and cannot "
                            "be answered here."
                        )
                        % {"label": str(declaration.label)}
                    ]
                }
            )
        try:
            cleaned[key] = clean_value(
                declaration, value, about_an_excursion=statement.excursion is not None
            )
        except ValidationError as problem:
            raise ValidationError({key: problem.messages}) from None
    return cleaned


def clean_value(declaration: Input, value: Any, *, about_an_excursion: bool = True) -> Any:
    """One answer, checked against one declaration and converted.

    Public because it is the whole of the widget vocabulary in one place:
    ``money`` becomes a non-negative ``Decimal``, ``int`` a bounded whole
    number, ``member`` and ``member_set`` ids from the declaration's own
    options, ``choice`` one of the declaration's own choices, ``bool`` a flag,
    and anything else text.

    ``about_an_excursion`` picks the wording when somebody names a person the
    rules did not offer. The message Kompass has always given says "youth
    leaders of this excursion", which is true of a trip and false of a
    statement that settles a purchase — where the people on offer come from
    whoever paid a receipt. It defaults to the trip's wording because the
    admin's excursion inline is always about one; :func:`clean` asks the
    statement.
    """
    if declaration.type in MEMBER_TYPES:
        return _clean_members(declaration, value, about_an_excursion=about_an_excursion)
    if declaration.type == "money":
        return _clean_money(declaration, value)
    if declaration.type == "int":
        return _clean_int(declaration, value)
    if declaration.type == "choice":
        return _clean_choice(declaration, value)
    if declaration.type == "bool":
        return bool(value)
    return "" if value is None else str(value)


def _clean_choice(declaration: Input, value: Any) -> str:
    """One of the alternatives the declaration offered, and nothing else.

    The other half of making ``choice`` a real widget (taxis #573): before the
    declaration could name its alternatives there was nothing to check an
    answer against, so this fell through to "anything else is text" and
    accepted any string at all — a question whose whole purpose is to be one of
    a fixed set, answerable with anything.

    Empty is accepted and reads back as ``""``, the same way an unanswered
    money question reads back as ``0.00``: a form is filled in gradually, and
    whether an answer is *needed* is :attr:`~kompass.rules.Input.required` and
    the ruleset's own checks, not this.
    """
    if value is None or value == "":
        return ""
    chosen = str(value)
    if chosen not in {choice.value for choice in declaration.choices}:
        raise ValidationError(
            _("%(label)s is not one of the options offered.") % {"label": str(declaration.label)}
        )
    return chosen


def _not_offered(about_an_excursion: bool) -> ValidationError:
    """The refusal for a person the rules did not offer, worded for the statement.

    Kompass has always said "youth leaders of this excursion", and for a
    statement that settles a trip that is both true and the most useful thing
    to say. For one that settles a purchase it is neither: there is no
    excursion, and the people on offer are whoever paid a receipt — so that
    wording sent somebody looking for a trip that does not exist.
    """
    if about_an_excursion:
        return ValidationError(_("Only youth leaders of this excursion may receive contributions."))
    return ValidationError(_("This person is not one of the people these rules offer."))


def _as_member(value: Any, *, about_an_excursion: bool) -> int:
    """``value`` as a member id, or a refusal the client can read.

    Whatever a client sends for a party-valued answer, this has to come back as
    a 422 and not as a 500. ``main`` got that from pydantic, which typed
    ``subsidy_to_id`` as an ``int``; now the answers arrive as a free-form
    ``dict`` and the only thing that looks at them is here. The message is the
    one the answer deserves, which is also true of a value that is not a person
    at all: it is not one of the people the rules offered.

    ``OverflowError`` is in the list because ``1e400`` is an ordinary JSON
    number that arrives as ``float('inf')``, and ``int()`` of that overflows
    rather than failing to parse.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        raise _not_offered(about_an_excursion) from None


def _clean_members(declaration: Input, value: Any, *, about_an_excursion: bool = True) -> Any:
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
    ids = [_as_member(member_id, about_an_excursion=about_an_excursion) for member_id in picked]
    for member_id in ids:
        if member_id not in allowed:
            raise _not_offered(about_an_excursion)
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
