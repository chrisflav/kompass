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

**A table is validated cell by cell, by the same code as a question.** A
``rows`` declaration asks one question several times over
(:class:`~kompass.rules.Field`), and :func:`clean_value` is given each cell as
the one-question :class:`~kompass.rules.Input` it is — so there is no second
vocabulary, no second domain check and no second set of messages to drift from
the first. What the table *does* need of its own is somewhere to put the
refusal: :func:`row_key` is the error-key grammar that lets a ``422`` about one
person's kilometres land on that cell instead of on the whole table, and it is
the one part of this feature a client depends on by shape rather than by value.

**A cell the declaration no longer names is ignored, not refused.**
:meth:`~kompass.rules.Ruleset.inputs` may declare a table's
:attr:`~kompass.rules.Input.fields` differently depending on an answer, so a
column can belong to one regime and not to the other — and a row stored while
it was asked for still carries it. Refusing that row would make switching the
regime back and forth refuse every later edit over a column nobody can see,
which is the shape of the bug taxis #579 fixed one level up. So the cell is
passed through to storage unread and unchecked (:func:`_clean_rows`), it moves
no money while the column is away —
:func:`finance.engine.answers._fitted_row` leaves it out of the row a rule gets
— and it is checked by the declaration that asks for it when the column comes
back.

What tells a retired cell from a typo is the statement's **own stored answer**:
:func:`retired_cells` reads the keys the stored rows carry, and nothing reaches
``Statement.inputs`` except through here, so a key in there is a key some
version of this declaration asked for. A key in neither the declaration nor the
storage is refused exactly as before.
"""

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from decimal import InvalidOperation
from typing import Any

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from finance.rules_api import Choice
from finance.rules_api import Input
from finance.rules_api import Member as RuleMember
from finance.rules_api import RuleContext
from members.models import Member

from .engine import Asked
from .engine import asking
from .engine import offers
from .engine import ruleset_for
from .engine import seeds
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

#: How precisely a ``decimal`` answer may be given, and how large it may be.
#:
#: Not the cent, which is the whole point of the type: a quantity that is not
#: money has no reason to stop at two places, and the money rules — whole
#: cents, nothing below zero — are about the euro, not about the decimal
#: point. Four places is a quarter of a day as ``0.25`` with room to spare, and
#: the ceiling is :func:`form_field`'s own, for the reason ``MONEY_DIGITS`` is.
#: A section that wants a narrower range writes a :class:`~kompass.rules.Check`.
DECIMAL_PLACES = 4
DECIMAL_DIGITS = 9
DECIMAL_MAX = Decimal(10 ** (DECIMAL_DIGITS - DECIMAL_PLACES)) - Decimal("0.0001")


def row_key(key: str, index: int) -> str:
    """``"reisen[1]"`` — the error key for one whole row of a table.

    The 422 this API answers is ``{"errors": {"<key>": [...]}}``, one entry per
    *question*, which a client prints under the field it names. A table is one
    question with a grid of fields, so a refusal about one person's kilometres
    had nowhere to land: keyed by the question it appears under the whole table,
    which tells somebody with five journeys in front of them that one of them is
    wrong.

    The keys are therefore a path, and this is the whole grammar:

    ``"reisen"``
        the table itself — too many rows, or not a table at all.
    ``"reisen[1]"``
        the row at index 1, zero-based, in the order the request sent them —
        a row that is not a set of answers, or answers a field that does not
        exist.
    ``"reisen[1].kilometers"``
        the ``kilometers`` cell of that row, which is where almost every
        refusal about a table actually belongs.

    Zero-based because the client sent an array and will index back into it;
    what a person is shown is the client's business, and a row number in the
    *message* would be a second numbering to keep in step with the first.

    Every key not in this shape is a question key exactly as before, so nothing
    that reads ``errors`` has to change to keep working — the type is still
    ``Record<string, string[]>``. What changes is that a cell error is now
    *placeable*, and that is the one decision in this feature that is hard to
    take back: an error key is what a client renders against, so it is settled
    here, in the one function both the message side and the documentation point
    at.
    """
    return f"{key}[{index}]"


def cell_key(key: str, index: int, field: str) -> str:
    """``"reisen[1].kilometers"`` — the error key for one cell (see :func:`row_key`)."""
    return f"{row_key(key, index)}.{field}"


def flat_messages(problem: ValidationError) -> list[str]:
    """``problem``'s messages as one flat list, cell paths folded into the text.

    For a form with one field per question and nowhere to put a per-cell error:
    the admin's excursion inline, which renders a table as one JSON field.
    ``"reisen[1].kilometers: Kilometer ist keine ganze Zahl."`` says the same
    thing in one string that the API says in a key, which is less than the SPA
    gets and is stated as less.
    """
    if not hasattr(problem, "error_dict"):
        return list(problem.messages)
    return [
        f"{where}: {message}"
        for where, messages in problem.message_dict.items()
        for message in messages
    ]


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


def _choices(choices: Iterable[Choice]) -> list[dict[str, Any]]:
    """The alternatives a ``choice`` offers, as a client needs them.

    Takes the tuple rather than the declaration, because a question and a cell
    of a table both have one and neither is the other's special case.
    """
    return [{"value": choice.value, "label": str(choice.label)} for choice in choices]


def _declaration(declaration: Input) -> dict[str, Any]:
    """One declaration as a client needs it, with its options resolved.

    ``fields`` is the cells of a ``rows`` question and empty for every other
    type. The people a party-valued cell may name are **not** repeated per
    field: they are the question's ``options``, once, because that is where the
    declaration puts them — so a client renders the same picker in every row of
    that column and cannot be handed two different domains for one table.
    """
    return {
        "key": declaration.key,
        "label": str(declaration.label),
        "type": declaration.type,
        "required": declaration.required,
        "help": str(declaration.help),
        "max": declaration.max,
        "options": options_for(declaration),
        "choices": _choices(declaration.choices),
        "fields": [
            {
                "key": cell.key,
                "label": str(cell.label),
                "type": cell.type,
                "required": cell.required,
                "help": str(cell.help),
                "max": cell.max,
                "choices": _choices(cell.choices),
            }
            for cell in declaration.fields
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
    """A derived or seeded value the way ``Statement.inputs`` would have held it.

    So that one client-side code path reads a derived answer and a stored one:
    money as text, a person as an id, a set of people as a list of ids, a row as
    an object of those. A value that is none of those — a source naming a nested
    structure rather than a figure, which is a ruleset's mistake — comes back as
    text rather than as a 500 on the one endpoint that would say what is wrong.

    It is also what writes a seed down, which is why a mapping is in the list:
    a seeded row *is* stored, so its cells have to come out in exactly the JSON
    a client would have sent for them —
    :func:`finance.engine.declared.seeds` hands over the typed values and this
    is where they become an answer.
    """
    if isinstance(value, RuleMember):
        return int(value.id)
    if isinstance(value, tuple):
        return [_as_json(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _as_json(item) for key, item in value.items()}
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

    **A table is served with its rows as stored**, which means a row may carry
    a cell this form's ``fields`` does not name: a column the declaration has
    put away, holding the answer somebody gave while it was asked for. It is
    served rather than stripped because serving it is what lets a client hand
    it back — :func:`clean` ignores it rather than refusing it, so an echo of
    this payload keeps the value, and a payload that leaves it out drops it.
    Nothing reads it while the column is away, and what makes it readable again
    is the answer that brings the column back.
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


def vocabulary(statement: Any) -> tuple[tuple[Input, ...], RuleContext]:
    """Every key ``statement``'s rules may read or store, and the context asked.

    ``inputs`` and not ``relevant_inputs``, for the two callers whose question
    is about *storage* rather than about the form: which answers name people,
    and which tables are seeded. Both write to or prune ``Statement.inputs``, so
    both have to match :func:`finance.engine.context.build_context`'s own
    vocabulary rather than the narrowed form — a key the form has retired still
    holds an answer, and an answer with a dangling member id in it is a
    constraint violation whether the form shows it or not.

    The context comes back with it, like :func:`asked`'s does and for the same
    reason: a seed is resolved against the context the declarations were asked
    about, and resolving it against a second one is how the two would come
    apart.
    """
    ruleset = ruleset_for(statement)
    context = statement_context(statement, ruleset)
    return asking(ruleset, context, form=False).vocabulary, context


def seeded(statement: Any) -> dict[str, list[dict[str, Any]]]:
    """The rows every seeded table starts with, as ``Statement.inputs`` holds them.

    Called at the one moment a seed applies — when the statement's excursion is
    **set or changed** — and nowhere else. Three call sites, all of them places
    where somebody is editing a statement:
    :func:`finance.api.router.create_statement`,
    :func:`finance.api.router.update_statement` and the admin's excursion
    inline. Not :func:`finance.engine.context.build_context`, and that is the
    whole difference between a seed and a derived value: a context build is a
    read, and a seed is an edit made once on the person's behalf.

    What it must not be is state-triggered. "Seed when the table is empty" is
    the obvious shortcut and it is wrong in the way that matters: a person who
    deletes the prefilled row — because nobody drove — would watch it come back
    on the next page load, with no way to say no. "Seed on every build" is worse
    still: it overwrites the split they just entered. So the trigger is an
    event, the event is the excursion being set, and the answer is the person's
    from then on.

    Every seeded table is in the result, including as an **empty list** when
    none of its seeds resolved — that is what empties the row when an excursion
    is cleared or swapped for a trip-less statement. A table with no seeded
    field at all is not here, so changing the excursion leaves it alone.
    """
    declared, context = vocabulary(statement)
    return {key: [_as_json(row) for row in rows] for key, rows in seeds(declared, context).items()}


def party_answers(statement: Any) -> dict[str, frozenset[str]]:
    """Every key whose answer can name people, mapped to the cells that do.

    A ``member`` or ``member_set`` question maps to the empty set — the answer
    itself names somebody. A ``rows`` question maps to the keys of its
    party-valued **fields**, because that is where the ids are: the answer is a
    list of objects, and a pruner that treated it as a list of ids would walk
    past every one of them.

    Which is not a hypothetical. :mod:`finance.signals` takes a deleted member
    out of a draft's answers precisely to stop an ``Obligation`` being written
    with a ``destination_member_id`` that has no row behind it; told only the
    *key*, it would clear nothing inside a table and leave exactly that. And it
    may not guess, either: a cell holding a count of kilometres can equal a
    member's id, so the fields are asked for by name.

    A **retired** party-valued cell — a column the declaration does not
    currently name — is not in this list, because nothing can be asked of a
    declaration that is not there. A deleted member's id therefore stays inside
    it, and that fails closed rather than open: the cell is unread while the
    column is away, and when the column comes back the id is no longer one the
    rules offer, so :func:`finance.engine.answers.within` drops the table and
    the evaluation says so. Nothing is paid to a member who no longer exists;
    the statement stops resolving until the table is given again.
    """
    found: dict[str, frozenset[str]] = {}
    for declaration in vocabulary(statement)[0]:
        if declaration.type in MEMBER_TYPES:
            found[declaration.key] = frozenset()
        elif declaration.type == "rows":
            cells = frozenset(cell.key for cell in declaration.fields if cell.type in MEMBER_TYPES)
            if cells:
                found[declaration.key] = cells
    return found


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

    A ``rows`` question with a party-valued cell is one of these: its answer
    names people, so it is dropped when the excursion is swapped like any other.
    A caller that has to reach *inside* a row asks :func:`party_answers`, which
    this is the key set of.
    """
    return set(party_answers(statement))


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
    if declaration.type == "decimal":
        # The bound `_clean_decimal` enforces, and no `min_value`: a quantity
        # that is not money may be below zero.
        return forms.DecimalField(
            decimal_places=DECIMAL_PLACES, max_digits=DECIMAL_DIGITS, **common
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
    if declaration.type == "rows":
        # A table, as JSON in a textarea. The admin's inline writes every field
        # it renders, and there is no stock Django widget for a repeating row —
        # a formset inside a nested inline inside a formset is not a thing this
        # form can build per request. So the table is shown as the list of
        # objects it is, `clean_value` checks it exactly as it checks the SPA's,
        # and the refusals arrive folded into one message list
        # (:func:`flat_messages`).
        #
        # That is less than the SPA gets and it is stated as less. A section
        # whose rules ask for a table is a section whose people use the SPA; the
        # admin stays able to read and correct one, which is what it is for.
        return forms.JSONField(**common)
    return forms.CharField(**common)


def retired_cells(declaration: Input, stored: Any) -> frozenset[str]:
    """The cells ``stored`` answers that ``declaration`` does not name any more.

    The witness for "this column was once asked for". A ruleset may declare a
    table's :attr:`~kompass.rules.Input.fields` differently depending on an
    answer, and the engine then has to tell two unknown cell keys apart: one a
    regime has put away, whose stored value is somebody's answer and has to
    survive, and one that is not a column of this table and never was.
    Nothing reaches ``Statement.inputs`` except through :func:`clean` and the
    seeds it checks against the same declarations, so a key the stored rows
    carry is a key a declaration asked for — which makes the storage the only
    record of the wider declaration there is, and the right thing to read.

    It is asked of the **stored** answer and never of the incoming one, so a
    request cannot widen its own vocabulary by inventing a column and then
    claiming it had been put away.

    Anything that is not a list of objects answers the empty set. A table whose
    stored value does not fit its declaration at all is a retyped key, which is
    reported loudly elsewhere (:func:`finance.engine.answers.typed`) and is not
    this function's business.
    """
    if declaration.type != "rows" or not isinstance(stored, list):
        return frozenset()
    declared = {cell.key for cell in declaration.fields}
    return frozenset(
        key for row in stored if isinstance(row, Mapping) for key in row if key not in declared
    )


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

    A **retired cell** of a table is the one thing neither refused nor checked:
    a column the declaration does not name but this statement's stored rows do
    (:func:`retired_cells`) is passed through to storage as it came. There is no
    declaration left to check it against, nothing reads it while the column is
    away, and it is the answer somebody gave while it was asked for — so the
    choice is between keeping it and throwing it away, and refusing the row it
    sits in would do neither while making the form unusable. A cell key the
    storage does not know either is refused exactly as before.
    """
    by_key = {declaration.key: declaration for declaration in declarations(statement)}
    # Read once: `answers` copies the JSON column on every access, and the only
    # thing wanted of it here is the record of a column that has been put away.
    carried = statement.answers
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
                declaration,
                value,
                about_an_excursion=statement.excursion is not None,
                # Read off this statement's own stored answer, which is the only
                # record of a column the declaration has since put away
                # (:func:`retired_cells`). Without it a row echoed back from
                # ``/form`` would be refused over a cell nobody can see.
                retired=retired_cells(declaration, carried.get(key)),
            )
        except ValidationError as problem:
            # A table's refusal is **already keyed**, per cell (:func:`row_key`),
            # so it is raised as it stands. Re-keying it by the question would
            # throw away the only thing that makes it placeable, and the keys it
            # carries all start with this question's own key, so nothing else
            # can claim them.
            if hasattr(problem, "error_dict"):
                raise
            raise ValidationError({key: problem.messages}) from None
    return cleaned


def clean_value(
    declaration: Input,
    value: Any,
    *,
    about_an_excursion: bool = True,
    retired: frozenset[str] = frozenset(),
) -> Any:
    """One answer, checked against one declaration and converted.

    Public because it is the whole of the widget vocabulary in one place:
    ``money`` becomes a non-negative ``Decimal`` in whole cents, ``decimal`` a
    ``Decimal`` held to no cent, ``int`` a bounded whole number, ``member`` and ``member_set`` ids from the declaration's own
    options, ``choice`` one of the declaration's own choices, ``bool`` a flag,
    and anything else text.

    ``rows`` is a list of rows, each row a mapping over the declaration's own
    fields, and every cell goes back through **this function** against the
    one-question declaration :meth:`~kompass.rules.Field.as_input` makes of its
    field. That is not a convenience: it is the guarantee that a ``choice`` cell
    is checked against its choices and a ``member`` cell against the table's
    people, by the same code and with the same message as the question of that
    type a section could have asked instead. A table refuses with a
    ``ValidationError`` **keyed per cell** rather than with a flat message list
    (:func:`row_key`), which is the one way this function's contract differs by
    type.

    ``about_an_excursion`` picks the wording when somebody names a person the
    rules did not offer. The message Kompass has always given says "youth
    leaders of this excursion", which is true of a trip and false of a
    statement that settles a purchase — where the people on offer come from
    whoever paid a receipt. It defaults to the trip's wording because the
    admin's excursion inline is always about one; :func:`clean` asks the
    statement.

    ``retired`` are the cell keys of a ``rows`` ``declaration`` that a stored
    answer carries and the declaration does not, which :func:`clean` resolves
    from the statement (:func:`retired_cells`). They are ignored rather than
    refused, and they default to none, which is what a caller holding a
    declaration and nothing else can honestly say: there is no statement to read
    a wider vocabulary off, so every unknown cell is a typo.
    """
    if declaration.type == "rows":
        return _clean_rows(
            declaration, value, about_an_excursion=about_an_excursion, retired=retired
        )
    if declaration.type in MEMBER_TYPES:
        return _clean_members(declaration, value, about_an_excursion=about_an_excursion)
    if declaration.type == "money":
        return _clean_money(declaration, value)
    if declaration.type == "decimal":
        return _clean_decimal(declaration, value)
    if declaration.type == "int":
        return _clean_int(declaration, value)
    if declaration.type == "choice":
        return _clean_choice(declaration, value)
    if declaration.type == "bool":
        return bool(value)
    return "" if value is None else str(value)


def _clean_rows(
    declaration: Input,
    value: Any,
    *,
    about_an_excursion: bool = True,
    retired: frozenset[str] = frozenset(),
) -> list[dict[str, Any]]:
    """A table of rows, every cell against the field that asks for it.

    **Three states are decided here, and all three are decisions.**

    *An empty table is an unanswered question.* ``[]`` and a key nobody sent
    mean the same thing, are stored the same way and read as ``()``. Nothing
    here refuses one: whether a table is *needed* is
    :attr:`~kompass.rules.Input.required` and the section's own
    :class:`~kompass.rules.Check`, exactly as it is for every other type — a
    form is filled in gradually, and a ``422`` on a table somebody has not
    reached yet would make the first ``PATCH`` of a draft impossible.

    *A row with an empty required cell is accepted and stored.*
    :attr:`~kompass.rules.Field.required` is advisory in the same way
    :attr:`~kompass.rules.Input.required` is: the cell is stored empty and reads
    as its type's empty value, and what refuses to hand the statement in is the
    section's ``checks``, where the sentence is in the section's own words
    ("Für jede Fahrt braucht es ein Verkehrsmittel"). Enforcing it here instead
    would put the one wording Kompass can write in the way of a half-filled
    form, and a rule that pays per kilometre already has to survive a row with
    no distance, because a person can always type ``0``.

    *A member named in two rows is accepted*, and this is the one that deserves
    its reason stated. The engine does not know which field identifies a row —
    nothing in the declaration says so — and more to the point **it cannot tell
    a double entry from a split journey**: two rows for one person at 120 km
    each is a there-and-back that was entered in two halves as readily as it is
    the same trip typed twice. Refusing would make the honest table unsayable in
    order to catch a mistake it cannot reliably recognise, and deduplicating
    would silently discard somebody's row. A section that means one row per
    person says so in a ``Check``, which is the same answer this module already
    gives for a ceiling on an amount, and for the same reason: the sentence is
    the section's.

    *A cell the declaration no longer names is ignored and kept.* ``retired``
    is the set of them, read off the statement's stored answer by
    :func:`retired_cells`, and a row carrying one is neither refused nor
    stripped: the value goes back where it came from, untouched and unchecked.
    A ruleset may declare a table's columns differently depending on an answer,
    so switching that answer back and forth would otherwise refuse every later
    edit over a column nobody can see — the bug taxis #579 fixed for a whole
    question, one level further in. Nothing reads it while the column is away
    (:func:`finance.engine.answers._fitted_row`), so it moves no money; the
    declaration that asks for it checks it again when it returns. An unknown
    cell the storage does not know either is still a refusal keyed to the row.

    **Every cell error at once.** A table is one answer with a grid of fields,
    and a person correcting it wants to see all of what is wrong rather than one
    cell per round trip. Across *questions* the first problem still raises, as
    it always has; within a table nothing is raised until every cell has been
    checked.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValidationError(
            {
                declaration.key: [
                    _("%(label)s is a list of rows.") % {"label": str(declaration.label)}
                ]
            }
        )
    if declaration.max is not None and len(value) > declaration.max:
        raise ValidationError(
            {
                declaration.key: [
                    _("%(label)s may have at most %(max)s rows, but you gave %(count)s.")
                    % {
                        "label": str(declaration.label),
                        "max": str(declaration.max),
                        "count": str(len(value)),
                    }
                ]
            }
        )
    cells = [cell.as_input(declaration.options) for cell in declaration.fields]
    problems: dict[str, list[str]] = {}
    rows: list[dict[str, Any]] = []
    for index, row in enumerate(value):
        if not isinstance(row, dict):
            problems[row_key(declaration.key, index)] = [
                str(_("This row is not a set of answers."))
            ]
            continue
        unknown = sorted(set(row) - {cell.key for cell in cells})
        # A cell this statement already answers is a column a declaration asked
        # for and this one does not: ignored, not refused. A cell nothing has
        # ever stored is a typo, and the message is the one it always was.
        bogus = [key for key in unknown if key not in retired]
        if bogus:
            problems[row_key(declaration.key, index)] = [
                _("This row answers %(keys)s, which these rules do not ask for.")
                % {"keys": ", ".join(bogus)}
            ]
            continue
        cleaned: dict[str, Any] = {}
        for cell in cells:
            try:
                cleaned[cell.key] = clean_value(
                    cell, row.get(cell.key), about_an_excursion=about_an_excursion
                )
            except ValidationError as problem:
                problems[cell_key(declaration.key, index, cell.key)] = problem.messages
        # The retired cells last, as they came. Kept because the value is the
        # person's answer from when the column was asked for, and unchecked
        # because there is no declaration left to check it against — which costs
        # nothing while it is unread, and is checked by the declaration that
        # asks for it the moment the column comes back.
        cleaned.update({key: row[key] for key in unknown})
        rows.append(cleaned)
    if problems:
        raise ValidationError(problems)
    return rows


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


def _clean_decimal(declaration: Input, value: Any) -> Decimal:
    """A quantity that is not money: any sign, up to :data:`DECIMAL_PLACES` places.

    The refusals of :func:`_clean_money` that are about *numbers* and none of
    those that are about *euros*. A value that is not a number, or not a
    finite one, is refused for the same reasons and by the same means; a
    negative one is not, because nothing about a decimal makes it a payment
    in the wrong direction; and a third or fourth place is an answer rather
    than a fraction of a cent.
    """
    try:
        number = Decimal(str(value if value is not None else 0))
    except InvalidOperation:
        raise ValidationError(
            _("%(label)s is not a number.") % {"label": str(declaration.label)}
        ) from None
    if not number.is_finite():
        raise ValidationError(_("%(label)s is not a number.") % {"label": str(declaration.label)})
    # The exponent rather than `normalize()`, and `copy_abs()` rather than
    # `abs()`, for the reason `_clean_money` gives: both of the others apply
    # the decimal context, and `abs(Decimal("1E+1000000"))` raises `Overflow`
    # — a 500 for a string anybody can send. Neither of these uses a context.
    places = max(0, -int(number.as_tuple().exponent))
    if places > DECIMAL_PLACES or number.copy_abs() > DECIMAL_MAX:
        raise ValidationError(
            _(
                "%(label)s has to be a number with at most %(places)s decimal places, "
                "no larger than %(max)s either way."
            )
            % {
                "label": str(declaration.label),
                "places": str(DECIMAL_PLACES),
                "max": str(DECIMAL_MAX),
            }
        )
    return number


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
    return {key: _stored_value(value) for key, value in values.items()}


def _stored_value(value: Any) -> Any:
    """One cleaned answer as JSON, to any depth a table takes it.

    Money is text wherever it sits, including inside a row: a ``Decimal`` is not
    JSON and a float is not money, so a cent in a cell goes through ``str`` for
    the same reason a cent in an answer does.
    """
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, list):
        return [_stored_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _stored_value(item) for key, item in value.items()}
    return value
