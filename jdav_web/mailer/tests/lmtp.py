from unittest import mock

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import SimpleTestCase
from mailer.lmtp import _check_recipient
from mailer.lmtp import _deliver
from mailer.lmtp import _with_connection
from mailer.lmtp import RouterHandler
from mailer.models import DeliveryAttempt
from mailer.models import MailDeliveryState

from .utils import BasicMailerTestCase

RAW = b"""From: "Max Mustermann" <max@outside.example>
To: foobar@club.example
Subject: Hallo
Message-ID: <msg-1@outside.example>
Content-Type: text/plain; charset="utf-8"

Inhalt
"""


class CheckRecipientTestCase(BasicMailerTestCase):
    def test_known_list_address_is_accepted(self):
        self.assertTrue(
            _check_recipient("foobar@club.example", "max@outside.example").startswith("250")
        )

    def test_unknown_address_is_rejected_permanently(self):
        reply = _check_recipient("nobody@club.example", "max@outside.example")
        self.assertTrue(reply.startswith("550"))

    def test_personal_address_is_accepted(self):
        user = User.objects.create(username="fritz.wulter")
        self.fritz.user = user
        self.fritz.save()
        self.assertTrue(
            _check_recipient("fritz.wulter@club.example", "x@y.example").startswith("250")
        )

    def test_bounce_address_is_accepted(self):
        reply = _check_recipient("{}+tok@club.example".format(settings.MAIL_BOUNCE_LOCAL_PART), "")
        self.assertTrue(reply.startswith("250"))

    def test_bounce_address_without_token_is_rejected(self):
        reply = _check_recipient("{}@club.example".format(settings.MAIL_BOUNCE_LOCAL_PART), "")
        self.assertTrue(reply.startswith("550"))

    @override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=["inside.org"])
    def test_restricted_address_rejects_outside_sender(self):
        self.em.internal_only = True
        self.em.save()
        reply = _check_recipient("foobar@club.example", "stranger@elsewhere.com")
        self.assertTrue(reply.startswith("550"))

    def test_database_failure_defers_instead_of_losing_mail(self):
        """The old sieve silently kept the mail in an unread mailbox instead."""
        with mock.patch("mailer.lmtp._classify", side_effect=RuntimeError("db down")):
            reply = _check_recipient("foobar@club.example", "max@outside.example")
        self.assertTrue(reply.startswith("451"))


class DeliverTestCase(BasicMailerTestCase):
    def deliver(self, raw=RAW, address="foobar@club.example", sender="max@outside.example"):
        with mock.patch("mailer.delivery.send_raw") as send_raw:
            reply = _deliver(address, sender, raw)
        return reply, send_raw

    def test_successful_forward(self):
        reply, send_raw = self.deliver()
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(send_raw.call_count, 2)

    def test_send_failure_defers_for_retry(self):
        with mock.patch("mailer.delivery.send_raw", side_effect=OSError("down")):
            reply = _deliver("foobar@club.example", "max@outside.example", RAW)
        self.assertTrue(reply.startswith("451"))

    def test_loop_is_dropped(self):
        raw = RAW.replace(
            b"Subject:", "X-Loop: foobar@{}\nSubject:".format(settings.DOMAIN).encode()
        )
        reply, send_raw = self.deliver(raw)
        self.assertTrue(reply.startswith("554"))
        self.assertEqual(send_raw.call_count, 0)

    def test_message_without_message_id_is_still_idempotent(self):
        raw = RAW.replace(b"Message-ID: <msg-1@outside.example>\n", b"")
        reply, _send_raw = self.deliver(raw)
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(DeliveryAttempt.objects.count(), 2)

    def test_unknown_recipient_at_data_time(self):
        reply, _send_raw = self.deliver(address="nobody@club.example")
        self.assertTrue(reply.startswith("550"))

    def test_bounce_is_recorded_not_forwarded(self):
        attempt = DeliveryAttempt.objects.create(
            token="tok",
            message_id="<m@outside.example>",
            address="foobar@club.example",
            recipient="paul@foo.com",
        )
        report = b"""From: MAILER-DAEMON@club.example
To: bounce+tok@club.example
Subject: failed
Content-Type: multipart/report; report-type=delivery-status; boundary="B"

--B
Content-Type: message/delivery-status

Final-Recipient: rfc822; paul@foo.com
Action: failed
Status: 5.1.1

--B--
"""
        reply, send_raw = self.deliver(
            report, address="{}+tok@club.example".format(settings.MAIL_BOUNCE_LOCAL_PART), sender=""
        )
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(send_raw.call_count, 0)
        attempt.refresh_from_db()
        self.assertIsNotNone(attempt.bounced_at)
        self.assertEqual(MailDeliveryState.objects.get(email="paul@foo.com").hard_bounces, 1)

    def test_personal_route_is_forwarded_the_same_way(self):
        user = User.objects.create(username="fritz.wulter")
        self.fritz.user = user
        self.fritz.save()

        reply, send_raw = self.deliver(address="fritz.wulter@club.example")
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(send_raw.call_count, 1)
        self.assertEqual(send_raw.call_args.args[1], "fritz@foo.com")
        payload = send_raw.call_args.args[2].decode()
        self.assertIn("fritz.wulter@{}".format(settings.DOMAIN), payload)


class WithConnectionTestCase(SimpleTestCase):
    """The wrapper owns connection lifecycle so the routing code does not."""

    def test_returns_the_result(self):
        with mock.patch("mailer.lmtp.close_old_connections"):
            self.assertEqual(_with_connection(lambda: 42), 42)

    def test_refreshes_the_connection_around_the_work(self):
        with mock.patch("mailer.lmtp.close_old_connections") as close:
            _with_connection(lambda: None)
        self.assertEqual(close.call_count, 2)

    def test_refreshes_even_when_the_work_raises(self):
        with mock.patch("mailer.lmtp.close_old_connections") as close:
            with self.assertRaises(ValueError):
                _with_connection(mock.Mock(side_effect=ValueError("boom")))
        self.assertEqual(close.call_count, 2)


class Envelope:
    def __init__(self, mail_from="max@outside.example", content=RAW):
        self.mail_from = mail_from
        self.rcpt_tos = []
        self.content = content
        self.original_content = content


class HandlerTestCase(BasicMailerTestCase):
    """The aiosmtpd entry points, exercised the way the server calls them."""

    def setUp(self):
        super().setUp()
        self.handler = RouterHandler()

    def rcpt(self, address, envelope=None):
        envelope = envelope or Envelope()
        with mock.patch("mailer.lmtp.close_old_connections"):
            reply = async_to_sync(self.handler.handle_RCPT)(None, None, envelope, address, [])
        return reply, envelope

    def data(self, envelope):
        with mock.patch("mailer.lmtp.close_old_connections"):
            with mock.patch("mailer.delivery.send_raw") as send_raw:
                reply = async_to_sync(self.handler.handle_DATA)(None, None, envelope)
        return reply, send_raw

    def test_accepted_recipient_is_recorded_on_the_envelope(self):
        reply, envelope = self.rcpt("foobar@club.example")
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(envelope.rcpt_tos, ["foobar@club.example"])

    def test_rejected_recipient_is_not_recorded(self):
        reply, envelope = self.rcpt("nobody@club.example")
        self.assertTrue(reply.startswith("550"))
        self.assertEqual(envelope.rcpt_tos, [])

    def test_data_forwards_accepted_recipients(self):
        _reply, envelope = self.rcpt("foobar@club.example")
        reply, send_raw = self.data(envelope)
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(send_raw.call_count, 2)

    def test_data_without_recipients(self):
        reply, _send_raw = self.data(Envelope())
        self.assertTrue(reply.startswith("250"))

    def test_data_reports_the_failing_recipient(self):
        _reply, envelope = self.rcpt("foobar@club.example")
        with mock.patch("mailer.lmtp.close_old_connections"):
            with mock.patch("mailer.delivery.send_raw", side_effect=OSError("down")):
                reply = async_to_sync(self.handler.handle_DATA)(None, None, envelope)
        self.assertTrue(reply.startswith("451"))

    def test_unexpected_error_defers_rather_than_losing_the_mail(self):
        _reply, envelope = self.rcpt("foobar@club.example")
        with mock.patch("mailer.lmtp.close_old_connections"):
            with mock.patch("mailer.lmtp._deliver", side_effect=RuntimeError("boom")):
                reply = async_to_sync(self.handler.handle_DATA)(None, None, envelope)
        self.assertTrue(reply.startswith("451"))

    def test_falls_back_to_decoded_content(self):
        envelope = Envelope()
        envelope.original_content = None
        _reply, envelope = self.rcpt("foobar@club.example", envelope)
        reply, send_raw = self.data(envelope)
        self.assertTrue(reply.startswith("250"))
        self.assertEqual(send_raw.call_count, 2)
