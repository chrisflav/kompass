"""Read/write schemas for the material API.

Responses are built as plain dicts by the ``serialize_*`` helpers in
``equipment.api.serialize``, so the schemas here only state the contract.
"""

from datetime import date
from datetime import datetime
from decimal import Decimal

from members.api.schemas import GroupBrief
from members.api.schemas import MemberRef
from ninja import Schema


class Ref(Schema):
    id: int
    name: str


# --- tags --------------------------------------------------------------------


class TagBrief(Schema):
    id: int
    name: str


class TagOut(Schema):
    id: int
    name: str
    product_types: list[Ref]


class TagIn(Schema):
    name: str


# --- locations ---------------------------------------------------------------


class LocationOut(Schema):
    id: int
    name: str
    address: str
    opening_hours: str


class LocationIn(Schema):
    name: str
    address: str = ""
    opening_hours: str = ""


# --- sizes -------------------------------------------------------------------


class SizeOut(Schema):
    """A size kept as a counted stock. ``available`` is free in the asked period."""

    id: int
    name: str
    product_type: Ref
    quantity: int
    per_set: int
    group: GroupBrief | None
    location: Ref | None
    position: int
    available: int


class SizeIn(Schema):
    name: str
    quantity: int = 0
    per_set: int = 1
    group: int | None = None
    location: int | None = None
    position: int = 0


class SizeUpdate(Schema):
    name: str | None = None
    quantity: int | None = None
    per_set: int | None = None
    group: int | None = None
    location: int | None = None
    position: int | None = None


class SizeRef(Schema):
    id: int
    name: str
    product_type: Ref


class SizeCount(Schema):
    size: SizeRef
    quantity: int
    group: GroupBrief | None


# --- product types -----------------------------------------------------------


class GroupCount(Schema):
    """How many free pieces of a type one owner group has. ``id`` null is the section."""

    id: int | None
    name: str
    available: int
    needs_approval: bool


class ProductTypeCard(Schema):
    """A product type as the catalogue shows it."""

    id: int
    name: str
    manufacturer: str
    product_group: str
    is_psa: bool
    photo: str | None
    tags: list[TagBrief]
    total: int
    available: int
    available_direct: int
    groups: list[GroupCount]
    sizes: list[SizeOut]
    #: How many whole sets are free; null for a type without sizes.
    sets: int | None


class CalendarEntry(Schema):
    start: date
    end: date
    status: str
    count: int
    borrower: MemberRef | None


class PartBrief(Schema):
    id: int
    label: str
    product_type: Ref
    psa_id: str | None
    serial_number: str
    group: GroupBrief | None
    holder: MemberRef | None
    location: Ref | None
    status: str
    lent_until: date | None


class ProductTypeOut(ProductTypeCard):
    description: str
    article_number: str
    manual: str | None
    usage_years: int | None
    inspection_interval_days: int
    daily_rate: Decimal | None
    calendar: list[CalendarEntry]
    #: Only for those who manage material; others see counts.
    parts: list[PartBrief] | None


class ProductTypeIn(Schema):
    name: str
    manufacturer: str = ""
    product_group: str = ""
    description: str = ""
    is_psa: bool = False
    article_number: str = ""
    usage_years: int | None = None
    inspection_interval_days: int = 365
    daily_rate: Decimal | None = None
    tags: list[int] = []


class ProductTypeUpdate(Schema):
    name: str | None = None
    manufacturer: str | None = None
    product_group: str | None = None
    description: str | None = None
    is_psa: bool | None = None
    article_number: str | None = None
    usage_years: int | None = None
    inspection_interval_days: int | None = None
    daily_rate: Decimal | None = None
    tags: list[int] | None = None


# --- parts -------------------------------------------------------------------


class InspectionOut(Schema):
    id: int
    date: date
    result: str
    inspector: MemberRef | None
    comment: str
    photo: str | None


class CustodyEventOut(Schema):
    id: int
    kind: str
    at: datetime
    from_name: str | None
    to_name: str | None
    by: MemberRef | None


class PartReservation(Schema):
    id: int
    start: date
    end: date
    status: str
    borrower: MemberRef


class PartHistory(Schema):
    """What deleting a piece erases: its loans, past reservations, inspections and handovers."""

    loans: int
    reservations: int
    inspections: int
    handovers: int


class PartOut(PartBrief):
    note: str
    photo: str | None
    manufactured_on: date | None
    buy_date: date | None
    home_location: Ref | None
    parent: PartBrief | None
    components: list[PartBrief]
    retired_on: date | None
    next_inspection: date | None
    past_usage_period: bool
    inspections: list[InspectionOut] | None
    custody: list[CustodyEventOut] | None
    history: PartHistory | None
    reservations: list[PartReservation]


class PartIn(Schema):
    product_type: int
    group: int | None = None
    psa_id: str | None = None
    serial_number: str = ""
    manufactured_on: date | None = None
    buy_date: date | None = None
    note: str = ""
    home_location: int | None = None
    parent: int | None = None
    #: How many identical pieces to create. Only without a PSA ID or serial number.
    count: int = 1


class PartUpdate(Schema):
    group: int | None = None
    psa_id: str | None = None
    serial_number: str | None = None
    manufactured_on: date | None = None
    buy_date: date | None = None
    note: str | None = None
    home_location: int | None = None
    parent: int | None = None


class SizeQuantity(Schema):
    size: int
    quantity: int


class TransferIn(Schema):
    parts: list[int] = []
    sizes: list[SizeQuantity] = []
    member: int | None = None
    location: int | None = None
    #: Lend to ``member`` until this day; without, hand over for good.
    due: date | None = None


class WarningsOut(Schema):
    warnings: list[str]


class PsaRow(Schema):
    id: int
    label: str
    psa_id: str | None
    product_type: Ref
    group: GroupBrief | None
    holder: MemberRef | None
    location: Ref | None
    status: str
    last_inspection: InspectionOut | None
    next_inspection: date | None
    days_left: int | None
    past_usage_period: bool
    incomplete: bool


# --- reservations ------------------------------------------------------------


class LineIn(Schema):
    product_type: int | None = None
    quantity: int = 1
    part: int | None = None
    size: int | None = None


class ReservationIn(Schema):
    start: date
    end: date
    lines: list[LineIn]
    note: str = ""
    #: Reserve for someone else. Needs the lending permission.
    borrower: int | None = None


class ReservationCheckOut(Schema):
    ok: bool
    problems: list[str]
    parts: list[PartBrief]
    sizes: list[SizeCount]
    approval_groups: list[GroupBrief]


class ApprovalOut(Schema):
    group: GroupBrief
    approved: bool | None
    decided_by: MemberRef | None
    comment: str


class TypeCount(Schema):
    product_type: Ref
    count: int


class ReservationOut(Schema):
    id: int
    borrower: MemberRef
    start: date
    end: date
    status: str
    note: str
    created_at: datetime
    lines: list[TypeCount]
    parts: list[PartBrief]
    sizes: list[SizeCount]
    approvals: list[ApprovalOut]
    #: The groups the current user may decide for.
    decidable_groups: list[int]


class DecisionIn(Schema):
    group: int
    approved: bool
    comment: str = ""


# --- loans -------------------------------------------------------------------


class LoanIn(Schema):
    parts: list[int] = []
    sizes: list[SizeQuantity] = []
    due: date | None = None
    reservation: int | None = None
    borrower: int | None = None
    #: Take the pieces for good, without a return date.
    permanent: bool = False


class LoanLineOut(Schema):
    part: PartBrief
    returned_at: datetime | None


class LentSizeOut(Schema):
    id: int
    size: SizeRef
    quantity: int
    returned: int


class LoanOut(Schema):
    id: int
    #: None once the borrower's member record is deleted; the loan stays on record.
    borrower: MemberRef | None
    out_at: datetime
    due: date
    reservation: int | None
    overdue: bool
    lines: list[LoanLineOut]
    sizes: list[LentSizeOut]


class LentQuantity(Schema):
    #: The id of a lent size of a loan.
    lent: int
    quantity: int


class ReturnIn(Schema):
    parts: list[int] = []
    sizes: list[LentQuantity] = []
    location: int | None = None
    flagged: list[int] = []


class ReturnOut(Schema):
    returned: list[int]


# --- overviews ---------------------------------------------------------------


class HeldPart(PartBrief):
    due: date | None
    overdue: bool


class HeldSize(Schema):
    #: The id of the lent size, for returning it.
    id: int
    size: SizeRef
    #: How many are still out.
    quantity: int
    due: date
    overdue: bool


class MineOut(Schema):
    held: list[HeldPart]
    held_sizes: list[HeldSize]
    reservations: list[ReservationOut]
    to_decide: int


class DeskOut(Schema):
    pickups: list[ReservationOut]
    due: list[LoanOut]
    overdue: list[LoanOut]
    requests: list[ReservationOut]
    inspection_due: list[PartBrief]


# --- deficits ----------------------------------------------------------------


class DeficitIn(Schema):
    product_type: int | None = None
    text: str = ""
    wanted_from: date | None = None
    wanted_to: date | None = None
    comment: str = ""


class DeficitOut(Schema):
    id: int
    product_type: Ref | None
    text: str
    wanted_from: date | None
    wanted_to: date | None
    comment: str
    reported_by: MemberRef | None
    created_at: datetime
    status: str


class DeficitUpdate(Schema):
    status: str
