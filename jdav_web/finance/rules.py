from contrib.rules import memberize_user
from members.models import Freizeit
from members.rules import _is_leader
from rules import predicate


@predicate
@memberize_user
def is_creator(self, statement):
    assert statement is not None
    return statement.created_by == self


@predicate
@memberize_user
def not_submitted(self, statement):
    assert statement is not None
    if isinstance(statement, Freizeit):
        if hasattr(statement, "statement"):
            return not statement.statement.submitted
        else:
            return True
    return not statement.submitted


@predicate
@memberize_user
def leads_excursion(self, statement):
    assert statement is not None
    if isinstance(statement, Freizeit):
        return _is_leader(self, statement)
    if not hasattr(statement, "excursion"):
        return False
    if statement.excursion is None:
        return False
    return _is_leader(self, statement.excursion)


@predicate
@memberize_user
def may_approve(self, statement):
    """Whether this member still has something to sign on ``statement``.

    The second half of the approval question. The first half is the global
    capability — ``finance.process_statementsubmitted``, which says somebody
    may act as an approver at all — and this says whether the section's rules
    leave them anything to do: membership in the eligible set of a constraint
    that applies and is neither signed off nor overridden. A constraint that
    names nobody is answered by the capability alone, which is what Kompass did
    before there were constraints.
    """
    assert statement is not None
    if isinstance(statement, Freizeit):
        statement = getattr(statement, "statement", None)
    if statement is None:
        return False
    return statement.may_be_approved_by(self)
