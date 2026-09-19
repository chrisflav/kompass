from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings
from django.test import TestCase
from mailer.mailutils import flow_link
from mailer.mailutils import NOT_SENT
from mailer.mailutils import send
from mailer.mailutils import SENT


class MailUtilsTest(TestCase):
    def setUp(self):
        self.subject = "Test Subject"
        self.content = "Test Content"
        self.sender = "sender@example.com"
        self.recipient = "recipient@example.com"

    def test_send_with_reply_to(self):
        with patch("mailer.mailutils.mail.get_connection") as mock_connection:
            mock_conn = Mock()
            mock_connection.return_value = mock_conn
            result = send(
                self.subject,
                self.content,
                self.sender,
                self.recipient,
                reply_to=["reply@example.com"],
            )
            self.assertEqual(result, SENT)

    def test_send_with_message_id(self):
        with patch("mailer.mailutils.mail.get_connection") as mock_connection:
            mock_conn = Mock()
            mock_connection.return_value = mock_conn
            result = send(
                self.subject,
                self.content,
                self.sender,
                self.recipient,
                message_id="<test@example.com>",
            )
            self.assertEqual(result, SENT)

    def test_send_exception_handling(self):
        with patch("mailer.mailutils.mail.get_connection") as mock_connection:
            mock_conn = Mock()
            mock_conn.send_messages.side_effect = Exception("Test exception")
            mock_connection.return_value = mock_conn
            with patch("builtins.print"):
                result = send(self.subject, self.content, self.sender, self.recipient)
            self.assertEqual(result, NOT_SENT)


class FlowLinkTest(TestCase):
    """The secret-key links in outgoing mail, in both deployment shapes."""

    def test_without_a_frontend_points_at_the_django_view(self):
        with override_settings(FRONTEND_BASE_URL=""):
            link = flow_link("/members/echo", "KEY123")
        self.assertIn("/members/echo?key=KEY123", link)

    def test_with_a_frontend_points_at_its_own_route(self):
        with override_settings(FRONTEND_BASE_URL="https://neu.example.org"):
            link = flow_link("/members/echo", "KEY123")
        self.assertEqual(link, "https://neu.example.org/echo?key=KEY123")

    def test_a_trailing_slash_on_the_frontend_url_is_not_doubled(self):
        with override_settings(FRONTEND_BASE_URL="https://neu.example.org/"):
            link = flow_link("/members/echo", "KEY123")
        self.assertEqual(link, "https://neu.example.org/echo?key=KEY123")

    def test_the_language_prefix_reverse_adds_is_stripped_for_the_lookup(self):
        # `reverse()` returns `/de/members/echo` for a view inside
        # i18n_patterns; the SPA route table is keyed without that prefix, and
        # without stripping it the link would fall through to the legacy path.
        with override_settings(FRONTEND_BASE_URL="https://neu.example.org"):
            link = flow_link("/de/members/echo", "KEY123")
        self.assertEqual(link, "https://neu.example.org/echo?key=KEY123")

    def test_an_unmapped_path_is_carried_over_as_it_is(self):
        with override_settings(FRONTEND_BASE_URL="https://neu.example.org"):
            link = flow_link("/members/unbekannt", "KEY123")
        self.assertEqual(link, "https://neu.example.org/members/unbekannt?key=KEY123")
