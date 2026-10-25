"""Who may do what to a statement, as object-level predicates.

Every one of these is asked about an *object*, and django-rules will ask them
without one: ``user.has_perm("finance.view_obj_statement")`` with no second
argument pads the call with ``None`` (``rules.predicates.Predicate._apply``).
That is a question — "may this person view statements at all?" — and for an
object permission the answer is no. It used to be an ``AssertionError`` out of
:func:`is_creator`, which turned every global check against an object
permission into a 500; a permission that cannot answer is worse than one that
answers conservatively, and ``assert`` was not a refusal in any case, because
``python -O`` drops it.
"""

from typing import Any

from contrib.rules import memberize_user
from members.models import Freizeit
from members.rules import _is_leader
from rules import predicate


@predicate
@memberize_user
def is_creator(self: Any, statement: Any) -> bool:
    if statement is None:
        return False
    return bool(statement.created_by == self)


@predicate
@memberize_user
def not_submitted(self: Any, statement: Any) -> bool:
    if statement is None:
        return False
    if isinstance(statement, Freizeit):
        if hasattr(statement, "statement"):
            return not statement.statement.submitted
        else:
            return True
    return bool(not statement.submitted)


@predicate
@memberize_user
def leads_excursion(self: Any, statement: Any) -> bool:
    if statement is None:
        return False
    if isinstance(statement, Freizeit):
        return bool(_is_leader(self, statement))
    if not hasattr(statement, "excursion"):
        return False
    if statement.excursion is None:
        return False
    return bool(_is_leader(self, statement.excursion))


@predicate
@memberize_user
def may_approve(self: Any, statement: Any) -> bool:
    """Whether this member still has something to sign on ``statement``.

    The second half of the approval question. The first half is the global
    capability — ``finance.process_statementsubmitted``, which says somebody
    may act as an approver at all — and this says whether the section's rules
    leave them anything to do: membership in the eligible set of a constraint
    that applies and is neither signed off nor overridden. A constraint that
    names nobody is answered by the capability alone, which is what Kompass did
    before there were constraints.
    """
    if isinstance(statement, Freizeit):
        statement = getattr(statement, "statement", None)
    if statement is None:
        return False
    return bool(statement.may_be_approved_by(self))
