from django.test import TestCase
from django.conf import settings
from django.contrib.auth.models import User
from mailer.rules import is_creator
from mailer.models import Message
from members.models import Member, MALE


class MailerRulesTestCase(TestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(username="alice", password="test123")
        self.member1 = Member.objects.create(
            prename="Alice", lastname="Smith", birth_date="1990-01-01",
            email=settings.TEST_MAIL, gender=MALE, user=self.user1
        )

        self.message = Message.objects.create(
            subject="Test Message",
            content="Test content",
            created_by=self.member1
        )

    def test_is_creator_returns_true_when_user_created_message(self):
        """Test is_creator predicate returns True when user created the message"""
        result = is_creator(self.user1, self.message)
        self.assertTrue(result)

    def test_is_creator_returns_false_when_message_is_none(self):
        """Test is_creator predicate returns False when message is None"""
        result = is_creator(self.user1, None)
        self.assertFalse(result)
