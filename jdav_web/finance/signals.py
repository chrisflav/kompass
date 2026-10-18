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

from django.db.models.signals import post_delete
from django.dispatch import receiver
from members.models import Member

from .inputs import party_keys
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
    for statement in Statement.objects.filter(pk__in=mentions):
        keys = _party_keys(statement)
        if keys is None:
            continue
        answers = statement.answers
        pruned = dict(answers)
        for key in keys:
            value = answers.get(key)
            if isinstance(value, list):
                pruned[key] = [pk for pk in value if not _is(pk, member_id)]
            elif _is(value, member_id):
                pruned[key] = None
        if pruned != answers:
            statement.inputs = pruned
            statement.save(update_fields=["inputs"])
            changed.append(statement.pk)
    return changed


def _party_keys(statement: Any) -> set[str] | None:
    """Which answers name people, or ``None`` when the rules would not say.

    Asking is a call into a section's own Python, and this one runs inside the
    deletion's transaction: raising would propagate out of ``member.delete()``,
    poison that transaction and roll the deletion back, so a section's own bug
    would make members undeletable. :func:`finance.engine.evaluation.evaluate`
    goes to the same trouble for the same reason. Skipping leaves an id in a
    *draft*, which the readouts drop and which nothing has frozen.
    """
    try:
        return party_keys(statement)
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
    """
    for value in answers.values():
        if _is(value, member_id):
            return True
        if isinstance(value, list) and any(_is(entry, member_id) for entry in value):
            return True
    return False


@receiver(post_delete, sender=Member, dispatch_uid="finance.forget_deleted_member")
def _forget_deleted_member(sender: Any, instance: Any, **kwargs: Any) -> None:
    forget_member(instance.pk)
