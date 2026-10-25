from unittest.mock import Mock

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from finance.models import Ledger
from finance.models import Statement
from finance.rules import is_creator
from finance.rules import leads_excursion
from finance.rules import may_approve
from finance.rules import not_submitted
from members.models import FEMALE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import MALE
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE


class FinanceRulesTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Test Group")
        self.ledger = Ledger.objects.create(name="Test Ledger")

        self.user1 = User.objects.create_user(username="alice", password="test123")
        self.member1 = Member.objects.create(
            prename="Alice",
            lastname="Smith",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=FEMALE,
            user=self.user1,
        )
        self.member1.group.add(self.group)

        self.user2 = User.objects.create_user(username="bob", password="test123")
        self.member2 = Member.objects.create(
            prename="Bob",
            lastname="Jones",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
            user=self.user2,
        )
        self.member2.group.add(self.group)

        self.freizeit = Freizeit.objects.create(
            name="Test Excursion",
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=2,
        )
        self.freizeit.jugendleiter.add(self.member1)

        self.statement = Statement.objects.create(
            short_description="Test Statement",
            explanation="Test explanation",
            inputs={"night_cost": "27", "allowance_to": [self.member1.pk]},
            created_by=self.member1,
            excursion=self.freizeit,
        )

    def test_is_creator_true(self):
        """Test is_creator predicate returns True when user created the statement"""
        self.assertTrue(is_creator(self.user1, self.statement))
        self.assertFalse(is_creator(self.user2, self.statement))

    def test_not_submitted_statement(self):
        """Test not_submitted predicate returns True when statement is not submitted"""
        self.statement.status = Statement.UNSUBMITTED
        self.assertTrue(not_submitted(self.user1, self.statement))
        self.statement.status = Statement.SUBMITTED
        self.assertFalse(not_submitted(self.user1, self.statement))

    def test_not_submitted_freizeit_with_statement(self):
        """Test not_submitted predicate with Freizeit having unsubmitted statement"""
        self.freizeit.statement = self.statement
        self.statement.status = Statement.UNSUBMITTED
        self.assertTrue(not_submitted(self.user1, self.freizeit))

    def test_not_submitted_freizeit_without_statement(self):
        """Test not_submitted predicate with Freizeit having no statement attribute"""
        # Create a mock Freizeit that truly doesn't have the statement attribute
        mock_freizeit = Mock(spec=Freizeit)
        # Remove the statement attribute entirely
        if hasattr(mock_freizeit, "statement"):
            delattr(mock_freizeit, "statement")
        self.assertTrue(not_submitted(self.user1, mock_freizeit))

    def test_leads_excursion_freizeit_user_is_leader(self):
        """Test leads_excursion predicate returns True when user leads the Freizeit"""
        self.assertTrue(leads_excursion(self.user1, self.freizeit))
        self.assertFalse(leads_excursion(self.user2, self.freizeit))

    def test_leads_excursion_statement_with_excursion(self):
        """Test leads_excursion predicate with statement having excursion led by user"""
        result = leads_excursion(self.user1, self.statement)
        self.assertTrue(result)

    def test_leads_excursion_statement_no_excursion_attribute(self):
        """Test leads_excursion predicate with statement having no excursion attribute"""
        mock_statement = Mock()
        del mock_statement.excursion
        result = leads_excursion(self.user1, mock_statement)
        self.assertFalse(result)

    def test_an_object_permission_asked_without_an_object_answers(self):
        """``has_perm("finance.view_obj_statement")`` with no row was a 500.

        django-rules pads a missing object with ``None``
        (``Predicate._apply``), and three of these predicates met it with an
        ``assert`` — so any global check against an object permission raised
        ``AssertionError`` out of the permission backend rather than
        answering. It is a question, and for an object permission the answer
        is no; the one clause of ``view_obj`` that is itself global still
        answers yes, which is what says the chain was evaluated rather than
        short-circuited to a refusal.
        """
        predicates = {
            "is_creator": is_creator,
            "not_submitted": not_submitted,
            "leads_excursion": leads_excursion,
            "may_approve": may_approve,
        }
        for name, pred in predicates.items():
            with self.subTest(predicate=name):
                self.assertFalse(pred(self.user1, None))
        user = User.objects.get(pk=self.user1.pk)
        for name in ("view_obj", "change_obj", "delete_obj", "approve_obj"):
            with self.subTest(permission=name):
                self.assertFalse(user.has_perm(f"finance.{name}_statement"))
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="finance", codename="view_global_statement"
            )
        )
        self.assertTrue(
            User.objects.get(pk=user.pk).has_perm("finance.view_obj_statement"),
            "the global clause of it answers for itself",
        )

    def test_leads_excursion_statement_excursion_is_none(self):
        """Test leads_excursion predicate with statement having None excursion"""
        statement_no_excursion = Statement.objects.create(
            short_description="Test Statement No Excursion",
            explanation="Test explanation",
            inputs={"night_cost": "27"},
            created_by=self.member1,
            excursion=None,
        )
        result = leads_excursion(self.user1, statement_no_excursion)
        self.assertFalse(result)
