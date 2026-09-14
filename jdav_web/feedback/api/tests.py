"""End-to-end tests for the feedback API.

Sending is open to everyone (the button is on the public website too) but is
attributed when a bearer token is presented; reading is gated on
``feedback.view_feedback``.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from feedback.models import Feedback
from members.models import DIVERSE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


class FeedbackApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.user = User.objects.create_user(username="sender", password="secret")
        self.member = Member.objects.create(
            prename="Sender",
            lastname="Test",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )
        self.member.user = self.user
        self.member.save()
        self.reader = User.objects.create_user(username="reader", password="secret")
        self.reader.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="view_feedback")
        )
        self.reader = User.objects.get(pk=self.reader.pk)

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def post(self, body, **extra):
        return self.client.post(
            "/api/feedback", data=body, content_type="application/json", **extra
        )

    # --- sending ----------------------------------------------------------

    def test_anonymous_visitor_may_send(self):
        """The button sits on the public website, so no account is required."""
        r = self.post({"message": "Die Seite ist super."})
        self.assertEqual(r.status_code, 200, r.content)
        feedback = Feedback.objects.get(pk=r.json()["id"])
        self.assertEqual(feedback.message, "Die Seite ist super.")
        self.assertIsNone(feedback.submitted_by)

    def test_signed_in_sender_is_attributed(self):
        r = self.post({"message": "Ein Hinweis."}, **self.auth(self.user))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(Feedback.objects.get(pk=r.json()["id"]).submitted_by, self.member)

    def test_context_is_stored_only_when_sent(self):
        """The dialog's checkbox decides; the API stores exactly what it is given."""
        with_ctx = self.post(
            {
                "message": "Hier klemmt was.",
                "page_url": "http://localhost/kompass/members",
                "user_agent": "Mozilla/5.0",
            }
        )
        without = self.post({"message": "Nur ein Lob."})

        stored = Feedback.objects.get(pk=with_ctx.json()["id"])
        self.assertEqual(stored.page_url, "http://localhost/kompass/members")
        self.assertEqual(stored.user_agent, "Mozilla/5.0")
        self.assertTrue(stored.has_context)

        bare = Feedback.objects.get(pk=without.json()["id"])
        self.assertEqual(bare.page_url, "")
        self.assertFalse(bare.has_context)

    def test_an_empty_message_is_refused(self):
        r = self.post({"message": "   "})
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_an_overlong_message_is_refused(self):
        r = self.post({"message": "x" * 5001})
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(Feedback.objects.count(), 0)

    def test_overlong_context_is_truncated_not_rejected(self):
        """Context is a convenience; a long URL must not cost someone their note."""
        r = self.post({"message": "Passt.", "page_url": "http://x/" + "a" * 900})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(Feedback.objects.get(pk=r.json()["id"]).page_url), 500)

    def test_an_invalid_token_still_sends_unattributed(self):
        """A stale login must not swallow the feedback someone just typed."""
        r = self.post({"message": "Trotzdem senden."}, HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(Feedback.objects.get(pk=r.json()["id"]).submitted_by)

    # --- reading ----------------------------------------------------------

    def test_listing_requires_the_permission(self):
        Feedback.objects.create(message="Geheim")
        self.assertEqual(self.client.get("/api/feedback").status_code, 401)
        r = self.client.get("/api/feedback", **self.auth(self.user))
        self.assertEqual(r.status_code, 403)

    def test_reader_sees_feedback_newest_first(self):
        old = Feedback.objects.create(message="Alt")
        new = Feedback.objects.create(message="Neu")
        r = self.client.get("/api/feedback", **self.auth(self.reader))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([row["id"] for row in r.json()], [new.pk, old.pk])

    def test_detail_exposes_the_browser_only_on_the_single_view(self):
        feedback = Feedback.objects.create(message="Mit Kontext", user_agent="Mozilla/5.0")
        r = self.client.get("/api/feedback/{}".format(feedback.pk), **self.auth(self.reader))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["user_agent"], "Mozilla/5.0")

    def test_deleting_requires_the_delete_permission(self):
        feedback = Feedback.objects.create(message="Erledigt")
        r = self.client.delete("/api/feedback/{}".format(feedback.pk), **self.auth(self.reader))
        self.assertEqual(r.status_code, 403)

        self.reader.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="delete_feedback")
        )
        reader = User.objects.get(pk=self.reader.pk)
        r = self.client.delete("/api/feedback/{}".format(feedback.pk), **self.auth(reader))
        self.assertEqual(r.status_code, 204, r.content)
        self.assertEqual(Feedback.objects.count(), 0)
