from unittest.mock import Mock
from unittest.mock import patch

from django.test import override_settings
from django.test import TestCase
from mailer.mailutils import app_link
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


@override_settings(PROTOCOL="https", BASE_URL="kompass.example.org")
class LinkBuildingTest(TestCase):
    """The absolute links that outgoing mail points at.

    ``app_link`` replaced the ``reverse("admin:…")`` deep links the notify mails
    used before the admin was retired, so its output has to land on a real SPA
    route.
    """

    @override_settings(FRONTEND_BASE_URL="https://spa.example.org")
    def test_app_link_uses_the_frontend_when_configured(self):
        self.assertEqual(
            app_link("/excursions/12"), "https://spa.example.org/kompass/excursions/12"
        )

    @override_settings(FRONTEND_BASE_URL="https://spa.example.org/")
    def test_app_link_does_not_double_the_separator(self):
        self.assertEqual(
            app_link("/registrations/7"), "https://spa.example.org/kompass/registrations/7"
        )

    @override_settings(FRONTEND_BASE_URL="")
    def test_app_link_falls_back_to_this_host(self):
        self.assertEqual(
            app_link("/excursions/12"), "https://kompass.example.org/kompass/excursions/12"
        )

    @override_settings(FRONTEND_BASE_URL="https://spa.example.org")
    def test_flow_link_maps_a_legacy_path_to_its_spa_route(self):
        self.assertEqual(flow_link("/members/echo", "abc"), "https://spa.example.org/echo?key=abc")

    @override_settings(FRONTEND_BASE_URL="")
    def test_flow_link_keeps_the_django_view_without_a_frontend(self):
        self.assertEqual(
            flow_link("/members/echo", "abc"), "https://kompass.example.org/members/echo?key=abc"
        )
