"""Query-count tests for the finance API statements, bills and transactions."""

import datetime

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.models import Transaction
from members.models import Intervention
from members.models import LJPProposal
from members.tests.api import make_member_user
from members.tests.api_queries import QueryCountMixin


class StatementListQueryCountTestCase(QueryCountMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.manager_user, self.manager = make_member_user("manager")
        for codename in ("list_global_statement", "view_global_statement", "view_transaction"):
            self.manager_user.user_permissions.add(
                Permission.objects.get(content_type__app_label="finance", codename=codename)
            )
        self.manager_user = User.objects.get(pk=self.manager_user.pk)

    def make_statement(self, with_excursion, with_ljp):
        leaders = [self.make_member("leader"), self.make_member("leader")]
        leaders[0].group.set([self.make_group()])
        excursion = None
        if with_excursion:
            participants = [self.make_member() for _ in range(4)]
            excursion = self.make_excursion(participants=participants, leaders=leaders)
        statement = Statement.objects.create(
            short_description="Abrechnung",
            explanation="",
            excursion=excursion,
            created_by=leaders[0],
            inputs={
                "night_cost": "20",
                "subsidy_to": leaders[0].pk,
                "ljp_to": leaders[1].pk if with_ljp else None,
                "allowance_to": sorted(leader.pk for leader in leaders),
            },
        )
        for covered in (True, False):
            Bill.objects.create(
                statement=statement,
                short_description="Beleg",
                amount=12,
                paid_by=leaders[1],
                costs_covered=covered,
            )
        if with_ljp:
            proposal = LJPProposal.objects.create(
                title="Seminar",
                category=LJPProposal.LJP_STAFF_TRAINING,
                goal=LJPProposal.LJP_ENVIRONMENT,
                goal_strategy="Strategie",
                not_bw_reason=LJPProposal.NOT_BW_ROOMS,
                excursion=excursion,
            )
            # Two seminar days: one full (5 hours), one half (3 hours).
            for day, hours in ((0, 3), (0, 2), (1, 3)):
                Intervention.objects.create(
                    date_start=excursion.date + datetime.timedelta(days=day),
                    duration=hours,
                    activity="Einheit",
                    ljp_proposal=proposal,
                )
        return statement

    def test_list_statements(self):
        def make_rows(n):
            # Equally many without excursion, with one and with an LJP proposal.
            for i in range(n):
                self.make_statement(with_excursion=i % 3 > 0, with_ljp=i % 3 == 2)

        body = self.assertConstantQueries("/api/finance/statements", self.manager_user, make_rows)
        self.assertEqual(len(body), 9)
        statements = Statement.objects.all()
        self.assertEqual(
            {s["id"]: s["total"] for s in body}, {s.pk: float(s.total) for s in statements}
        )
        ljp = [s for s in statements if s.inputs.get("ljp_to")]
        self.assertEqual(len(ljp), 3)
        self.assertTrue(all(s.excursion.total_seminar_days == 1.5 for s in ljp))
        self.assertTrue(all(s.paid_ljp_contributions > 0 for s in ljp))
        self.assertTrue(all(len(s["created_by"]["groups"]) == 1 for s in body))

    def test_list_statements_scoped(self):
        """A member without global permissions lists their own statements, once each.

        Half of them belong to an excursion with two youth leaders, which
        listed them twice before.
        """
        user, member = make_member_user("creator")
        # Somebody else's statement is not listed.
        self.make_statement(with_excursion=True, with_ljp=False)
        own = []

        def make_rows(n):
            for i in range(n):
                statement = self.make_statement(with_excursion=i % 2 == 0, with_ljp=False)
                Statement.objects.filter(pk=statement.pk).update(created_by=member)
                own.append(statement.pk)

        body = self.assertConstantQueries("/api/finance/statements", user, make_rows)
        self.assertEqual(sorted(s["id"] for s in body), sorted(own))
        self.assertEqual(
            {s["id"]: s["total"] for s in body},
            {s.pk: float(s.total) for s in Statement.objects.filter(pk__in=own)},
        )

    def test_list_statements_as_youth_leader(self):
        """A youth leader of the excursion lists its statement once."""
        user, member = make_member_user("yl")
        statement = self.make_statement(with_excursion=True, with_ljp=False)
        statement.excursion.jugendleiter.add(member)
        r = self.client.get("/api/finance/statements", **self.auth(user))
        self.assertEqual([s["id"] for s in r.json()], [statement.pk])

    def add_bill_and_transaction(self, statement):
        """A covered bill and a transaction, each naming members with a group."""
        payer, recipient, confirmer = (self.make_member() for _ in range(3))
        for member in (payer, recipient, confirmer):
            member.group.set([self.make_group()])
        Bill.objects.create(
            statement=statement,
            short_description="Beleg",
            amount=10,
            paid_by=payer,
            costs_covered=True,
        )
        Transaction.objects.create(
            statement=statement,
            member=recipient,
            amount=10,
            reference="Erstattung",
            ledger=Ledger.objects.create(name="Konto {}".format(self.counter)),
            confirmed_by=confirmer,
        )

    def test_retrieve_statement(self):
        statement = self.make_statement(with_excursion=True, with_ljp=True)

        def make_rows(n):
            for _ in range(n):
                self.add_bill_and_transaction(statement)

        body = self.assertConstantQueries(
            "/api/finance/statements/{}".format(statement.pk), self.manager_user, make_rows
        )
        statement = Statement.objects.get(pk=statement.pk)
        self.assertEqual(len(body["bills"]), 2 + 9)
        self.assertTrue(all(len(b["paid_by"]["groups"]) == 1 for b in body["bills"][2:]))
        self.assertEqual(body["total"], float(statement.total))
        self.assertEqual(body["total_bills"], float(statement.total_bills))
        self.assertEqual(body["paid_ljp_contributions"], float(statement.paid_ljp_contributions))
        self.assertEqual(body["validity"], statement.validity)
        self.assertEqual(len(body["transaction_issues"]), len(statement.transaction_issues))
        self.assertEqual(len(body["excursion"]["participant_ids"]), 6)

    def test_list_bills(self):
        def make_rows(n):
            for _ in range(n):
                self.add_bill_and_transaction(
                    self.make_statement(with_excursion=False, with_ljp=False)
                )

        body = self.assertConstantQueries("/api/finance/bills", self.manager_user, make_rows)
        self.assertEqual(len(body), 9 * 3)
        self.assertEqual(
            {b["id"]: len(b["paid_by"]["groups"]) for b in body},
            {b.pk: b.paid_by.group.count() for b in Bill.objects.all()},
        )
        self.assertEqual(sum(len(b["paid_by"]["groups"]) for b in body), 9)

    def test_list_transactions(self):
        statement = self.make_statement(with_excursion=False, with_ljp=False)

        def make_rows(n):
            for _ in range(n):
                self.add_bill_and_transaction(statement)

        body = self.assertConstantQueries("/api/finance/transactions", self.manager_user, make_rows)
        self.assertEqual(len(body), 9)
        self.assertTrue(all(len(t["member"]["groups"]) == 1 for t in body))
        self.assertTrue(all(len(t["confirmed_by"]["groups"]) == 1 for t in body))
        self.assertTrue(all(t["ledger"] for t in body))

    def test_list_statement_transactions(self):
        statement = self.make_statement(with_excursion=False, with_ljp=False)
        # Another statement's transactions are not listed.
        self.add_bill_and_transaction(self.make_statement(with_excursion=False, with_ljp=False))

        def make_rows(n):
            for _ in range(n):
                self.add_bill_and_transaction(statement)

        body = self.assertConstantQueries(
            "/api/finance/statements/{}/transactions".format(statement.pk),
            self.manager_user,
            make_rows,
        )
        expected = list(statement.transaction_set.order_by("id"))
        self.assertEqual([t["id"] for t in body], [t.pk for t in expected])
        self.assertTrue(all(len(t["member"]["groups"]) == 1 for t in body))
