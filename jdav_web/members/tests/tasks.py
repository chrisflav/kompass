from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.conf import settings

from ..models import MemberWaitingList, Freizeit, Group, DIVERSE, GEMEINSCHAFTS_TOUR
from ..tasks import ask_for_waiting_confirmation, send_crisis_intervention_list, send_notification_crisis_intervention_list
from mailer.models import EmailAddress


class TasksTestCase(TestCase):
    def setUp(self):
        # Create test email address
        self.email_address = EmailAddress.objects.create(name='test@example.com')

        # Create test group
        self.group = Group.objects.create(name='Test Group')
        self.group.contact_email = self.email_address
        self.group.save()

        # Create test waiters
        now = timezone.now()
        old_confirmation = now - timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY + 1)
        old_reminder = now - timezone.timedelta(days=settings.CONFIRMATION_REMINDER_FREQUENCY + 1)

        self.waiter1 = MemberWaitingList.objects.create(
            prename='Test',
            lastname='Waiter1',
            birth_date=now.date(),
            email='waiter1@example.com',
            gender=DIVERSE,
            last_wait_confirmation=old_confirmation,
            last_reminder=old_reminder,
            sent_reminders=0
        )

        self.waiter2 = MemberWaitingList.objects.create(
            prename='Test',
            lastname='Waiter2',
            birth_date=now.date(),
            email='waiter2@example.com',
            gender=DIVERSE,
            last_wait_confirmation=old_confirmation,
            last_reminder=old_reminder,
            sent_reminders=settings.MAX_REMINDER_COUNT - 1
        )

        # Create waiter that shouldn't receive reminder (too recent confirmation)
        self.waiter3 = MemberWaitingList.objects.create(
            prename='Test',
            lastname='Waiter3',
            birth_date=now.date(),
            email='waiter3@example.com',
            gender=DIVERSE,
            last_wait_confirmation=now,
            last_reminder=old_reminder,
            sent_reminders=0
        )

        # Create waiter that shouldn't receive reminder (max reminders reached)
        self.waiter4 = MemberWaitingList.objects.create(
            prename='Test',
            lastname='Waiter4',
            birth_date=now.date(),
            email='waiter4@example.com',
            gender=DIVERSE,
            last_wait_confirmation=old_confirmation,
            last_reminder=old_reminder,
            sent_reminders=settings.MAX_REMINDER_COUNT
        )

        # Create test excursions
        today = timezone.now().date()
        tomorrow = today + timezone.timedelta(days=1)

        self.excursion_today_not_sent = Freizeit.objects.create(
            name='Today Excursion 1',
            date=timezone.now() + timezone.timedelta(hours=4),
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
            crisis_intervention_list_sent=False,
            notification_crisis_intervention_list_sent=False
        )

        self.excursion_today_sent = Freizeit.objects.create(
            name='Today Excursion 2',
            date=timezone.now() + timezone.timedelta(hours=4),
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
            crisis_intervention_list_sent=True,
            notification_crisis_intervention_list_sent=True
        )

        self.excursion_tomorrow_not_sent = Freizeit.objects.create(
            name='Tomorrow Excursion 1',
            date=timezone.now() + timezone.timedelta(days=1, hours=4),
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
            crisis_intervention_list_sent=False,
            notification_crisis_intervention_list_sent=False
        )

        self.excursion_tomorrow_sent = Freizeit.objects.create(
            name='Tomorrow Excursion 2',
            date=timezone.now() + timezone.timedelta(days=1, hours=4),
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
            crisis_intervention_list_sent=True,
            notification_crisis_intervention_list_sent=True
        )

    @patch.object(MemberWaitingList, 'ask_for_wait_confirmation')
    def test_ask_for_waiting_confirmation(self, mock_ask):
        """Test ask_for_waiting_confirmation task calls correct waiters."""
        result = ask_for_waiting_confirmation()

        # Should call ask_for_wait_confirmation for waiter1 and waiter2 only
        self.assertEqual(result, 2)
        self.assertEqual(mock_ask.call_count, 2)

    @patch.object(Freizeit, 'send_crisis_intervention_list')
    def test_send_crisis_intervention_list(self, mock_send):
        """Test send_crisis_intervention_list task calls correct excursions."""
        result = send_crisis_intervention_list()

        # Should call send_crisis_intervention_list for today's excursions that haven't been sent
        self.assertEqual(result, 1)
        self.assertEqual(mock_send.call_count, 1)

    @patch.object(Freizeit, 'notify_leaders_crisis_intervention_list')
    def test_send_notification_crisis_intervention_list(self, mock_notify):
        """Test send_notification_crisis_intervention_list task calls correct excursions."""
        result = send_notification_crisis_intervention_list()

        # Should call notify_leaders_crisis_intervention_list for tomorrow's and todays excursions
        # that haven't been sent
        self.assertEqual(result, 2)
        self.assertEqual(mock_notify.call_count, 2)
