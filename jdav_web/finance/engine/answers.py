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
a set larger than the bound — is **dropped and reported**
(:func:`within`, applied in :func:`finance.engine.evaluation._answered`). The
rules read it as unanswered, which is the same decision as a retired question
(taxis #579), *and* the evaluation says so, which is the part that cannot be
left out: a statement that owes somebody money must not close at ``0.00``
while every page still names the recipient.

The domain is only ever asked of an answer somebody **gave**. A value the
engine supplies from a :attr:`~kompass.rules.Input.source` comes out of the
statement's own data instead, and what bounds that is
:func:`finance.engine.declared.unbounded`.

**A ``rows`` answer is one answer**, and both paragraphs above apply to it
whole. Each cell is typed and domain-checked by the one-question declaration
:meth:`~kompass.rules.Field.as_input` makes of it, so there is no second
vocabulary and no second domain check; but a cell that fails takes the table
with it — a type error makes the whole table read as the raw JSON and raise, a
withdrawn option drops the whole table and reports it. That is the
``member_set`` decision ("dropped **whole**, not member by member") read for a
table, and for the same reason: which rows survive is a selection nobody made,
and the statement is blocked either way.
"""

from collections.abc import Iterable
from collections.abc import Mapping
from decimal import Decimal
from typing import Any

from finance.rules_api import Input
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Row

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
#:
#: ``rows`` is ``()``, and that is the whole of what an empty table means: a
#: table nobody has filled in, a table whose rows were all deleted and a table
#: the form has stopped asking for read the same, because they *are* the same
#: and inventing a difference would need a state nothing stores. A rule that
#: pays per row pays nothing for any of the three.
EMPTY: dict[str, object] = {
    "money": Decimal("0.00"),
    "int": 0,
    "bool": False,
    "text": "",
    "choice": "",
    "member": None,
    "member_set": (),
    "rows": (),
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

    **It judges only what it recognises.** A value whose type does not fit its
    declaration is outside every domain, and reading it as "no longer offered"
    would be the wrong story *and* would hide the right one: a retyped key has
    to stay loud, so that the rule's own accessor raises and the evaluation
    reports it as the type error it is. So each arm below asks its question of
    a value of its own type and answers ``True`` for anything else.

    The domain is asked of an answer somebody *gave*. It says nothing about one
    the engine supplies from a :attr:`~kompass.rules.Input.source`: that value
    comes out of the statement's own data rather than out of this list, and
    what bounds it is :func:`finance.engine.declared.unbounded`.
    """
    if declaration.type == "choice":
        if not isinstance(value, str):
            return True
        return value == "" or value in {choice.value for choice in declaration.choices}
    if declaration.type == "member":
        return not isinstance(value, Member) or value in declaration.options
    if declaration.type == "member_set":
        if not isinstance(value, tuple) or not all(isinstance(who, Member) for who in value):
            return True
        if declaration.max is not None and len(value) > declaration.max:
            return False
        return all(who in declaration.options for who in value)
    if declaration.type == "int":
        if isinstance(value, bool) or not isinstance(value, int):
            return True
        return declaration.max is None or value <= declaration.max
    if declaration.type == "rows":
        if not isinstance(value, tuple) or not all(isinstance(row, Row) for row in value):
            return True
        if declaration.max is not None and len(value) > declaration.max:
            return False
        # A table is dropped **whole**, exactly as a `member_set` is, and for
        # the same reason: picking which rows survive is a selection nobody
        # made. One journey naming somebody the rules no longer offer stops the
        # statement paying any of them, the evaluation says so, and nothing is
        # paid until the table is given again.
        cells = _cells(declaration)
        return all(within(cell, row.raw(cell.key)) for row in value for cell in cells)
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
    """One **stored** answer, as the type its declaration promises.

    The other half of :func:`finance.inputs.clean_value`: that one takes what a
    client sent and makes it storable, this one takes what was stored and makes
    it readable by a rule. The vocabulary is the same eight types, and an
    unanswered question reads as its type's empty value — ``0.00`` for money,
    ``None`` for a person, ``()`` for a set of them — because
    :class:`kompass.rules.Inputs` promises exactly that.

    Money goes through ``str`` on its way to :class:`~decimal.Decimal`, so a
    JSON number never arrives as its binary expansion.

    **A value that does not fit is handed through untouched**, not raised on.
    A section may change what a question asks for while statements still hold
    an answer under that key, and ``inputs`` keeps a retired key rather than
    pruning it. Raising here would make every read of that statement a 500,
    including the ``/form`` request that is the only way to put a new answer
    in. Handed through, the rule's own typed accessor raises
    :class:`kompass.rules.RuleError` instead, which
    :func:`finance.engine.evaluation.evaluate` reports.

    What it deliberately does **not** do is drop an answer the declaration no
    longer offers. That is :func:`within`'s question, and it is asked in
    :func:`finance.engine.evaluation._answered` instead — because dropping an
    answer is a thing somebody has to be *told* about, and ``evaluate`` is
    where a thing can be told. Dropping it here left the one state nobody
    could see: zero paid, the recipient still named on every page, no error, no
    failing check, and ``validity`` reporting that everything was in order.
    """
    try:
        return _fitted(declaration, value)
    except (TypeError, ValueError, ArithmeticError):
        return value


def _cells(declaration: Input) -> tuple[Input, ...]:
    """Each cell of a ``rows`` question as the one-question declaration it is.

    The table's people are passed down to every party-valued cell, because who
    may be named belongs to the question and not to the column
    (:attr:`kompass.rules.Input.options`). Everything below then validates a
    cell with the same functions it validates an answer with, which is the
    point: there is one domain check for a ``choice``, and a ``choice`` cell is
    on it.
    """
    return tuple(cell.as_input(declaration.options) for cell in declaration.fields)


def _fitted_row(declaration: Input, cells: tuple[Input, ...], row: Any) -> Row:
    """One row, as the :class:`~kompass.rules.Row` of typed cells a rule reads.

    Every declared field is present whether the row answered it or not, so a
    rule reading a cell nobody filled in gets that type's empty value rather
    than a :class:`~kompass.rules.RuleError` — the same promise
    :class:`~kompass.rules.Inputs` makes about a question. A key the row carries
    and the declaration does not is dropped here, for the same reason
    :func:`typed_inputs` restricts the answers: the rules stopped asking.

    A cell whose *type* does not fit raises, which takes the **whole table**
    through :func:`typed`'s ``except`` and hands it to the rules as the raw
    JSON — so ``ctx.inputs.rows(...)`` raises and the evaluation reports it.
    That is the retyped-key reading, applied to a table: loud, because a section
    that changed what a column asks for while answers are stored under it has a
    statement somebody has to look at, not a figure to quietly read as zero.
    """
    if not isinstance(row, Mapping):
        raise TypeError(f"a row is not {type(row).__name__}")
    return Row(declaration.key, {cell.key: _fitted(cell, row.get(cell.key)) for cell in cells})


def _fitted(declaration: Input, value: Any) -> object:
    if declaration.type == "rows":
        # A string is iterable and a dict iterates its keys, so the same guard
        # `member_set` needs applies here and for the same reason: a section
        # retyping a key that already holds a text answer.
        if value is not None and not isinstance(value, list | tuple):
            raise TypeError(f"a table of rows is not {type(value).__name__}")
        cells = _cells(declaration)
        return tuple(_fitted_row(declaration, cells, row) for row in value or ())
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
    was derived, or a hand-crafted write — is shadowed rather than read.

    Nothing here drops an answer for being outside its domain: that is
    :func:`finance.engine.evaluation._answered`'s job, where it can be
    reported. So the context this builds carries the answer as *stored*, which
    is what :meth:`~kompass.rules.Ruleset.relevant_inputs` and ``/form`` are
    asked about — and an answer in that state is one the evaluation refuses to
    settle, so there is no steady state in which the two could disagree about
    a figure that matters.
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


def no_longer_offered(declarations: Iterable[Input], answers: Mapping[str, object]) -> list[str]:
    """Every *typed* answer in ``answers`` its declaration no longer offers.

    Asked of a context's own answers rather than of the stored JSON, so that
    one implementation serves every route: a statement, a case file and the
    fuzzer all arrive here as typed values.

    Keys the engine supplied are not in scope, and are the caller's to leave
    out: a derived figure is not an answer somebody gave, so there is no domain
    it could have fallen out of.
    """
    return [
        declaration.key
        for declaration in declarations
        if not within(declaration, answers.get(declaration.key))
    ]
