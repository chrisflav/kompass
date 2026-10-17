"""Taking a deleted member out of the answers that named them.

The four Heidelberg columns did this for free and it was easy to miss that they
did: ``subsidy_to`` and ``ljp_to`` were ``SET_NULL`` and ``allowance_to``'s
through rows cascaded, so deleting a member left no statement naming them. JSON
has no such mechanism, and the two sides of the new arrangement then disagree —
:meth:`finance.models.Statement.answer_members` drops an id with no member row,
so every readout says nobody, while :func:`finance.engine.answers.coerce_input`
keeps it, so the rules still name them. The next materialisation writes an
``Obligation`` whose ``destination_member_id`` points at a row that is gone,
and that foreign key has a real constraint behind it: on MariaDB the next
``Bill.save()`` and the next ``POST …/submit`` are both 500s.

So the cleanup is explicit now. Which answers name people is the ruleset's
declaration, not a list of three keys, so it is asked — but only of the
statements whose answers actually mention the id, which is a scan of one column
rather than a context per statement.
"""

from typing import Any

from django.db.models.signals import post_delete
from django.dispatch import receiver
from members.models import Member

from .inputs import party_keys
from .models import Statement


def forget_member(member_id: int) -> list[int]:
    """Drop ``member_id`` from every answer that names them.

    Returns the statements that changed, which is what makes this testable
    without reading every row back.
    """
    changed: list[int] = []
    for statement in Statement.objects.all():
        answers = statement.answers
        if not _mentions(answers, member_id):
            continue
        pruned = dict(answers)
        for key in party_keys(statement):
            value = answers.get(key)
            if isinstance(value, list):
                pruned[key] = [pk for pk in value if pk != member_id]
            elif value == member_id:
                pruned[key] = None
        if pruned != answers:
            statement.inputs = pruned
            statement.save(update_fields=["inputs"])
            changed.append(statement.pk)
    return changed


def _mentions(answers: dict, member_id: int) -> bool:
    """Whether ``member_id`` appears anywhere in ``answers``, by any key.

    Cheap and deliberately over-eager: it decides only whether the statement is
    worth asking its ruleset about, and the declarations decide what is an
    answer that names somebody. A number that happens to equal a member's id —
    a count of nights, say — gets a context built for nothing and keeps its
    value, which is the right way round.
    """
    for value in answers.values():
        if value == member_id:
            return True
        if isinstance(value, list) and member_id in value:
            return True
    return False


@receiver(post_delete, sender=Member, dispatch_uid="finance.forget_deleted_member")
def _forget_deleted_member(sender: Any, instance: Any, **kwargs: Any) -> None:
    forget_member(instance.pk)
