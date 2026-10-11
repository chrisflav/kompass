"""Query-count tests for the finance API statement list."""

import datetime

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from finance.models import Bill
from finance.models import Statement
from members.models import Intervention
from members.models import LJPProposal
from members.tests.api import make_member_user
from members.tests.api_queries import QueryCountMixin


class StatementListQueryCountTestCase(QueryCountMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.manager_user, self.manager = make_member_user("manager")
        for codename in ("list_global_statement", "view_global_statement"):
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
            night_cost=20,
            excursion=excursion,
            created_by=leaders[0],
            subsidy_to=leaders[0],
            ljp_to=leaders[1] if with_ljp else None,
        )
        statement.allowance_to.set(leaders)
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
        ljp = [s for s in statements if s.ljp_to_id]
        self.assertEqual(len(ljp), 3)
        self.assertTrue(all(s.excursion.total_seminar_days == 1.5 for s in ljp))
        self.assertTrue(all(s.paid_ljp_contributions > 0 for s in ljp))
        self.assertTrue(all(len(s["created_by"]["groups"]) == 1 for s in body))
