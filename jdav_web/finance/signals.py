"""Taking a deleted member out of the answers a draft still holds.

The four Heidelberg columns did this for free and it was easy to miss that they
did: ``subsidy_to`` and ``ljp_to`` were ``SET_NULL`` and ``allowance_to``'s
through rows cascaded, so deleting a member left no statement naming them. JSON
has no such mechanism, and the two sides of the new arrangement then disagree —
:meth:`finance.models.Statement.answer_members` drops an id with no member row,
so every readout says nobody, while
:func:`finance.engine.answers.coerce_input` keeps it, so the rules still name
them. The next materialisation writes an ``Obligation`` whose
``destination_member_id`` points at a row that is gone, and that foreign key
has a real constraint behind it: on MariaDB the next ``Bill.save()`` and the
next ``POST …/submit`` are both 500s.

**Drafts only, and that is not a compromise.** A statement that has been handed
in is already safe without any of this: ``Obligation``'s member columns are
``SET_NULL`` and ``destination_name`` is copied onto the row precisely so that
"an obligation is a record of what was owed to whom, and it has to stay
readable after the member row is gone". Pruning a submitted statement would
instead reach past every freeze there is — ``update_statement`` refuses any
edit to one, the admin's fields go read-only, ``Bill._refresh_statement``
refuses to touch a confirmed one at all — and it would do it silently: the one
edit that stays open after submission, a treasurer marking a bill covered,
re-materialises the live rows, so an allowance and a subsidy would simply stop
being owed and the participants' contribution would be re-struck, with no error
and nothing superseded. ``inputs`` has no supersede mechanism and
``CommonModel`` keeps no history, so there would be no trace either.

An answer to a ``rows`` question needs one more thing of this, and it is why
:func:`finance.inputs.party_answers` reports the *fields* and not only the key:
the answer is a list of objects, so the ids sit one level further in than this
used to reach. Told only the key, the scan would walk past them and the pruning
would clear nothing — which is precisely the dangling ``destination_member_id``
the whole module exists to prevent. The cell is cleared and the row stays; see
:func:`_pruned_rows` for why that and not the other way round.

Which answers name people is the ruleset's declaration rather than a list of
three keys, so it is asked — of :meth:`~kompass.rules.Ruleset.inputs` and not
of ``relevant_inputs``, because the question this has to match is the one
:func:`finance.engine.context.build_context` asks. A ruleset that narrows only
``relevant_inputs`` would otherwise take a key off the form while the engine
kept reading it, and this would skip exactly the key whose dangling id it
exists to remove.
"""

import logging
from typing import Any

from django.db.models import QuerySet
from django.db.models.signals import post_delete
from members.models import Member
from members.models import MemberUnconfirmedProxy

from .inputs import party_answers
from .models import Bill
from .models import BillOnExcursionProxy
from .models import BillOnStatementProxy
from .models import Statement

logger = logging.getLogger(__name__)


def forget_member(member_id: int) -> list[int]:
    """Drop ``member_id`` from every draft answer that names them.

    Returns the statements that changed, which is what lets a test say what
    happened without reading every row back.
    """
    changed: list[int] = []
    # Two phases on purpose. The scan reads two columns of the drafts, because
    # a member deletion is rare but it is one query either way and a statement
    # carries its whole ruleset snapshot — tens of kilobytes of a section's
    # source — in a column nothing here looks at. Only a statement that
    # actually mentions the id is then read in full and asked about its rules.
    mentions = [
        pk
        for pk, answers in Statement.objects.filter(status=Statement.UNSUBMITTED).values_list(
            "pk", "inputs"
        )
        if _mentions(answers or {}, member_id)
    ]
    # The status is asked **again** here, and the rows are locked while this
    # runs. The scan above is a read and the save below is a write, so without
    # it a statement handed in between the two would be pruned anyway —
    # `save()`'s own guard cannot catch that either, since it reads the status
    # off the stale instance this loop fetched. The window is tens of
    # milliseconds and the consequence is round 2's defect at a smaller number:
    # an allowance struck off a frozen payout, silently.
    locked = Statement.objects.filter(
        pk__in=mentions, status=Statement.UNSUBMITTED
    ).select_for_update()
    for statement in locked:
        answering = _party_answers(statement)
        if answering is None:
            continue
        answers = statement.answers
        pruned = dict(answers)
        for key, cells in answering.items():
            value = answers.get(key)
            if cells:
                pruned[key] = _pruned_rows(value, cells, member_id)
            elif isinstance(value, list):
                pruned[key] = [pk for pk in value if not _is(pk, member_id)]
            elif _is(value, member_id):
                pruned[key] = None
        if pruned != answers:
            statement.inputs = pruned
            statement.save(update_fields=["inputs"])
            changed.append(statement.pk)
    return changed


def _pruned_rows(value: Any, cells: frozenset[str], member_id: int) -> Any:
    """``value``, a table, with ``member_id`` out of every cell that named them.

    **The cell is cleared; the row stays.** That is the reading the four columns
    had — ``subsidy_to`` was ``SET_NULL``, so deleting a member left the
    statement and emptied the answer — applied one level in. Dropping the row
    instead would throw away a journey somebody entered, in a draft, with no
    trace and nothing to put it back; cleared, the row is still there with its
    distance and its mode, the cell is empty, and the question is visibly
    unanswered for whoever opens the statement next. A rule reading a journey
    with nobody in it pays nobody, which is the same thing an unanswered
    ``member`` answer does.

    Only the cells :func:`finance.inputs.party_answers` named, never every cell:
    a count of kilometres can equal a member's id, and clearing that would be
    this function inventing a figure.
    """
    if not isinstance(value, list):
        return value
    pruned = []
    for row in value:
        if not isinstance(row, dict):
            pruned.append(row)
            continue
        kept = dict(row)
        for cell in cells:
            held = row.get(cell)
            if isinstance(held, list):
                kept[cell] = [pk for pk in held if not _is(pk, member_id)]
            elif _is(held, member_id):
                kept[cell] = None
        pruned.append(kept)
    return pruned


def _party_answers(statement: Any) -> dict[str, frozenset[str]] | None:
    """Which answers name people, or ``None`` when the rules would not say.

    Asking is a call into a section's own Python, and this one runs inside the
    deletion's transaction: raising would propagate out of ``member.delete()``,
    poison that transaction and roll the deletion back, so a section's own bug
    would make members undeletable. :func:`finance.engine.evaluation.evaluate`
    goes to the same trouble for the same reason. Skipping leaves an id in a
    *draft*, which the readouts drop and which nothing has frozen.
    """
    try:
        return party_answers(statement)
    except Exception as problem:
        logger.warning(
            "statement %s could not say which of its answers name people (%s: %s); "
            "leaving its answers alone",
            statement.pk,
            type(problem).__name__,
            problem,
            exc_info=True,
        )
        return None


def _is(value: Any, member_id: int) -> bool:
    """Whether ``value`` is that member's id — and not ``True``.

    ``True == 1``, so a plain comparison makes every yes/no answer look like
    member 1.
    """
    return not isinstance(value, bool) and value == member_id


def _mentions(answers: dict[str, Any], member_id: int) -> bool:
    """Whether ``member_id`` appears anywhere in ``answers``, under any key.

    Cheap and deliberately over-eager: it decides only whether a statement is
    worth asking its ruleset about, and the declarations decide what counts as
    an answer that names somebody. A number that happens to equal a member's id
    — a count of nights, say — costs one context and keeps its value, which is
    the right way round.

    It looks **inside a row**, because an answer to a ``rows`` question is a list
    of objects and the ids are in their values. This is the scan that decides
    whether a statement is read at all, so missing a table here would make the
    pruning below unreachable for exactly the answers it was extended to reach.
    """
    return any(_mentions_value(value, member_id) for value in answers.values())


def _mentions_value(value: Any, member_id: int) -> bool:
    """Whether ``member_id`` is in ``value``, one level into a list or a row."""
    if _is(value, member_id):
        return True
    if isinstance(value, list):
        return any(_mentions_value(entry, member_id) for entry in value)
    if isinstance(value, dict):
        return any(_mentions_value(cell, member_id) for cell in value.values())
    return False


def _forget_deleted_member(sender: Any, instance: Any, **kwargs: Any) -> None:
    forget_member(instance.pk)


# Connected for the proxy as well as for the model, which is not a belt-and-
# braces nicety: django's collector sends `post_delete` with
# `sender = objs[0].__class__`, so deleting a `MemberUnconfirmedProxy` — the
# admin's *Unbestätigte Anmeldungen*, and what `Member.demote_to_waiter()`
# deletes — never reached a receiver bound to `Member` alone. The collector
# honours `SET_NULL` and the m2m cascade through a proxy, so the arrangement
# this replaces had nothing to miss and this one did. `sender=None` would catch
# any future proxy, but it also gives every model in the project a `post_delete`
# listener, and `Collector.can_fast_delete` checks exactly that: it would turn
# off bulk deletion everywhere. `MemberUnconfirmedProxy` is the only proxy of
# `Member` in the tree. `Signal.connect` keys on `(dispatch_uid, sender)`, so
# the same uid stays idempotent for each.
for _sender in (Member, MemberUnconfirmedProxy):
    post_delete.connect(
        _forget_deleted_member,
        sender=_sender,
        dispatch_uid="finance.forget_deleted_member",
    )


def _deleting_bills(origin: Any) -> bool:
    """Whether the deletion ``origin`` started was a deletion *of bills*.

    The other way a bill goes is in a cascade — its statement being deleted —
    and that one must not be re-resolved: the statement is going too, the
    collector has already listed the rows it will delete, and a generation
    written now would be a row it never listed, refused by the foreign key on
    its way out.
    """
    if isinstance(origin, Bill):
        return True
    return isinstance(origin, QuerySet) and issubclass(origin.model, Bill)


def _refresh_after_bill_deleted(
    sender: Any, instance: Any, origin: Any = None, **kwargs: Any
) -> None:
    """Re-resolve the statement a deleted bill was on, however it was deleted.

    This was ``Bill.delete``, and ``Model.delete`` is the one route a
    *queryset* delete never takes. On a submitted statement that is the route
    back from a retired record: a receipt the rules cannot resolve retires
    the frozen approval rows and writes none (:func:`finance.engine.statements.
    materialise`), and only the next re-freeze writes them again. Deleted
    through a queryset, the receipt took its error with it and left no
    re-freeze behind — rules that resolve cleanly, a statement that reads as
    valid, and not one live row, so nobody could sign it, ever.

    Once per statement per deletion: a queryset delete sends this for every
    bill it removed, after removing all of them, so every call would resolve
    the same state and write the same generation again.
    """
    if not _deleting_bills(origin):
        return
    done = origin.__dict__.setdefault("_refreshed_statements", set())
    if instance.statement_id in done:
        return
    done.add(instance.statement_id)
    instance._refresh_statement()


# For each proxy as well, for the reason the receiver above gives: the
# collector sends `post_delete` with the class of the objects it deleted.
for _sender in (Bill, BillOnExcursionProxy, BillOnStatementProxy):
    post_delete.connect(
        _refresh_after_bill_deleted,
        sender=_sender,
        dispatch_uid="finance.refresh_after_bill_deleted",
    )
