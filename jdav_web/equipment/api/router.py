"""Material API routes.

Who may do what:

- every member may browse, reserve, borrow, return what they hold, request
  another group's material and report a deficit;
- a group's leaders decide requests for its material;
- ``equipment.manage_lending`` (the desk) acts for any borrower and sees every
  reservation and loan;
- ``equipment.manage_inventory`` (inventory and PSA) edits types, pieces,
  locations and sizes, records inspections and sees the custody of each piece.

The rules of lending live in ``equipment.services``; the routes check who is
asking and hand over.
"""

from datetime import date
from datetime import timedelta

from contrib.api.perms import authorize
from contrib.api.perms import Forbidden
from contrib.api.perms import get_member
from contrib.api.perms import set_scalar_fields
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.db.models import ProtectedError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from equipment import services
from equipment.models import CustodyEvent
from equipment.models import Deficit
from equipment.models import Inspection
from equipment.models import LentSize
from equipment.models import Loan
from equipment.models import LoanLine
from equipment.models import Location
from equipment.models import Part
from equipment.models import ProductType
from equipment.models import Reservation
from equipment.models import Size
from equipment.models import Tag
from members.models import Group
from members.models import Member
from members.pdf import render_tex
from ninja import File
from ninja import Form
from ninja import Router
from ninja import UploadedFile

from . import serialize
from .schemas import DecisionIn
from .schemas import DeficitIn
from .schemas import DeficitOut
from .schemas import DeficitUpdate
from .schemas import DeskOut
from .schemas import InspectionOut
from .schemas import LoanIn
from .schemas import LoanOut
from .schemas import LocationIn
from .schemas import LocationOut
from .schemas import MineOut
from .schemas import PartBrief
from .schemas import PartIn
from .schemas import PartOut
from .schemas import PartUpdate
from .schemas import ProductTypeCard
from .schemas import ProductTypeIn
from .schemas import ProductTypeOut
from .schemas import ProductTypeUpdate
from .schemas import PsaRow
from .schemas import Ref
from .schemas import ReservationCheckOut
from .schemas import ReservationIn
from .schemas import ReservationOut
from .schemas import ReturnIn
from .schemas import ReturnOut
from .schemas import SizeIn
from .schemas import SizeOut
from .schemas import SizeUpdate
from .schemas import TagBrief
from .schemas import TagIn
from .schemas import TagOut
from .schemas import TransferIn
from .schemas import WarningsOut

router = Router()

INVENTORY = "equipment.manage_inventory"
LENDING = "equipment.manage_lending"

ALLOWED_PHOTO_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")
MAX_PHOTO_SIZE = 10 * 1024 * 1024
MAX_MANUAL_SIZE = 20 * 1024 * 1024


def _validate_photo(photo):
    if photo.content_type not in ALLOWED_PHOTO_TYPES:
        raise ValidationError(_("Filetype not supported."))
    if photo.size > MAX_PHOTO_SIZE:
        raise ValidationError(_("File too large."))


def _validate_manual(manual):
    if manual.content_type != "application/pdf":
        raise ValidationError(_("Filetype not supported."))
    if manual.size > MAX_MANUAL_SIZE:
        raise ValidationError(_("File too large."))


def _can(request, perm):
    return request.user.has_perm(perm)


def _manager(request):
    return _can(request, INVENTORY) or _can(request, LENDING)


def _led_group_ids(request, member):
    """Groups ``member`` decides for: those they lead, or all with the lending permission."""
    if _can(request, LENDING):
        return set(Group.objects.values_list("pk", flat=True))
    return set(member.leited_groups.values_list("pk", flat=True))


def _borrower(request, member, borrower_id):
    """The borrower a request is for: oneself, or anyone for the desk."""
    if borrower_id is None or borrower_id == member.pk:
        return member
    authorize(request, LENDING)
    return get_object_or_404(Member, pk=borrower_id)


def _parts(ids):
    parts = list(Part.objects.filter(pk__in=ids))
    if len(parts) != len(set(ids)):
        raise ValidationError(_("Unknown material."))
    return parts


def _optional(model, pk):
    return get_object_or_404(model, pk=pk) if pk is not None else None


def _period(start, end):
    today = timezone.localdate()
    start = start or today
    return start, end or start


# --- tags ----------------------------------------------------------------


@router.get("/categories", response=list[TagBrief])
def list_categories(request):
    get_member(request)
    return [{"id": c.pk, "name": c.name} for c in Tag.objects.order_by("name")]


@router.get("/categories/{category_id}", response=TagOut)
def retrieve_category(request, category_id: int):
    get_member(request)
    category = get_object_or_404(Tag, pk=category_id)
    return {
        "id": category.pk,
        "name": category.name,
        "product_types": [serialize.type_ref(t) for t in category.producttype_set.all()],
    }


@router.post("/categories", response=TagOut)
def create_category(request, payload: TagIn):
    authorize(request, INVENTORY)
    category = Tag.objects.create(name=payload.name)
    return {"id": category.pk, "name": category.name, "product_types": []}


@router.put("/categories/{category_id}", response=TagOut)
def update_category(request, category_id: int, payload: TagIn):
    authorize(request, INVENTORY)
    category = get_object_or_404(Tag, pk=category_id)
    category.name = payload.name
    category.save()
    return retrieve_category(request, category_id)


@router.delete("/categories/{category_id}")
def delete_category(request, category_id: int):
    authorize(request, INVENTORY)
    get_object_or_404(Tag, pk=category_id).delete()
    return {"success": True}


# --- locations -----------------------------------------------------------


def _location(location):
    return {
        "id": location.pk,
        "name": location.name,
        "address": location.address,
        "opening_hours": location.opening_hours,
    }


@router.get("/locations", response=list[LocationOut])
def list_locations(request):
    get_member(request)
    return [_location(location) for location in Location.objects.all()]


@router.get("/recipients", response=list[Ref])
def list_recipients(request):
    """Everyone material can be handed over to: the names of all confirmed members.

    Unlike /members/ this is not narrowed to the members one may see, since a
    holder may pass a piece on to any member.
    """
    get_member(request)
    members = Member.objects.order_by("prename", "lastname").only("prename", "lastname")
    return [serialize.ref(m) for m in members]


@router.post("/locations", response=LocationOut)
def create_location(request, payload: LocationIn):
    authorize(request, INVENTORY)
    return _location(Location.objects.create(**payload.dict()))


@router.put("/locations/{location_id}", response=LocationOut)
def update_location(request, location_id: int, payload: LocationIn):
    authorize(request, INVENTORY)
    location = get_object_or_404(Location, pk=location_id)
    set_scalar_fields(location, payload.dict(), ["name", "address", "opening_hours"])
    location.save()
    return _location(location)


@router.delete("/locations/{location_id}")
def delete_location(request, location_id: int):
    authorize(request, INVENTORY)
    get_object_or_404(Location, pk=location_id).delete()
    return {"success": True}


# --- catalogue -----------------------------------------------------------


@router.get("/types", response=list[ProductTypeCard])
def list_types(
    request,
    q: str = "",
    tag: int | None = None,
    group: int | None = None,
    start: date | None = None,
    end: date | None = None,
):
    """The catalogue: every type with pieces, and how many are free in the period."""
    member = get_member(request)
    start, end = _period(start, end)
    types = ProductType.objects.prefetch_related("tags", "sizes__group", "sizes__location")
    if q:
        types = types.filter(
            Q(name__icontains=q)
            | Q(manufacturer__icontains=q)
            | Q(product_group__icontains=q)
            | Q(tags__name__icontains=q)
        ).distinct()
    if tag is not None:
        types = types.filter(tags=tag)
    if group is not None:
        types = types.filter(Q(parts__group=group) | Q(sizes__group=group)).distinct()
    types = list(types)
    counts = services.availability(types, start, end, member)
    own = services.member_group_ids(member)
    return [serialize.type_card(t, counts, own) for t in types]


@router.get("/groups", response=list[Ref])
def list_groups(request):
    """The groups that own material, for the catalogue's group filter.

    Only lendable pieces and sizes in stock count, so a group whose material is
    all retired, built into other pieces or used up is not offered. Every member
    sees the full list: the catalogue names each piece's group on its card
    anyway, whereas ``/api/members/groups`` is scoped to the groups one leads.
    """
    get_member(request)
    groups = Group.objects.filter(
        Q(pk__in=services.lendable().values("group")) | Q(material_sizes__quantity__gt=0)
    )
    return [serialize.ref(g) for g in groups.distinct().order_by("name")]


@router.get("/types/{type_id}", response=ProductTypeOut)
def retrieve_type(request, type_id: int, start: date | None = None, end: date | None = None):
    member = get_member(request)
    product_type = get_object_or_404(ProductType, pk=type_id)
    start, end = _period(start, end)
    return serialize.type_detail(product_type, start, end, member, _manager(request))


def _save_type(product_type, data):
    tags = data.pop("tags", None)
    set_scalar_fields(product_type, data, list(data))
    product_type.full_clean(exclude=["photo", "manual", "tags"])
    product_type.save()
    if tags is not None:
        product_type.tags.set(Tag.objects.filter(pk__in=tags))
    return product_type


@router.post("/types", response=ProductTypeOut)
def create_type(request, payload: ProductTypeIn):
    authorize(request, INVENTORY)
    product_type = _save_type(ProductType(), payload.dict())
    return retrieve_type(request, product_type.pk)


@router.patch("/types/{type_id}", response=ProductTypeOut)
def update_type(request, type_id: int, payload: ProductTypeUpdate):
    authorize(request, INVENTORY)
    product_type = get_object_or_404(ProductType, pk=type_id)
    _save_type(product_type, payload.dict(exclude_unset=True))
    return retrieve_type(request, type_id)


@router.delete("/types/{type_id}")
def delete_type(request, type_id: int):
    authorize(request, INVENTORY)
    product_type = get_object_or_404(ProductType, pk=type_id)
    if product_type.parts.exists():
        raise Forbidden(_("A type that still has pieces cannot be deleted."))
    try:
        product_type.delete()
    except ProtectedError:
        raise ValidationError(
            _("A size of this type has been reserved or lent. Set its stock to 0 instead.")
        ) from None
    return {"success": True}


@router.post("/types/{type_id}/photo", response=ProductTypeOut)
def update_type_photo(request, type_id: int, photo: UploadedFile = File(...)):
    authorize(request, INVENTORY)
    product_type = get_object_or_404(ProductType, pk=type_id)
    _validate_photo(photo)
    product_type.photo = photo
    product_type.save()
    return retrieve_type(request, type_id)


@router.post("/types/{type_id}/manual", response=ProductTypeOut)
def update_type_manual(request, type_id: int, manual: UploadedFile = File(...)):
    authorize(request, INVENTORY)
    product_type = get_object_or_404(ProductType, pk=type_id)
    _validate_manual(manual)
    product_type.manual = manual
    product_type.save()
    return retrieve_type(request, type_id)


# --- pieces --------------------------------------------------------------


@router.get("/parts", response=list[PartBrief])
def list_parts(
    request,
    q: str = "",
    product_type: int | None = None,
    group: int | None = None,
    holder: int | None = None,
    location: int | None = None,
    status: str | None = None,
):
    get_member(request)
    if not _manager(request):
        raise Forbidden(_("Only the material team sees every single piece."))
    parts = Part.objects.select_related("product_type", "group", "holder", "location")
    if q:
        parts = parts.filter(
            Q(psa_id__icontains=q)
            | Q(serial_number__icontains=q)
            | Q(product_type__name__icontains=q)
            | Q(note__icontains=q)
        )
    filters = {
        "product_type": product_type,
        "group": group,
        "holder": holder,
        "location": location,
        "status": status,
    }
    parts = parts.filter(**{k: v for k, v in filters.items() if v is not None})
    if status is None:
        parts = parts.exclude(status=Part.RETIRED)
    lent = services.open_loan_dues()
    return [serialize.part_brief(p, lent_until=lent.get(p.pk)) for p in parts]


@router.get("/parts/lookup", response=PartOut)
def lookup_part(request, code: str):
    """Find the piece whose PSA ID or serial number is ``code``, and lend its outermost assembly."""
    get_member(request)
    code = code.strip()
    part = (
        Part.objects.filter(psa_id__iexact=code).first()
        or Part.objects.filter(serial_number__iexact=code).first()
    )
    if part is None and code.lstrip("#").isdigit():
        part = Part.objects.filter(pk=int(code.lstrip("#"))).first()
    if part is None:
        raise ValidationError(_("No material has this ID."))
    return serialize.part_detail(part.top_level, _manager(request))


@router.post("/parts/transfer", response=WarningsOut)
def transfer_parts(request, payload: TransferIn):
    """Hand pieces over (issue #449): to a person until a day or for good, or to a place.

    Members hand over what they hold and what their groups own; the material
    team anything, including counted sizes.
    """
    # A piece out on loan is passed on only by the one who has it or the
    # material team, never to oneself, and stays on loan with its due date
    # unless a date is given: only the desk ends a loan by handing it over for good.
    member = get_member(request)
    parts = _parts(payload.parts)
    sizes = [(get_object_or_404(Size, pk=s.size), s.quantity) for s in payload.sizes]
    lending = _can(request, LENDING)
    lent = services.open_loan_lines([part.top_level for part in parts])
    if not _manager(request):
        if sizes:
            raise Forbidden(_("Only the material team hands out counted material."))
        led = set(member.leited_groups.values_list("pk", flat=True))
        for part in parts:
            piece = part.top_level
            line = lent.get(piece.pk)
            if line is not None:
                if member.pk not in (piece.holder_id, line.loan.borrower_id):
                    raise Forbidden(
                        _("%(part)s is lent to someone else. Only they can pass it on.")
                        % {"part": piece}
                    )
            elif piece.holder_id != member.pk and (
                piece.group_id is None or piece.group_id not in led
            ):
                raise Forbidden(_("You can only pass on material you hold or your groups own."))
    target = _optional(Member, payload.member)
    location = _optional(Location, payload.location)
    if lent and not lending and target is not None and target.pk == member.pk:
        raise ValidationError(_("Material on loan cannot be handed over to yourself."))
    warnings = services.hand_over(
        parts,
        member,
        member=target,
        location=location,
        due=payload.due,
        sizes=sizes,
        keep_loans=not lending,
    )
    return {"warnings": warnings}


@router.get("/parts/{part_id}", response=PartOut)
def retrieve_part(request, part_id: int):
    get_member(request)
    part = get_object_or_404(Part, pk=part_id)
    return serialize.part_detail(part, _manager(request))


def _part_fields(data):
    """Resolve the foreign keys of a part payload."""
    resolved = {}
    for key, model in (("group", Group), ("home_location", Location)):
        if key in data:
            resolved[key] = _optional(model, data.pop(key))
    resolved.update(data)
    return resolved


@router.post("/parts", response=list[PartBrief])
def create_parts(request, payload: PartIn):
    """Add pieces to the stock: one, or ``count`` identical ones without IDs."""
    authorize(request, INVENTORY)
    member = get_member(request)
    data = payload.dict()
    count = data.pop("count")
    parent = _optional(Part, data.pop("parent"))
    product_type = get_object_or_404(ProductType, pk=data.pop("product_type"))
    if count < 1 or count > 200:
        raise ValidationError(_("Create between 1 and 200 pieces at once."))
    if count > 1 and (data["psa_id"] or data["serial_number"]):
        raise ValidationError(_("Pieces with an ID are added one at a time."))
    data["psa_id"] = data["psa_id"] or None
    fields = _part_fields(data)
    created = []
    with transaction.atomic():
        for _index in range(count):
            part = Part(product_type=product_type, **fields)
            part.full_clean(exclude=["photo"])
            part.save()
            if part.home_location is not None:
                services._move(part, CustodyEvent.TRANSFER, member, location=part.home_location)
            if parent is not None:
                services.assemble(part, parent, member)
            created.append(part)
    return [serialize.part_brief(p, lent_until=None) for p in created]


@router.patch("/parts/{part_id}", response=PartOut)
def update_part(request, part_id: int, payload: PartUpdate):
    authorize(request, INVENTORY)
    member = get_member(request)
    part = get_object_or_404(Part, pk=part_id)
    data = payload.dict(exclude_unset=True)
    with transaction.atomic():
        if "parent" in data:
            services.assemble(part, _optional(Part, data.pop("parent")), member)
        if "psa_id" in data:
            data["psa_id"] = data["psa_id"] or None
        for key, value in _part_fields(data).items():
            setattr(part, key, value)
        part.full_clean(exclude=["photo"])
        part.save()
    return serialize.part_detail(part, True)


@router.delete("/parts/{part_id}")
def delete_part(request, part_id: int):
    authorize(request, INVENTORY)
    services.delete_part(get_object_or_404(Part, pk=part_id))
    return {"success": True}


@router.post("/parts/{part_id}/photo", response=PartOut)
def update_part_photo(request, part_id: int, photo: UploadedFile = File(...)):
    authorize(request, INVENTORY)
    part = get_object_or_404(Part, pk=part_id)
    _validate_photo(photo)
    part.photo = photo
    part.save()
    return serialize.part_detail(part, True)


@router.post("/parts/{part_id}/inspections", response=InspectionOut)
def create_inspection(
    request,
    part_id: int,
    result: str = Form(...),
    date: date | None = Form(None),
    comment: str = Form(""),
    photo: UploadedFile = File(None),
):
    authorize(request, INVENTORY)
    member = get_member(request)
    part = get_object_or_404(Part, pk=part_id)
    if part.status == Part.RETIRED:
        raise ValidationError(_("This piece is retired."))
    if photo is not None:
        _validate_photo(photo)
    inspection = services.inspect(part, result, member, date, comment, photo)
    return serialize.inspection(inspection)


@router.get("/psa", response=list[PsaRow])
def psa_register(request, retired: bool = False):
    """Every piece of personal protective equipment, the next inspection due first."""
    authorize(request, INVENTORY)
    parts = (
        Part.objects.filter(product_type__is_psa=True)
        .select_related("product_type", "group", "holder", "location")
        .prefetch_related(
            Prefetch(
                "inspections",
                queryset=Inspection.objects.select_related("inspector").order_by("-date", "-pk"),
            )
        )
    )
    if retired:
        parts = parts.filter(status=Part.RETIRED)
    else:
        parts = parts.exclude(status=Part.RETIRED)
    rows = [serialize.psa_row(p) for p in parts]
    rows.sort(key=lambda r: (r["days_left"] is None, r["days_left"] or 0, r["label"]))
    return rows


# --- sizes ---------------------------------------------------------------


@router.get("/sizes", response=list[SizeOut])
def list_sizes(request):
    """Every size, for the desk to pick from."""
    get_member(request)
    return [
        serialize.size(s) for s in Size.objects.select_related("product_type", "group", "location")
    ]


def _size_fields(data):
    resolved = {}
    for key, model in (("group", Group), ("location", Location)):
        if key in data:
            resolved[key] = _optional(model, data.pop(key))
    resolved.update(data)
    return resolved


@router.post("/types/{type_id}/sizes", response=SizeOut)
def create_size(request, type_id: int, payload: SizeIn):
    authorize(request, INVENTORY)
    product_type = get_object_or_404(ProductType, pk=type_id)
    size = Size(product_type=product_type, **_size_fields(payload.dict()))
    size.full_clean()
    size.save()
    return serialize.size(size)


@router.patch("/sizes/{size_id}", response=SizeOut)
def update_size(request, size_id: int, payload: SizeUpdate):
    authorize(request, INVENTORY)
    size = get_object_or_404(Size, pk=size_id)
    data = {k: v for k, v in payload.dict(exclude_unset=True).items()}
    for key, value in _size_fields(data).items():
        setattr(size, key, value)
    size.full_clean()
    size.save()
    return serialize.size(size)


@router.delete("/sizes/{size_id}")
def delete_size(request, size_id: int):
    authorize(request, INVENTORY)
    try:
        get_object_or_404(Size, pk=size_id).delete()
    except ProtectedError:
        raise ValidationError(
            _("This size has been reserved or lent. Set its stock to 0 instead.")
        ) from None
    return {"success": True}


# --- reservations --------------------------------------------------------


def _lines(payload_lines):
    lines = []
    for line in payload_lines:
        if line.size is not None and line.quantity > 0:
            lines.append(
                services.Line(size=get_object_or_404(Size, pk=line.size), quantity=line.quantity)
            )
        elif line.part is not None:
            lines.append(services.Line(part=get_object_or_404(Part, pk=line.part)))
        elif line.product_type is not None and line.quantity > 0:
            lines.append(
                services.Line(
                    product_type=get_object_or_404(ProductType, pk=line.product_type),
                    quantity=line.quantity,
                )
            )
    return lines


@router.post("/reservations/check", response=ReservationCheckOut)
def check_reservation(request, payload: ReservationIn):
    """What a reservation would take, and what stands in its way, without making it."""
    member = get_member(request)
    borrower = _borrower(request, member, payload.borrower)
    parts, sizes, problems, groups = services.check_reservation(
        borrower, payload.start, payload.end, _lines(payload.lines)
    )
    dues = services.open_loan_dues([p.pk for p in parts])
    return {
        "ok": not problems,
        "problems": problems,
        "parts": [serialize.part_brief(p, dues.get(p.pk)) for p in parts],
        "sizes": [
            {"size": serialize.size_ref(s), "quantity": q, "group": serialize.ref(s.group)}
            for s, q in sizes
        ],
        "approval_groups": [serialize.ref(g) for g in sorted(groups, key=lambda g: g.name)],
    }


@router.post("/reservations", response=ReservationOut)
def create_reservation(request, payload: ReservationIn):
    member = get_member(request)
    borrower = _borrower(request, member, payload.borrower)
    reservation = services.reserve(
        borrower, payload.start, payload.end, _lines(payload.lines), by=member, note=payload.note
    )
    return serialize.reservation(reservation)


@router.get("/reservations", response=list[ReservationOut])
def list_reservations(
    request,
    scope: str = "mine",
    status: str | None = None,
    product_type: int | None = None,
):
    """``mine``: one's own. ``approvals``: waiting for a group one decides for. ``all``: the desk's view."""
    member = get_member(request)
    led = _led_group_ids(request, member)
    reservations = Reservation.objects.select_related("borrower")
    if scope == "all":
        authorize(request, LENDING)
    elif scope == "approvals":
        reservations = reservations.filter(
            status=Reservation.REQUESTED,
            approvals__group__in=led,
            approvals__approved__isnull=True,
        ).distinct()
    else:
        reservations = reservations.filter(borrower=member)
    if status is not None:
        reservations = reservations.filter(status=status)
    if product_type is not None:
        reservations = reservations.filter(
            Q(reservedpart__part__product_type=product_type)
            | Q(reserved_sizes__size__product_type=product_type)
        ).distinct()
    return serialize.reservations(reservations, led)


def _visible_reservation(request, member, reservation_id):
    reservation = get_object_or_404(Reservation, pk=reservation_id)
    led = _led_group_ids(request, member)
    involved = set(reservation.approvals.values_list("group_id", flat=True))
    if reservation.borrower_id != member.pk and not _can(request, LENDING) and not (involved & led):
        raise Forbidden(_("This reservation is someone else's."))
    return reservation, led


@router.get("/reservations/{reservation_id}", response=ReservationOut)
def retrieve_reservation(request, reservation_id: int):
    member = get_member(request)
    reservation, led = _visible_reservation(request, member, reservation_id)
    return serialize.reservation(reservation, led)


@router.post("/reservations/{reservation_id}/cancel", response=ReservationOut)
def cancel_reservation(request, reservation_id: int):
    member = get_member(request)
    reservation = get_object_or_404(Reservation, pk=reservation_id)
    if reservation.borrower_id != member.pk:
        authorize(request, LENDING)
    services.cancel(reservation)
    return serialize.reservation(reservation)


@router.post("/reservations/{reservation_id}/decide", response=ReservationOut)
def decide_reservation(request, reservation_id: int, payload: DecisionIn):
    member = get_member(request)
    reservation = get_object_or_404(Reservation, pk=reservation_id)
    led = _led_group_ids(request, member)
    if payload.group not in led:
        raise Forbidden(_("Only the group's leaders decide on its material."))
    group = get_object_or_404(Group, pk=payload.group)
    services.decide(reservation, group, payload.approved, member, payload.comment)
    return serialize.reservation(reservation, led)


# --- loans ---------------------------------------------------------------


@router.post("/loans", response=LoanOut | None)
def create_loan(request, payload: LoanIn):
    """Take pieces: for a reservation, or on the spot with a return date.

    ``permanent`` takes them for good, without a loan; the answer is then null.
    """
    member = get_member(request)
    borrower = _borrower(request, member, payload.borrower)
    reservation = None
    if payload.reservation is not None:
        reservation = get_object_or_404(Reservation, pk=payload.reservation)
        if reservation.borrower_id != borrower.pk:
            raise Forbidden(_("This reservation is someone else's."))
    sizes = [(get_object_or_404(Size, pk=s.size), s.quantity) for s in payload.sizes]
    loan = services.lend(
        borrower,
        _parts(payload.parts),
        member,
        due=payload.due,
        reservation=reservation,
        sizes=sizes,
        permanent=payload.permanent,
        desk=_can(request, LENDING),
    )
    return serialize.loan(loan) if loan is not None else None


@router.get("/loans", response=list[LoanOut])
def list_loans(request, scope: str = "mine", open: bool = True):
    member = get_member(request)
    loans = Loan.objects.select_related("borrower")
    if scope == "all":
        authorize(request, LENDING)
    else:
        loans = loans.filter(borrower=member)
    if open:
        loans = loans.filter(pk__in=services.open_loans())
    return serialize.loans(loans)


@router.get("/loans/{loan_id}/receipt")
def loan_receipt(request, loan_id: int):
    """A printable receipt of a loan, for the desk and the borrower."""
    member = get_member(request)
    loan = get_object_or_404(Loan, pk=loan_id)
    if loan.borrower_id != member.pk:
        authorize(request, LENDING)
    lines = list(loan.lines.select_related("part__product_type"))
    rate_days = (loan.due - timezone.localdate(loan.out_at)).days + 1
    rows = []
    for line in lines:
        rate = line.part.product_type.daily_rate
        rows.append(
            {
                "part": str(line.part),
                "rate": rate,
                "amount": rate * rate_days if rate is not None else None,
            }
        )
    for lent in loan.lent_sizes.select_related("size__product_type"):
        rate = lent.size.product_type.daily_rate
        rows.append(
            {
                "part": "{} × {}".format(lent.quantity, lent.size),
                "rate": rate,
                "amount": rate * rate_days * lent.quantity if rate is not None else None,
            }
        )
    total = sum(row["amount"] for row in rows if row["amount"] is not None)
    return render_tex(
        "Leihschein_{}".format(loan.pk),
        "equipment/loan_receipt.tex",
        {"loan": loan, "rows": rows, "days": rate_days, "total": total},
    )


@router.post("/returns", response=ReturnOut)
def return_parts(request, payload: ReturnIn):
    """Give back pieces one holds, to a location or each piece's home, and counts of lent sizes."""
    member = get_member(request)
    parts = _parts(payload.parts)
    sizes = [
        (get_object_or_404(LentSize.objects.select_related("loan"), pk=s.lent), s.quantity)
        for s in payload.sizes
    ]
    if not _manager(request):
        for part in parts:
            if part.top_level.holder_id != member.pk:
                raise Forbidden(_("You can only return material you hold."))
        for lent, _quantity in sizes:
            if lent.loan.borrower_id != member.pk:
                raise Forbidden(_("You can only return material you hold."))
    location = _optional(Location, payload.location)
    flagged = _parts(payload.flagged)
    with transaction.atomic():
        returned = services.return_parts(parts, member, location=location, flagged=flagged)
        services.return_sizes(sizes)
    return {"returned": [p.pk for p in returned]}


# --- overviews -----------------------------------------------------------


@router.get("/mine", response=MineOut)
def mine(request):
    """What I hold, what I reserved, and how many requests wait for my decision."""
    member = get_member(request)
    today = timezone.localdate()
    held = []
    lines = {
        line.part_id: line.loan
        for line in LoanLine.objects.filter(
            returned_at__isnull=True, loan__borrower=member
        ).select_related("loan")
    }
    for part in member.held_material.filter(parent__isnull=True).select_related(
        "product_type", "group", "holder", "location"
    ):
        loan = lines.get(part.pk)
        data = serialize.part_brief(part, lent_until=loan.due if loan else None)
        data["due"] = loan.due if loan else None
        data["overdue"] = bool(loan and loan.due < today)
        held.append(data)
    held.sort(key=lambda p: (not p["overdue"], p["due"] or today.max, p["label"]))
    held_sizes = [
        {
            "id": lent.pk,
            "size": serialize.size_ref(lent.size),
            "quantity": lent.outstanding,
            "due": lent.loan.due,
            "overdue": lent.loan.due < today,
        }
        for lent in LentSize.objects.filter(
            loan__borrower=member, returned_at__isnull=True
        ).select_related("loan", "size__product_type")
    ]
    held_sizes.sort(key=lambda s: (not s["overdue"], s["due"], s["size"]["name"]))
    reservations = Reservation.objects.filter(
        borrower=member, status__in=Reservation.BLOCKING, end__gte=today
    ).select_related("borrower")
    led = _led_group_ids(request, member)
    to_decide = (
        Reservation.objects.filter(
            status=Reservation.REQUESTED,
            approvals__group__in=led,
            approvals__approved__isnull=True,
        )
        .distinct()
        .count()
    )
    return {
        "held": held,
        "held_sizes": held_sizes,
        "reservations": serialize.reservations(reservations, led),
        "to_decide": to_decide,
    }


@router.get("/desk", response=DeskOut)
def desk(request):
    """The desk's day: pickups, returns due, overdue loans, open requests, pieces to inspect."""
    authorize(request, LENDING)
    member = get_member(request)
    today = timezone.localdate()
    led = _led_group_ids(request, member)
    open_loans = services.open_loans().select_related("borrower")
    to_inspect = list(
        Part.objects.filter(status=Part.INSPECTION_DUE).select_related(
            "product_type", "group", "holder", "location"
        )
    )
    dues = services.open_loan_dues([p.pk for p in to_inspect])
    return {
        "pickups": serialize.reservations(
            Reservation.objects.filter(
                status=Reservation.CONFIRMED, start__lte=today + timedelta(days=1)
            ).select_related("borrower"),
            led,
        ),
        "due": serialize.loans(open_loans.filter(due=today)),
        "overdue": serialize.loans(open_loans.filter(due__lt=today)),
        "requests": serialize.reservations(
            Reservation.objects.filter(status=Reservation.REQUESTED).select_related("borrower"),
            led,
        ),
        "inspection_due": [serialize.part_brief(p, dues.get(p.pk)) for p in to_inspect],
    }


# --- deficits ------------------------------------------------------------


@router.post("/deficits", response=DeficitOut)
def report_deficit(request, payload: DeficitIn):
    """Put a wish on the Materialwarte's list."""
    member = get_member(request)
    data = payload.dict()
    data["product_type"] = _optional(ProductType, data["product_type"])
    if data["product_type"] is None and not data["text"].strip():
        raise ValidationError(_("Say what is missing."))
    deficit = Deficit(reported_by=member, **data)
    deficit.full_clean()
    deficit.save()
    return serialize.deficit(deficit)


@router.get("/deficits", response=list[DeficitOut])
def list_deficits(request, status: str | None = Deficit.OPEN):
    authorize(request, INVENTORY)
    deficits = Deficit.objects.select_related("product_type", "reported_by")
    if status:
        deficits = deficits.filter(status=status)
    return [serialize.deficit(d) for d in deficits]


@router.patch("/deficits/{deficit_id}", response=DeficitOut)
def update_deficit(request, deficit_id: int, payload: DeficitUpdate):
    authorize(request, INVENTORY)
    deficit = get_object_or_404(Deficit, pk=deficit_id)
    deficit.status = payload.status
    deficit.full_clean()
    deficit.save()
    return serialize.deficit(deficit)
