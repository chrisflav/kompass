"""Rendering the approval state for the API and the admin.

One function, used by three callers (the ``/approval`` endpoint, the two
actions that change it, and the admin's overview page), so that what a person
sees about who still has to sign is assembled in exactly one place.

A statement that is still waiting shows the states the **gate** uses — the
frozen rows with eligibility re-asked, which is what decides whether the
button appears — and a settled one shows the rows as they were frozen, because
that is the record and nothing should re-run the rules to render it. Showing
one and deciding by the other is how an earlier version came to report
``approved: true`` beside a constraint displayed as open.

Which is also why the words come from the state and not from the row; see
:func:`state_display`.
"""

from typing import Any

from django.utils.translation import gettext as _
from finance.engine.approval import ConstraintState
from members.models import Member


def state_display(state: ConstraintState) -> str:
    """The state as a person reads it, with override and quorum apart.

    "Does not apply" and "nobody signed" are different facts, and so are "the
    quorum is in" and "somebody decided to go ahead anyway" — which is why
    this has more answers than a boolean. "Could not be resolved" is the
    reason a payout is stuck when a section's own rule broke.

    It is derived from the :class:`~finance.engine.approval.ConstraintState`
    rather than from the frozen
    :class:`~finance.store.ApprovalConstraint` row, and that is the whole
    point: every other field in the payload comes from the state, so a row
    answering this one made a constraint contradict itself in its own
    rendering. The two ways it did, both measured: a signer who has since lost
    the capability left the row's ``satisfied`` column standing, so the payload
    read ``state_display: "Signed"`` beside ``satisfied: false``, ``open:
    true`` and nobody in ``signed_by``; and a step the rules can no longer
    resolve read ``state_display: "Open"`` beside an empty ``eligible`` and an
    error, where "could not be resolved" is the answer. The row is the record
    of what was true at submission (:meth:`~finance.store.ApprovalConstraint.
    as_row`) — a fine thing to render *as the record*, which is what the state
    of a settled statement already is, since it is read from that very row.
    """
    # `gettext`, not `gettext_lazy`: the payload is serialised in the request
    # that built it, and so is the admin page it also feeds. Annotated because
    # Django is `Any` to this repository's mypy configuration.
    text: str
    if not state.applicable:
        text = _("Does not apply")
    elif state.overridden:
        text = _("Overridden")
    elif state.satisfied:
        text = _("Signed")
    elif state.error:
        text = _("Could not be resolved")
    elif not state.eligible:
        # Whatever emptied the group — a forbid that caught everyone, a
        # permission check that rejected everyone, a vacant role — there is
        # nobody who may sign, and that is a different thing to read than
        # "waiting for a signature".
        text = _("Nobody may sign")
    else:
        text = _("Open")
    return text


def approval_payload(statement: Any, member: Any = None) -> dict[str, Any]:
    """Who has to sign ``statement`` off, and who has.

    ``member`` is the person asking, so the payload can say whether *they* may
    still sign — which is the one thing a client needs in order to decide
    whether to offer the button.
    """
    states = (
        statement.live_approval_states
        if statement.submitted and not statement.confirmed
        else statement.approval_states
    )
    rows = {row.name: row for row in statement.approval_constraint_set.all()}
    ids = set()
    for state in states:
        ids.update(state.eligible)
        ids.update(state.signed_by)
        ids.update(exclusion.member for exclusion in state.excluded)
    for approval in statement.approval_set.all():
        if approval.member_id:
            ids.add(approval.member_id)
    for row in rows.values():
        if row.overridden_by_id:
            ids.add(row.overridden_by_id)
    people = Member.objects.in_bulk(sorted(ids)) if ids else {}
    constraints = []
    for state in states:
        row = rows.get(state.name)
        constraints.append(
            {
                "name": state.name,
                "description": state.description,
                "applicable": state.applicable,
                "required": state.required,
                "satisfied": state.satisfied,
                "overridden": state.overridden,
                "open": state.open,
                "missing": state.missing,
                "state_display": state_display(state),
                "eligible": [people[pk] for pk in state.eligible if pk in people],
                "signed_by": [people[pk] for pk in state.signed_by if pk in people],
                "excluded": [
                    {"member": people.get(exclusion.member), "forbid": exclusion.forbid}
                    for exclusion in state.excluded
                ],
                "overridden_by": (people.get(row.overridden_by_id) if row is not None else None),
                "override_reason": row.override_reason if row is not None else "",
            }
        )
    return {
        "statement_id": statement.pk,
        "approved": statement.fully_approved,
        "may_approve": statement.may_be_approved_by(member),
        "constraints": constraints,
        "signatures": [
            {
                "member": people.get(approval.member_id),
                "at": approval.at,
                "note": approval.note,
            }
            for approval in statement.approval_set.all()
        ],
    }
