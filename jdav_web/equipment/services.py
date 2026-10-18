"""The rules of lending, in one place.

Everything that changes custody or a reservation goes through here, so the API,
the admin actions and the daily task enforce the same rules:

- a piece is never in two blocking reservations whose periods overlap;
- a piece out on a loan is blocked until its due date;
- holding a piece blocks nothing;
- every change of custody writes a ``CustodyEvent``.

Reservations are made for a product type and a quantity, or for one specific
piece. A type line is allocated to concrete pieces at booking, so that the
holders of exactly those pieces can be asked to bring them back. A piece picked
from the cupboard at pickup may replace the allocated one; an allocation that was
not pinned to a piece is moved to another free piece when its piece is lent to
someone else.

A type may also be kept by size, as a counted stock without IDs (the sizes of a
set of Friends). A reservation or loan then takes a number of pieces of a size,
and a size is free as far as its stock exceeds the most taken on any day of the
period.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Exists
from django.db.models import OuterRef
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext as _
from mailer.mailutils import prepend_base_url

from .models import Approval
from .models import CustodyEvent
from .models import Inspection
from .models import LentSize
from .models import Loan
from .models import LoanLine
from .models import Part
from .models import Reservation
from .models import ReservedPart
from .models import ReservedSize
from .models import Size


class Conflict(ValidationError):
    """A request the current bookings cannot satisfy. Carries one message per problem."""


@dataclass
class Line:
    """One line of a reservation: a type and a quantity, one specific piece, or a size and a quantity."""

    product_type: object = None
    quantity: int = 1
    part: object = None
    size: object = None


# --- who may use what --------------------------------------------------------


def member_group_ids(member):
    """The groups whose material ``member`` may use without asking: their own and the ones they lead."""
    if member is None:
        return set()
    ids = set(member.group.values_list("pk", flat=True))
    ids.update(member.leited_groups.values_list("pk", flat=True))
    return ids


def needs_approval(material, own_group_ids):
    """Whether lending ``material`` (a piece or a size) needs its group's approval.

    It does when it belongs to a group that is not one's own.
    """
    return material.group_id is not None and material.group_id not in own_group_ids


def lendable():
    """Pieces that can be reserved or lent: active and not built into another piece."""
    return Part.objects.filter(status=Part.ACTIVE, parent__isnull=True)


# --- what is blocked ---------------------------------------------------------


def blocking_reservations(start, end):
    """Reserved pieces of reservations that block ``start``–``end``."""
    return ReservedPart.objects.filter(
        reservation__status__in=Reservation.BLOCKING,
        reservation__start__lte=end,
        reservation__end__gte=start,
    )


def _still_out(start):
    """Open loans that reach into a period from ``start``: due then or later, or overdue.

    An overdue piece or size is not back, so it counts as taken until it is.
    """
    return Q(loan__due__gte=start) | Q(loan__due__lt=timezone.localdate())


def blocked_part_ids(start, end):
    """Ids of pieces that are reserved or lent somewhere in ``start``–``end``."""
    reserved = blocking_reservations(start, end)
    lent = LoanLine.objects.filter(_still_out(start), returned_at__isnull=True)
    return set(reserved.values_list("part_id", flat=True)) | set(
        lent.values_list("part_id", flat=True)
    )


def _peak(intervals, start, end):
    """Per key, the highest sum of counts on any one day of ``start``–``end``.

    ``intervals`` are ``(key, first day, last day, count)``, each overlapping the period.
    """
    changes = {}
    for key, first, last, count in intervals:
        first, last = max(first, start), min(last, end)
        deltas = changes.setdefault(key, Counter())
        deltas[first] += count
        deltas[last + timedelta(days=1)] -= count
    peaks = {}
    for key, deltas in changes.items():
        level = top = 0
        for day in sorted(deltas):
            level += deltas[day]
            top = max(top, level)
        peaks[key] = top
    return peaks


def sizes_taken(start, end, exclude_reservation=None):
    """Per size id: the most pieces reserved or lent out on any one day of ``start``–``end``."""
    reserved = ReservedSize.objects.filter(
        reservation__status__in=Reservation.BLOCKING,
        reservation__start__lte=end,
        reservation__end__gte=start,
    )
    if exclude_reservation is not None:
        reserved = reserved.exclude(reservation=exclude_reservation)
    intervals = list(
        reserved.values_list("size_id", "reservation__start", "reservation__end", "quantity")
    )
    today = timezone.localdate()
    lent = LentSize.objects.filter(_still_out(start), returned_at__isnull=True)
    for size_id, due, quantity, returned in lent.values_list(
        "size_id", "loan__due", "quantity", "returned"
    ):
        last = end if due < today else due
        intervals.append((size_id, start, last, quantity - returned))
    return _peak(intervals, start, end)


def open_loan_line(part):
    return (
        LoanLine.objects.filter(part=part, returned_at__isnull=True)
        .select_related("loan__borrower")
        .first()
    )


def open_loan_lines(parts):
    """Per piece id: the open loan line of each of ``parts`` that is out on a loan."""
    lines = LoanLine.objects.filter(part__in=parts, returned_at__isnull=True)
    return {line.part_id: line for line in lines.select_related("loan")}


def open_loan_dues(part_ids=None):
    """Per piece id: the due date of the loan it is out on."""
    lines = LoanLine.objects.filter(returned_at__isnull=True)
    if part_ids is not None:
        lines = lines.filter(part_id__in=part_ids)
    return dict(lines.values_list("part_id", "loan__due"))


def open_loans():
    """Loans with a piece or a size not yet back."""
    lines = LoanLine.objects.filter(loan=OuterRef("pk"), returned_at__isnull=True)
    sizes = LentSize.objects.filter(loan=OuterRef("pk"), returned_at__isnull=True)
    return Loan.objects.filter(Exists(lines) | Exists(sizes))


def availability(product_types, start=None, end=None, member=None):
    """Per type id: what exists and what is free in ``start``–``end``.

    Each entry holds ``total``, ``available`` and ``available_direct`` (free and
    needing no approval), ``groups`` (free per owner group id, with its name),
    ``sizes`` (free per size id) and ``sets`` (how many whole sets are free, or
    None for a type without sizes). Without a period, "free" means free today.
    Sizes are read through ``product_type.sizes``, so prefetch them for a list.
    """
    today = timezone.localdate()
    start = start or today
    end = end or start
    blocked = blocked_part_ids(start, end)
    own = member_group_ids(member)
    counts = {
        pt.pk: {
            "total": 0,
            "available": 0,
            "available_direct": 0,
            "groups": {},
            "sizes": {},
            "sets": None,
        }
        for pt in product_types
    }

    def count(entry, group_id, group_name, total, free, direct):
        entry["total"] += total
        entry["available"] += free
        if direct:
            entry["available_direct"] += free
        if free:
            group = entry["groups"].setdefault(group_id, [group_name or "", 0])
            group[1] += free

    pieces = lendable().filter(product_type__in=list(counts))
    for part_id, type_id, group_id, group_name in pieces.values_list(
        "pk", "product_type_id", "group_id", "group__name"
    ):
        free = 0 if part_id in blocked else 1
        direct = group_id is None or group_id in own
        count(counts[type_id], group_id, group_name, 1, free, direct)
    taken = sizes_taken(start, end)
    for product_type in product_types:
        entry = counts[product_type.pk]
        sets = []
        for size in product_type.sizes.all():
            free = max(size.quantity - taken.get(size.pk, 0), 0)
            entry["sizes"][size.pk] = free
            group_name = size.group.name if size.group_id is not None else ""
            count(
                entry, size.group_id, group_name, size.quantity, free, not needs_approval(size, own)
            )
            if size.per_set:
                sets.append(free // size.per_set)
        if sets:
            entry["sets"] = min(sets)
    return counts


# --- allocation --------------------------------------------------------------


def _rank(part, borrower, own, holder_counts):
    """Order candidates: no approval first, then with the borrower, at a location, held by few people."""
    if part.holder_id is None:
        place = 1
    elif borrower is not None and part.holder_id == borrower.pk:
        place = 0
    else:
        place = 2
    return (
        needs_approval(part, own),
        place,
        -holder_counts.get(part.holder_id, 0),
        part.pk,
    )


def allocate(lines, start, end, borrower):
    """Choose pieces for ``lines``. Returns ``(parts, pinned_ids, sizes, problems)``.

    ``sizes`` lists ``(size, quantity)``, one entry per size. ``problems`` holds
    one user-facing message per line that cannot be served.
    """
    blocked = blocked_part_ids(start, end)
    own = member_group_ids(borrower)
    chosen, pinned, problems = [], set(), []
    taken = set()
    sizes, size_taken = {}, None
    for line in lines:
        if line.size is not None:
            if size_taken is None:
                size_taken = sizes_taken(start, end)
            size = line.size
            already = sizes[size.pk][1] if size.pk in sizes else 0
            free = size.quantity - size_taken.get(size.pk, 0) - already
            if free < line.quantity:
                problems.append(
                    _("Only %(count)d of %(type)s are free in this period.")
                    % {"count": max(free, 0), "type": size}
                )
            else:
                sizes[size.pk] = (size, already + line.quantity)
            continue
        if line.part is not None:
            part = line.part.top_level
            if part.status != Part.ACTIVE:
                problems.append(_("%(part)s cannot be lent at the moment.") % {"part": part})
            elif part.pk in blocked or part.pk in taken:
                problems.append(_("%(part)s is already booked in this period.") % {"part": part})
            else:
                chosen.append(part)
                pinned.add(part.pk)
                taken.add(part.pk)
            continue
        candidates = [
            p
            for p in lendable().filter(product_type=line.product_type)
            if p.pk not in blocked and p.pk not in taken
        ]
        holder_counts = {}
        for p in candidates:
            holder_counts[p.holder_id] = holder_counts.get(p.holder_id, 0) + 1
        candidates.sort(key=lambda p: _rank(p, borrower, own, holder_counts))
        if len(candidates) < line.quantity:
            problems.append(
                _("Only %(count)d of %(type)s are free in this period.")
                % {"count": len(candidates), "type": line.product_type}
            )
            continue
        for part in candidates[: line.quantity]:
            chosen.append(part)
            taken.add(part.pk)
    return chosen, pinned, list(sizes.values()), problems


def _lock(parts, sizes=()):
    """Lock the rows of ``parts`` and ``sizes`` (and so serialise bookings on them) until the transaction ends.

    The custody and status of ``parts`` are read again once locked, so what
    follows acts on the current state, not the one read before the lock.
    """
    locked = {
        p.pk: p for p in Part.objects.select_for_update().filter(pk__in=[p.pk for p in parts])
    }
    for part in parts:
        current = locked[part.pk]
        part.holder_id = current.holder_id
        part.location_id = current.location_id
        part.status = current.status
    list(Size.objects.select_for_update().filter(pk__in=[s.pk for s in sizes]))


def _lock_reservation(reservation):
    """Lock ``reservation`` until the transaction ends, and read its current status."""
    reservation.status = (
        Reservation.objects.select_for_update()
        .values_list("status", flat=True)
        .get(pk=reservation.pk)
    )


def _top_levels(parts):
    """The pieces that move for ``parts``: each one's outermost assembly, once."""
    pieces = {}
    for part in parts:
        piece = part.top_level
        pieces.setdefault(piece.pk, piece)
    return list(pieces.values())


def _approval_groups(parts, sizes, own):
    return {m.group for m in list(parts) + [size for size, _q in sizes] if needs_approval(m, own)}


# --- reservations ------------------------------------------------------------


def check_reservation(borrower, start, end, lines):
    """A dry run of :func:`reserve`: the pieces and sizes it would take, and what would stop it.

    Returns ``(parts, sizes, problems, approval_groups)``.
    """
    problems = _period_problems(start, end)
    if problems:
        return [], [], problems, set()
    parts, _pinned, sizes, problems = allocate(lines, start, end, borrower)
    groups = _approval_groups(parts, sizes, member_group_ids(borrower))
    return parts, sizes, problems, groups


def _period_problems(start, end):
    if end < start:
        return [_("The end of the period lies before its start.")]
    if start < timezone.localdate():
        return [_("The period lies in the past.")]
    return []


@transaction.atomic
def reserve(borrower, start, end, lines, by=None, note=""):
    """Reserve ``lines`` for ``borrower``. Raises :class:`Conflict` if they cannot all be served."""
    problems = _period_problems(start, end)
    if problems:
        raise Conflict(problems)
    types = [line.product_type for line in lines if line.product_type is not None]
    _lock(
        list(Part.objects.filter(product_type__in=types))
        + [line.part for line in lines if line.part is not None],
        [line.size for line in lines if line.size is not None],
    )
    parts, pinned, sizes, problems = allocate(lines, start, end, borrower)
    if problems:
        raise Conflict(problems)
    if not parts and not sizes:
        raise Conflict([_("Nothing was selected.")])
    groups = _approval_groups(parts, sizes, member_group_ids(borrower))
    reservation = Reservation.objects.create(
        borrower=borrower,
        start=start,
        end=end,
        note=note,
        created_by=by,
        status=Reservation.REQUESTED if groups else Reservation.CONFIRMED,
    )
    ReservedPart.objects.bulk_create(
        ReservedPart(reservation=reservation, part=p, pinned=p.pk in pinned) for p in parts
    )
    ReservedSize.objects.bulk_create(
        ReservedSize(reservation=reservation, size=size, quantity=quantity)
        for size, quantity in sizes
    )
    for group in groups:
        Approval.objects.create(reservation=reservation, group=group)
    if groups:
        notify_request(reservation, groups)
    else:
        notify_reservation_confirmed(reservation)
    return reservation


@transaction.atomic
def decide(reservation, group, approved, by, comment=""):
    """Record ``group``'s decision on ``reservation``.

    The reservation is locked first, so of two decisions at once the second
    sees the first, and the last approval confirms the reservation.
    """
    _lock_reservation(reservation)
    if reservation.status != Reservation.REQUESTED:
        raise ValidationError(_("This reservation is no longer waiting for a decision."))
    approval = reservation.approvals.filter(group=group, approved__isnull=True).first()
    if approval is None:
        raise ValidationError(_("This group has nothing to decide on this reservation."))
    approval.approved = approved
    approval.decided_by = by
    approval.decided_at = timezone.now()
    approval.comment = comment
    approval.save()
    if not approved:
        reservation.status = Reservation.DECLINED
        reservation.save(update_fields=["status"])
        notify_decision(reservation, approved=False, comment=comment)
    elif not reservation.approvals.filter(Q(approved__isnull=True) | Q(approved=False)).exists():
        reservation.status = Reservation.CONFIRMED
        reservation.save(update_fields=["status"])
        notify_decision(reservation, approved=True, comment=comment)
    return reservation


@transaction.atomic
def cancel(reservation):
    _lock_reservation(reservation)
    if reservation.status not in Reservation.BLOCKING:
        raise ValidationError(_("Only an open reservation can be cancelled."))
    reservation.status = Reservation.CANCELLED
    reservation.save(update_fields=["status"])
    return reservation


def _reallocate(reserved_part, start, end, avoid):
    """Move an unpinned allocation to another free piece of the same type. Returns success."""
    reservation = reserved_part.reservation
    blocked = blocked_part_ids(reservation.start, reservation.end) | avoid
    own = member_group_ids(reservation.borrower)
    candidates = [
        p
        for p in lendable().filter(product_type=reserved_part.part.product_type)
        if p.pk not in blocked
        and (not needs_approval(p, own) or p.group_id == reserved_part.part.group_id)
    ]
    if not candidates:
        return False
    candidates.sort(key=lambda p: _rank(p, reservation.borrower, own, {}))
    reserved_part.part = candidates[0]
    reserved_part.save(update_fields=["part"])
    return True


def _claim(part, start, end, reservation=None, avoid=()):
    """Make ``part`` free for ``start``–``end``, taking it from another reservation if allowed.

    A piece allocated to ``reservation`` itself is fine. One allocated, unpinned, to
    another reservation is replaced there by another free piece, never by one of
    ``avoid`` (the pieces handed out together with ``part``). Raises
    :class:`Conflict` otherwise.
    """
    avoid = set(avoid) | {part.pk}
    others = (
        blocking_reservations(start, end)
        .filter(part=part)
        .select_related("reservation", "part__product_type")
    )
    if reservation is not None:
        others = others.exclude(reservation=reservation)
    for reserved in others:
        if reserved.pinned or not _reallocate(reserved, start, end, avoid):
            raise Conflict(
                [
                    _("%(part)s is reserved by %(name)s from %(start)s to %(end)s.")
                    % {
                        "part": part,
                        "name": reserved.reservation.borrower.name,
                        "start": reserved.reservation.start,
                        "end": reserved.reservation.end,
                    }
                ]
            )


# --- custody -----------------------------------------------------------------


def _with_components(part):
    """``part`` and every piece built into it, outermost first."""
    pieces, queue, seen = [], [part], set()
    while queue:
        piece = queue.pop(0)
        if piece.pk in seen:
            continue
        seen.add(piece.pk)
        pieces.append(piece)
        queue.extend(piece.components.all())
    return pieces


def _move(part, kind, by, member=None, location=None, loan=None):
    """Move ``part`` and its components to ``member`` or ``location``, recording each move."""
    for piece in _with_components(part):
        CustodyEvent.objects.create(
            part=piece,
            kind=kind,
            from_member=piece.holder,
            from_location=piece.location,
            to_member=member,
            to_location=location,
            by=by,
            loan=loan,
        )
        piece.holder = member
        piece.location = location
        piece.save(update_fields=["holder", "location"])


@transaction.atomic
def lend(borrower, parts, by, due=None, reservation=None, sizes=(), permanent=False, desk=False):
    """Hand ``parts`` and ``sizes`` (``(size, quantity)`` pairs) to ``borrower``. Returns the loan.

    With a reservation the loan is due at its end, and pieces of a type the
    reservation holds replace its allocated pieces of that type; what it
    reserved but was not taken is released. Without one, ``due`` is required.

    ``permanent`` hands the pieces over for good instead: the borrower then
    holds them without a loan (see :func:`transfer`), and None is returned.
    Counted sizes cannot be handed over for good.

    Unless the ``desk`` lends, material of a group that is not the borrower's
    own needs that group's approval: it must be covered by ``reservation``.
    """
    today = timezone.localdate()
    if reservation is not None:
        _lock_reservation(reservation)
        if reservation.status != Reservation.CONFIRMED:
            raise ValidationError(_("Only a confirmed reservation can be picked up."))
    if permanent:
        if any(quantity > 0 for _size, quantity in sizes):
            raise ValidationError(_("Counted material can only be lent with a return date."))
    elif reservation is not None:
        due = reservation.end
    if not permanent and (due is None or due < today):
        raise ValidationError(_("Give a return date that is not in the past."))
    pieces = _top_levels(parts)
    wanted = Counter()
    by_pk = {}
    for size, quantity in sizes:
        if quantity > 0:
            wanted[size.pk] += quantity
            by_pk[size.pk] = size
    if not pieces and not wanted:
        raise ValidationError(_("Nothing was selected."))
    _lock(pieces, by_pk.values())
    problems = []
    if not desk:
        for material in _without_approval(borrower, pieces, wanted, by_pk, reservation):
            problems.append(
                _("%(part)s belongs to %(group)s. Reserve it and wait for the group's approval.")
                % {"part": material, "group": material.group.name}
            )
    taken = sizes_taken(today, due, exclude_reservation=reservation) if wanted else {}
    for pk, quantity in wanted.items():
        size = by_pk[pk]
        free = size.quantity - taken.get(pk, 0)
        if quantity > free:
            problems.append(
                _("Only %(count)d of %(type)s are free in this period.")
                % {"count": max(free, 0), "type": size}
            )
    for piece in pieces:
        if piece.status != Part.ACTIVE:
            problems.append(_("%(part)s cannot be lent at the moment.") % {"part": piece})
            continue
        line = open_loan_line(piece)
        if line is not None:
            problems.append(
                _("%(part)s is still lent to %(name)s.")
                % {"part": piece, "name": line.loan.borrower_name}
            )
    if problems:
        raise Conflict(problems)
    if reservation is not None:
        _swap_into(reservation, pieces)
    together = {piece.pk for piece in pieces}
    # Taken for good, a piece is held from today on with no end.
    for piece in pieces:
        _claim(piece, today, date.max if permanent else due, reservation, together)
    if permanent:
        for piece in pieces:
            _move(piece, CustodyEvent.TRANSFER, by, member=borrower)
        _fulfil(reservation)
        return None
    loan = Loan.objects.create(borrower=borrower, reservation=reservation, due=due, created_by=by)
    for piece in pieces:
        LoanLine.objects.create(loan=loan, part=piece)
        _move(piece, CustodyEvent.CHECKOUT, by, member=borrower, loan=loan)
    for pk, quantity in wanted.items():
        LentSize.objects.create(loan=loan, size=by_pk[pk], quantity=quantity)
    _fulfil(reservation)
    return loan


def _without_approval(borrower, pieces, wanted, sizes, reservation):
    """The pieces and sizes of a loan that need an approval ``borrower`` has not got.

    Material of a group that is not the borrower's own is covered only by their
    confirmed ``reservation``: a piece allocated to it, a piece of the same type
    and group standing in for an allocated one, or no more of a size than it
    reserved. ``wanted`` counts the pieces taken per size id, ``sizes`` maps
    size ids to sizes.
    """
    own = member_group_ids(borrower)
    allocated, reserved = [], {}
    if reservation is not None:
        allocated = list(reservation.reservedpart_set.select_related("part"))
        reserved = dict(reservation.reserved_sizes.values_list("size_id", "quantity"))
    picked = {p.pk for p in pieces}
    allocated_ids = {rp.part_id for rp in allocated}
    spare = Counter(
        (rp.part.product_type_id, rp.part.group_id)
        for rp in allocated
        if rp.part_id not in picked and not rp.pinned
    )
    missing = []
    for piece in pieces:
        if not needs_approval(piece, own) or piece.pk in allocated_ids:
            continue
        key = (piece.product_type_id, piece.group_id)
        if spare[key] > 0:
            spare[key] -= 1
        else:
            missing.append(piece)
    for pk, quantity in wanted.items():
        if needs_approval(sizes[pk], own) and quantity > reserved.get(pk, 0):
            missing.append(sizes[pk])
    return missing


def _fulfil(reservation):
    if reservation is not None:
        reservation.status = Reservation.FULFILLED
        reservation.save(update_fields=["status"])


def _swap_into(reservation, pieces):
    """Let pieces picked at pickup stand in for the reservation's allocated pieces of their type.

    An allocated piece of the same owner group is replaced first.
    """
    allocated = list(reservation.reservedpart_set.select_related("part"))
    picked = {p.pk for p in pieces}
    spare = [rp for rp in allocated if rp.part_id not in picked and not rp.pinned]
    for piece in pieces:
        if piece.pk in {rp.part_id for rp in allocated}:
            continue
        same_type = [rp for rp in spare if rp.part.product_type_id == piece.product_type_id]
        same_group = [rp for rp in same_type if rp.part.group_id == piece.group_id]
        match = (same_group or same_type or [None])[0]
        if match is not None:
            spare.remove(match)
            match.part = piece
            match.save(update_fields=["part"])


@transaction.atomic
def return_parts(parts, by, location=None, flagged=()):
    """Take ``parts`` back, to ``location`` or each piece's home location.

    A piece without a home location needs ``location``: a returned piece is
    always somewhere.
    """
    # A flagged component flags the piece it is built into.
    flagged_ids = {p.top_level.pk for p in flagged}
    pieces = _top_levels(parts)
    _lock(pieces)
    for piece in pieces:
        if location is None and piece.home_location is None:
            raise ValidationError(
                _("%(part)s has no home location. Choose where it is returned to.")
                % {"part": piece}
            )
    for piece in pieces:
        line = open_loan_line(piece)
        if line is not None:
            line.returned_at = timezone.now()
            line.save(update_fields=["returned_at"])
        _move(
            piece,
            CustodyEvent.RETURN,
            by,
            location=location or piece.home_location,
            loan=line.loan if line else None,
        )
        if piece.pk in flagged_ids:
            piece.status = Part.INSPECTION_DUE
            piece.save(update_fields=["status"])
    return pieces


@transaction.atomic
def return_sizes(returns):
    """Take back ``(lent size, quantity)`` pairs. Returns the lent sizes that changed."""
    locked = {
        lent.pk: lent
        for lent in LentSize.objects.select_for_update().filter(
            pk__in=[lent.pk for lent, _quantity in returns]
        )
    }
    changed = []
    for lent, quantity in returns:
        current = locked[lent.pk]
        lent.returned, lent.returned_at = current.returned, current.returned_at
        quantity = min(quantity, lent.outstanding)
        if quantity <= 0:
            continue
        lent.returned += quantity
        if lent.returned == lent.quantity:
            lent.returned_at = timezone.now()
        lent.save(update_fields=["returned", "returned_at"])
        changed.append(lent)
    return changed


def _close_loan_lines(pieces):
    """End the open loans of ``pieces``: whoever hands a piece on is no longer its borrower."""
    LoanLine.objects.filter(part__in=pieces, returned_at__isnull=True).update(
        returned_at=timezone.now()
    )


@transaction.atomic
def hand_over(parts, by, member=None, location=None, due=None, sizes=(), keep_loans=False):
    """Hand ``parts`` to ``member`` or put them at ``location``. Returns warnings.

    With ``due`` the member borrows them until then, together with ``sizes``.
    Without, the member has them for good: they stay bookable, and the member
    is asked to bring them back when someone reserves them. Open loans of the
    pieces end first, so the one handing them on is no longer their borrower.

    ``keep_loans`` keeps a lent piece on loan when it goes to a member without
    ``due``: the member takes the loan over until its due date, so passing a
    piece on cannot end the duty to bring it back.
    """
    pieces = _top_levels(parts)
    _lock(pieces)
    if due is None:
        if any(quantity > 0 for _size, quantity in sizes):
            raise ValidationError(_("Counted material can only be lent with a return date."))
        warnings = []
        if keep_loans and member is not None:
            pieces, warnings = _pass_loans_on(pieces, by, member)
            if not pieces:
                return warnings
        return warnings + transfer(pieces, by, member=member, location=location)
    if member is None:
        raise ValidationError(_("Only a person can borrow material."))
    _close_loan_lines(pieces)
    lend(member, pieces, by, due=due, sizes=sizes, desk=True)
    return []


def _pass_loans_on(pieces, by, member):
    """Lend the lent ones of ``pieces`` to ``member`` until they are due. Returns the others, and warnings."""
    today = timezone.localdate()
    dues = open_loan_dues([p.pk for p in pieces])
    lent, rest, warnings = {}, [], []
    for piece in pieces:
        if piece.pk in dues:
            lent.setdefault(max(dues[piece.pk], today), []).append(piece)
        else:
            rest.append(piece)
    for due, group in sorted(lent.items()):
        _close_loan_lines(group)
        lend(member, group, by, due=due, desk=True)
        warnings += [
            _("%(part)s stays on loan until %(due)s.") % {"part": piece, "due": due}
            for piece in group
        ]
    return rest, warnings


@transaction.atomic
def transfer(parts, by, member=None, location=None):
    """Give ``parts`` to a new holder for good, or put them at a location (issue #449). Returns warnings.

    A lent piece is returned on the way: a member then has it without a loan.
    """
    if (member is None) == (location is None):
        raise ValidationError(_("Choose either a member or a location."))
    warnings = []
    soon = timezone.localdate() + timedelta(days=7)
    pieces = _top_levels(parts)
    _lock(pieces)
    _close_loan_lines(pieces)
    for piece in pieces:
        reserved = (
            blocking_reservations(timezone.localdate(), soon)
            .filter(part=piece)
            .exclude(reservation__borrower=member)
            .select_related("reservation__borrower")
            .first()
        )
        if reserved is not None:
            warnings.append(
                _("%(part)s is reserved by %(name)s from %(start)s.")
                % {
                    "part": piece,
                    "name": reserved.reservation.borrower.name,
                    "start": reserved.reservation.start,
                }
            )
        _move(piece, CustodyEvent.TRANSFER, by, member=member, location=location)
    return warnings


@transaction.atomic
def assemble(part, parent, by):
    """Build ``part`` into ``parent`` (or take it out with ``parent=None``)."""
    if parent is not None:
        if parent.pk == part.pk or part.pk in {p.pk for p in _ancestors(parent)}:
            raise ValidationError(_("A piece cannot be assembled into itself."))
        if open_loan_line(part) is not None:
            raise ValidationError(_("A lent piece cannot be assembled."))
    part.parent = parent
    part.save(update_fields=["parent"])
    if parent is not None:
        _move(part, CustodyEvent.ASSEMBLE, by, member=parent.holder, location=parent.location)
    return part


def _ancestors(part):
    seen, piece = [], part
    while piece.parent_id is not None and piece.parent_id not in {p.pk for p in seen}:
        piece = piece.parent
        seen.append(piece)
    return seen


@transaction.atomic
def inspect(part, result, by, date=None, comment="", photo=None):
    """Record an inspection. ``retired`` takes the piece out of the stock for good."""
    inspection = Inspection(
        part=part,
        result=result,
        inspector=by,
        date=date or timezone.localdate(),
        comment=comment,
    )
    if photo is not None:
        inspection.photo = photo
    inspection.full_clean()
    inspection.save()
    if result == Inspection.RETIRED:
        part.status = Part.RETIRED
        part.retired_on = inspection.date
        part.save(update_fields=["status", "retired_on"])
        CustodyEvent.objects.create(
            part=part,
            kind=CustodyEvent.RETIRE,
            from_member=part.holder,
            from_location=part.location,
            to_member=part.holder,
            to_location=part.location,
            by=by,
        )
        today = timezone.localdate()
        shrunk = {}
        for reserved in ReservedPart.objects.filter(
            part=part, reservation__status__in=Reservation.BLOCKING, reservation__end__gte=today
        ).select_related("reservation__borrower", "part__product_type"):
            if not _reallocate(
                reserved, reserved.reservation.start, reserved.reservation.end, {part.pk}
            ):
                reserved.delete()
                shrunk[reserved.reservation.pk] = reserved.reservation
        for reservation in shrunk.values():
            _drop_retired(reservation, part)
    elif part.status == Part.INSPECTION_DUE:
        part.status = Part.ACTIVE
        part.save(update_fields=["status"])
    return inspection


def _drop_retired(reservation, part):
    """Tell the borrower of ``reservation`` that the retired ``part`` left it without a replacement.

    A reservation left with nothing is cancelled.
    """
    cancelled = (
        not reservation.reservedpart_set.exists() and not reservation.reserved_sizes.exists()
    )
    if cancelled:
        reservation.status = Reservation.CANCELLED
        reservation.save(update_fields=["status"])
    _mail(
        reservation.borrower,
        _("Material reservation cancelled") if cancelled else _("Reserved material retired"),
        settings.MATERIAL_PIECE_RETIRED_TEXT.format(
            name=reservation.borrower.prename,
            part=part,
            start=reservation.start,
            end=reservation.end,
            parts=_reservation_text(reservation) or "-",
            link=material_link("/mine"),
        ),
    )


# --- mails -------------------------------------------------------------------


def material_link(path=""):
    """An absolute link into the material pages of the SPA."""
    frontend = getattr(settings, "FRONTEND_BASE_URL", "")
    path = "/kompass/material{}".format(path)
    if frontend:
        return frontend.rstrip("/") + path
    return prepend_base_url(path)


def _pieces_text(parts, sizes=()):
    """One line per piece, and one per size with its count."""
    lines = ["- {}".format(p) for p in parts]
    lines += ["- {} × {}".format(quantity, size) for size, quantity in sizes]
    return "\n".join(lines)


def _reservation_text(reservation, group=None):
    """What ``reservation`` takes, or only what of it belongs to ``group``."""
    parts = reservation.parts.all()
    sizes = reservation.reserved_sizes.select_related("size__product_type")
    if group is not None:
        parts = parts.filter(group=group)
        sizes = sizes.filter(size__group=group)
    return _pieces_text(parts, [(r.size, r.quantity) for r in sizes])


def _mail(member, subject, text):
    if member is not None:
        member.send_mail(subject, text)


def notify_reservation_confirmed(reservation):
    _mail(
        reservation.borrower,
        _("Material reserved"),
        settings.MATERIAL_RESERVATION_CONFIRMED_TEXT.format(
            name=reservation.borrower.prename,
            start=reservation.start,
            end=reservation.end,
            parts=_reservation_text(reservation),
            link=material_link("/mine"),
        ),
    )


def notify_request(reservation, groups):
    for group in groups:
        parts = _reservation_text(reservation, group)
        for leader in group.leiters.all():
            _mail(
                leader,
                _("Material request for %(group)s") % {"group": group.name},
                settings.MATERIAL_REQUEST_TEXT.format(
                    name=leader.prename,
                    borrower=reservation.borrower.name,
                    group=group.name,
                    start=reservation.start,
                    end=reservation.end,
                    parts=parts,
                    link=material_link("/requests"),
                ),
            )
    _mail(
        reservation.borrower,
        _("Material requested"),
        settings.MATERIAL_REQUEST_RECEIVED_TEXT.format(
            name=reservation.borrower.prename,
            groups=", ".join(sorted(g.name for g in groups)),
            start=reservation.start,
            end=reservation.end,
            parts=_reservation_text(reservation),
        ),
    )


def notify_decision(reservation, approved, comment=""):
    text = (
        settings.MATERIAL_REQUEST_APPROVED_TEXT
        if approved
        else settings.MATERIAL_REQUEST_DECLINED_TEXT
    )
    _mail(
        reservation.borrower,
        _("Material request approved") if approved else _("Material request declined"),
        text.format(
            name=reservation.borrower.prename,
            start=reservation.start,
            end=reservation.end,
            parts=_reservation_text(reservation),
            comment=comment or "-",
            link=material_link("/mine"),
        ),
    )


# --- the daily run -----------------------------------------------------------


def holder_notice_due(days_until, notice_days):
    """Whether holders are asked on a day ``days_until`` days before the start.

    On each of ``notice_days``, and then every day from the last of them on.
    """
    if not notice_days:
        return False
    return days_until in notice_days or days_until <= min(notice_days)


def send_notices(today=None):
    """Decline unanswered requests, ask holders to bring pieces back, and remind borrowers.

    Returns how many mails of each kind went out. Safe to run more than once a day.
    """
    today = today or timezone.localdate()
    counts = {"declined": 0, "holders": 0, "pickups": 0, "returns": 0}

    # Leaders may decide until the first day of the period is over.
    for reservation in Reservation.objects.filter(status=Reservation.REQUESTED, start__lt=today):
        reservation.status = Reservation.DECLINED
        reservation.save(update_fields=["status"])
        notify_decision(reservation, approved=False, comment=_("No answer before the start."))
        counts["declined"] += 1

    notice_days = list(settings.MATERIAL_HOLDER_NOTICE_DAYS)
    for reservation in Reservation.objects.filter(
        status=Reservation.CONFIRMED, end__gte=today
    ).exclude(last_holder_notice=today):
        days_until = (reservation.start - today).days
        if not holder_notice_due(days_until, notice_days):
            continue
        away = {}
        for part in reservation.parts.select_related("holder"):
            if part.holder_id is not None and part.holder_id != reservation.borrower_id:
                away.setdefault(part.holder, []).append(part)
        for holder, parts in away.items():
            _mail(
                holder,
                _("Please bring back material"),
                settings.MATERIAL_HOLDER_NOTICE_TEXT.format(
                    name=holder.prename,
                    borrower=reservation.borrower.name,
                    start=reservation.start,
                    parts=_pieces_text(parts),
                    link=material_link("/mine"),
                ),
            )
            counts["holders"] += 1
        reservation.last_holder_notice = today
        reservation.save(update_fields=["last_holder_notice"])
        if days_until == 1:
            _mail(
                reservation.borrower,
                _("Your material reservation starts tomorrow"),
                settings.MATERIAL_PICKUP_REMINDER_TEXT.format(
                    name=reservation.borrower.prename,
                    start=reservation.start,
                    end=reservation.end,
                    parts=_reservation_text(reservation),
                    link=material_link("/mine"),
                ),
            )
            counts["pickups"] += 1

    tomorrow = today + timedelta(days=1)
    # The loan of a deleted member stays on record, but there is no one to remind.
    for loan in (
        open_loans()
        .filter(due__lte=tomorrow, borrower__isnull=False)
        .exclude(last_reminder=today)
        .select_related("borrower")
    ):
        parts = [line.part for line in loan.lines.filter(returned_at__isnull=True)]
        sizes = [
            (lent.size, lent.outstanding)
            for lent in loan.lent_sizes.filter(returned_at__isnull=True).select_related(
                "size__product_type"
            )
        ]
        _mail(
            loan.borrower,
            _("Material overdue") if loan.due < today else _("Material due tomorrow"),
            settings.MATERIAL_RETURN_REMINDER_TEXT.format(
                name=loan.borrower.prename,
                due=loan.due,
                parts=_pieces_text(parts, sizes),
                link=material_link("/mine"),
            ),
        )
        loan.last_reminder = today
        loan.save(update_fields=["last_reminder"])
        counts["returns"] += 1
    return counts
