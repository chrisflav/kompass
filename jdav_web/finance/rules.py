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

from contrib.rules import has_global_perm
from contrib.rules import memberize_user
from members.models import Freizeit
from members.rules import _is_leader
from rules import predicate


def _statement_of(obj: Any) -> Any:
    """The statement a predicate was asked about, or ``None``.

    Two callers pass something that is not a statement. The admin's excursion
    page asks these predicates about the :class:`~members.models.Freizeit`
    itself, which stands for the statement hanging off it — and a trip without
    one stands for nothing. And django-rules asks them with ``None`` when the
    permission is checked globally.
    """
    if isinstance(obj, Freizeit):
        return getattr(obj, "statement", None)
    return obj


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
    statement = _statement_of(statement)
    if statement is None:
        return False
    return bool(statement.may_be_approved_by(self))


@predicate
@memberize_user
def is_named_signer(self: Any, statement: Any) -> bool:
    """Whether the section's rules name this member a signer of ``statement``.

    Being asked for a signature is what makes a statement this person's
    business, so it is also what lets them *see* it — the hole this closes was
    a Ressortleitung whom Ludwigsburg's rules name on her own department's
    statement, who could sign it and could not open the page that would have
    let her: the right to sign came from the rules and the right to look came
    from an object ACL that knew nothing about them.

    It is deliberately a *wider* question than :func:`may_approve`, and the
    difference is a signature already given: somebody who has signed has
    nothing left to sign, and a page that disappears the moment you use it is
    not a page. So this asks whether the record names her among those who may
    sign a step the rules are actually **asking for** — not whether that step
    is still open.

    Three bounds make it self-limiting rather than a permission:

    * it is **per statement**, named by that statement's own frozen record;
    * only a step that **applies** counts, so a treasurer named on a threshold
      step the payout never reached is not named by it;
    * it starts at **submission** and follows the record, so a draft names
      nobody (the rules have asked for nothing yet) and a statement handed
      back to its author stops naming anybody again.

    See :meth:`finance.models.Statement.names_as_signer`, which is also what
    the statement list is scoped by, so the list and this predicate cannot
    disagree.
    """
    statement = _statement_of(statement)
    if statement is None:
        return False
    return bool(statement.names_as_signer(self))


#: The right to sign a statement off: the global capability, and whatever the
#: section's rules still leave this person to do.
#:
#: One object, used for ``approve_obj`` **and** as one of the ways to earn
#: ``view_obj`` — so "may sign" can never again mean "may not look". The two
#: rights are the same predicate rather than two predicates that agree today.
may_sign_now = has_global_perm("finance.process_statementsubmitted") & may_approve
