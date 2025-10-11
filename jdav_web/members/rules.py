from contrib.rules import memberize_user
from django.utils import timezone
from rules import predicate


@predicate
@memberize_user
def is_oneself(self, other):
    assert other is not None
    return self.pk == other.pk


@predicate
@memberize_user
def may_view(self, other):
    assert other is not None
    return self.may_view(other)


@predicate
@memberize_user
def may_change(self, other):
    assert other is not None
    return self.may_change(other)


@predicate
@memberize_user
def may_delete(self, other):
    assert other is not None
    return self.may_delete(other)


@predicate
@memberize_user
def is_own_training(self, training):
    assert training is not None
    return training.member == self


@predicate
@memberize_user
def is_leader_of_excursion(self, ljpproposal):
    assert ljpproposal is not None
    if not hasattr(ljpproposal, 'excursion'):
        return _is_leader(self, ljpproposal)
    return _is_leader(self, ljpproposal.excursion)


@predicate
@memberize_user
def is_leader(self, excursion):
    assert excursion is not None
    return _is_leader(self, excursion)


def _is_leader(member, excursion):
    if not hasattr(member, 'pk'):
        return False
    if member.pk is None:
        return False
    if member in excursion.jugendleiter.all():
        return True
    yl = [ yl for group in excursion.groups.all() for yl in group.leiters.all() ]
    return member in yl


@predicate
@memberize_user
def statement_not_submitted(self, excursion):
    assert excursion is not None
    if not hasattr(excursion, 'statement'):
        return False
    if excursion.statement is None:
        return False
    return not excursion.statement.submitted


@predicate
@memberize_user
def is_leader_of_relevant_invitation(member, waiter):
    assert waiter is not None
    return waiter.invitationtogroup_set.filter(group__leiters=member).exists()
