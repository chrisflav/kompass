"""Editable admin-inline REST routes for the finance app.

The ``TransactionAdmin`` site is fully read-only (add/change/delete all disabled)
— transactions are only ever edited through the
``TransactionOnSubmittedStatementInline`` that ``StatementAdmin`` shows on a
*submitted* statement (``get_inlines``). That inline exposes exactly
``amount``, ``member``, ``reference`` and ``ledger`` and is reachable only from
the ``StatementSubmitted`` change view, which is gated on the global
``finance.process_statementsubmitted`` permission and only offered while the
statement is submitted-and-not-confirmed (mirroring ``overview_view``'s
condition ``obj.submitted and not obj.confirmed``).

These routes reproduce that surface precisely:

* ``GET /statements/{id}/transactions`` lists a statement's transactions for the
  inline display, authorized through the parent statement's object-level view
  permission (the inline lives inside the statement change view).
* ``PATCH /transactions/{id}`` edits the four inline fields, gated on the same
  ``process_statementsubmitted`` global permission AND guarded so it only
  succeeds while the parent statement is submitted-and-not-confirmed —
  reproducing the admin inline's editability rather than the always-read-only
  standalone ``TransactionAdmin``. ``full_clean`` validates the changed fields
  (→ 422).

Mounted at ``/api/finance`` (same prefix as ``finance.api.router``); its GET/PATCH
paths do not collide with that router's operations.
"""

from contrib.api.perms import authorize
from django.shortcuts import get_object_or_404
from finance.models import Statement
from ninja import Router

from .schemas import TransactionOut

router = Router()


# --- transaction inline (list-by-statement) -------------------------------
# NOTE: the editable PATCH /transactions/{id} lives in finance/api/router.py
# (same router as GET /transactions/{id}); a second router on that same path
# returns 405 for the other method rather than falling through.


@router.get("/statements/{statement_id}/transactions", response=list[TransactionOut])
def list_statement_transactions(request, statement_id: int):
    """List a submitted statement's transactions for the inline display.

    Authorized through the parent statement's object-level view permission — the
    inline is rendered inside the statement change view, so visibility follows
    the statement, not the always-read-only standalone transaction perm.
    """
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.view_obj_statement", statement)
    return statement.transaction_set.all().order_by("id")
