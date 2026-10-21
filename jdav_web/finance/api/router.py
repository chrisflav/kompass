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
from finance.inputs import clean as clean_inputs
from finance.inputs import form as statement_form_body
from finance.inputs import party_keys
from finance.inputs import seeded as seeded_rows
from finance.inputs import stored as stored_inputs
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

from .approval import approval_payload
from .schemas import ApprovalCreate
from .schemas import ApprovalOverride
from .schemas import BillBrief
from .schemas import BillCreate
from .schemas import BillOut
from .schemas import BillUpdate
from .schemas import FinanceEnumsOut
from .schemas import FinanceOverviewOut
from .schemas import PreflightOut
from .schemas import StatementApprovalOut
from .schemas import StatementBrief
from .schemas import StatementCreate
from .schemas import StatementFormOut
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


def _authorize_bill_change(request, bill):
    """Authorize editing ``bill``, honouring the finance officer's review right.

    A statement freezes on submit, so ``change_obj_statement`` alone would lock
    the finance officer out of the one field that exists for them:
    ``costs_covered`` ("bills that are marked for reimbursement by the finance
    officer"). ``BillOnStatementProxy`` already encodes the admin's rule —
    editable while a draft, or at any time with ``process_statementsubmitted``.
    Its predicates are written against the *statement* (that is what the admin
    inline passes them), hence ``bill.statement`` as the object.

    The check is a union so it only ever widens: every caller the statement rule
    already allowed keeps working.
    """
    if request.user.has_perm("finance.change_obj_statement", bill.statement):
        return
    authorize(request, "finance.change_obj_billonstatementproxy", bill.statement)


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
    # Every row computes its total from its bills, allowances and excursion, so
    # those relations are loaded in bulk rather than once per statement.
    queryset = (
        Statement.objects.select_related("created_by", "excursion", "excursion__ljpproposal")
        .prefetch_related(
            "bill_set",
            # A submitted statement's total is read off its frozen rows.
            "obligation_set",
            "created_by__group",
            "excursion__jugendleiter",
            "excursion__membersonlist__member",
            "excursion__ljpproposal__intervention_set",
        )
        .order_by("-submitted_date")
    )
    return scope_queryset(request.user, queryset, model=Statement)


@router.post("/statements", response=StatementOut)
def create_statement(request, payload: StatementCreate):
    """Create a draft statement (requires the global add permission).

    A statement created *on* an excursion has its seeded tables filled in here
    — one row, as the trip describes it, for the person to correct or to split
    (:func:`finance.inputs.seeded`). This is one of the two moments a seed
    applies; the other is an excursion being changed in ``update_statement``.
    """
    authorize(request, "finance.add_global_statement")
    excursion = None
    if payload.excursion_id is not None:
        excursion = get_object_or_404(Freizeit, pk=payload.excursion_id)
        # ``Statement.excursion`` is unique: without this guard a second create
        # for the same excursion surfaces as a raw IntegrityError (500).
        if Statement.objects.filter(excursion=excursion).exists():
            raise ValidationError(_("This excursion already has a statement."))
    statement = Statement(
        short_description=payload.short_description,
        explanation=payload.explanation,
        excursion=excursion,
        created_by=get_member(request),
    )
    # Resolved against the unsaved row, so the statement is written once: the
    # declarations only need the excursion, and a statement with no bills yet is
    # a context the engine already builds (``_bills`` answers ``()`` for an
    # unsaved one, for the admin's inline).
    statement.inputs = seeded_rows(statement)
    statement.save()
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
        "allowance_to": [recipient(m) for m in statement.allowance_to],
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
    """Update the editable subset of a draft statement, authorized per object.

    Changing the excursion does two things to the answers, for one reason: they
    were given about a different trip. Every answer that names somebody goes,
    because the people the rules offer are the incoming trip's; and every seeded
    table is re-seeded, because the row it held carried the outgoing trip's
    distance and mode. An answer restated **in this same request** wins over
    both, so correcting the excursion and the table together is one call.

    A refusal about a table is keyed per cell — ``"reisen[1].kilometers"`` —
    rather than by the question; see :func:`finance.inputs.row_key`.
    """
    statement = get_authorized(request, Statement, statement_id, "finance.change_obj_statement")
    # Match the admin, which freezes all fields once a statement is submitted
    # (StatementAdmin.get_readonly_fields / has_change_permission).
    if statement.submitted:
        raise ValidationError(_("Submitted statements can no longer be edited."))
    data = payload.dict(exclude_unset=True)
    excursion_id = data.pop("excursion_id", _UNSET)
    # The answers, by declaration key. There is no second language any more:
    # `allowance_to_ids`, `subsidy_to_id`, `ljp_to_id` and `night_cost` were
    # four fields here because they were four columns there, and a section
    # whose rules ask a fifth question had no way to be asked it.
    answers = data.pop("inputs", _UNSET)
    # The excursion is applied to the in-memory instance FIRST, because the
    # declarations are derived from it: who may be named is who leads *this*
    # trip. Validating before the swap would check an answer against the
    # outgoing excursion and accept a youth leader who doesn't lead the
    # incoming one.
    excursion_changed = False
    if excursion_id is not _UNSET:
        excursion = get_object_or_404(Freizeit, pk=excursion_id) if excursion_id else None
        excursion_changed = excursion != statement.excursion
        statement.excursion = excursion
    # Validate everything BEFORE writing anything, and wrap the writes in a
    # transaction, so a rejected answer never leaves a partial update behind
    # (mirrors the admin form validating in ``clean``).
    cleaned = clean_inputs(statement, answers) if answers is not _UNSET and answers else {}
    kept = statement.answers
    if excursion_changed:
        # An answer naming somebody belonged to the previous trip and is not
        # admissible against this one, so it goes unless this request restated
        # it. Which answers those are is the declarations' business, not a list
        # of three keys the API happens to know.
        kept = {key: value for key, value in kept.items() if key not in party_keys(statement)}
        # And every seeded table is **re-seeded**, on the same reasoning: the
        # row it held described the outgoing trip — its distance, its mode — so
        # keeping it would be this statement claiming a journey nobody made.
        # Clearing the excursion seeds nothing, which empties the table.
        kept = dict(kept, **seeded_rows(statement))
    with transaction.atomic():
        set_scalar_fields(statement, data, list(data.keys()))
        statement.inputs = dict(kept, **stored_inputs(cleaned))
        statement.save()
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
    if not statement.confirm(get_member(request), user=request.user):
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
    _authorize_bill_change(request, bill)
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


# --- the form, the preflight and the signatures ---------------------------


@router.get("/statements/{statement_id}/form", response=StatementFormOut)
def statement_form(request, statement_id: int):
    """The questions the section's rules ask about this statement.

    Derived from the rules rather than written beside them, so a section that
    reimburses something else gets a different form without a release. The
    answers go back through ``PATCH /statements/{id}`` as ``inputs``, and each
    one is validated against the declaration it belongs to.

    ``answers`` is what the statement carries today, restricted to the keys
    this form asks for — so one request is a whole form, questions and answers
    together, and an answer the rules have since stopped asking for is not
    handed back to be re-submitted. A *derived* answer is in there too, read
    off the statement's own data rather than out of storage, which is why the
    whole payload comes from one call: the questions, their grouping and the
    answers are all resolved against one context.
    """
    statement = get_authorized(request, Statement, statement_id, "finance.view_obj_statement")
    return {"statement_id": statement.pk, **statement_form_body(statement)}


@router.get("/statements/{statement_id}/preflight", response=PreflightOut)
def statement_preflight(request, statement_id: int):
    """What stands between this statement and being handed in.

    The ruleset's own checks, plus anything the evaluation reported, so that a
    client can show them before somebody presses the button rather than after.

    Neither list is what ``POST …/submit`` itself refuses on: that endpoint
    reproduces the excursion overview's two guards (valid allowance recipients,
    and a proof per bill when LJP contributions are claimed) and consults
    neither ``checks`` nor ``errors``. What an error *does* do is stop the
    statement resolving, so nothing is materialised and nothing is frozen —
    which is why a client should read this before submitting and why a failing
    check here is advice rather than a lock.
    """
    statement = get_authorized(request, Statement, statement_id, "finance.view_obj_statement")
    result = statement.rule_result
    checks = [{"ok": check.ok, "message": str(check.message)} for check in result.checks]
    failing = [check for check in checks if not check["ok"]]
    return {
        "statement_id": statement.pk,
        "ok": not failing and not result.errors,
        "checks": checks,
        "failing": failing,
        "errors": [str(error) for error in result.errors],
    }


@router.get("/statements/{statement_id}/approval", response=StatementApprovalOut)
def statement_approval(request, statement_id: int):
    """Who has to sign this statement off, and who has."""
    statement = get_authorized(request, Statement, statement_id, "finance.view_obj_statement")
    return approval_payload(statement, get_member(request))


@router.post("/statements/{statement_id}/approve", response=StatementApprovalOut)
def approve_statement(request, statement_id: int, payload: ApprovalCreate):
    """Sign a submitted statement off; pay it out once the last signature is in.

    The capability is the global permission, as it always was; whether this
    person still has anything to sign is the section's rules' business, and the
    object permission asks them both.
    """
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.approve_obj_statement", statement)
    member = get_member(request)
    # The account goes on the row beside the member: a signature from an
    # administrator with no member record is one signature from one person.
    statement.approve(member, note=payload.note, user=request.user)
    statement.refresh_from_db()
    return approval_payload(statement, member)


@router.post("/statements/{statement_id}/override-approval", response=StatementApprovalOut)
def override_statement_approval(request, statement_id: int, payload: ApprovalOverride):
    """Sign a constraint off without its quorum, with who and why recorded."""
    # Every refusal answers 422, so that a 200 means the override is on the
    # record whether or not it was the last signature the payout needed. They
    # used to be restated here, one `raise` per refusal beside the model's own
    # `return False`, and the two lists drifted the first time one was added:
    # a step the rules are not asking for was refused by the model and
    # answered 200 here, with `overridden: false` in a body that also said
    # `approved: true`, which reads as success. `override_refusal` is the one
    # list, and it says which refusal it was.
    #
    # The docstring stays one line on purpose: it is the operation's
    # `description` in `frontend/openapi.json` and in the generated
    # `schema.d.ts`, both pinned byte for byte, and none of the above is
    # something a client reads.
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.process_statementsubmitted")
    if not payload.reason.strip():
        raise ValidationError(_("An override has to say why."))
    member = get_member(request)
    refusal = statement.override_refusal(payload.name, member)
    if refusal is not None:
        raise ValidationError(refusal)
    statement.override_approval(payload.name, member, payload.reason)
    statement.refresh_from_db()
    return approval_payload(statement, member)
