"""Read/write schemas for the finance API.

Money figures are surfaced as ``float`` to keep the JSON contract simple for the
TypeScript frontend; the underlying model stores them as ``Decimal``. Write
schemas keep money as ``Decimal`` so a client-supplied amount is never assigned
to a ``DecimalField`` as a float — the in-memory instance would then mix the two
types and every computed money property would raise ``Decimal + float``. The rich
``StatementOut`` mirrors the values that ``Statement.template_context`` and the
computed money properties expose, while ``StatementBrief`` carries only the
identity/status a list row needs.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

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


class TransferPartyOut(Schema):
    """One end of a transfer: a member, the section, or the participants.

    ``member`` is filled only for ``kind == "member"``; the other two parties
    are the section's own money and the participants' contributions, which
    have no bank account of their own in Kompass.
    """

    kind: str
    member: MemberBrief | None = None


class TransferOut(Schema):
    """One movement of money the section's rules resolved.

    The payout list, as the rules see it rather than as the statement's
    columns happen to be shaped: who owes whom how much, under which rule, and
    in which category. The last transfer of a statement is the engine's
    balancing one — what the participants' contributions have to cover — so the
    list adds up to zero by construction.

    ``reference`` is the text the generated bank transaction carries.

    ``settlement_group`` is the token the rules put on the transfer to keep it
    out of other bank transfers: two amounts to the same person out of the same
    ledger are bundled into one payment only when it is equal, and an empty
    string means no group at all.
    """

    source: TransferPartyOut
    destination: TransferPartyOut
    amount: float
    category: str
    rule_id: str
    label: str = ""
    explanation: str = ""
    reference: str = ""
    settlement_group: str = ""


class BillBrief(ModelSchema):
    id: int
    amount: float
    costs_covered: bool
    refunded: bool
    statement_id: int
    paid_by: MemberBrief | None = None
    # Proof info is carried on the brief (not just ``BillOut``) so the statement
    # flow can flag bills without a receipt and the review screen can show the
    # evidence without fetching every bill individually.
    proof_url: str | None = None
    has_proof: bool

    class Meta:
        model = Bill
        fields = ["short_description", "explanation"]

    @staticmethod
    def resolve_proof_url(obj) -> str | None:
        if obj.proof:
            return obj.proof.url
        return None

    @staticmethod
    def resolve_has_proof(obj) -> bool:
        return bool(obj.proof)


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
    # Who makes the bank transfers once this statement is released —
    # ``"self"``, the person reviewing it, or ``"office"``, the section's
    # Geschäftsstelle after a handoff. It is the declaration of the ruleset
    # this statement is *bound* to, so it is a fact about the statement and
    # not about the instance, and a client has to read it per statement.
    #
    # There is no wording true under both: a release means *ausgezahlt* in one
    # and *zur Auszahlung übergeben* in the other. A client that showed one
    # sentence for both would be telling half its users something that did not
    # happen, which is why this is in the payload at all.
    payout_mode: str
    transaction_issues: list[TransactionIssueOut] = []
    excursion: ExcursionBrief | None = None
    created_by: MemberBrief | None = None
    submitted_by: MemberBrief | None = None
    confirmed_by: MemberBrief | None = None
    # The three party-valued answers, resolved to people. They are a *reading*
    # of ``inputs``, not fields: the record view and the excursion's finance
    # overview narrate the Heidelberg payout and name its recipients, and the
    # answers they name are the ones the section's rules asked for. Writing one
    # is ``PATCH`` with ``inputs``, which checks it against its declaration.
    subsidy_to: MemberBrief | None = None
    ljp_to: MemberBrief | None = None
    allowance_to: list[MemberBrief] = []
    night_cost: float
    bills: list[BillBrief] = []
    # The payout, as the rules resolved it. Every money figure below is a
    # summary of these, so a client that wants the breakdown reads them
    # instead of re-deriving it from the named totals.
    transfers: list[TransferOut] = []
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
        return obj.allowance_to

    @staticmethod
    def resolve_night_cost(obj) -> float:
        return obj.night_cost

    @staticmethod
    def resolve_bills(obj):
        return obj.bill_set.all()

    @staticmethod
    def resolve_transfers(obj):
        return obj.transfer_payload()


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
    # The payout screen lists the account each transfer goes to and renders
    # ``code`` as an EPC-QR, mirroring the admin's confirm view. The IBAN rides
    # on the transaction rather than on ``MemberBrief`` (which is embedded all
    # over the API) so bank details stay scoped to this screen's payload.
    iban: str = ""
    iban_valid: bool = False
    # The payout screen has to be able to say *why* one person has two rows,
    # and the count on its "bundle recipients" button is wrong without this:
    # what may be bundled is ``(member, ledger, settlement_group)``, so a
    # screen keying on the first two offers to merge a taxable payment with a
    # mileage claim and then nothing happens. Annotated here rather than named
    # in ``Meta.fields`` so that it is a plain ``string`` in the contract: the
    # column is ``NOT NULL`` with an empty default, a blank model field comes
    # out of ``ModelSchema`` as ``string | null``, and a client that has to
    # handle a ``null`` that cannot occur would key its grouping on it.
    settlement_group: str = ""

    class Meta:
        model = Transaction
        fields = ["reference"]

    @staticmethod
    def resolve_code(obj) -> str:
        return obj.code()

    @staticmethod
    def resolve_iban(obj) -> str:
        return obj.member.iban or ""

    @staticmethod
    def resolve_iban_valid(obj) -> bool:
        return obj.member.iban_valid


class StatementCreate(Schema):
    """A new draft. The answers come afterwards, through ``inputs``.

    ``night_cost`` used to be here, because it used to be a column; a create
    now says what the statement is for and nothing a section's rules might not
    ask about.

    One exception, and it is not an answer this request gives: a draft created
    with an ``excursion_id`` comes back with every **seeded** table already
    holding one row, as the trip describes it. That is the trip's own distance
    and mode written into the answers once, for the person to correct or to
    split into one row per traveller. ``GET .../form`` then serves it like any
    other answer.
    """

    short_description: str
    explanation: str = ""
    excursion_id: int | None = None


class StatementUpdate(Schema):
    """Editable draft fields; PATCH semantics (only supplied fields applied).

    ``inputs`` is the answers by declaration key, validated against what the
    section's rules actually ask for (``GET .../form``). It replaces the four
    fields that were here — ``night_cost``, ``allowance_to_ids``,
    ``subsidy_to_id`` and ``ljp_to_id`` — which were four fields because they
    were four columns on ``Statement``, and so a section whose rules ask a
    fifth question had no way to be asked it. A key the rules do not ask for is
    refused; a key left out is unchanged.

    **Where a refusal lands.** A ``422`` from here is
    ``{"detail": [...], "errors": {"<where>": ["<message>", ...]}}``, and
    ``<where>`` is a path rather than always a bare key, so that a client can
    print each message against the control that caused it:

    ``"night_cost"``
        the answer to that question.
    ``"reisen"``
        a ``rows`` answer as a whole — too many rows, or not a list of rows.
    ``"reisen[1]"``
        the row at index 1, **zero-based**, in the order this request sent them.
    ``"reisen[1].kilometers"``
        the ``kilometers`` cell of that row.

    A table reports **every** cell it found wrong, in one response; across
    different questions the first problem still answers alone. ``"__all__"``
    holds a refusal about the request rather than about one answer, as it always
    has. The type is unchanged — the keys are strings and the values are lists
    of messages — so a client that renders ``errors`` by key keeps working and
    one that wants to place a cell error parses the path.
    """

    short_description: str | None = None
    explanation: str | None = None
    # The associated excursion stays editable while the statement is a draft, so
    # picking the wrong one in the submission flow is a correction rather than a
    # delete-and-start-over. ``update_statement`` refuses any edit once submitted.
    # Changing it drops every answer that named a person, because the people the
    # rules offer are the incoming trip's, and re-seeds every table that has a
    # seed, because the row it held described the outgoing trip. An answer
    # restated in the same request wins over both.
    excursion_id: int | None = None
    inputs: dict[str, Any] | None = None


class BillCreate(Schema):
    statement_id: int
    short_description: str
    explanation: str = ""
    amount: Decimal = Decimal(0)
    paid_by_id: int | None = None
    costs_covered: bool = False


class BillUpdate(Schema):
    short_description: str | None = None
    explanation: str | None = None
    amount: Decimal | None = None
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


# --- the form, the preflight and the signatures (derived from the rules) ---


class InputOptionOut(Schema):
    """One person a party-valued answer may name."""

    id: int
    name: str


class InputChoiceOut(Schema):
    """One alternative a ``choice`` answer may be.

    ``value`` is what goes back in ``inputs`` and what the rules read;
    ``label`` is what the person picking it is shown.
    """

    value: str
    label: str


class InputFieldOut(Schema):
    """One cell of a ``rows`` question — a column of the table.

    A cell is a question asked once per row, so everything here means what it
    means on ``InputDeclarationOut``: ``type`` is the same widget vocabulary
    minus ``rows`` (there is no table inside a table), ``choices`` are a
    ``choice`` cell's own alternatives, and ``max`` is that cell's ceiling or
    count — never the number of rows, which is the question's own ``max``.

    There is no ``options`` here on purpose. The people a party-valued cell may
    name are the **question's** ``options``, stated once for the whole table, so
    one column cannot be served two different domains in two rows.

    ``required`` is advisory, exactly as it is on a question: an empty cell is
    accepted and stored, and what refuses to hand the statement in is the
    section's own checks (``GET …/preflight``).
    """

    key: str
    label: str
    type: str
    required: bool
    help: str = ""
    max: int | None = None
    choices: list[InputChoiceOut] = []


class InputDeclarationOut(Schema):
    """One question the section's rules ask about a statement.

    Derived from :meth:`kompass.rules.Ruleset.inputs`, so a section that asks
    for something else gets a different form without anybody editing the API.
    ``type`` is the widget vocabulary — ``money``, ``decimal``, ``int``,
    ``bool``, ``text``, ``choice``, ``member``, ``member_set``, ``rows``. A
    ``decimal`` is a quantity that is not money: shown as a plain number, and
    not held to the cent. ``options`` is the domain a
    party-valued answer may be picked from, resolved to names here because the
    rules themselves never see them; ``choices`` is the same thing for a
    ``choice``.

    ``rows`` is a **repeating row**: a table whose columns are ``fields`` and
    whose answer is a list of objects keyed by those fields' keys. It exists
    because one statement settles a trip several people travelled differently,
    and whether somebody gets a rate per kilometre at all depends on *their*
    mode of travel — so the mode and the distance belong together, per
    traveller, in a row. ``max`` bounds **the number of rows**; a cell's own
    bound is on its field. A party-valued cell's people are this declaration's
    ``options``, not the field's. ``fields`` is empty for every other type.

    ``derived`` says the engine supplies this answer itself, from the
    statement's own data — the kilometres off the excursion rather than off a
    person. The value is in ``answers`` like any other, and
    ``PATCH /statements/{id}`` **refuses** a value for the key: it is a reading
    of the trip, and a wrong one is corrected on the trip. A table is never
    ``derived``: it may be *seeded* from the trip when the excursion is set, and
    a seeded row is editable, stored, and does not follow the trip afterwards —
    which is the whole difference and why the two are not one mechanism.

    ``step`` is the label of the group the question belongs to; see
    ``StatementFormOut.steps``.
    """

    key: str
    label: str
    type: str
    required: bool
    help: str = ""
    max: int | None = None
    options: list[InputOptionOut] = []
    choices: list[InputChoiceOut] = []
    fields: list[InputFieldOut] = []
    step: str = ""
    derived: bool = False


class FormStepOut(Schema):
    """One group of questions the rules said belong together.

    A label and the keys in it, in declaration order. Nothing more: there is no
    page state here and no notion of a step being finished — which questions
    belong together is the section's business, and how to lay them out is the
    client's.
    """

    label: str
    keys: list[str] = []


class StatementFormOut(Schema):
    """The questions this statement still has to answer, and its answers.

    ``relevant_inputs`` is asked, not ``inputs``, so a ruleset may retire a
    question once an earlier answer makes it moot — and since taxis #579 that
    is also the question the *rules* are asked, so a question that is not here
    is one no rule reads either. ``answers`` is restricted to the keys that
    survived, so a retired answer is not handed back to be re-submitted.

    The values are as ``Statement.inputs`` holds them: money as a string, a
    person as an id, a set of people as a list of ids, a ``rows`` answer as a
    list of objects keyed by that question's field keys — with each cell in the
    shape its own type would have had as a question, so money in a cell is a
    string too. Two of them are not read
    out of storage. A ``derived`` answer is resolved from the statement's own
    data on every request, because nothing stores it. And an answer the
    declaration no longer *offers* — a ``choice`` whose option has been
    withdrawn, a person who is no longer in ``options`` because the receipt
    they paid was cleared — comes back ``null``, because that is what the rules
    now read and serving anything else would hand back a value this API would
    refuse.

    So **what this serves is what the rules read**, and a client may send back
    everything except the keys marked ``derived``: those are served to be shown
    and refused to be changed, which is the whole of the refusal.

    One further exception: an answer whose stored *type* no longer fits its
    declaration — because the section retyped the key — is served as it stands
    and refused on the way back, since it is a broken answer rather than a
    withdrawn one and the rules report it rather than reading it as
    unanswered. Answering that question properly clears it.

    ``steps`` partitions ``inputs`` into the groups the ruleset named, in
    order; every key appears in exactly one, and a form whose rules named no
    steps comes back as a single step with an empty label.
    """

    statement_id: int
    inputs: list[InputDeclarationOut] = []
    steps: list[FormStepOut] = []
    answers: dict[str, Any] = {}


class CheckOut(Schema):
    """One precondition for handing a statement in, and whether it holds."""

    ok: bool
    message: str


class PreflightOut(Schema):
    """What stands between this statement and being handed in."""

    statement_id: int
    ok: bool
    checks: list[CheckOut] = []
    failing: list[CheckOut] = []
    errors: list[str] = []


class ExclusionOut(Schema):
    """One person a forbid (or the permission check) removed from a constraint."""

    member: MemberBrief | None = None
    forbid: str


class ApprovalConstraintOut(Schema):
    """One signature the rules asked for, and where it stands.

    ``applicable`` and ``satisfied`` are separate states, and an override is a
    third: a constraint that was waved through stays in the list with who did
    it and why, rather than disappearing.
    """

    name: str
    description: str = ""
    applicable: bool
    required: int
    satisfied: bool
    overridden: bool
    open: bool
    missing: int
    state_display: str
    eligible: list[MemberBrief] = []
    signed_by: list[MemberBrief] = []
    excluded: list[ExclusionOut] = []
    overridden_by: MemberBrief | None = None
    override_reason: str = ""
    #: Whether the asking person may sign this step off without its quorum —
    #: the override endpoint's own refusals, asked in advance, so a client
    #: offers the override only where it would be taken.
    may_override: bool = False


class SignatureOut(Schema):
    """One signature on a statement."""

    member: MemberBrief | None = None
    at: datetime
    note: str = ""


class StatementApprovalOut(Schema):
    """Who has to sign a statement off, and who has.

    Routing runs on the resolved transfers rather than on the statement's
    fields, which is what lets a rule say "nobody who receives money from this
    statement" — so this list is frozen at submission, beside the payout.

    ``may_approve`` says whether the asking person has anything left to sign;
    ``completes_approval`` says whether signing it would be the last signature,
    which is the difference between recording a signature and paying the
    statement out. One surface shows both acts, so it has to know which one a
    click is about to be.
    """

    statement_id: int
    approved: bool
    may_approve: bool
    completes_approval: bool
    constraints: list[ApprovalConstraintOut] = []
    signatures: list[SignatureOut] = []


class ApprovalCreate(Schema):
    """A signature, with an optional note for the record."""

    note: str = ""


class ApprovalOverride(Schema):
    """Signing a constraint off without its quorum, on the record."""

    name: str
    reason: str
