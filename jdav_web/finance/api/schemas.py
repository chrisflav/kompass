"""Read/write schemas for the finance API.

Money figures are surfaced as ``float`` to keep the JSON contract simple for the
TypeScript frontend; the underlying model stores them as ``Decimal``. The rich
``StatementOut`` mirrors the values that ``Statement.template_context`` and the
computed money properties expose, while ``StatementBrief`` carries only the
identity/status a list row needs.
"""

from datetime import datetime

from finance.models import Bill
from finance.models import Statement
from finance.models import Transaction
from members.api.schemas import ExcursionBrief
from members.api.schemas import MemberBrief
from ninja import ModelSchema
from ninja import Schema


class LedgerBrief(Schema):
    id: int
    name: str


class BillBrief(ModelSchema):
    id: int
    amount: float
    costs_covered: bool
    refunded: bool
    statement_id: int
    paid_by: MemberBrief | None = None

    class Meta:
        model = Bill
        fields = ["short_description", "explanation"]


class BillOut(ModelSchema):
    id: int
    amount: float
    statement_id: int
    paid_by: MemberBrief | None = None
    proof_url: str | None = None
    has_proof: bool

    class Meta:
        model = Bill
        fields = ["short_description", "explanation", "costs_covered", "refunded"]

    @staticmethod
    def resolve_proof_url(obj) -> str | None:
        if obj.proof:
            return obj.proof.url
        return None

    @staticmethod
    def resolve_has_proof(obj) -> bool:
        return bool(obj.proof)


class StatementBrief(ModelSchema):
    # Declared explicitly so the response contract types it as a required
    # non-null int (ModelSchema would otherwise mark the AutoField optional).
    id: int
    title: str
    status_display: str
    submitted: bool
    confirmed: bool
    excursion_id: int | None = None
    created_by: MemberBrief | None = None
    total: float
    total_pretty: str

    class Meta:
        model = Statement
        fields = ["short_description", "status", "submitted_date", "confirmed_date"]

    @staticmethod
    def resolve_status_display(obj) -> str:
        return obj.get_status_display()

    @staticmethod
    def resolve_total(obj) -> float:
        return obj.total

    @staticmethod
    def resolve_total_pretty(obj) -> str:
        return obj.total_pretty()


class StatementOut(ModelSchema):
    id: int
    title: str
    status_display: str
    submitted: bool
    confirmed: bool
    is_valid: bool
    validity: int
    excursion: ExcursionBrief | None = None
    created_by: MemberBrief | None = None
    submitted_by: MemberBrief | None = None
    confirmed_by: MemberBrief | None = None
    subsidy_to: MemberBrief | None = None
    ljp_to: MemberBrief | None = None
    allowance_to: list[MemberBrief] = []
    bills: list[BillBrief] = []
    # Computed money figures (mirroring ``template_context`` / the properties).
    total: float
    total_bills: float
    total_bills_theoretic: float
    total_bills_not_covered: float
    total_theoretic: float
    total_allowance: float
    allowance_per_yl: float
    allowances_paid: int
    total_subsidies: float
    subsidies_paid: float
    total_transportation: float
    transportation_per_yl: float
    total_nights: float
    nights_per_yl: float
    real_night_cost: float
    euro_per_km: float
    total_per_yl: float
    total_staff: float
    total_staff_paid: float
    theoretical_total_staff: float
    real_staff_count: int
    total_org_fee: float
    total_org_fee_theoretical: float
    paid_ljp_contributions: float

    class Meta:
        model = Statement
        fields = [
            "short_description",
            "explanation",
            "night_cost",
            "status",
            "submitted_date",
            "confirmed_date",
        ]

    @staticmethod
    def resolve_status_display(obj) -> str:
        return obj.get_status_display()

    @staticmethod
    def resolve_is_valid(obj) -> bool:
        return obj.is_valid()

    @staticmethod
    def resolve_allowance_to(obj):
        return obj.allowance_to.all()

    @staticmethod
    def resolve_bills(obj):
        return obj.bill_set.all()


class TransactionBrief(ModelSchema):
    id: int
    amount: float
    confirmed: bool
    confirmed_date: datetime | None = None
    statement_id: int
    member: MemberBrief
    ledger: LedgerBrief | None = None
    confirmed_by: MemberBrief | None = None

    class Meta:
        model = Transaction
        fields = ["reference"]


class TransactionOut(ModelSchema):
    id: int
    amount: float
    confirmed: bool
    confirmed_date: datetime | None = None
    statement_id: int
    member: MemberBrief
    ledger: LedgerBrief | None = None
    confirmed_by: MemberBrief | None = None
    code: str

    class Meta:
        model = Transaction
        fields = ["reference"]

    @staticmethod
    def resolve_code(obj) -> str:
        return obj.code()


class StatementCreate(Schema):
    short_description: str
    explanation: str = ""
    excursion_id: int | None = None
    night_cost: float = 0


class StatementUpdate(Schema):
    """Editable draft fields; PATCH semantics (only supplied fields applied)."""

    short_description: str | None = None
    explanation: str | None = None
    night_cost: float | None = None


class BillCreate(Schema):
    statement_id: int
    short_description: str
    explanation: str = ""
    amount: float = 0
    paid_by_id: int | None = None
    costs_covered: bool = False


class BillUpdate(Schema):
    short_description: str | None = None
    explanation: str | None = None
    amount: float | None = None
    paid_by_id: int | None = None
    costs_covered: bool | None = None
    refunded: bool | None = None


class ChoiceOut(Schema):
    """A single ``{value, label}`` option for a Django choice field."""

    value: int
    label: str


class FinanceEnumsOut(Schema):
    """Labelled choices for the finance app's choice fields (for SPA selects)."""

    status: list[ChoiceOut]
