from django.test import TestCase, override_settings
from unittest.mock import patch, Mock
from mailer.mailutils import send, SENT, NOT_SENT


class MailUtilsTest(TestCase):
    def setUp(self):
        self.subject = "Test Subject"
        self.content = "Test Content"
        self.sender = "sender@example.com"
        self.recipient = "recipient@example.com"

    def test_send_with_reply_to(self):
        with patch('mailer.mailutils.mail.get_connection') as mock_connection:
            mock_conn = Mock()
            mock_connection.return_value = mock_conn
            result = send(self.subject, self.content, self.sender, self.recipient, reply_to=["reply@example.com"])
            self.assertEqual(result, SENT)

    def test_send_with_message_id(self):
        with patch('mailer.mailutils.mail.get_connection') as mock_connection:
            mock_conn = Mock()
            mock_connection.return_value = mock_conn
            result = send(self.subject, self.content, self.sender, self.recipient, message_id="<test@example.com>")
            self.assertEqual(result, SENT)

    def test_send_exception_handling(self):
        with patch('mailer.mailutils.mail.get_connection') as mock_connection:
            mock_conn = Mock()
            mock_conn.send_messages.side_effect = Exception("Test exception")
            mock_connection.return_value = mock_conn
            with patch('builtins.print'):
                result = send(self.subject, self.content, self.sender, self.recipient)
            self.assertEqual(result, NOT_SENT)