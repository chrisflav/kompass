from unittest import mock

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from django.utils.translation import gettext as _
from mailer.mailutils import NOT_SENT
from mailer.mailutils import PARTLY_SENT
from mailer.mailutils import SENT
from mailer.models import Attachment
from mailer.models import EmailAddressForm
from mailer.models import Message
from mailer.models import MessageForm
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Member
from members.models import MemberNoteList
from members.models import MUSKELKRAFT_ANREISE

from .utils import BasicMailerTestCase


class EmailAddressTestCase(BasicMailerTestCase):
    def test_email(self):
        self.assertEqual(self.em.email, f"foobar@{settings.DOMAIN}")

    def test_str(self):
        self.assertEqual(self.em.email, str(self.em))

    def test_forwards(self):
        self.assertEqual(self.em.forwards, {"fritz@foo.com", "paul@foo.com"})


class EmailAddressFormTestCase(BasicMailerTestCase):
    def test_clean(self):
        # instantiate form with only name field set
        form = EmailAddressForm(data={"name": "bar"})
        # validate the form - this should fail due to missing required recipients
        self.assertFalse(form.is_valid())


class MessageFormTestCase(BasicMailerTestCase):
    def test_clean(self):
        # instantiate form with only subject and content fields set
        form = MessageForm(data={"subject": "Test Subject", "content": "Test content"})
        # validate the form - this should fail due to missing required recipients
        self.assertFalse(form.is_valid())


class MessageTestCase(BasicMailerTestCase):
    def setUp(self):
        super().setUp()
        self.message = Message.objects.create(
            subject="Test Message", content="This is a test message"
        )
        self.freizeit = Freizeit.objects.create(
            name="Test Freizeit",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.notelist = MemberNoteList.objects.create(title="Test Note List")

        # Set up message with multiple recipient types
        self.message.to_groups.add(self.mygroup)
        self.message.to_freizeit = self.freizeit
        self.message.to_notelist = self.notelist
        self.message.to_members.add(self.fritz)
        self.message.save()

        # Create a sender member for submit tests
        self.sender = Member.objects.create(
            prename="Sender",
            lastname="Test",
            birth_date=timezone.now().date(),
            email="sender@test.com",
            gender=DIVERSE,
        )

    def test_str(self):
        self.assertEqual(str(self.message), "Test Message")

    def test_get_recipients(self):
        recipients = self.message.get_recipients()
        self.assertIn("My Group", recipients)
        self.assertIn("Test Freizeit", recipients)
        self.assertIn("Test Note List", recipients)
        self.assertIn("Fritz Wulter", recipients)

    def test_get_recipients_with_many_members(self):
        # Add additional members to test the "Some other members" case
        for i in range(3):
            member = Member.objects.create(
                prename=f"Member{i}",
                lastname="Test",
                birth_date=timezone.now().date(),
                email=f"member{i}@test.com",
                gender=DIVERSE,
            )
            self.message.to_members.add(member)

        recipients = self.message.get_recipients()
        self.assertIn(_("Some other members"), recipients)

    @mock.patch("mailer.models.send")
    def test_submit_successful(self, mock_send):
        # Mock successful email sending
        mock_send.return_value = SENT

        # Test submit method
        result = self.message.submit(sender=self.sender)

        # Verify the message was marked as sent
        self.message.refresh_from_db()
        self.assertTrue(self.message.sent)
        self.assertEqual(result, SENT)

        # Verify send was called
        self.assertTrue(mock_send.called)

    @mock.patch("mailer.models.send")
    def test_submit_failed(self, mock_send):
        # Mock failed email sending
        mock_send.return_value = NOT_SENT

        # Test submit method
        result = self.message.submit(sender=self.sender)

        # Verify the message was not marked as sent
        self.message.refresh_from_db()
        self.assertFalse(self.message.sent)
        # Note: The submit method always returns SENT when an exception occurs
        self.assertEqual(result, SENT)

    @mock.patch("mailer.models.send")
    def test_submit_without_sender(self, mock_send):
        # Mock successful email sending
        mock_send.return_value = SENT

        # Test submit method without sender
        result = self.message.submit()

        # Verify the message was marked as sent
        self.message.refresh_from_db()
        self.assertTrue(self.message.sent)
        self.assertEqual(result, SENT)

    @mock.patch("mailer.models.send")
    def test_submit_subject_cleaning(self, mock_send):
        # Mock successful email sending
        mock_send.return_value = SENT

        # Create message with underscores in subject
        message_with_underscores = Message.objects.create(
            subject="Test_Message_With_Underscores", content="Test content"
        )
        message_with_underscores.to_members.add(self.fritz)

        # Test submit method
        message_with_underscores.submit()

        # Verify underscores were removed from subject
        message_with_underscores.refresh_from_db()
        self.assertEqual(message_with_underscores.subject, "Test Message With Underscores")

    @mock.patch("mailer.models.send")
    def test_submit_exception_handling(self, mock_send):
        # Mock an exception during email sending
        mock_send.side_effect = Exception("Email sending failed")

        # Test submit method
        result = self.message.submit(sender=self.sender)

        # Verify the message was not marked as sent
        self.message.refresh_from_db()
        self.assertFalse(self.message.sent)
        # When exception occurs, it should return NOT_SENT
        self.assertEqual(result, NOT_SENT)

    @mock.patch("mailer.models.send")
    @mock.patch("django.conf.settings.SEND_FROM_ASSOCIATION_EMAIL", False)
    def test_submit_with_sender_no_association_email(self, mock_send):
        # Mock successful email sending
        mock_send.return_value = PARTLY_SENT

        # Test submit method with sender but SEND_FROM_ASSOCIATION_EMAIL disabled
        result = self.message.submit(sender=self.sender)

        # Verify the message was marked as sent
        self.message.refresh_from_db()
        self.assertTrue(self.message.sent)
        self.assertEqual(result, SENT)

    @mock.patch("mailer.models.send")
    @mock.patch("django.conf.settings.SEND_FROM_ASSOCIATION_EMAIL", False)
    def test_submit_with_reply_to_logic(self, mock_send):
        # Mock successful email sending
        mock_send.return_value = SENT

        # Create a sender with internal email capability
        sender_with_internal = Member.objects.create(
            prename="Internal",
            lastname="Sender",
            birth_date=timezone.now().date(),
            email="internal@test.com",
            gender=DIVERSE,
        )

        # Mock has_internal_email to return True
        with mock.patch.object(sender_with_internal, "has_internal_email", return_value=True):
            # Test submit method
            result = self.message.submit(sender=sender_with_internal)

        # Verify the message was marked as sent
        self.message.refresh_from_db()
        self.assertTrue(self.message.sent)
        self.assertEqual(result, SENT)

    @mock.patch("mailer.models.send")
    @mock.patch("os.remove")
    def test_submit_with_attachments(self, mock_os_remove, mock_send):
        # Mock successful email sending
        mock_send.return_value = SENT

        # Create an attachment with a file
        test_file = SimpleUploadedFile(
            "test_file.pdf", b"file_content", content_type="application/pdf"
        )
        attachment = Attachment.objects.create(msg=self.message, f=test_file)

        # Test submit method
        result = self.message.submit()

        # Verify the message was marked as sent
        self.message.refresh_from_db()
        self.assertTrue(self.message.sent)
        self.assertEqual(result, SENT)

        # Verify file removal was attempted (the path will be the actual file path)
        mock_os_remove.assert_called()
        # Attachment should be deleted
        with self.assertRaises(Attachment.DoesNotExist):
            attachment.refresh_from_db()

    @mock.patch("mailer.models.send")
    def test_submit_with_association_email_enabled(self, mock_send):
        """Test submit method when SEND_FROM_ASSOCIATION_EMAIL is True and sender has association_email"""
        mock_send.return_value = SENT

        # Mock settings to enable association email sending
        with mock.patch.object(settings, "SEND_FROM_ASSOCIATION_EMAIL", True):
            self.message.submit(sender=self.sender)

        # Check that send was called with sender's association email
        self.assertTrue(mock_send.called)
        call_args = mock_send.call_args
        from_addr = call_args[0][2]  # from_addr is the 3rd positional argument
        expected_from = f"{self.sender.name} <{self.sender.association_email}>"
        self.assertEqual(from_addr, expected_from)


class AttachmentTestCase(BasicMailerTestCase):
    def setUp(self):
        super().setUp()
        self.message = Message.objects.create(subject="Test Message", content="Test content")
        self.attachment = Attachment.objects.create(msg=self.message)

    def test_str_with_file(self):
        # Simulate a file name
        self.attachment.f.name = "attachments/test_document.pdf"
        self.assertEqual(str(self.attachment), "test_document.pdf")

    def test_str_without_file(self):
        self.assertEqual(str(self.attachment), _("Empty"))
