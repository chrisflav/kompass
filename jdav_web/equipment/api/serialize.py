"""Turn material objects into the dicts the API schemas describe."""

from collections import Counter

from django.db.models import Count
from django.db.models import Prefetch
from django.db.models import prefetch_related_objects
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from equipment import services
from equipment.models import Approval
from equipment.models import LentSize
from equipment.models import LoanLine
from equipment.models import Part
from equipment.models import Reservation
from equipment.models import ReservedPart
from equipment.models import ReservedSize


def ref(obj):
    return {"id": obj.pk, "name": obj.name} if obj is not None else None


def type_ref(product_type):
    return {"id": product_type.pk, "name": str(product_type)}


def url(field):
    return field.url if field else None


def part_label(part):
    """How a piece is named in lists: its PSA ID, its serial number, or its number."""
    return part.psa_id or part.serial_number or "#{}".format(part.pk)


#: Tells :func:`part_brief` to look the open loan up itself.
LOOK_UP = object()


def part_brief(part, lent_until=LOOK_UP):
    """A piece in a list. Pass ``lent_until`` (from :func:`services.open_loan_dues`) for many pieces."""
    if lent_until is LOOK_UP:
        line = services.open_loan_line(part)
        lent_until = line.loan.due if line else None
    return {
        "id": part.pk,
        "label": part_label(part),
        "product_type": type_ref(part.product_type),
        "psa_id": part.psa_id,
        "serial_number": part.serial_number,
        "group": ref(part.group),
        "holder": ref(part.holder),
        "location": ref(part.location),
        "status": part.status,
        "lent_until": lent_until,
    }


def inspection(obj):
    return {
        "id": obj.pk,
        "date": obj.date,
        "result": obj.result,
        "inspector": ref(obj.inspector),
        "comment": obj.comment,
        "photo": url(obj.photo),
    }


def custody_event(event):
    def place(member, location):
        if member is not None:
            return member.name
        if location is not None:
            return location.name
        return None

    return {
        "id": event.pk,
        "kind": event.kind,
        "at": event.at,
        "from_name": place(event.from_member, event.from_location),
        "to_name": place(event.to_member, event.to_location),
        "by": ref(event.by),
    }


def part_detail(part, manager):
    today = timezone.localdate()
    reservations = (
        Reservation.objects.filter(
            reservedpart__part=part, status__in=Reservation.BLOCKING, end__gte=today
        )
        .select_related("borrower")
        .order_by("start")
    )
    data = part_brief(part)
    data.update(
        {
            "note": part.note,
            "photo": url(part.photo) or url(part.product_type.photo),
            "manufactured_on": part.manufactured_on,
            "buy_date": part.buy_date,
            "home_location": ref(part.home_location),
            "parent": part_brief(part.parent) if part.parent else None,
            "components": [part_brief(c) for c in part.components.all()],
            "retired_on": part.retired_on,
            "next_inspection": part.next_inspection_due(),
            "past_usage_period": part.past_usage_period(),
            "inspections": [inspection(i) for i in part.inspections.all()] if manager else None,
            "custody": (
                [custody_event(e) for e in part.custody.select_related("by")[:50]]
                if manager
                else None
            ),
            "reservations": [
                {
                    "id": r.pk,
                    "start": r.start,
                    "end": r.end,
                    "status": r.status,
                    "borrower": ref(r.borrower),
                }
                for r in reservations
            ],
        }
    )
    return data


def size_ref(size):
    return {"id": size.pk, "name": size.name, "product_type": type_ref(size.product_type)}


def size(obj, available=None):
    return {
        "id": obj.pk,
        "name": obj.name,
        "product_type": type_ref(obj.product_type),
        "quantity": obj.quantity,
        "per_set": obj.per_set,
        "group": ref(obj.group),
        "location": ref(obj.location),
        "position": obj.position,
        "available": available if available is not None else obj.quantity,
    }


def type_card(product_type, counts, own):
    """``counts`` comes from :func:`services.availability`; ``own`` are the member's group ids."""
    entry = counts[product_type.pk]
    groups = [
        {
            "id": group_id,
            "name": name,
            "available": available,
            "needs_approval": group_id is not None and group_id not in own,
        }
        for group_id, (name, available) in entry["groups"].items()
    ]
    groups.sort(key=lambda row: (row["needs_approval"], row["name"]))
    return {
        "id": product_type.pk,
        "name": product_type.name,
        "manufacturer": product_type.manufacturer,
        "product_group": product_type.product_group,
        "is_psa": product_type.is_psa,
        "photo": url(product_type.photo),
        "tags": [{"id": t.pk, "name": t.name} for t in product_type.tags.all()],
        "total": entry["total"],
        "available": entry["available"],
        "available_direct": entry["available_direct"],
        "groups": groups,
        "sizes": [size(s, entry["sizes"][s.pk]) for s in product_type.sizes.all()],
        "sets": entry["sets"],
    }


def type_detail(product_type, start, end, member, manager):
    counts = services.availability([product_type], start, end, member)
    data = type_card(product_type, counts, services.member_group_ids(member))
    today = timezone.localdate()
    calendar = []
    reservations = (
        Reservation.objects.filter(
            Q(reservedpart__part__product_type=product_type)
            | Q(reserved_sizes__size__product_type=product_type),
            status__in=Reservation.BLOCKING + (Reservation.FULFILLED,),
            end__gte=today,
        )
        .select_related("borrower")
        .distinct()
        .order_by("start")
    )
    reservations = list(reservations)
    ids = [r.pk for r in reservations]
    pieces = dict(
        ReservedPart.objects.filter(reservation__in=ids, part__product_type=product_type)
        .values("reservation")
        .annotate(n=Count("pk"))
        .values_list("reservation", "n")
    )
    sized = dict(
        ReservedSize.objects.filter(reservation__in=ids, size__product_type=product_type)
        .values("reservation")
        .annotate(n=Sum("quantity"))
        .values_list("reservation", "n")
    )
    for reservation in reservations:
        calendar.append(
            {
                "start": reservation.start,
                "end": reservation.end,
                "status": reservation.status,
                "count": pieces.get(reservation.pk, 0) + sized.get(reservation.pk, 0),
                "borrower": ref(reservation.borrower),
            }
        )
    parts = None
    if manager:
        rows = list(
            product_type.parts.exclude(status=Part.RETIRED).select_related(
                "group", "holder", "location", "product_type"
            )
        )
        dues = services.open_loan_dues([p.pk for p in rows])
        parts = [part_brief(p, dues.get(p.pk)) for p in rows]
    data.update(
        {
            "description": product_type.description,
            "article_number": product_type.article_number,
            "manual": url(product_type.manual),
            "usage_years": product_type.usage_years,
            "inspection_interval_days": product_type.inspection_interval_days,
            "daily_rate": product_type.daily_rate,
            "calendar": calendar,
            "parts": parts,
        }
    )
    return data


#: What :func:`reservation` reads of each reservation, fetched once for a whole list.
RESERVATION_PREFETCH = (
    Prefetch(
        "parts",
        queryset=Part.objects.select_related("product_type", "group", "holder", "location"),
    ),
    Prefetch(
        "reserved_sizes",
        queryset=ReservedSize.objects.select_related("size__product_type", "size__group"),
    ),
    Prefetch("approvals", queryset=Approval.objects.select_related("group", "decided_by")),
)


def reservations(objs, decidable_groups=()):
    """Serialise many reservations with a fixed number of queries. Select ``borrower`` on ``objs``."""
    objs = list(objs)
    prefetch_related_objects(objs, *RESERVATION_PREFETCH)
    dues = services.open_loan_dues({p.pk for obj in objs for p in obj.parts.all()})
    return [reservation(obj, decidable_groups, dues) for obj in objs]


def reservation(obj, decidable_groups=(), dues=None):
    """One reservation. ``dues`` (from :func:`services.open_loan_dues`) is given by :func:`reservations`."""
    if dues is None:
        return reservations([obj], decidable_groups)[0]
    parts = list(obj.parts.all())
    sizes = list(obj.reserved_sizes.all())
    approvals = list(obj.approvals.all())
    counts = Counter(p.product_type for p in parts)
    return {
        "id": obj.pk,
        "borrower": ref(obj.borrower),
        "start": obj.start,
        "end": obj.end,
        "status": obj.status,
        "note": obj.note,
        "created_at": obj.created_at,
        "lines": [
            {"product_type": type_ref(pt), "count": count}
            for pt, count in sorted(counts.items(), key=lambda item: item[0].name)
        ],
        "parts": [part_brief(p, dues.get(p.pk)) for p in parts],
        "sizes": [
            {"size": size_ref(r.size), "quantity": r.quantity, "group": ref(r.size.group)}
            for r in sizes
        ],
        "approvals": [
            {
                "group": ref(a.group),
                "approved": a.approved,
                "decided_by": ref(a.decided_by),
                "comment": a.comment,
            }
            for a in approvals
        ],
        "decidable_groups": sorted(
            a.group_id for a in approvals if a.approved is None and a.group_id in decidable_groups
        ),
    }


#: What :func:`loan` reads of each loan, fetched once for a whole list.
LOAN_PREFETCH = (
    Prefetch(
        "lines",
        queryset=LoanLine.objects.select_related(
            "part__product_type", "part__group", "part__holder", "part__location"
        ),
    ),
    Prefetch("lent_sizes", queryset=LentSize.objects.select_related("size__product_type")),
)


def loans(objs):
    """Serialise many loans with a fixed number of queries. Select ``borrower`` on ``objs``."""
    objs = list(objs)
    prefetch_related_objects(objs, *LOAN_PREFETCH)
    return [loan(obj) for obj in objs]


def loan(obj):
    prefetch_related_objects([obj], *LOAN_PREFETCH)
    today = timezone.localdate()
    lines = list(obj.lines.all())
    sizes = list(obj.lent_sizes.all())
    open_lines = [line for line in lines if line.returned_at is None]
    open_lines += [lent for lent in sizes if lent.returned_at is None]
    return {
        "id": obj.pk,
        "borrower": ref(obj.borrower),
        "out_at": obj.out_at,
        "due": obj.due,
        "reservation": obj.reservation_id,
        "overdue": bool(open_lines) and obj.due < today,
        "lines": [
            {
                "part": part_brief(
                    line.part, lent_until=obj.due if line.returned_at is None else None
                ),
                "returned_at": line.returned_at,
            }
            for line in lines
        ],
        "sizes": [
            {
                "id": lent.pk,
                "size": size_ref(lent.size),
                "quantity": lent.quantity,
                "returned": lent.returned,
            }
            for lent in sizes
        ],
    }


def psa_row(part):
    """A row of the PSA register. Prefetch ``inspections`` ordered newest first."""
    today = timezone.localdate()
    inspections = list(part.inspections.all())
    last = inspections[0] if inspections else None
    next_due = part.next_inspection_due(inspections)
    return {
        "id": part.pk,
        "label": part_label(part),
        "psa_id": part.psa_id,
        "product_type": type_ref(part.product_type),
        "group": ref(part.group),
        "holder": ref(part.holder),
        "location": ref(part.location),
        "status": part.status,
        "last_inspection": inspection(last) if last else None,
        "next_inspection": next_due,
        "days_left": (next_due - today).days if next_due else None,
        "past_usage_period": part.past_usage_period(today),
        "incomplete": not part.psa_id or part.manufactured_on is None,
    }


def deficit(obj):
    return {
        "id": obj.pk,
        "product_type": type_ref(obj.product_type) if obj.product_type else None,
        "text": obj.text,
        "wanted_from": obj.wanted_from,
        "wanted_to": obj.wanted_to,
        "comment": obj.comment,
        "reported_by": ref(obj.reported_by),
        "created_at": obj.created_at,
        "status": obj.status,
    }
