import tempfile
from datetime import date
from datetime import timedelta
from unittest.mock import patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone

from . import services
from .models import Approval
from .models import CustodyEvent
from .models import Deficit
from .models import Inspection
from .models import LentSize
from .models import Loan
from .models import Part
from .models import Reservation
from .models import ReservedPart
from .models import Size
from .models import Tag
from .services import Conflict
from .services import Line
from .tasks import send_material_notices
from .testing import MaterialFixture

TODAY = timezone.localdate()


def days(n):
    return TODAY + timedelta(days=n)


class ModelTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_str(self):
        self.assertEqual(str(Tag(name="Hochtour")), "Hochtour")
        self.assertEqual(str(self.cupboard), "Griffwerk")
        self.assertEqual(str(self.sling_type), "Bandschlinge 120 cm")
        self.assertEqual(str(self.harness_type), "Petzl Gurt")
        self.assertEqual(str(self.harness), "Petzl Gurt (G1)")
        self.assertEqual(str(self.slings[0]), "Bandschlinge 120 cm (#{})".format(self.slings[0].pk))
        self.slings[0].serial_number = "B77"
        self.assertEqual(str(self.slings[0]), "Bandschlinge 120 cm (B77)")
        self.assertEqual(str(Deficit(text="Seilsack")), "Seilsack")
        self.assertEqual(str(Deficit(product_type=self.sling_type)), "Bandschlinge 120 cm")
        inspection = Inspection(date=date(2026, 1, 2), result=Inspection.OK)
        self.assertEqual(str(inspection), "2026-01-02 ok")
        reservation = Reservation(borrower=self.alice, start=date(2026, 1, 1), end=date(2026, 1, 2))
        self.assertEqual(str(reservation), "Alice Test 2026-01-01–2026-01-02")
        loan = Loan(borrower=self.alice, due=TODAY)
        self.assertIn("Alice Test", str(loan))

    def test_clean_requires_psa_fields(self):
        part = Part(product_type=self.harness_type)
        with self.assertRaises(ValidationError) as context:
            part.full_clean()
        self.assertIn("psa_id", context.exception.message_dict)
        self.assertIn("manufactured_on", context.exception.message_dict)

    def test_clean_rejects_self_as_parent(self):
        part = self.slings[0]
        part.parent_id = part.pk
        with self.assertRaises(ValidationError):
            part.clean()

    def test_top_level_follows_parents_and_stops_at_cycles(self):
        a, b, c = self.slings[:3]
        b.parent = a
        b.save()
        c.parent = b
        c.save()
        self.assertEqual(c.top_level, a)
        # A cycle written past the service does not loop forever.
        a.parent = c
        a.save()
        self.assertIn(c.top_level, [a, b, c])

    def test_next_inspection_due(self):
        self.assertIsNone(self.slings[0].next_inspection_due())
        self.assertEqual(self.harness.next_inspection_due(), date(2024, 12, 31))
        Inspection.objects.create(part=self.harness, date=date(2025, 6, 1), result=Inspection.OK)
        self.assertEqual(self.harness.next_inspection_due(), date(2026, 6, 1))
        self.assertEqual(self.harness.last_inspection().date, date(2025, 6, 1))
        undated = self.make_part(self.harness_type, psa_id="G2")
        self.assertIsNone(undated.next_inspection_due())

    def test_past_usage_period(self):
        self.assertFalse(self.harness.past_usage_period())
        self.harness_type.usage_years = 1
        self.assertTrue(self.harness.past_usage_period(date(2025, 1, 1)))
        self.assertFalse(self.harness.past_usage_period(date(2024, 12, 31)))
        self.harness.manufactured_on = date(2024, 2, 29)
        self.assertTrue(self.harness.past_usage_period(date(2025, 2, 28)))
        self.assertTrue(self.harness.past_usage_period())

    def test_custody_is_append_only(self):
        event = CustodyEvent.objects.create(part=self.slings[0], kind=CustodyEvent.TRANSFER)
        self.assertIn("transfer", str(event))
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            CustodyEvent.objects.all().update(kind=CustodyEvent.RETURN)
        with self.assertRaises(ValidationError):
            CustodyEvent.objects.all().delete()

    def test_reservation_and_loan_state(self):
        reservation = Reservation(status=Reservation.REQUESTED)
        self.assertTrue(reservation.is_blocking)
        reservation.status = Reservation.DECLINED
        self.assertFalse(reservation.is_blocking)
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=days(1))
        self.assertTrue(loan.is_open)
        services.return_parts([self.slings[0]], self.alice)
        self.assertFalse(loan.is_open)


class AvailabilityTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_group_ids_include_led_groups(self):
        self.assertEqual(services.member_group_ids(self.alice), {self.jugend.pk})
        self.assertEqual(services.member_group_ids(self.bob), {self.jugend.pk})
        self.assertEqual(services.member_group_ids(None), set())

    def test_counts(self):
        counts = services.availability([self.sling_type, self.crampon_type], member=self.alice)
        self.assertEqual(
            counts[self.sling_type.pk],
            {
                "total": 4,
                "available": 4,
                "available_direct": 4,
                "groups": {None: ["", 4]},
                "sizes": {},
                "sets": None,
            },
        )
        entry = counts[self.crampon_type.pk]
        self.assertEqual((entry["total"], entry["available"], entry["available_direct"]), (2, 2, 0))
        self.assertEqual(entry["groups"], {self.hochtour.pk: ["Hochtour", 2]})

    def test_reservations_and_loans_block(self):
        services.reserve(self.alice, days(5), days(6), [Line(self.sling_type, 2)])
        services.lend(self.alice, [self.slings[3]], self.alice, due=days(10))
        counts = services.availability([self.sling_type], days(5), days(5), self.alice)
        self.assertEqual(counts[self.sling_type.pk]["available"], 1)
        # Before the reservation only the loan blocks.
        counts = services.availability([self.sling_type], days(1), None, self.alice)
        self.assertEqual(counts[self.sling_type.pk]["available"], 3)
        # A loan blocks nothing after it is due.
        counts = services.availability([self.sling_type], days(11), days(12), self.alice)
        self.assertEqual(counts[self.sling_type.pk]["available"], 4)

    def test_holding_does_not_block(self):
        counts = services.availability([self.sling_type], days(1), days(2), self.alice)
        self.assertEqual(counts[self.sling_type.pk]["available"], 4)

    def test_retired_and_assembled_pieces_are_not_lendable(self):
        self.slings[0].status = Part.RETIRED
        self.slings[0].save()
        self.slings[1].parent = self.slings[2]
        self.slings[1].save()
        counts = services.availability([self.sling_type])
        self.assertEqual(counts[self.sling_type.pk]["total"], 2)


class AllocationTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_prefers_own_pieces_then_the_cupboard_then_few_holders(self):
        parts, pinned, _sizes, problems = services.allocate(
            [Line(self.sling_type, 3)], days(1), days(2), self.bob
        )
        self.assertEqual(problems, [])
        self.assertEqual(pinned, set())
        self.assertEqual(parts, [self.slings[2], self.slings[0], self.slings[1]])

    def test_too_few(self):
        _parts, _pinned, _sizes, problems = services.allocate(
            [Line(self.sling_type, 5)], days(1), days(2), self.alice
        )
        self.assertEqual(len(problems), 1)
        self.assertIn("Only 4", problems[0])

    def test_specific_piece(self):
        parts, pinned, _sizes, problems = services.allocate(
            [Line(part=self.slings[1]), Line(part=self.slings[1])], days(1), days(2), self.alice
        )
        self.assertEqual(parts, [self.slings[1]])
        self.assertEqual(pinned, {self.slings[1].pk})
        self.assertEqual(len(problems), 1)

    def test_specific_piece_not_lendable(self):
        self.slings[1].status = Part.INSPECTION_DUE
        self.slings[1].save()
        _parts, _pinned, _sizes, problems = services.allocate(
            [Line(part=self.slings[1])], days(1), days(2), self.alice
        )
        self.assertIn("cannot be lent", problems[0])

    def test_a_component_reserves_its_assembly(self):
        self.slings[1].parent = self.slings[0]
        self.slings[1].save()
        parts, _pinned, _sizes, _problems = services.allocate(
            [Line(part=self.slings[1])], days(1), days(2), self.alice
        )
        self.assertEqual(parts, [self.slings[0]])


class ReservationTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_check(self):
        parts, _sizes, problems, groups = services.check_reservation(
            self.alice, days(1), days(2), [Line(self.crampon_type, 1)]
        )
        self.assertEqual(len(parts), 1)
        self.assertEqual(problems, [])
        self.assertEqual(groups, {self.hochtour})
        _parts, _sizes, problems, _groups = services.check_reservation(
            self.alice, days(2), days(1), [Line(self.crampon_type, 1)]
        )
        self.assertIn("before its start", problems[0])
        _parts, _sizes, problems, _groups = services.check_reservation(
            self.alice, days(-2), days(1), [Line(self.crampon_type, 1)]
        )
        self.assertIn("past", problems[0])

    def test_own_material_is_confirmed_at_once(self):
        reservation = services.reserve(
            self.alice, days(1), days(2), [Line(self.sling_type, 2)], by=self.alice, note="Kurs"
        )
        self.assertEqual(reservation.status, Reservation.CONFIRMED)
        self.assertEqual(reservation.parts.count(), 2)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])

    def test_other_groups_material_is_requested(self):
        reservation = services.reserve(self.alice, days(1), days(2), [Line(self.crampon_type, 2)])
        self.assertEqual(reservation.status, Reservation.REQUESTED)
        self.assertEqual(
            list(reservation.approvals.values_list("group", flat=True)), [self.hochtour.pk]
        )
        recipients = sorted(m.to[0] for m in mail.outbox)
        self.assertEqual(recipients, ["alice@example.com", "carol@example.com"])

    def test_no_double_booking(self):
        services.reserve(self.alice, days(1), days(3), [Line(part=self.harness)])
        with self.assertRaises(Conflict):
            services.reserve(self.bob, days(3), days(4), [Line(part=self.harness)])
        # Back to back is fine.
        services.reserve(self.bob, days(4), days(5), [Line(part=self.harness)])

    def test_refuses_problems(self):
        with self.assertRaises(Conflict):
            services.reserve(self.alice, days(2), days(1), [Line(self.sling_type, 1)])
        with self.assertRaises(Conflict):
            services.reserve(self.alice, days(1), days(2), [Line(self.sling_type, 9)])
        with self.assertRaises(Conflict):
            services.reserve(self.alice, days(1), days(2), [])

    def test_decide(self):
        self.crampons[1].group = self.jugend
        self.crampons[1].save()
        reservation = services.reserve(self.carol, days(1), days(2), [Line(self.crampon_type, 2)])
        self.assertEqual(reservation.approvals.count(), 1)
        mail.outbox = []
        services.decide(reservation, self.jugend, True, self.bob, "gern")
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.CONFIRMED)
        self.assertIn("gern", mail.outbox[0].body)
        with self.assertRaises(ValidationError):
            services.decide(reservation, self.jugend, True, self.bob)

    def test_decide_waits_for_every_group(self):
        self.crampons[1].group = self.jugend
        self.crampons[1].save()
        outsider = self.make_member("Dora")
        reservation = services.reserve(outsider, days(1), days(2), [Line(self.crampon_type, 2)])
        services.decide(reservation, self.jugend, True, self.bob)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.REQUESTED)
        with self.assertRaises(ValidationError):
            services.decide(reservation, self.jugend, False, self.bob)
        services.decide(reservation, self.hochtour, False, self.carol)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.DECLINED)

    def test_cancel(self):
        reservation = services.reserve(self.alice, days(1), days(2), [Line(self.sling_type, 1)])
        services.cancel(reservation)
        self.assertEqual(reservation.status, Reservation.CANCELLED)
        with self.assertRaises(ValidationError):
            services.cancel(reservation)


class LendingTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_take_for_good(self):
        reservation = services.reserve(self.alice, TODAY, days(1), [Line(self.sling_type, 1)])
        self.assertIsNone(
            services.lend(
                self.alice, [self.slings[1]], self.alice, reservation=reservation, permanent=True
            )
        )
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.FULFILLED)
        self.slings[1].refresh_from_db()
        self.assertEqual(self.slings[1].holder, self.alice)
        self.assertFalse(Loan.objects.exists())
        self.setUpSizes()
        with self.assertRaisesMessage(ValidationError, "with a return date"):
            services.lend(self.alice, [], self.alice, sizes=[(self.size1, 1)], permanent=True)

    def test_lend_and_return_on_the_spot(self):
        loan = services.lend(self.alice, [self.slings[0], self.slings[0]], self.alice, due=days(3))
        self.assertEqual(loan.lines.count(), 1)
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].holder, self.alice)
        self.assertIsNone(self.slings[0].location)
        event = self.slings[0].custody.first()
        self.assertEqual(
            (event.kind, event.from_location, event.to_member),
            ("checkout", self.cupboard, self.alice),
        )

        returned = services.return_parts(
            [self.slings[0], self.slings[0]], self.alice, flagged=[self.slings[0]]
        )
        self.assertEqual(returned, [self.slings[0]])
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].location, self.cupboard)
        self.assertEqual(self.slings[0].status, Part.INSPECTION_DUE)
        self.assertIsNotNone(loan.lines.get().returned_at)

    def test_return_without_loan_to_a_given_place(self):
        services.return_parts([self.slings[2]], self.bob, location=self.cupboard)
        self.slings[2].refresh_from_db()
        self.assertIsNone(self.slings[2].holder)
        self.assertEqual(self.slings[2].custody.first().kind, CustodyEvent.RETURN)

    def test_lend_refuses(self):
        with self.assertRaises(ValidationError):
            services.lend(self.alice, [self.slings[0]], self.alice)
        with self.assertRaises(ValidationError):
            services.lend(self.alice, [self.slings[0]], self.alice, due=days(-1))
        with self.assertRaises(ValidationError):
            services.lend(self.alice, [], self.alice, due=days(1))
        self.slings[1].status = Part.RETIRED
        self.slings[1].save()
        with self.assertRaises(Conflict):
            services.lend(self.alice, [self.slings[1]], self.alice, due=days(1))
        services.lend(self.alice, [self.slings[0]], self.alice, due=days(1))
        with self.assertRaises(Conflict) as context:
            services.lend(self.bob, [self.slings[0]], self.bob, due=days(1))
        self.assertIn("still lent to Alice Test", context.exception.messages[0])

    def test_pickup_swaps_in_the_pieces_taken(self):
        reservation = services.reserve(self.alice, TODAY, days(2), [Line(self.sling_type, 2)])
        allocated = set(reservation.parts.values_list("pk", flat=True))
        taken = [p for p in self.slings if p.pk not in allocated][0]
        loan = services.lend(self.alice, [taken], self.alice, reservation=reservation)
        self.assertEqual(loan.due, days(2))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.FULFILLED)
        self.assertIn(taken.pk, set(reservation.parts.values_list("pk", flat=True)))
        with self.assertRaises(ValidationError):
            services.lend(self.alice, [self.slings[0]], self.alice, reservation=reservation)

    def test_pickup_keeps_pieces_that_were_allocated(self):
        reservation = services.reserve(self.alice, TODAY, days(2), [Line(self.sling_type, 1)])
        piece = reservation.parts.get()
        services.lend(self.alice, [piece], self.alice, reservation=reservation)
        self.assertEqual(reservation.parts.get(), piece)

    def test_lending_a_reserved_piece_moves_the_reservation(self):
        reservation = services.reserve(self.bob, days(1), days(2), [Line(self.sling_type, 1)])
        piece = reservation.parts.get()
        services.lend(self.alice, [piece], self.alice, due=days(3))
        self.assertNotEqual(reservation.parts.get(), piece)

    def test_moved_reservation_keeps_to_its_groups(self):
        reservation = services.reserve(self.carol, days(1), days(2), [Line(self.crampon_type, 1)])
        piece = reservation.parts.get()
        services.lend(self.carol, [piece], self.carol, due=days(3))
        self.assertNotEqual(reservation.parts.get(), piece)

    def test_lending_a_pinned_piece_is_refused(self):
        services.reserve(self.bob, days(1), days(2), [Line(part=self.slings[0])])
        with self.assertRaises(Conflict) as context:
            services.lend(self.alice, [self.slings[0]], self.alice, due=days(3))
        self.assertIn("reserved by Bob Test", context.exception.messages[0])

    def test_lending_the_last_reserved_piece_is_refused(self):
        services.reserve(self.bob, days(1), days(2), [Line(self.sling_type, 4)])
        with self.assertRaises(Conflict):
            services.lend(self.alice, [self.slings[0]], self.alice, due=days(3))

    def test_assemblies_move_together(self):
        services.assemble(self.slings[1], self.slings[0], self.alice)
        services.lend(self.alice, [self.slings[1]], self.alice, due=days(1))
        self.slings[1].refresh_from_db()
        self.assertEqual(self.slings[1].holder, self.alice)
        self.assertEqual(self.slings[1].custody.first().kind, CustodyEvent.CHECKOUT)

    def test_assemble_refuses(self):
        services.assemble(self.slings[1], self.slings[0], self.alice)
        with self.assertRaises(ValidationError):
            services.assemble(self.slings[0], self.slings[0], self.alice)
        with self.assertRaises(ValidationError):
            services.assemble(self.slings[0], self.slings[1], self.alice)
        services.lend(self.alice, [self.slings[2]], self.alice, due=days(1))
        with self.assertRaises(ValidationError):
            services.assemble(self.slings[2], self.slings[0], self.alice)
        with self.assertRaises(ValidationError) as context:
            services.assemble(self.slings[0], self.slings[2], self.alice)
        self.assertIn("out on loan", context.exception.messages[0])
        self.slings[3].status = Part.RETIRED
        self.slings[3].save()
        with self.assertRaises(ValidationError) as context:
            services.assemble(self.slings[0], self.slings[3], self.alice)
        self.assertIn("retired", context.exception.messages[0])
        services.assemble(self.slings[1], None, self.alice)
        self.assertIsNone(self.slings[1].parent)

    def test_a_piece_of_a_lent_set_stays_in_it(self):
        services.assemble(self.slings[1], self.slings[0], self.alice)
        services.lend(self.alice, [self.slings[0]], self.bob, due=days(1))
        self.slings[1].refresh_from_db()
        for parent in (None, self.slings[3]):
            with self.assertRaises(ValidationError):
                services.assemble(self.slings[1], parent, self.alice)
        self.slings[1].refresh_from_db()
        self.assertEqual(self.slings[1].parent, self.slings[0])

    def test_components_are_visited_once(self):
        a, b = self.slings[:2]
        b.parent = a
        b.save()
        # A cycle written past the service.
        Part.objects.filter(pk=a.pk).update(parent=b)
        a.refresh_from_db()
        self.assertEqual(len(services._with_components(a)), 2)


class TransferTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_transfer(self):
        warnings = services.transfer(
            [self.slings[0], self.slings[0], self.slings[1]], self.bob, member=self.carol
        )
        self.assertEqual(warnings, [])
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].holder, self.carol)
        self.assertEqual(self.slings[0].custody.first().kind, CustodyEvent.TRANSFER)

    def test_needs_one_target(self):
        with self.assertRaises(ValidationError):
            services.transfer([self.slings[0]], self.bob)
        with self.assertRaises(ValidationError):
            services.transfer([self.slings[0]], self.bob, member=self.bob, location=self.cupboard)

    def test_a_lent_piece_is_returned_on_the_way(self):
        loan = services.lend(self.alice, self.slings[:2], self.alice, due=days(3))
        services.transfer(self.slings[:2], self.alice, member=self.bob)
        self.assertFalse(loan.is_open)
        self.assertFalse(Loan.objects.filter(borrower=self.bob).exists())
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].holder, self.bob)

    def test_hand_over_until_a_day(self):
        loan = services.lend(self.alice, self.slings[:1], self.alice, due=days(1))
        warnings = services.hand_over(self.slings[:1], self.alice, member=self.bob, due=days(4))
        self.assertEqual(warnings, [])
        self.assertFalse(loan.is_open)
        handed = Loan.objects.get(borrower=self.bob)
        self.assertEqual((handed.due, handed.lines.get().part), (days(4), self.slings[0]))

    def test_hand_over_for_good(self):
        services.hand_over(self.slings[:1], self.bob, member=self.alice)
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].holder, self.alice)
        self.assertFalse(Loan.objects.exists())

    def test_hand_over_refuses(self):
        self.setUpSizes()
        with self.assertRaisesMessage(ValidationError, "with a return date"):
            services.hand_over([], self.bob, member=self.alice, sizes=[(self.size1, 1)])
        with self.assertRaisesMessage(ValidationError, "Only a person can borrow material."):
            services.hand_over(self.slings[:1], self.bob, location=self.cupboard, due=days(1))

    def test_warns_about_reservations(self):
        services.reserve(self.alice, days(2), days(3), [Line(part=self.slings[0])])
        warnings = services.transfer([self.slings[0]], self.bob, member=self.carol)
        self.assertIn("reserved by Alice Test", warnings[0])


class InspectionTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())
    def test_ok_clears_a_flag(self):
        self.harness.status = Part.INSPECTION_DUE
        self.harness.save()
        photo = SimpleUploadedFile("a.png", b"x", content_type="image/png")
        inspection = services.inspect(self.harness, Inspection.OK, self.bob, photo=photo)
        self.assertTrue(inspection.photo)
        self.harness.refresh_from_db()
        self.assertEqual(self.harness.status, Part.ACTIVE)

    def test_ok_leaves_active_pieces(self):
        services.inspect(self.harness, Inspection.OK, self.bob, date=date(2026, 1, 1))
        self.harness.refresh_from_db()
        self.assertEqual(self.harness.status, Part.ACTIVE)

    def test_retire_moves_or_drops_reservations(self):
        moved = services.reserve(self.alice, days(1), days(2), [Line(self.sling_type, 1)])
        piece = moved.parts.get()
        dropped = services.reserve(self.alice, days(1), days(2), [Line(part=self.harness)])
        services.inspect(piece, Inspection.RETIRED, self.bob, comment="Mantel beschädigt")
        services.inspect(self.harness, Inspection.RETIRED, self.bob)
        piece.refresh_from_db()
        self.assertEqual(piece.status, Part.RETIRED)
        self.assertEqual(piece.retired_on, TODAY)
        self.assertEqual(piece.custody.first().kind, CustodyEvent.RETIRE)
        self.assertNotEqual(moved.parts.get(), piece)
        self.assertFalse(dropped.parts.exists())
        # A reservation left with nothing is cancelled, and its borrower told.
        dropped.refresh_from_db()
        self.assertEqual(dropped.status, Reservation.CANCELLED)
        self.assertEqual(mail.outbox[-1].subject, "Material reservation cancelled")
        self.assertIn("wurde aus dem Bestand", mail.outbox[-1].body)

    def test_retire_tells_the_borrower_what_is_left(self):
        reservation = services.reserve(
            self.alice, days(1), days(2), [Line(part=self.harness), Line(part=self.slings[0])]
        )
        mail.outbox = []
        services.inspect(self.harness, Inspection.RETIRED, self.bob)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.CONFIRMED)
        self.assertEqual(list(reservation.parts.all()), [self.slings[0]])
        self.assertEqual(mail.outbox[0].to, ["alice@example.com"])
        self.assertEqual(mail.outbox[0].subject, "Reserved material no longer available")
        self.assertIn(str(self.harness), mail.outbox[0].body)
        self.assertIn("- {}".format(self.slings[0]), mail.outbox[0].body)

    def test_invalid_result(self):
        with self.assertRaises(ValidationError):
            services.inspect(self.harness, "broken", self.bob)


class DeletePartTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_deletes_the_history_with_the_piece(self):
        services.lend(self.alice, [self.harness], self.bob, due=days(3))
        services.lend(self.alice, [self.slings[0], self.slings[1]], self.bob, due=days(3))
        services.return_parts([self.harness, self.slings[0]], self.bob, location=self.cupboard)
        services.inspect(self.harness, Inspection.OK, self.bob)
        harness_id = self.harness.pk
        services.delete_part(self.harness)
        services.delete_part(self.slings[0])
        self.assertFalse(Part.objects.filter(pk=harness_id).exists())
        self.assertFalse(CustodyEvent.objects.filter(part_id=harness_id).exists())
        self.assertFalse(Inspection.objects.exists())
        # A loan of nothing but the piece goes with it; one of more stays.
        self.assertEqual(
            list(Loan.objects.get().lines.values_list("part", flat=True)), [self.slings[1].pk]
        )

    def test_refuses_a_piece_out_on_loan(self):
        self.slings[1].parent = self.slings[0]
        self.slings[1].save()
        services.lend(self.alice, [self.slings[0]], self.bob, due=days(3))
        with self.assertRaises(ValidationError):
            services.delete_part(self.slings[0])
        self.assertTrue(Part.objects.filter(pk=self.slings[0].pk).exists())

    def test_moves_or_drops_reservations(self):
        moved = services.reserve(self.alice, days(1), days(2), [Line(self.sling_type, 1)])
        piece = moved.parts.get()
        dropped = services.reserve(self.alice, days(1), days(2), [Line(part=self.harness)])
        services.delete_part(piece)
        services.delete_part(self.harness)
        self.assertNotEqual(moved.parts.get(), piece)
        dropped.refresh_from_db()
        self.assertEqual(dropped.status, Reservation.CANCELLED)
        self.assertEqual(mail.outbox[-1].to, ["alice@example.com"])

    def test_keeps_the_components(self):
        self.slings[1].parent = self.slings[0]
        self.slings[1].save()
        services.delete_part(self.slings[0])
        self.slings[1].refresh_from_db()
        self.assertIsNone(self.slings[1].parent)


class NoticeTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_links(self):
        self.assertEqual(
            services.material_link("/mine"), "http://localhost:8000/kompass/material/mine"
        )
        with self.settings(FRONTEND_BASE_URL="https://app.example.com/"):
            self.assertEqual(services.material_link(), "https://app.example.com/kompass/material")

    def test_holder_notice_days(self):
        self.assertTrue(services.holder_notice_due(7, [7, 2]))
        self.assertFalse(services.holder_notice_due(5, [7, 2]))
        self.assertTrue(services.holder_notice_due(2, [7, 2]))
        self.assertTrue(services.holder_notice_due(-1, [7, 2]))
        self.assertFalse(services.holder_notice_due(1, []))

    def test_unanswered_requests_are_declined(self):
        reservation = services.reserve(self.alice, TODAY, days(2), [Line(self.crampon_type, 1)])
        mail.outbox = []
        # The leaders have until the first day is over.
        self.assertEqual(services.send_notices()["declined"], 0)
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.REQUESTED)
        counts = services.send_notices(days(1))
        reservation.refresh_from_db()
        self.assertEqual(reservation.status, Reservation.DECLINED)
        self.assertEqual(counts["declined"], 1)
        self.assertIn("No answer", mail.outbox[0].body)

    def test_holders_are_asked_and_borrowers_reminded(self):
        reservation = services.reserve(self.alice, days(7), days(9), [Line(self.sling_type, 4)])
        mail.outbox = []
        counts = services.send_notices(TODAY)
        self.assertEqual(counts["holders"], 2)
        self.assertEqual(
            sorted(m.to[0] for m in mail.outbox), ["bob@example.com", "carol@example.com"]
        )
        # Twice on the same day sends nothing new.
        self.assertEqual(services.send_notices(TODAY)["holders"], 0)
        # Nothing on a day that is not a notice day.
        self.assertEqual(services.send_notices(days(1))["holders"], 0)
        counts = services.send_notices(days(6))
        self.assertEqual((counts["holders"], counts["pickups"]), (2, 1))
        reservation.refresh_from_db()
        self.assertEqual(reservation.last_holder_notice, days(6))

    def test_return_reminders(self):
        services.lend(self.alice, [self.slings[0]], self.alice, due=days(1))
        mail.outbox = []
        self.assertEqual(services.send_notices(TODAY)["returns"], 1)
        self.assertIn("due tomorrow", mail.outbox[0].subject)
        self.assertEqual(services.send_notices(TODAY)["returns"], 0)
        self.assertEqual(services.send_notices(days(3))["returns"], 1)
        self.assertIn("overdue", mail.outbox[-1].subject)

    def test_mail_without_member_is_skipped(self):
        services._mail(None, "subject", "text")
        self.assertEqual(mail.outbox, [])

    def test_task(self):
        with patch("equipment.tasks.services.send_notices", return_value={"declined": 0}) as run:
            self.assertEqual(send_material_notices(), {"declined": 0})
        run.assert_called_once()


class ReservedPartTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_approval_and_allocation_rows(self):
        reservation = services.reserve(self.alice, days(1), days(1), [Line(part=self.crampons[0])])
        self.assertTrue(ReservedPart.objects.get(reservation=reservation).pinned)
        self.assertEqual(Approval.objects.get(reservation=reservation).group, self.hochtour)


class SizeTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()
        self.setUpSizes()

    def test_str(self):
        self.assertEqual(str(self.size1), "Friends 1")

    def test_availability(self):
        entry = services.availability([self.friends_type], member=self.alice)[self.friends_type.pk]
        self.assertEqual((entry["total"], entry["available"], entry["available_direct"]), (6, 6, 5))
        self.assertEqual(entry["sets"], 1)
        self.assertEqual(entry["groups"], {None: ["", 5], self.hochtour.pk: ["Hochtour", 1]})
        Size.objects.create(product_type=self.friends_type, name="Beutel", quantity=1, per_set=0)
        self.friends_type.refresh_from_db()
        entry = services.availability([self.friends_type], member=self.alice)[self.friends_type.pk]
        self.assertEqual(entry["sets"], 1)

    def test_free_is_the_peak_of_a_day(self):
        services.reserve(self.alice, days(1), days(2), [Line(size=self.size1)])
        services.reserve(self.alice, days(4), days(5), [Line(size=self.size1)])
        entry = services.availability([self.friends_type], days(1), days(5))[self.friends_type.pk]
        self.assertEqual(entry["sizes"][self.size1.pk], 1)
        services.reserve(self.alice, days(2), days(4), [Line(size=self.size1)])
        with self.assertRaisesMessage(Conflict, "Only 0 of Friends 1 are free in this period."):
            services.reserve(self.alice, days(1), days(5), [Line(size=self.size1)])

    def test_reserve(self):
        lines = [Line(size=self.size2), Line(size=self.size2, quantity=2)]
        parts, sizes, problems, groups = services.check_reservation(
            self.alice, days(1), days(2), lines
        )
        self.assertEqual((parts, sizes, problems, groups), ([], [(self.size2, 3)], [], set()))
        _parts, _sizes, problems, _groups = services.check_reservation(
            self.alice, days(1), days(2), [*lines, Line(size=self.size2)]
        )
        self.assertEqual(problems, ["Only 0 of Friends 2 are free in this period."])
        reservation = services.reserve(
            self.alice, days(1), days(2), [Line(size=self.size1), Line(size=self.size3)]
        )
        self.assertEqual(reservation.status, Reservation.REQUESTED)
        self.assertEqual(
            list(reservation.reserved_sizes.values_list("size", "quantity")),
            [(self.size1.pk, 1), (self.size3.pk, 1)],
        )
        self.assertEqual(
            list(reservation.approvals.values_list("group", flat=True)), [self.hochtour.pk]
        )
        to_carol = next(m for m in mail.outbox if "carol@example.com" in m.to)
        self.assertIn("- 1 × Friends 3", to_carol.body)
        self.assertNotIn("Friends 1", to_carol.body)

    def test_lend_and_return(self):
        reservation = services.reserve(
            self.alice, TODAY, days(1), [Line(size=self.size1, quantity=2)]
        )
        loan = services.lend(
            self.alice,
            [],
            self.alice,
            reservation=reservation,
            sizes=[(self.size1, 2), (self.size2, 0)],
        )
        lent = loan.lent_sizes.get()
        self.assertEqual((lent.size, lent.quantity), (self.size1, 2))
        self.assertTrue(loan.is_open)
        entry = services.availability([self.friends_type], TODAY, days(1))[self.friends_type.pk]
        self.assertEqual(entry["sizes"][self.size1.pk], 0)
        with self.assertRaisesMessage(Conflict, "Only 0 of Friends 1 are free in this period."):
            services.lend(self.bob, [], self.bob, due=TODAY, sizes=[(self.size1, 1)])
        with self.assertRaisesMessage(ValidationError, "Nothing was selected."):
            services.lend(self.bob, [], self.bob, due=TODAY, sizes=[(self.size1, 0)])
        self.assertEqual(services.return_sizes([(lent, 1)]), [lent])
        self.assertEqual((lent.returned, lent.outstanding, lent.returned_at), (1, 1, None))
        services.return_sizes([(lent, 5)])
        self.assertEqual(lent.returned, 2)
        self.assertIsNotNone(lent.returned_at)
        self.assertEqual(services.return_sizes([(lent, 1)]), [])
        self.assertFalse(loan.is_open)

    def test_return_reminder_lists_sizes(self):
        services.lend(self.alice, [], self.alice, due=days(1), sizes=[(self.size2, 2)])
        self.assertEqual(services.send_notices()["returns"], 1)
        self.assertIn("- 2 × Friends 2", mail.outbox[-1].body)


class ApprovalAtLendingTestCase(MaterialFixture, TestCase):
    """Taking another group's material needs its approval, through a confirmed reservation."""

    def setUp(self):
        self.setUpMaterial()
        self.setUpSizes()

    def test_another_groups_piece_needs_a_reservation(self):
        with self.assertRaisesMessage(Conflict, "belongs to Hochtour"):
            services.lend(self.alice, [self.crampons[0]], self.alice, due=days(1))
        with self.assertRaisesMessage(Conflict, "belongs to Hochtour"):
            services.lend(self.alice, [self.crampons[0]], self.alice, permanent=True)
        with self.assertRaisesMessage(Conflict, "belongs to Hochtour"):
            services.lend(self.alice, [], self.alice, due=days(1), sizes=[(self.size3, 1)])
        # The group's own members, and the desk, need no approval.
        services.lend(self.carol, [self.crampons[0]], self.carol, due=days(1))
        services.lend(self.alice, [self.crampons[1]], self.bob, due=days(1), desk=True)

    def approved(self, lines):
        reservation = services.reserve(self.alice, TODAY, days(2), lines)
        self.assertEqual(reservation.status, Reservation.REQUESTED)
        services.decide(reservation, self.hochtour, True, self.carol)
        reservation.refresh_from_db()
        return reservation

    def test_a_confirmed_reservation_covers_its_pieces(self):
        reservation = self.approved([Line(self.crampon_type, 1)])
        allocated = reservation.parts.get()
        other = next(c for c in self.crampons if c != allocated)
        # Only as many pieces as were approved.
        with self.assertRaisesMessage(Conflict, "belongs to Hochtour"):
            services.lend(self.alice, self.crampons, self.alice, reservation=reservation)
        # Another piece of the same type and group may stand in for the allocated one.
        loan = services.lend(self.alice, [other], self.alice, reservation=reservation)
        self.assertEqual([line.part for line in loan.lines.all()], [other])

    def test_a_confirmed_reservation_covers_its_sizes(self):
        reservation = self.approved([Line(size=self.size3, quantity=1)])
        self.size3.quantity = 2
        self.size3.save()
        with self.assertRaisesMessage(Conflict, "Friends 3 belongs to Hochtour"):
            services.lend(
                self.alice, [], self.alice, reservation=reservation, sizes=[(self.size3, 2)]
            )
        loan = services.lend(
            self.alice, [], self.alice, reservation=reservation, sizes=[(self.size3, 1)]
        )
        self.assertEqual(loan.lent_sizes.get().quantity, 1)

    def test_a_picked_piece_replaces_one_of_its_own_group(self):
        section = self.make_part(self.crampon_type, location=self.cupboard)
        reservation = self.approved([Line(self.crampon_type, 2)])
        allocated = set(reservation.parts.all())
        self.assertIn(section, allocated)
        picked = next(c for c in self.crampons if c not in allocated)
        services.lend(self.alice, [picked], self.alice, reservation=reservation)
        self.assertEqual(set(reservation.parts.all()), {section, picked})

    def test_a_stale_reservation_is_read_again(self):
        reservation = services.reserve(self.alice, TODAY, days(1), [Line(self.sling_type, 1)])
        stale = Reservation.objects.get(pk=reservation.pk)
        services.lend(
            self.alice, list(reservation.parts.all()), self.alice, reservation=reservation
        )
        with self.assertRaisesMessage(ValidationError, "Only a confirmed reservation"):
            services.lend(self.alice, [self.slings[0]], self.alice, reservation=stale)


class ClaimTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()

    def test_taking_for_good_respects_reservations(self):
        services.reserve(self.bob, days(1), days(2), [Line(part=self.slings[0])])
        with self.assertRaisesMessage(Conflict, "reserved by Bob Test"):
            services.lend(self.alice, [self.slings[0]], self.alice, permanent=True)
        reservation = services.reserve(self.bob, days(5), days(6), [Line(self.sling_type, 1)])
        piece = reservation.parts.get()
        services.lend(self.alice, [piece], self.alice, permanent=True)
        self.assertNotEqual(reservation.parts.get(), piece)

    def test_a_moved_reservation_avoids_the_pieces_lent_with_it(self):
        reservation = services.reserve(self.carol, days(1), days(2), [Line(self.sling_type, 1)])
        # Carol's own sling is allocated; the cupboard's first sling would be next.
        self.assertEqual(reservation.parts.get(), self.slings[3])
        loan = services.lend(self.alice, [self.slings[3], self.slings[0]], self.alice, due=days(3))
        lent = set(loan.lines.values_list("part", flat=True))
        self.assertEqual(lent, {self.slings[3].pk, self.slings[0].pk})
        self.assertNotIn(reservation.parts.get().pk, lent)


class OverdueTestCase(MaterialFixture, TestCase):
    """What is overdue is not back, so it stays taken until it is."""

    def setUp(self):
        self.setUpMaterial()
        self.setUpSizes()

    def test_overdue_sizes_stay_taken(self):
        loan = services.lend(self.alice, [], self.alice, due=TODAY, sizes=[(self.size1, 2)])
        Loan.objects.filter(pk=loan.pk).update(due=days(-2))
        with self.assertRaisesMessage(Conflict, "Only 0 of Friends 1 are free in this period."):
            services.lend(self.bob, [], self.bob, due=days(1), sizes=[(self.size1, 1)])
        entry = services.availability([self.friends_type], days(5), days(6))[self.friends_type.pk]
        self.assertEqual(entry["sizes"][self.size1.pk], 0)

    def test_sizes_due_before_the_period_are_free(self):
        services.lend(self.alice, [], self.alice, due=days(1), sizes=[(self.size1, 2)])
        entry = services.availability([self.friends_type], days(5), days(6))[self.friends_type.pk]
        self.assertEqual(entry["sizes"][self.size1.pk], 2)

    def test_overdue_pieces_stay_blocked(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=TODAY)
        Loan.objects.filter(pk=loan.pk).update(due=days(-2))
        self.assertIn(self.slings[0].pk, services.blocked_part_ids(days(5), days(6)))
        with self.assertRaisesMessage(Conflict, "already booked"):
            services.reserve(self.bob, days(5), days(6), [Line(part=self.slings[0])])


class PassingOnTestCase(MaterialFixture, TestCase):
    """Passing on a lent piece without a date keeps it on loan."""

    def setUp(self):
        self.setUpMaterial()

    def test_the_loan_goes_with_the_piece(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=days(3))
        warnings = services.hand_over(
            [self.slings[0], self.slings[1]], self.alice, member=self.bob, keep_loans=True
        )
        self.assertEqual(warnings, ["{} stays on loan until {}.".format(self.slings[0], days(3))])
        self.assertFalse(loan.is_open)
        passed = Loan.objects.get(borrower=self.bob)
        self.assertEqual((passed.due, passed.lines.get().part), (days(3), self.slings[0]))
        self.slings[1].refresh_from_db()
        self.assertEqual(self.slings[1].holder, self.bob)
        self.assertFalse(self.slings[1].loan_lines.exists())

    def test_an_overdue_loan_is_due_today(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=TODAY)
        Loan.objects.filter(pk=loan.pk).update(due=days(-1))
        services.hand_over([self.slings[0]], self.alice, member=self.bob, keep_loans=True)
        self.assertEqual(Loan.objects.get(borrower=self.bob).due, TODAY)

    def test_a_place_takes_it_back(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=days(3))
        services.hand_over([self.slings[0]], self.alice, location=self.cupboard, keep_loans=True)
        self.assertFalse(loan.is_open)
        self.assertFalse(Loan.objects.filter(borrower=self.bob).exists())


class ReturnTestCase(MaterialFixture, TestCase):
    def setUp(self):
        self.setUpMaterial()
        self.setUpSizes()

    def test_a_piece_without_home_needs_a_place(self):
        services.lend(self.carol, [self.crampons[0]], self.carol, due=days(1))
        with self.assertRaisesMessage(ValidationError, "has no home location"):
            services.return_parts([self.crampons[0]], self.carol)
        services.return_parts([self.crampons[0]], self.carol, location=self.cupboard)
        self.crampons[0].refresh_from_db()
        self.assertEqual(
            (self.crampons[0].holder, self.crampons[0].location), (None, self.cupboard)
        )

    def test_a_flagged_component_flags_its_piece(self):
        services.assemble(self.slings[1], self.slings[0], self.alice)
        services.return_parts([self.slings[0]], self.alice, flagged=[self.slings[1]])
        self.slings[0].refresh_from_db()
        self.assertEqual(self.slings[0].status, Part.INSPECTION_DUE)

    def test_sizes_are_read_again_once_locked(self):
        loan = services.lend(self.alice, [], self.alice, due=days(1), sizes=[(self.size1, 2)])
        lent = loan.lent_sizes.get()
        stale = LentSize.objects.get(pk=lent.pk)
        services.return_sizes([(lent, 2)])
        self.assertEqual(services.return_sizes([(stale, 2)]), [])
        lent.refresh_from_db()
        self.assertEqual(lent.returned, 2)


class LockingTestCase(MaterialFixture, TestCase):
    """Decisions act on the reservation as it is now, not as it was read."""

    def setUp(self):
        self.setUpMaterial()

    def test_decide_reads_the_reservation_again(self):
        reservation = services.reserve(self.alice, days(1), days(2), [Line(self.crampon_type, 1)])
        stale = Reservation.objects.get(pk=reservation.pk)
        services.cancel(reservation)
        with self.assertRaisesMessage(ValidationError, "no longer waiting"):
            services.decide(stale, self.hochtour, True, self.carol)
        with self.assertRaisesMessage(ValidationError, "Only an open reservation"):
            services.cancel(stale)


class DeletedBorrowerTestCase(MaterialFixture, TestCase):
    """Deleting a member keeps their loans on record, and their pieces blocked."""

    def setUp(self):
        self.setUpMaterial()

    def test_the_loan_stays(self):
        loan = services.lend(self.alice, [self.slings[0]], self.alice, due=days(1))
        self.alice.delete()
        loan.refresh_from_db()
        self.assertIsNone(loan.borrower)
        self.assertTrue(loan.is_open)
        self.assertEqual(loan.borrower_name, "a deleted member")
        self.assertIn("a deleted member", str(loan))
        self.assertIn(self.slings[0].pk, services.blocked_part_ids(TODAY, days(1)))
        with self.assertRaisesMessage(Conflict, "still lent to a deleted member"):
            services.lend(self.bob, [self.slings[0]], self.bob, due=days(1))
        mail.outbox = []
        self.assertEqual(services.send_notices()["returns"], 0)
        self.assertEqual(mail.outbox, [])


class DeficitTestCase(TestCase):
    def test_the_wish_ends_after_it_starts(self):
        deficit = Deficit(text="Seilsack", wanted_from=days(3), wanted_to=days(1))
        with self.assertRaises(ValidationError) as context:
            deficit.full_clean()
        self.assertIn("wanted_to", context.exception.message_dict)
        Deficit(text="Seilsack", wanted_from=days(1), wanted_to=days(1)).full_clean()
