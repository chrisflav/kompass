"""Finance API routes.

Permission model reuse:

* ``Statement`` is a :class:`contrib.models.CommonModel`, so it carries the
  custom object-level rules permissions (``view_obj``/``change_obj``/
  ``delete_obj``) and is listed via :func:`contrib.permissions.scope_queryset`.
  The stateful actions reproduce the exact guards and global permissions the
  admin enforces (``process_statementsubmitted`` for submitted-stage actions,
  ``may_manage_confirmed_statements`` for unconfirming).
* ``Bill`` is a ``CommonModel`` too, but its object-level rules live only on the
  ``BillOn*Proxy`` proxies (the base ``Bill`` has none, and it is not handled by
  the member queryset filter). A bill's visibility/editability follows its parent
  statement, so bills are authorized through the statement's object permissions —
  reusing the same predicates rather than inventing new ones.
* ``Transaction`` is a plain model gated by the standard ``view_transaction``
  permission and is strictly read-only (mirroring ``TransactionAdmin``).
"""

from contrib.api.perms import authorize
from contrib.api.perms import get_authorized
from contrib.api.perms import get_member
from contrib.api.perms import partial_clean
from contrib.api.perms import set_scalar_fields
from contrib.permissions import scope_queryset
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.models import Transaction
from members.models import Freizeit
from members.models import Member
from ninja import File
from ninja import Form
from ninja import Router
from ninja import Schema
from ninja.files import UploadedFile

from .schemas import BillBrief
from .schemas import BillCreate
from .schemas import BillOut
from .schemas import BillUpdate
from .schemas import FinanceEnumsOut
from .schemas import FinanceOverviewOut
from .schemas import StatementBrief
from .schemas import StatementCreate
from .schemas import StatementOut
from .schemas import StatementUpdate
from .schemas import TransactionBrief
from .schemas import TransactionOut

router = Router()

# Reproduces the ``RestrictedFileField`` constraints on ``Bill.proof``.
PROOF_CONTENT_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/gif"]
PROOF_MAX_UPLOAD_SIZE_MB = 5


def validate_proof(upload):
    """Enforce the ``Bill.proof`` upload constraints (content type + size)."""
    if upload.content_type not in PROOF_CONTENT_TYPES:
        raise ValidationError(_("Filetype not supported."))
    limit = PROOF_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > limit:
        raise ValidationError(
            _("Please keep filesize under %(mb)s MiB.") % {"mb": PROOF_MAX_UPLOAD_SIZE_MB}
        )


# Sentinel distinguishing "field omitted from the PATCH" from "set to null".
_UNSET = object()


def _resolve_recipient(statement, member_id):
    """Resolve a statement recipient id to a Member, or ``None`` when cleared.

    Mirrors ``StatementOnListForm``: recipients must be youth leaders of the
    statement's excursion (a statement without an excursion accepts none).
    """
    if member_id is None:
        return None
    member = get_object_or_404(Member, pk=member_id)
    excursion = statement.excursion
    if excursion is None or not excursion.jugendleiter.filter(pk=member.pk).exists():
        raise ValidationError(_("Only youth leaders of this excursion may receive contributions."))
    return member


def _validate_allowance_count(statement, members):
    """Replicate ``StatementOnListForm.clean``: allowance recipients must not
    exceed the excursion's approved youth-leader count."""
    excursion = statement.excursion
    if excursion is not None and len(members) > excursion.approved_staff_count:
        raise ValidationError(
            _(
                "This excursion only has up to %(approved_count)s approved youth "
                "leaders, but you listed %(entered_count)s."
            )
            % {
                "approved_count": str(excursion.approved_staff_count),
                "entered_count": str(len(members)),
            }
        )


# --- enums / choices ------------------------------------------------------


@router.get("/enums", response=FinanceEnumsOut)
def finance_enums(request):
    """Labelled choices for the finance app's choice fields (any authenticated user).

    Lets the SPA render labelled ``<select>`` widgets. Currently the only choice
    field in the finance app is ``Statement.status``.
    """
    status = [
        {"value": value, "label": str(label)}
        for value, label in Statement._meta.get_field("status").choices
    ]
    return {"status": status}


# --- statements -----------------------------------------------------------


@router.get("/statements", response=list[StatementBrief])
def list_statements(request):
    """Statements the user may list, scoped by the shared permission filter."""
    return scope_queryset(
        request.user, Statement.objects.all().order_by("-submitted_date"), model=Statement
    )


@router.post("/statements", response=StatementOut)
def create_statement(request, payload: StatementCreate):
    """Create a draft statement (requires the global add permission)."""
    authorize(request, "finance.add_global_statement")
    excursion = None
    if payload.excursion_id is not None:
        excursion = get_object_or_404(Freizeit, pk=payload.excursion_id)
        # ``Statement.excursion`` is unique: without this guard a second create
        # for the same excursion surfaces as a raw IntegrityError (500).
        if Statement.objects.filter(excursion=excursion).exists():
            raise ValidationError(_("This excursion already has a statement."))
    statement = Statement.objects.create(
        short_description=payload.short_description,
        explanation=payload.explanation,
        night_cost=payload.night_cost,
        excursion=excursion,
        created_by=get_member(request),
    )
    # Read the row back so every field carries its database-native type before
    # the computed money properties run during serialization.
    statement.refresh_from_db()
    return statement


@router.get("/statements/{statement_id}", response=StatementOut)
def retrieve_statement(request, statement_id: int):
    """Full statement detail with computed figures, authorized per object."""
    return get_authorized(request, Statement, statement_id, "finance.view_obj_statement")


@router.get("/statements/{statement_id}/overview", response=FinanceOverviewOut)
def statement_finance_overview(request, statement_id: int):
    """The excursion finance overview (``FreizeitAdmin.finance_overview``).

    An estimate of the excursion's expenses vs. the association's contributions,
    mirroring ``admin/freizeit_finance_overview.html``. Requires the statement to
    be tied to an excursion (there is nothing to estimate otherwise).
    """
    statement = get_authorized(request, Statement, statement_id, "finance.view_obj_statement")
    excursion = statement.excursion
    if excursion is None:
        raise Http404(_("This statement is not tied to an excursion."))

    def recipient(member):
        return {"name": member.name, "iban_valid": member.iban_valid} if member else None

    return {
        "statement_id": statement.pk,
        "excursion_name": excursion.name,
        "submitted": statement.submitted,
        "bills": [
            {
                "short_description": bill.short_description,
                "explanation": bill.explanation,
                "amount": bill.amount,
                "paid_by_name": bill.paid_by.name if bill.paid_by else None,
                "paid_by_iban_valid": bool(bill.paid_by and bill.paid_by.iban_valid),
            }
            for bill in statement.bill_set.all()
        ],
        "total_bills_theoretic": statement.total_bills_theoretic,
        "staff_count": statement.real_staff_count,
        "nights": excursion.night_count,
        "price_per_night": statement.real_night_cost,
        "nights_per_yl": statement.nights_per_yl,
        "duration": excursion.duration,
        "allowance_per_day": statement._get_setting("ALLOWANCE_PER_DAY"),
        "allowance_per_yl": statement.allowance_per_yl,
        "kilometers_traveled": excursion.kilometers_traveled,
        "means_of_transport": excursion.get_tour_approach(),
        "euro_per_km": statement.euro_per_km,
        "transportation_per_yl": statement.transportation_per_yl,
        "allowances_paid": statement.allowances_paid,
        "real_staff_count": statement.real_staff_count,
        "allowance_to": [recipient(m) for m in statement.allowance_to.all()],
        "allowance_to_valid": statement.allowance_to_valid,
        "subsidy_to": recipient(statement.subsidy_to),
        "total_subsidies": statement.total_subsidies,
        "total_org_fee": statement.total_org_fee,
        "total_org_fee_theoretical": statement.total_org_fee_theoretical,
        "org_fee": statement._get_setting("EXCURSION_ORG_FEE"),
        "old_participant_count": excursion.old_participant_count,
        "ljp_to": recipient(statement.ljp_to),
        "ljp_contributions": excursion.payable_ljp_contributions,
        "total_seminar_days": excursion.total_seminar_days,
        "ljp_participant_count": excursion.ljp_participant_count,
        "theoretic_ljp_participant_count": excursion.theoretic_ljp_participant_count,
        "seminar_days": [
            {
                "day": str(day["day"]),
                "total_duration": day["total_duration"],
                "sum_days": day["sum_days"],
            }
            for day in excursion.seminar_time_per_day
        ],
        "total_relative_costs": excursion.total_relative_costs,
    }


@router.patch("/statements/{statement_id}", response=StatementOut)
def update_statement(request, statement_id: int, payload: StatementUpdate):
    """Update the editable subset of a draft statement, authorized per object."""
    statement = get_authorized(request, Statement, statement_id, "finance.change_obj_statement")
    # Match the admin, which freezes all fields once a statement is submitted
    # (StatementAdmin.get_readonly_fields / has_change_permission).
    if statement.submitted:
        raise ValidationError(_("Submitted statements can no longer be edited."))
    data = payload.dict(exclude_unset=True)
    # The recipient relations mirror the admin's ``StatementOnListInline``
    # (allowance_to / subsidy_to / ljp_to); apply them separately from the scalars.
    allowance_to_ids = data.pop("allowance_to_ids", _UNSET)
    subsidy_to_id = data.pop("subsidy_to_id", _UNSET)
    ljp_to_id = data.pop("ljp_to_id", _UNSET)
    # Resolve + validate every recipient BEFORE writing anything, and wrap the
    # writes in a transaction, so a rejected recipient never leaves a partial
    # update behind (mirrors the admin form validating in ``clean``).
    subsidy_to = (
        _resolve_recipient(statement, subsidy_to_id) if subsidy_to_id is not _UNSET else _UNSET
    )
    ljp_to = _resolve_recipient(statement, ljp_to_id) if ljp_to_id is not _UNSET else _UNSET
    allowance_members = None
    if allowance_to_ids is not _UNSET and allowance_to_ids is not None:
        allowance_members = [_resolve_recipient(statement, mid) for mid in allowance_to_ids]
        _validate_allowance_count(statement, allowance_members)
    with transaction.atomic():
        set_scalar_fields(statement, data, list(data.keys()))
        if subsidy_to is not _UNSET:
            statement.subsidy_to = subsidy_to
        if ljp_to is not _UNSET:
            statement.ljp_to = ljp_to
        statement.save()
        if allowance_members is not None:
            statement.allowance_to.set(allowance_members)
    statement.refresh_from_db()
    return statement


@router.delete("/statements/{statement_id}", response={204: None})
def delete_statement(request, statement_id: int):
    """Delete a draft statement (the rules guard forbids submitted ones)."""
    statement = get_authorized(request, Statement, statement_id, "finance.delete_obj_statement")
    statement.delete()
    return 204, None


# --- statement actions ----------------------------------------------------


@router.post("/statements/{statement_id}/submit", response=StatementOut)
def submit_statement(request, statement_id: int):
    """Submit a draft statement to the finance department."""
    statement = get_authorized(request, Statement, statement_id, "finance.change_obj_statement")
    if statement.submitted:
        raise ValidationError(_("Statement is already submitted."))
    # Reproduce the excursion finance-overview submit guards (FreizeitAdmin.
    # finance_overview): valid allowance recipients, and a proof for every bill
    # when LJP contributions are claimed.
    if statement.excursion is not None:
        if not statement.allowance_to_valid:
            raise ValidationError(
                _(
                    "The configured recipients of the allowance don't match the "
                    "regulations. Please correct this and try again."
                )
            )
        if statement.ljp_to and len(statement.bills_without_proof) > 0:
            raise ValidationError(
                _(
                    "The excursion is configured to claim LJP contributions. In that "
                    "case, a proof must be uploaded for every bill."
                )
            )
    statement.submit(get_member(request))
    return statement


@router.post("/statements/{statement_id}/generate-transactions", response=StatementOut)
def generate_transactions(request, statement_id: int):
    """Generate the payout transactions for a submitted statement."""
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.process_statementsubmitted")
    if not statement.submitted or statement.confirmed:
        raise ValidationError(_("Only submitted, unconfirmed statements can be processed."))
    if statement.transaction_set.count() > 0:
        raise ValidationError(_("Statement already has transactions."))
    if not statement.generate_transactions():
        raise ValidationError(
            _("Could not generate transactions. Ensure every covered bill has a payer.")
        )
    return statement


@router.post("/statements/{statement_id}/reduce-transactions", response=StatementOut)
def reduce_transactions(request, statement_id: int):
    """Bundle transactions to the same member/ledger to reduce bank transfers."""
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.process_statementsubmitted")
    if not statement.submitted or statement.confirmed:
        raise ValidationError(_("Only submitted, unconfirmed statements can be processed."))
    statement.reduce_transactions()
    return statement


@router.post("/statements/{statement_id}/confirm", response=StatementOut)
def confirm_statement(request, statement_id: int, send: bool = False):
    """Confirm (pay out) a submitted statement, optionally mailing the summary."""
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.process_statementsubmitted")
    if not statement.confirm(get_member(request)):
        raise ValidationError(_("Statement is not ready to be confirmed."))
    if send:
        member = get_member(request)
        statement.send_summary(cc=[member.email] if member else [])
    return statement


@router.post("/statements/{statement_id}/reject", response=StatementOut)
def reject_statement(request, statement_id: int):
    """Reject a submitted statement, returning it to the draft state."""
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.process_statementsubmitted")
    # A confirmed statement must go back through unconfirm (which requires the
    # stronger may_manage_confirmed_statements gate); reject only reverts drafts
    # that are still in the submitted stage.
    if not statement.submitted or statement.confirmed:
        raise ValidationError(_("Only submitted, unconfirmed statements can be rejected."))
    statement.status = Statement.UNSUBMITTED
    statement.save()
    return statement


@router.post("/statements/{statement_id}/unconfirm", response=StatementOut)
def unconfirm_statement(request, statement_id: int):
    """Revert a confirmed statement back to the submitted state."""
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.may_manage_confirmed_statements")
    if not statement.confirmed:
        raise ValidationError(_("Statement is not confirmed."))
    statement.status = Statement.SUBMITTED
    statement.confirmed_date = None
    statement.confirmed_by = None
    statement.save()
    return statement


# --- bills ----------------------------------------------------------------


@router.get("/bills", response=list[BillBrief])
def list_bills(request):
    """Bills belonging to statements the user may list."""
    statements = scope_queryset(request.user, Statement.objects.all(), model=Statement)
    return Bill.objects.filter(statement__in=statements).order_by("-id")


@router.post("/bills", response=BillOut)
def create_bill(
    request,
    payload: BillCreate = Form(...),
    proof: UploadedFile | None = File(None),
):
    """Create a bill on a statement the user may change."""
    statement = get_object_or_404(Statement, pk=payload.statement_id)
    authorize(request, "finance.change_obj_statement", statement)
    if proof is not None:
        validate_proof(proof)
    paid_by = None
    if payload.paid_by_id is not None:
        paid_by = get_object_or_404(Member, pk=payload.paid_by_id)
    bill = Bill(
        statement=statement,
        short_description=payload.short_description,
        explanation=payload.explanation,
        amount=payload.amount,
        paid_by=paid_by,
        costs_covered=payload.costs_covered,
    )
    if proof is not None:
        bill.proof = proof
    bill.save()
    return bill


@router.get("/bills/{bill_id}", response=BillOut)
def retrieve_bill(request, bill_id: int):
    """Bill detail, authorized through its parent statement."""
    bill = get_object_or_404(Bill, pk=bill_id)
    authorize(request, "finance.view_obj_statement", bill.statement)
    return bill


@router.patch("/bills/{bill_id}", response=BillOut)
def update_bill(request, bill_id: int, payload: BillUpdate):
    """Update a bill's scalar fields (proof is uploaded via the proof endpoint).

    File uploads are handled by the dedicated ``/bills/{id}/proof`` POST endpoint;
    Django only populates ``request.FILES`` for POST, so a JSON PATCH is used for
    the remaining fields.
    """
    bill = get_object_or_404(Bill, pk=bill_id)
    authorize(request, "finance.change_obj_statement", bill.statement)
    data = payload.dict(exclude_unset=True)
    if "paid_by_id" in data:
        paid_by_id = data.pop("paid_by_id")
        bill.paid_by = get_object_or_404(Member, pk=paid_by_id) if paid_by_id is not None else None
    set_scalar_fields(bill, data, list(data.keys()))
    bill.save()
    return bill


@router.post("/bills/{bill_id}/proof", response=BillOut)
def upload_bill_proof(request, bill_id: int, proof: UploadedFile = File(...)):
    """Attach/replace a bill's proof file on a statement the user may change."""
    bill = get_object_or_404(Bill, pk=bill_id)
    authorize(request, "finance.change_obj_statement", bill.statement)
    validate_proof(proof)
    bill.proof = proof
    bill.save()
    return bill


@router.delete("/bills/{bill_id}", response={204: None})
def delete_bill(request, bill_id: int):
    """Delete a bill on a statement the user may change."""
    bill = get_object_or_404(Bill, pk=bill_id)
    authorize(request, "finance.delete_obj_statement", bill.statement)
    bill.delete()
    return 204, None


# --- transactions (read-only) ---------------------------------------------


@router.get("/transactions", response=list[TransactionBrief])
def list_transactions(request):
    """List transactions (read-only; standard ``view_transaction`` perm)."""
    authorize(request, "finance.view_transaction")
    return Transaction.objects.all().order_by("-id")


@router.get("/transactions/{transaction_id}", response=TransactionOut)
def retrieve_transaction(request, transaction_id: int):
    """Transaction detail including its EPC-QR (``code``) payload."""
    authorize(request, "finance.view_transaction")
    return get_object_or_404(Transaction, pk=transaction_id)


class TransactionInlineUpdate(Schema):
    """Editable fields of the submitted-statement transaction inline.

    Mirrors ``TransactionOnSubmittedStatementInline.fields`` (amount, member,
    reference, ledger). All optional for PATCH; ``member``/``ledger`` set by id.
    """

    amount: float | None = None
    reference: str | None = None
    member_id: int | None = None
    ledger_id: int | None = None


@router.patch("/transactions/{transaction_id}", response=TransactionOut)
def update_transaction(request, transaction_id: int, payload: TransactionInlineUpdate):
    """Edit a transaction's inline fields (amount/member/reference/ledger).

    Reproduces ``TransactionOnSubmittedStatementInline`` (only reachable from a
    submitted statement): gated on ``finance.process_statementsubmitted`` and
    only while the parent statement is submitted-and-not-confirmed. Declared on
    this router (not the inlines router) so it shares the ``/transactions/{id}``
    path with the GET — a second router on the same path would 405.
    """
    authorize(request, "finance.process_statementsubmitted")
    transaction = get_object_or_404(Transaction, pk=transaction_id)
    statement = transaction.statement
    if not statement.submitted or statement.confirmed:
        raise ValidationError(
            _("Transactions can only be edited on submitted, unconfirmed statements.")
        )
    data = payload.dict(exclude_unset=True)
    changed = []
    if "amount" in data:
        transaction.amount = data["amount"]
        changed.append("amount")
    if "reference" in data:
        transaction.reference = data["reference"]
        changed.append("reference")
    if "member_id" in data:
        transaction.member = get_object_or_404(Member, pk=data["member_id"])
        changed.append("member")
    if "ledger_id" in data:
        ledger_id = data["ledger_id"]
        transaction.ledger = (
            get_object_or_404(Ledger, pk=ledger_id) if ledger_id is not None else None
        )
        changed.append("ledger")
    partial_clean(transaction, changed)
    transaction.save()
    return transaction
