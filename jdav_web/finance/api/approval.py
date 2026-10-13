"""Rendering the approval state for the API and the admin.

One function, used by three callers (the ``/approval`` endpoint, the two
actions that change it, and the admin's overview page), so that what a person
sees about who still has to sign is assembled in exactly one place.

The states come from the frozen :class:`~finance.store.ApprovalConstraint`
rows and the :class:`~finance.store.Approval` signatures, never from re-running
the rules: a statement's routing was decided when it was handed in.
"""

from typing import Any

from members.models import Member


def approval_payload(statement: Any, member: Any = None) -> dict[str, Any]:
    """Who has to sign ``statement`` off, and who has.

    ``member`` is the person asking, so the payload can say whether *they* may
    still sign — which is the one thing a client needs in order to decide
    whether to offer the button.
    """
    states = statement.approval_states
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
                "state_display": str(row.state_display) if row is not None else "",
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
