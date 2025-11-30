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
