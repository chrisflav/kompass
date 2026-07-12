"""End-to-end tests for the mailer REST API.

Mirrors ``members/tests/api.py``: real OAuth2 bearer-token authentication and
the object/row-level permission model, exercised through the HTTP API. The
``send`` helper is mocked (as in ``mailer/tests/models.py``) so ``submit`` is
tested for its state/permission effects without touching a mail server.
"""

import datetime
import uuid
from unittest import mock

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from mailer.mailutils import SENT
from mailer.models import Attachment
from mailer.models import EmailAddress
from mailer.models import Message
from members.models import DIVERSE
from members.models import Group
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def internal_email(local_part):
    """Build an address whose domain passes ``Member.has_internal_email``."""
    domains = settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER
    domain = next((d for d in domains if d != "*"), "example.org")
    return "{}@{}".format(local_part, domain)


def make_member_user(username, email=None):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=username.title(),
        lastname="Test",
        birth_date=timezone.now().date(),
        email=email or settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    return user, member


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="mailer", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


class MailerApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        # Owner has an internal email so it may compose/submit; it becomes the
        # creator of its own messages (the ``is_creator`` predicate).
        self.owner_user, self.owner = make_member_user("owner", internal_email("owner"))
        self.owner_user = grant(self.owner_user, "add_global_message")
        self.other_user, self.other = make_member_user("other")
        self.admin_user, self.admin = make_member_user("admin")
        self.admin_user = grant(
            self.admin_user,
            "list_global_message",
            "view_global_message",
            "change_global_message",
            "delete_global_message",
            "view_emailaddress",
            "add_emailaddress",
            "change_emailaddress",
            "delete_emailaddress",
        )
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def make_message(self, creator):
        message = Message.objects.create(subject="Hello", content="Body", created_by=creator)
        message.to_members.add(creator)
        return message

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/mailer/messages").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get("/api/mailer/messages", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- email addresses (standard perms, no scoping) ---------------------

    def test_email_addresses_forbidden_without_permission(self):
        r = self.client.get("/api/mailer/email-addresses", **self.auth(self.other_user))
        self.assertEqual(r.status_code, 403)

    def test_email_addresses_listed_with_permission(self):
        address = EmailAddress.objects.create(name="vorstand")
        address.to_members.add(self.owner)
        r = self.client.get("/api/mailer/email-addresses", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)
        rows = {row["name"]: row for row in r.json()}
        self.assertIn("vorstand", rows)
        self.assertEqual(rows["vorstand"]["email"], address.email)

    def test_email_address_create_and_computed_fields(self):
        r = self.client.post(
            "/api/mailer/email-addresses",
            data={"name": "kasse", "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.admin_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["email"], "kasse@{}".format(settings.DOMAIN))
        self.assertIn(self.owner.email, body["forwards"])
        self.assertTrue(EmailAddress.objects.filter(name="kasse").exists())

    def test_email_address_create_requires_recipient(self):
        r = self.client.post(
            "/api/mailer/email-addresses",
            data={"name": "empty"},
            content_type="application/json",
            **self.auth(self.admin_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(EmailAddress.objects.filter(name="empty").exists())

    def test_email_address_create_forbidden_without_permission(self):
        r = self.client.post(
            "/api/mailer/email-addresses",
            data={"name": "nope", "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_email_address_update(self):
        address = EmailAddress.objects.create(name="old")
        address.to_members.add(self.owner)
        r = self.client.put(
            "/api/mailer/email-addresses/{}".format(address.pk),
            data={"name": "new", "internal_only": True, "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.admin_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        address.refresh_from_db()
        self.assertEqual(address.name, "new")
        self.assertTrue(address.internal_only)

    def test_email_address_delete(self):
        address = EmailAddress.objects.create(name="gone")
        address.to_members.add(self.owner)
        r = self.client.delete(
            "/api/mailer/email-addresses/{}".format(address.pk), **self.auth(self.admin_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(EmailAddress.objects.filter(pk=address.pk).exists())

    # --- message list scoping ---------------------------------------------

    def test_messages_scoped_to_creator(self):
        mine = self.make_message(self.owner)
        self.make_message(self.admin)

        r = self.client.get("/api/mailer/messages", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({m["id"] for m in r.json()}, {mine.pk})

    def test_messages_empty_for_unrelated_member(self):
        self.make_message(self.owner)
        r = self.client.get("/api/mailer/messages", **self.auth(self.other_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), [])

    def test_messages_all_with_global_permission(self):
        a = self.make_message(self.owner)
        b = self.make_message(self.admin)
        r = self.client.get("/api/mailer/messages", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({m["id"] for m in r.json()}, {a.pk, b.pk})

    # --- message retrieval -------------------------------------------------

    def test_retrieve_own_message_allowed(self):
        message = self.make_message(self.owner)
        r = self.client.get(
            "/api/mailer/messages/{}".format(message.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["subject"], "Hello")

    def test_retrieve_other_message_forbidden(self):
        message = self.make_message(self.owner)
        r = self.client.get(
            "/api/mailer/messages/{}".format(message.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_retrieve_other_message_allowed_with_global_permission(self):
        message = self.make_message(self.owner)
        r = self.client.get(
            "/api/mailer/messages/{}".format(message.pk), **self.auth(self.admin_user)
        )
        self.assertEqual(r.status_code, 200)

    # --- message create ----------------------------------------------------

    def test_create_message_sets_creator(self):
        r = self.client.post(
            "/api/mailer/messages",
            data={"subject": "Hi", "content": "there", "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        message = Message.objects.get(pk=r.json()["id"])
        self.assertEqual(message.created_by, self.owner)
        self.assertEqual(list(message.to_members.all()), [self.owner])

    def test_create_message_forbidden_without_permission(self):
        r = self.client.post(
            "/api/mailer/messages",
            data={"subject": "Hi", "content": "there", "to_members": [self.other.pk]},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_create_message_requires_recipient(self):
        r = self.client.post(
            "/api/mailer/messages",
            data={"subject": "Hi", "content": "there"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422)

    # --- message update ----------------------------------------------------

    def test_update_own_message_allowed(self):
        message = self.make_message(self.owner)
        r = self.client.put(
            "/api/mailer/messages/{}".format(message.pk),
            data={"subject": "Changed", "content": "x", "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        message.refresh_from_db()
        self.assertEqual(message.subject, "Changed")

    def test_update_other_message_forbidden(self):
        message = self.make_message(self.owner)
        r = self.client.put(
            "/api/mailer/messages/{}".format(message.pk),
            data={"subject": "Nope", "content": "x", "to_members": [self.other.pk]},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_update_sent_message_forbidden(self):
        message = self.make_message(self.owner)
        message.sent = True
        message.save()
        r = self.client.put(
            "/api/mailer/messages/{}".format(message.pk),
            data={"subject": "Nope", "content": "x", "to_members": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    # --- message delete ----------------------------------------------------

    def test_delete_own_message(self):
        message = self.make_message(self.owner)
        r = self.client.delete(
            "/api/mailer/messages/{}".format(message.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Message.objects.filter(pk=message.pk).exists())

    # --- submit action -----------------------------------------------------

    @mock.patch("mailer.models.send")
    def test_submit_sends_and_marks_sent(self, mock_send):
        mock_send.return_value = SENT
        message = self.make_message(self.owner)
        r = self.client.post(
            "/api/mailer/messages/{}/submit".format(message.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(mock_send.called)
        message.refresh_from_db()
        self.assertTrue(message.sent)

    @mock.patch("mailer.models.send")
    def test_submit_forbidden_without_internal_email(self, mock_send):
        mock_send.return_value = SENT
        # A creator whose email is not internal may not submit.
        external_user, external = make_member_user("external", "external@localhost")
        external_user = grant(external_user, "add_global_message")
        message = self.make_message(external)
        r = self.client.post(
            "/api/mailer/messages/{}/submit".format(message.pk), **self.auth(external_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(mock_send.called)
        message.refresh_from_db()
        self.assertFalse(message.sent)

    @mock.patch("mailer.models.send")
    def test_submit_other_message_forbidden(self, mock_send):
        mock_send.return_value = SENT
        message = self.make_message(self.owner)
        r = self.client.post(
            "/api/mailer/messages/{}/submit".format(message.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(mock_send.called)

    # --- attachments -------------------------------------------------------

    def test_attachment_upload_list_and_delete(self):
        message = self.make_message(self.owner)
        upload = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        r = self.client.post(
            "/api/mailer/messages/{}/attachments".format(message.pk),
            data={"f": upload},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        attachment_id = r.json()["id"]
        self.assertTrue(Attachment.objects.filter(pk=attachment_id).exists())

        r = self.client.get(
            "/api/mailer/messages/{}/attachments".format(message.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual({a["id"] for a in r.json()}, {attachment_id})

        r = self.client.delete(
            "/api/mailer/attachments/{}".format(attachment_id), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Attachment.objects.filter(pk=attachment_id).exists())

    def test_attachment_upload_forbidden_for_other(self):
        message = self.make_message(self.owner)
        upload = SimpleUploadedFile("note.txt", b"hello", content_type="text/plain")
        r = self.client.post(
            "/api/mailer/messages/{}/attachments".format(message.pk),
            data={"f": upload},
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_attachment_upload_rejects_oversized_file(self):
        message = self.make_message(self.owner)
        oversized = SimpleUploadedFile(
            "big.bin", b"x" * (10 * 1024 * 1024 + 1), content_type="application/octet-stream"
        )
        r = self.client.post(
            "/api/mailer/messages/{}/attachments".format(message.pk),
            data={"f": oversized},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(Attachment.objects.filter(msg=message).exists())
