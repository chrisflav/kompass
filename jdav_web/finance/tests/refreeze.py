"""A submitted statement is never left without a live approval record.

Measured on an instance: a receipt added to a submitted statement made the
section's rules report a problem — Ludwigsburg's payees are the receipts'
payers once there are any, so the per diem answered to the statement's creator
fell out of the domain — and :func:`finance.engine.statements.materialise`
retired the frozen approval rows and wrote none, which is what it does while
the rules report a problem. Deleting the receipt again is what has to bring
them back, and deleted through a queryset it did not: the refresh lived in
``Bill.delete``, which a queryset delete never calls. Four superseded rows, no
live one, a statement that read as valid, and nobody who could sign it.

The assertions here are about **which** rows are live, never about how many:
a count is satisfied by the generation the statement was handed in with as
readily as by the one the rules just wrote.
"""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import TestCase
from finance.engine import import_from_directory
from finance.models import Bill
from finance.models import BillOnExcursionProxy
from finance.models import BillOnStatementProxy
from finance.models import Statement
from finance.store import ApprovalConstraint
from finance.store import ApprovalConstraintManager
from finance.store import Obligation
from finance.tests.approval import a_user

#: Two steps over two different groups, and a receipt nobody paid is a problem
#: the rules report — the shape of the instance where the record went missing.
TWO_STEPS_THAT_CAN_BREAK = """
from kompass.rules import Constraint, Member, Ruleset, SECTION, PARTICIPANTS, Transfer


class TwoStepsThatCanBreak(Ruleset):
    name = "two-steps-that-can-break"
    permissions = ("finance.process_statementsubmitted",)
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        transfers, errors = [], []
        for bill in ctx.bills:
            if not bill.covered:
                continue
            if bill.payer is None:
                errors.append("a covered receipt has nobody to pay back")
                continue
            transfers.append(Transfer(SECTION, bill.payer, bill.amount, "bill", rule_id="bills"))
        return transfers, errors

    def approval(self, ctx, transfers):
        signers = sorted(
            ctx.permission_holders("finance.process_statementsubmitted"),
            key=lambda member: int(member.id),
        )
        return (
            [
                Constraint(
                    name="Leitung",
                    description="",
                    applicable=True,
                    required=1,
                    eligible=tuple(signers[:1]),
                ),
                Constraint(
                    name="Kasse",
                    description="",
                    applicable=True,
                    required=1,
                    eligible=tuple(signers[1:]),
                ),
            ],
            [],
        )


ruleset = TwoStepsThatCanBreak()
"""


class TheRecordComesBackTestCase(TestCase):
    """Taking the receipt away again restores the record, however it is taken."""

    def setUp(self):
        self.leitung_user, self.leitung = a_user("leitung", permitted=True)
        self.kasse_user, self.kasse = a_user("kasse", permitted=True)
        self.payer_user, self.payer = a_user("zahler")
        self.directory = TemporaryDirectory()
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(TWO_STEPS_THAT_CAN_BREAK, encoding="utf-8")
        _row, problems = import_from_directory(package, name="two-steps-that-can-break")
        self.assertEqual(problems, [])
        self.statement = Statement.objects.create(short_description="Hütte")
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("40.00"),
            costs_covered=True,
            paid_by=self.payer,
        )
        self.statement.submit(submitter=self.payer)
        self.handed_in = self.live_ids()

    def tearDown(self):
        self.directory.cleanup()

    def live_ids(self):
        return set(
            ApprovalConstraint.objects.filter(statement=self.statement).values_list("pk", flat=True)
        )

    def live_rows(self):
        """The live rows, as what a signer is asked: step, group, frozen or not."""
        return [
            (row.name, row.eligible_member_ids, row.frozen_at is not None, row.error)
            for row in ApprovalConstraint.objects.filter(statement=self.statement).order_by(
                "position"
            )
        ]

    def break_it(self):
        """Add the receipt the rules cannot settle, and check that it broke."""
        receipt = Bill.objects.create(
            statement=self.statement,
            short_description="Hüttenrechnung",
            amount=Decimal("90.00"),
            costs_covered=True,
            paid_by=None,
        )
        fresh = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(fresh.rule_result.errors, "the receipt is one the rules cannot settle")
        self.assertEqual(self.live_ids(), set(), "and the record is retired while it is there")
        return receipt

    def assert_a_new_generation(self):
        """The rules' own answer is live again, written after the receipt went."""
        rows = ApprovalConstraint.objects.filter(statement=self.statement)
        self.assertEqual(
            self.live_rows(),
            [
                ("Leitung", [self.leitung.pk], True, ""),
                ("Kasse", [self.kasse.pk], True, ""),
            ],
        )
        newest = max(
            ApprovalConstraint.all_objects.filter(statement=self.statement).values_list(
                "pk", flat=True
            )
        )
        self.assertTrue(
            all(pk > max(self.handed_in) for pk in rows.values_list("pk", flat=True)),
            "the live rows are a new generation, not the one it was handed in with",
        )
        self.assertIn(newest, self.live_ids(), "and the newest row is one of them")
        self.assertTrue(
            all(
                row.superseded_at is not None
                for row in ApprovalConstraint.all_objects.filter(pk__in=self.handed_in)
            ),
            "the generation it was handed in with stays superseded",
        )
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertEqual(statement.rule_result.errors, ())
        self.assertTrue(statement.may_be_approved_by(self.leitung))
        self.assertTrue(statement.may_be_approved_by(self.kasse))

    def test_a_receipt_deleted_through_a_queryset_brings_the_record_back(self):
        receipt = self.break_it()
        Bill.objects.filter(pk=receipt.pk).delete()
        self.assert_a_new_generation()

    def test_a_receipt_deleted_on_its_own_brings_the_record_back(self):
        receipt = self.break_it()
        Bill.objects.get(pk=receipt.pk).delete()
        self.assert_a_new_generation()

    def test_a_receipt_deleted_through_its_statement_brings_the_record_back(self):
        """The related manager is a queryset too, and the obvious one to reach for."""
        receipt = self.break_it()
        Statement.objects.get(pk=self.statement.pk).bill_set.filter(pk=receipt.pk).delete()
        self.assert_a_new_generation()

    def test_a_proxy_deleted_through_a_queryset_brings_the_record_back(self):
        """The collector names the class it deleted, so a proxy is a sender of its own."""
        for proxy in (BillOnStatementProxy, BillOnExcursionProxy):
            with self.subTest(proxy=proxy.__name__):
                receipt = self.break_it()
                proxy.objects.filter(pk=receipt.pk).delete()
                self.assert_a_new_generation()

    def test_one_deletion_writes_one_generation(self):
        """A queryset delete reports every bill it removed, after removing all of them.

        So each report resolves the same state, and resolving it once per bill
        wrote the same generation once per bill.
        """
        first = self.break_it()
        second = Bill.objects.create(
            statement=self.statement,
            short_description="Noch eine",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=None,
        )
        before = set(
            ApprovalConstraint.all_objects.filter(statement=self.statement).values_list(
                "pk", flat=True
            )
        )
        Bill.objects.filter(pk__in=[first.pk, second.pk]).delete()
        written = (
            set(
                ApprovalConstraint.all_objects.filter(statement=self.statement).values_list(
                    "pk", flat=True
                )
            )
            - before
        )
        self.assertEqual(written, self.live_ids(), "everything written is the live generation")
        self.assert_a_new_generation()

    def test_deleting_the_statement_does_not_write_it_a_new_record(self):
        """A cascade takes the bills with the statement, and must not re-resolve it.

        The collector has listed the rows it will delete before it deletes
        the bills; a generation written in between is a row it never listed,
        left pointing at a statement that no longer exists. (An excursion's
        statement is ``SET_NULL``, so this is the one cascade there is.)
        """
        pk = self.statement.pk
        Statement.objects.get(pk=pk).delete()
        self.assertFalse(ApprovalConstraint.all_objects.filter(statement_id=pk).exists())
        self.assertFalse(Obligation.objects.filter(statement_id=pk).exists())


class TheOldGenerationStandsTestCase(TestCase):
    """A re-freeze that fails part of the way leaves the record as it was."""

    def setUp(self):
        self.user, self.treasurer = a_user("kasse", permitted=True)
        self.other_user, self.other = a_user("andere")
        self.statement = Statement.objects.create(short_description="Freigabe")
        self.bill = Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.other,
        )
        self.statement.submit(submitter=self.other)
        self.constraints = self.live(ApprovalConstraint.objects)
        self.obligations = self.live(Obligation.objects, superseded_at__isnull=True)
        self.assertTrue(self.constraints)
        self.assertTrue(self.obligations)

    def live(self, manager, **lookups):
        return set(manager.filter(statement=self.statement, **lookups).values_list("pk", flat=True))

    def assert_untouched(self):
        self.assertEqual(self.live(ApprovalConstraint.objects), self.constraints)
        self.assertEqual(
            self.live(Obligation.objects, superseded_at__isnull=True), self.obligations
        )

    def test_rules_that_fail_while_resolving_the_signatures_retire_nothing(self):
        """Resolving the constraints happened between retiring and writing."""
        self.bill.amount = Decimal("12.00")
        with (
            patch(
                "finance.engine.statements.resolve_constraints",
                side_effect=RuntimeError("the rules failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.bill.save()
        self.assert_untouched()

    def test_a_write_that_fails_takes_the_whole_generation_back(self):
        """The obligations are written first, so the constraints failing is half a swap."""
        self.bill.amount = Decimal("12.00")
        with (
            patch.object(
                ApprovalConstraintManager,
                "bulk_create",
                side_effect=RuntimeError("the database refused"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.bill.save()
        self.assert_untouched()

    def test_retiring_for_a_problem_is_both_halves_or_neither(self):
        """While the rules report a problem both halves of the record go, together.

        The obligations went first, so a failure retiring the constraints left
        a statement with no payout on the record and a live approval record
        still asking for signatures on it.
        """
        self.bill.paid_by = None
        with (
            patch(
                "finance.engine.statements._retire_constraint_rows",
                side_effect=RuntimeError("the database refused"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.bill.save()
        self.assert_untouched()
