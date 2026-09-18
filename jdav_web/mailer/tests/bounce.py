from django.test import override_settings
from mailer.bounce import handle
from mailer.bounce import parse_status
from mailer.models import DeliveryAttempt
from mailer.models import MailDeliveryState
from mailer.munge import parse

from .utils import BasicMailerTestCase


def dsn(action="failed", status="5.1.1"):
    return """From: MAILER-DAEMON@club.example
To: bounce+tok@club.example
Subject: Undelivered Mail Returned to Sender
Content-Type: multipart/report; report-type=delivery-status; boundary="B"

--B
Content-Type: text/plain

Delivery failed.

--B
Content-Type: message/delivery-status

Reporting-MTA: dns; club.example

Final-Recipient: rfc822; paul@foo.com
Action: {action}
Status: {status}

--B--
""".format(action=action, status=status).encode()


class ParseStatusTestCase(BasicMailerTestCase):
    def test_permanent_failure(self):
        permanent, status, _detail = parse_status(parse(dsn()))
        self.assertTrue(permanent)
        self.assertEqual(status, "5.1.1")

    def test_transient_failure(self):
        permanent, status, _detail = parse_status(parse(dsn(action="delayed", status="4.4.1")))
        self.assertFalse(permanent)
        self.assertEqual(status, "4.4.1")

    def test_delivered_report_is_not_permanent(self):
        permanent, _status, _detail = parse_status(parse(dsn(action="delivered", status="2.0.0")))
        self.assertFalse(permanent)

    def test_unparseable_report_is_treated_as_transient(self):
        """Suspending on a report we did not understand is the worse error."""
        permanent, _status, _detail = parse_status(parse(b"Subject: nonsense\n\nbody\n"))
        self.assertFalse(permanent)


class HandleTestCase(BasicMailerTestCase):
    def setUp(self):
        super().setUp()
        self.attempt = DeliveryAttempt.objects.create(
            token="tok",
            message_id="<m@outside.example>",
            address="foobar@club.example",
            recipient="paul@foo.com",
        )

    def test_unknown_token_is_ignored(self):
        self.assertFalse(handle("nosuchtoken", parse(dsn())))

    def test_marks_the_attempt(self):
        self.assertTrue(handle("tok", parse(dsn())))
        self.attempt.refresh_from_db()
        self.assertIsNotNone(self.attempt.bounced_at)
        self.assertEqual(self.attempt.bounce_status, "5.1.1")

    def test_creates_delivery_state_for_the_recipient(self):
        handle("tok", parse(dsn()))
        state = MailDeliveryState.objects.get(email="paul@foo.com")
        self.assertEqual(state.hard_bounces, 1)
        self.assertFalse(state.suspended)

    def test_transient_bounce_counts_separately(self):
        handle("tok", parse(dsn(action="delayed", status="4.4.1")))
        state = MailDeliveryState.objects.get(email="paul@foo.com")
        self.assertEqual(state.soft_bounces, 1)
        self.assertEqual(state.hard_bounces, 0)

    @override_settings(MAIL_HARD_BOUNCE_LIMIT=2)
    def test_address_is_suspended_once_the_limit_is_reached(self):
        state = MailDeliveryState.objects.create(email="paul@foo.com", hard_bounces=1)
        handle("tok", parse(dsn()))
        state.refresh_from_db()
        self.assertTrue(state.suspended)

    @override_settings(MAIL_HARD_BOUNCE_LIMIT=2)
    def test_transient_bounces_never_suspend(self):
        MailDeliveryState.objects.create(email="paul@foo.com", soft_bounces=99)
        handle("tok", parse(dsn(action="delayed", status="4.4.1")))
        self.assertFalse(MailDeliveryState.objects.get(email="paul@foo.com").suspended)


class BounceAddressTestCase(BasicMailerTestCase):
    def test_token_round_trips_through_the_envelope(self):
        from mailer.routing import split_address
        from mailer.routing import strip_detail

        attempt = DeliveryAttempt.objects.create(
            token="abc123",
            message_id="<m@x.example>",
            address="foobar@club.example",
            recipient="paul@foo.com",
        )
        local, _domain = split_address(attempt.bounce_address())
        self.assertEqual(strip_detail(local), ("bounce", "abc123"))


class ModelStrTestCase(BasicMailerTestCase):
    def test_delivery_state_str(self):
        state = MailDeliveryState.objects.create(email="paul@foo.com")
        self.assertEqual(str(state), "paul@foo.com")

    def test_delivery_attempt_str(self):
        attempt = DeliveryAttempt.objects.create(
            token="t1",
            message_id="<m@x.example>",
            address="foobar@club.example",
            recipient="paul@foo.com",
        )
        self.assertEqual(str(attempt), "foobar@club.example -> paul@foo.com")
