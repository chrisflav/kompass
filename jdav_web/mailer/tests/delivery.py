from unittest import mock

from django.conf import settings
from mailer.delivery import forward
from mailer.delivery import send_raw
from mailer.models import DeliveryAttempt
from mailer.models import MailDeliveryState
from mailer.munge import parse
from mailer.routing import resolve

from .utils import BasicMailerTestCase

RAW = b"""From: "Max Mustermann" <max@outside.example>
To: foobar@club.example
Subject: Hallo
Message-ID: <msg-1@outside.example>
Content-Type: text/plain; charset="utf-8"

Inhalt
"""


class ForwardTestCase(BasicMailerTestCase):
    def forward(self, raw=RAW, message_id="<msg-1@outside.example>"):
        with mock.patch("mailer.delivery.send_raw") as send_raw:
            deferred = forward(parse(raw), resolve("foobar"), "max@outside.example", message_id)
        return deferred, send_raw

    def test_sends_one_copy_per_target(self):
        deferred, send_raw = self.forward()
        self.assertEqual(deferred, [])
        self.assertEqual(send_raw.call_count, 2)
        self.assertEqual(
            {call.args[1] for call in send_raw.call_args_list},
            {"fritz@foo.com", "paul@foo.com"},
        )

    def test_each_copy_gets_its_own_envelope_sender(self):
        """Bounces are only attributable if the senders differ per recipient."""
        _deferred, send_raw = self.forward()
        senders = {call.args[0] for call in send_raw.call_args_list}
        self.assertEqual(len(senders), 2)
        for sender in senders:
            self.assertTrue(sender.startswith(settings.MAIL_BOUNCE_LOCAL_PART + "+"))

    def test_records_an_attempt_per_recipient(self):
        self.forward()
        self.assertEqual(DeliveryAttempt.objects.count(), 2)
        self.assertTrue(all(a.sent_at is not None for a in DeliveryAttempt.objects.all()))

    def test_retry_does_not_duplicate_delivered_copies(self):
        """Postfix replays the whole message when we defer it."""
        self.forward()
        _deferred, send_raw = self.forward()
        self.assertEqual(send_raw.call_count, 0)
        self.assertEqual(DeliveryAttempt.objects.count(), 2)

    def test_retry_resends_only_the_failed_copy(self):
        def fail_for_paul(envelope_from, recipient, payload):
            if recipient == "paul@foo.com":
                raise OSError("connection refused")

        with mock.patch("mailer.delivery.send_raw", side_effect=fail_for_paul):
            deferred = forward(
                parse(RAW), resolve("foobar"), "max@outside.example", "<msg-1@outside.example>"
            )
        self.assertEqual(deferred, ["paul@foo.com"])

        _deferred, send_raw = self.forward()
        self.assertEqual(send_raw.call_count, 1)
        self.assertEqual(send_raw.call_args.args[1], "paul@foo.com")

    def test_suspended_addresses_are_skipped(self):
        MailDeliveryState.objects.create(email="paul@foo.com", suspended=True)
        deferred, send_raw = self.forward()
        self.assertEqual(deferred, [])
        self.assertEqual(send_raw.call_count, 1)
        self.assertEqual(send_raw.call_args.args[1], "fritz@foo.com")

    def test_delivery_failure_is_reported_for_retry(self):
        with mock.patch("mailer.delivery.send_raw", side_effect=OSError("down")):
            deferred = forward(
                parse(RAW), resolve("foobar"), "max@outside.example", "<msg-1@outside.example>"
            )
        self.assertEqual(sorted(deferred), ["fritz@foo.com", "paul@foo.com"])

    def test_forwarded_copy_is_munged(self):
        _deferred, send_raw = self.forward()
        payload = send_raw.call_args.args[2].decode()
        self.assertIn("foobar@{}".format(settings.DOMAIN), payload)
        self.assertIn("Reply-To:", payload)

    def test_distinct_messages_get_distinct_attempts(self):
        self.forward()
        self.forward(message_id="<msg-2@outside.example>")
        self.assertEqual(DeliveryAttempt.objects.count(), 4)


class SendRawTestCase(BasicMailerTestCase):
    def test_hands_the_message_to_the_smtp_backend(self):
        with mock.patch("mailer.delivery.get_connection") as get_connection:
            connection = get_connection.return_value
            send_raw("bounce+tok@club.example", "paul@foo.com", b"raw")
        connection.open.assert_called_once()
        connection.connection.sendmail.assert_called_once_with(
            "bounce+tok@club.example", ["paul@foo.com"], b"raw"
        )
        connection.close.assert_called_once()

    def test_bypasses_the_celery_backend(self):
        """Forwarded copies carry their own envelope sender, which the celery
        backend cannot express, so the SMTP backend is requested explicitly."""
        with mock.patch("mailer.delivery.get_connection") as get_connection:
            send_raw("bounce+tok@club.example", "paul@foo.com", b"raw")
        self.assertEqual(
            get_connection.call_args.kwargs["backend"],
            "django.core.mail.backends.smtp.EmailBackend",
        )

    def test_connection_is_closed_when_sending_fails(self):
        with mock.patch("mailer.delivery.get_connection") as get_connection:
            connection = get_connection.return_value
            connection.connection.sendmail.side_effect = OSError("down")
            with self.assertRaises(OSError):
                send_raw("bounce+tok@club.example", "paul@foo.com", b"raw")
        connection.close.assert_called_once()
