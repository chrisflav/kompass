"""Query-count tests for the finance API statement list."""

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from finance.models import Bill
from finance.models import Statement
from members.tests.api import make_member_user
from members.tests.api_queries import QueryCountTestCase


class StatementListQueryCountTestCase(QueryCountTestCase):
    def setUp(self):
        super().setUp()
        self.manager_user, self.manager = make_member_user("manager")
        for codename in ("list_global_statement", "view_global_statement"):
            self.manager_user.user_permissions.add(
                Permission.objects.get(content_type__app_label="finance", codename=codename)
            )
        self.manager_user = User.objects.get(pk=self.manager_user.pk)

    def make_statement(self, with_excursion):
        leaders = [self.make_member("leader"), self.make_member("leader")]
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
        return statement

    def test_list_statements(self):
        def make_rows(n):
            for i in range(n):
                self.make_statement(with_excursion=i % 2 == 0)

        body = self.assertConstantQueries("/api/finance/statements", self.manager_user, make_rows)
        self.assertEqual(len(body), 9)
        expected = {s.pk: float(s.total) for s in Statement.objects.all()}
        self.assertEqual({s["id"]: s["total"] for s in body}, expected)
        self.assertTrue(all(s["created_by"]["groups"] == [] for s in body))
