from django.test import TestCase
from django.utils import timezone
from django.contrib.auth.models import User

from ..models import Member, Group, Freizeit, DIVERSE, GEMEINSCHAFTS_TOUR, MemberTraining, TrainingCategory, LJPProposal
from ..rules import is_oneself, may_view, may_change, may_delete, is_own_training, is_leader_of_excursion, is_leader, statement_not_submitted, _is_leader
from finance.models import Statement
from mailer.models import EmailAddress


class RulesTestCase(TestCase):
    def setUp(self):
        # Create email address for groups
        self.email_address = EmailAddress.objects.create(name='test@example.com')

        # Create test users and members
        self.user1 = User.objects.create_user(username='user1', email='user1@example.com')
        self.member1 = Member.objects.create(
            prename='Test',
            lastname='Member1',
            birth_date=timezone.now().date(),
            email='member1@example.com',
            gender=DIVERSE
        )
        self.user1.member = self.member1
        self.user1.save()

        self.user2 = User.objects.create_user(username='user2', email='user2@example.com')
        self.member2 = Member.objects.create(
            prename='Test',
            lastname='Member2',
            birth_date=timezone.now().date(),
            email='member2@example.com',
            gender=DIVERSE
        )
        self.user2.member = self.member2
        self.user2.save()

        self.user3 = User.objects.create_user(username='user3', email='user3@example.com')
        self.member3 = Member.objects.create(
            prename='Test',
            lastname='Member3',
            birth_date=timezone.now().date(),
            email='member3@example.com',
            gender=DIVERSE
        )
        self.user3.member = self.member3
        self.user3.save()

        # Create test group
        self.group = Group.objects.create(name='Test Group')
        self.group.contact_email = self.email_address
        self.group.leiters.add(self.member2)
        self.group.save()

        # Create test excursion
        self.excursion = Freizeit.objects.create(
            name='Test Excursion',
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1
        )
        self.excursion.jugendleiter.add(self.member1)
        self.excursion.groups.add(self.group)
        self.excursion.save()

        # Create training category and training
        self.training_category = TrainingCategory.objects.create(
            name='Test Training',
            permission_needed=False
        )

        self.training = MemberTraining.objects.create(
            member=self.member1,
            title='Test Training',
            category=self.training_category,
            participated=True,
            passed=True
        )

        # Create LJP proposal
        self.ljp_proposal = LJPProposal.objects.create(
            title='Test LJP',
            excursion=self.excursion
        )

        # Create statement
        self.statement_unsubmitted = Statement.objects.create(
            short_description='Unsubmitted Statement',
            excursion=self.excursion,
            submitted=False
        )

        self.statement_submitted = Statement.objects.create(
            short_description='Submitted Statement',
            submitted=True
        )

    def test_is_oneself(self):
        """Test is_oneself rule - member can identify themselves."""
        # Same member
        self.assertTrue(is_oneself(self.user1, self.member1))

        # Different members
        self.assertFalse(is_oneself(self.user1, self.member2))

    def test_may(self):
        """Test `may_` rules."""
        self.assertTrue(may_view(self.user1, self.member1))
        self.assertTrue(may_change(self.user1, self.member1))
        self.assertTrue(may_delete(self.user1, self.member1))

    def test_is_own_training(self):
        """Test is_own_training rule - member can access their own training."""
        # Own training
        self.assertTrue(is_own_training(self.user1, self.training))
        # Other member's training
        self.assertFalse(is_own_training(self.user2, self.training))

    def test_is_leader_of_excursion(self):
        """Test is_leader_of_excursion rule for LJP proposals."""
        # LJP proposal with excursion - member3 is not a leader
        self.assertFalse(is_leader_of_excursion(self.user3, self.ljp_proposal))
        # Directly pass an excursion
        self.assertTrue(is_leader_of_excursion(self.user1, self.excursion))

    def test_is_leader(self):
        """Test is_leader rule for excursions."""
        # Direct excursion leader
        self.assertTrue(is_leader(self.user1, self.excursion))

        # Group leader (member2 is leader of group that is part of excursion)
        self.assertTrue(is_leader(self.user2, self.excursion))

        # member3 is unrelated
        self.assertFalse(is_leader(self.user3, self.excursion))

        # Test user without member attribute
        user_no_member = User.objects.create_user(username='nomember', email='nomember@example.com')
        self.assertFalse(is_leader(user_no_member, self.excursion))

        # Test member without pk attribute
        class MemberNoPk:
            pass
        member_no_pk = MemberNoPk()
        self.assertFalse(_is_leader(member_no_pk, self.excursion))

        # Test member with None pk
        class MemberNonePk:
            pk = None
        member_none_pk = MemberNonePk()
        self.assertFalse(_is_leader(member_none_pk, self.excursion))

    def test_statement_not_submitted(self):
        """Test statement_not_submitted rule."""
        # Unsubmitted statement with excursion
        self.assertTrue(statement_not_submitted(self.user1, self.excursion))

        # Submitted statement
        self.excursion.statement = self.statement_submitted
        self.excursion.save()
        self.assertFalse(statement_not_submitted(self.user1, self.excursion))

        # Excursion without statement
        excursion_no_statement = Freizeit.objects.create(
            name='No Statement Excursion',
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1
        )
        self.assertFalse(statement_not_submitted(self.user1, excursion_no_statement))

        # Test the excursion.statement is None case
        # Create a special test object to directly trigger
        class ExcursionWithNoneStatement:
            def __init__(self):
                self.statement = None
        # if excursion.statement is None: return False
        self.assertFalse(statement_not_submitted(self.user1, ExcursionWithNoneStatement()))
