from django.test import TestCase
from django.utils import timezone
from django.conf import settings
from django.contrib.auth.models import User
from unittest.mock import Mock
from finance.rules import is_creator, not_submitted, leads_excursion
from finance.models import Statement, Ledger
from members.models import Member, Group, Freizeit, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE, MALE, FEMALE


class FinanceRulesTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Test Group")
        self.ledger = Ledger.objects.create(name="Test Ledger")

        self.user1 = User.objects.create_user(username="alice", password="test123")
        self.member1 = Member.objects.create(
            prename="Alice", lastname="Smith", birth_date=timezone.now().date(),
            email=settings.TEST_MAIL, gender=FEMALE, user=self.user1
        )
        self.member1.group.add(self.group)

        self.user2 = User.objects.create_user(username="bob", password="test123")
        self.member2 = Member.objects.create(
            prename="Bob", lastname="Jones", birth_date=timezone.now().date(),
            email=settings.TEST_MAIL, gender=MALE, user=self.user2
        )
        self.member2.group.add(self.group)

        self.freizeit = Freizeit.objects.create(
            name="Test Excursion",
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=2
        )
        self.freizeit.jugendleiter.add(self.member1)

        self.statement = Statement.objects.create(
            short_description="Test Statement",
            explanation="Test explanation",
            night_cost=27,
            created_by=self.member1,
            excursion=self.freizeit
        )
        self.statement.allowance_to.add(self.member1)

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
        if hasattr(mock_freizeit, 'statement'):
            delattr(mock_freizeit, 'statement')
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

    def test_leads_excursion_statement_excursion_is_none(self):
        """Test leads_excursion predicate with statement having None excursion"""
        statement_no_excursion = Statement.objects.create(
            short_description="Test Statement No Excursion",
            explanation="Test explanation",
            night_cost=27,
            created_by=self.member1,
            excursion=None
        )
        result = leads_excursion(self.user1, statement_no_excursion)
        self.assertFalse(result)
