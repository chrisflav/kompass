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


class TransactionIssueOut(Schema):
    """A per-recipient mismatch between the planned transactions and the costs.

    Resolves off ``finance.models.TransactionIssue`` (``member`` / ``current`` /
    ``target`` / ``difference``); surfaced by ``StatementOut.transaction_issues``
    so the SPA can render the soll/ist comparison from the submitted-statement
    review screen.
    """

    member: MemberBrief
    current: float
    target: float
    difference: float


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
    validity_display: str
    transaction_issues: list[TransactionIssueOut] = []
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
    def resolve_validity_display(obj) -> str:
        return str(obj.validity_display)

    @staticmethod
    def resolve_transaction_issues(obj):
        return obj.transaction_issues

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
    """Editable draft fields; PATCH semantics (only supplied fields applied).

    ``allowance_to_ids`` / ``subsidy_to_id`` / ``ljp_to_id`` mirror the admin's
    ``StatementOnListInline`` (edited from the excursion): the recipients of the
    allowance / subsidy / LJP contributions. Passing ``null`` clears an FK; an
    omitted field is left unchanged.
    """

    short_description: str | None = None
    explanation: str | None = None
    night_cost: float | None = None
    allowance_to_ids: list[int] | None = None
    subsidy_to_id: int | None = None
    ljp_to_id: int | None = None


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


# --- excursion finance overview (the admin's "Finance overview" estimate) ---


class OverviewRecipient(Schema):
    """A contribution recipient shown with its bank-account validity."""

    name: str
    iban_valid: bool


class OverviewBill(Schema):
    """A bill row in the finance overview's expenses table."""

    short_description: str
    explanation: str
    amount: float
    paid_by_name: str | None = None
    paid_by_iban_valid: bool = False


class OverviewSeminarDay(Schema):
    """A single seminar day derived from the LJP interventions."""

    day: str
    total_duration: float
    sum_days: float


class FinanceOverviewOut(Schema):
    """The excursion's estimated cost / contribution overview.

    Mirrors ``admin/freizeit_finance_overview.html`` (built from
    ``Statement.template_context`` plus the excursion's LJP / cost properties).
    An estimate, not a guaranteed cost plan.
    """

    statement_id: int
    excursion_name: str
    submitted: bool

    # Expenses
    bills: list[OverviewBill] = []
    total_bills_theoretic: float

    # Per-youth-leader contribution breakdown
    staff_count: int
    nights: int
    price_per_night: float
    nights_per_yl: float
    duration: float
    allowance_per_day: float
    allowance_per_yl: float
    kilometers_traveled: float
    means_of_transport: str
    euro_per_km: float
    transportation_per_yl: float

    # Allowance / subsidy recipients
    allowances_paid: int
    real_staff_count: int
    allowance_to: list[OverviewRecipient] = []
    allowance_to_valid: bool
    subsidy_to: OverviewRecipient | None = None
    total_subsidies: float

    # Org fee
    total_org_fee: float
    total_org_fee_theoretical: float
    org_fee: float
    old_participant_count: int

    # LJP contributions
    ljp_to: OverviewRecipient | None = None
    ljp_contributions: float
    total_seminar_days: float
    ljp_participant_count: int
    theoretic_ljp_participant_count: int
    seminar_days: list[OverviewSeminarDay] = []

    # Summary
    total_relative_costs: float
