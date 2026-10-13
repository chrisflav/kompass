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
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import SENT
from mailer.models import Attachment
from mailer.models import EmailAddress
from mailer.models import Message
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Member
from members.models import MemberNoteList
from members.models import MUSKELKRAFT_ANREISE
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

    def make_recipient_messages(self, count, creator):
        """Messages touching every relation ``get_recipients`` reads.

        Every message names a group, an excursion and a note list, and they
        alternate between few members (listed by name) and many members
        (summarised), so both branches of the recipient summary are serialized.
        """
        freizeit = Freizeit.objects.create(
            name="Hüttentour",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        notelist = MemberNoteList.objects.create(title="Kletterliste")
        for i in range(count):
            message = Message.objects.create(
                subject="Hello {}".format(i),
                content="Body",
                created_by=creator,
                to_freizeit=freizeit,
                to_notelist=notelist,
            )
            message.to_groups.add(self.group)
            if i % 2:
                message.to_members.add(self.owner, self.other, self.admin)
            else:
                message.to_members.add(self.owner)

    def list_messages_counting_queries(self, headers, path):
        with CaptureQueriesContext(connection) as queries:
            r = self.client.get(path, **headers)
        self.assertEqual(r.status_code, 200)
        return r.json(), len(queries)

    def assert_list_queries_do_not_grow(self, user, creator, path="/api/mailer/messages"):
        headers = self.auth(user)
        self.make_recipient_messages(2, creator)
        few, few_queries = self.list_messages_counting_queries(headers, path)
        self.make_recipient_messages(4, creator)
        many, many_queries = self.list_messages_counting_queries(headers, path)

        self.assertEqual(len(few), 2)
        self.assertEqual(len(many), 6)
        self.assertEqual(many_queries, few_queries)

    def test_message_list_queries_do_not_grow_with_messages(self):
        # global permissions: every message is listed
        self.assert_list_queries_do_not_grow(self.admin_user, self.admin)

    def test_creator_message_list_queries_do_not_grow_with_messages(self):
        # no global permissions: the list is scoped to the creator
        self.assert_list_queries_do_not_grow(self.owner_user, self.owner)

    def test_recent_message_list_queries_do_not_grow_with_messages(self):
        since = timezone.localdate() - datetime.timedelta(days=365)
        path = "/api/mailer/messages?since={}".format(since.isoformat())
        self.assert_list_queries_do_not_grow(self.admin_user, self.admin, path)

    # --- message list window ----------------------------------------------

    def make_dated_message(self, subject, created_at, sent=True):
        message = Message.objects.create(
            subject=subject, content="Body", created_by=self.admin, sent=sent
        )
        message.to_members.add(self.owner)
        # ``created_at`` is set on creation, so date the message afterwards
        Message.objects.filter(pk=message.pk).update(created_at=created_at)
        return message

    def list_subjects(self, user, query=""):
        r = self.client.get("/api/mailer/messages" + query, **self.auth(user))
        self.assertEqual(r.status_code, 200, r.content)
        return {row["subject"] for row in r.json()}

    def test_message_list_since_hides_older_sent_messages(self):
        now = timezone.now()
        self.make_dated_message("old", now - datetime.timedelta(days=500))
        self.make_dated_message("recent", now - datetime.timedelta(days=30))
        self.make_dated_message("old draft", now - datetime.timedelta(days=500), sent=False)
        since = (timezone.localdate() - datetime.timedelta(days=365)).isoformat()

        # unsent drafts are listed however old they are
        self.assertEqual(
            self.list_subjects(self.admin_user, "?since=" + since), {"recent", "old draft"}
        )
        # without ``since``, every message is listed
        self.assertEqual(self.list_subjects(self.admin_user), {"old", "recent", "old draft"})

    def test_message_list_since_starts_at_local_midnight(self):
        since = datetime.date(2025, 3, 1)
        start = timezone.make_aware(datetime.datetime(2025, 3, 1))
        self.make_dated_message("at midnight", start)
        self.make_dated_message("just before", start - datetime.timedelta(microseconds=1))
        # the day starts at midnight in the local time zone, not in UTC
        self.assertEqual(
            self.list_subjects(self.admin_user, "?since=" + since.isoformat()), {"at midnight"}
        )

    def test_message_list_since_keeps_creator_scope(self):
        now = timezone.now()
        mine = self.make_dated_message("mine", now)
        Message.objects.filter(pk=mine.pk).update(created_by=self.owner)
        self.make_dated_message("theirs", now)
        since = timezone.localdate().isoformat()
        self.assertEqual(self.list_subjects(self.owner_user, "?since=" + since), {"mine"})

    def test_message_list_rejects_invalid_since(self):
        r = self.client.get("/api/mailer/messages?since=yesterday", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 422)

    def test_message_created_at_is_set_on_creation(self):
        before = timezone.now()
        message = self.make_message(self.owner)
        self.assertGreaterEqual(message.created_at, before)
        self.assertLessEqual(message.created_at, timezone.now())

    def test_message_list_recipients(self):
        freizeit = Freizeit.objects.create(
            name="Hüttentour",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        notelist = MemberNoteList.objects.create(title="Kletterliste")
        unconfirmed = Member.objects.create(
            prename="Unconfirmed",
            lastname="Test",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            confirmed=False,
        )
        members_by_subject = {
            "none": [],
            "two": [self.owner, self.other],
            # unconfirmed members are not recipients, so this still lists names
            "two and unconfirmed": [self.owner, self.other, unconfirmed],
            "three": [self.owner, self.other, self.admin],
        }
        for subject, members in members_by_subject.items():
            message = Message.objects.create(
                subject=subject,
                content="Body",
                created_by=self.admin,
                to_freizeit=freizeit,
                to_notelist=notelist,
            )
            message.to_groups.add(self.group)
            message.to_members.add(*members)
        bare = Message.objects.create(subject="bare", content="Body", created_by=self.admin)
        bare.to_members.add(self.owner)

        r = self.client.get("/api/mailer/messages", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)
        rows = r.json()
        self.assertEqual(
            [row["subject"] for row in rows],
            ["bare", "three", "two and unconfirmed", "two", "none"],
        )
        for row in rows:
            self.assertEqual(set(row), {"id", "subject", "sent", "created_at", "recipients"})
            self.assertFalse(row["sent"])
        recipients = {row["subject"]: row["recipients"].split(", ") for row in rows}
        shared = ["Alpenfuechse", "Hüttentour", "Kletterliste"]
        self.assertEqual(recipients["none"], shared)
        self.assertCountEqual(recipients["two"], shared + ["Owner Test", "Other Test"])
        self.assertCountEqual(
            recipients["two and unconfirmed"], shared + ["Owner Test", "Other Test"]
        )
        self.assertEqual(recipients["three"], shared + [str(_("Some other members"))])
        self.assertEqual(recipients["bare"], ["Owner Test"])

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
        # The reason is the only thing that makes this 403 actionable: it is a
        # rule about the sender's address, not a missing permission, so being an
        # admin does not help and the client must be able to print it.
        self.assertTrue(r.json()["displayable"])
        # Compared against the translated string, not an English fragment of it:
        # the refusal is shown to the user, so it is German in a German session.
        self.assertEqual(
            r.json()["detail"],
            str(
                _("Your email address is not an internal email address and may not send messages.")
            ),
        )
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
        # A permission refusal carries a codename, which the client must not
        # print — the opposite case to the one above.
        self.assertFalse(r.json()["displayable"])
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

    def test_retrieve_email_address(self):
        address = EmailAddress.objects.create(name="vorstand")
        r = self.client.get(
            "/api/mailer/email-addresses/{}".format(address.pk), **self.auth(self.admin_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["name"], "vorstand")

    def test_retrieve_email_address_forbidden(self):
        address = EmailAddress.objects.create(name="vorstand")
        r = self.client.get(
            "/api/mailer/email-addresses/{}".format(address.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)

    @mock.patch("mailer.models.send")
    def test_attaching_to_a_sent_message_is_refused(self, mock_send):
        # The attachment would never go out, so the refusal has to be readable
        # rather than a generic permission error.
        mock_send.return_value = SENT
        message = self.make_message(self.owner)
        message.sent = True
        message.save()
        r = self.client.post(
            "/api/mailer/messages/{}/attachments".format(message.pk),
            data={
                "f": SimpleUploadedFile("anhang.pdf", b"fakepdf", content_type="application/pdf")
            },
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403, r.content)
        self.assertTrue(r.json()["displayable"])
