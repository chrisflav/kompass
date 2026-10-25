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
from django.core import mail
from django.db import connection
from django.test import override_settings
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from feedback.models import Feedback
from feedback.models import FeedbackResponse
from members.models import DIVERSE
from members.models import Group
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

    def test_listing_queries_do_not_grow_with_senders(self):
        def add_feedback(n):
            for _feedback in range(n):
                sender = Member.objects.create(
                    prename="Sender",
                    lastname="Test",
                    birth_date=timezone.now().date(),
                    email=settings.TEST_MAIL,
                    gender=DIVERSE,
                )
                sender.group.add(Group.objects.create(name="Gruppe {}".format(sender.pk)))
                Feedback.objects.create(message="Hinweis", submitted_by=sender)

        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                r = self.client.get("/api/feedback", **headers)
            self.assertEqual(r.status_code, 200, r.content)
            return r.json(), len(queries)

        headers = self.auth(self.reader)
        add_feedback(2)
        few = count_queries()[1]
        add_feedback(4)
        body, many = count_queries()
        self.assertEqual(many, few)
        self.assertEqual(len(body), 6)
        self.assertTrue(all(len(row["submitted_by"]["groups"]) == 1 for row in body))

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

    # --- resolving --------------------------------------------------------

    def resolver(self):
        """The signed-in sender, granted the view and change permissions."""
        for codename in ("view_feedback", "change_feedback"):
            self.user.user_permissions.add(
                Permission.objects.get(content_type__app_label="feedback", codename=codename)
            )
        return User.objects.get(pk=self.user.pk)

    def test_resolving_requires_the_change_permission(self):
        feedback = Feedback.objects.create(message="Offen")
        for action in ("resolve", "reopen"):
            r = self.client.post(
                "/api/feedback/{}/{}".format(feedback.pk, action), **self.auth(self.reader)
            )
            self.assertEqual(r.status_code, 403)
        feedback.refresh_from_db()
        self.assertFalse(feedback.is_resolved)

    def test_changing_without_viewing_is_refused(self):
        """The response carries the note itself, so change alone must not read it."""
        self.user.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="change_feedback")
        )
        changer = User.objects.get(pk=self.user.pk)
        feedback = Feedback.objects.create(message="Geheim")
        r = self.client.post("/api/feedback/{}/resolve".format(feedback.pk), **self.auth(changer))
        self.assertEqual(r.status_code, 403)

    def test_resolving_without_a_member_leaves_resolved_by_empty(self):
        self.reader.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="change_feedback")
        )
        reader = User.objects.get(pk=self.reader.pk)
        feedback = Feedback.objects.create(message="Ohne Mitglied")
        r = self.client.post("/api/feedback/{}/resolve".format(feedback.pk), **self.auth(reader))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["resolved_at"])
        self.assertIsNone(r.json()["resolved_by"])

    def test_resolving_records_who_and_when(self):
        feedback = Feedback.objects.create(message="Behoben")
        r = self.client.post(
            "/api/feedback/{}/resolve".format(feedback.pk), **self.auth(self.resolver())
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["resolved_at"])
        self.assertEqual(r.json()["resolved_by"]["id"], self.member.pk)
        feedback.refresh_from_db()
        self.assertTrue(feedback.is_resolved)
        self.assertEqual(feedback.resolved_by, self.member)

    def test_resolving_twice_keeps_the_original_record(self):
        first = timezone.now() - datetime.timedelta(days=3)
        feedback = Feedback.objects.create(message="Schon erledigt", resolved_at=first)
        r = self.client.post(
            "/api/feedback/{}/resolve".format(feedback.pk), **self.auth(self.resolver())
        )
        self.assertEqual(r.status_code, 200, r.content)
        feedback.refresh_from_db()
        self.assertEqual(feedback.resolved_at, first)
        self.assertIsNone(feedback.resolved_by)

    def test_reopening_clears_the_resolution(self):
        feedback = Feedback.objects.create(
            message="Doch nicht", resolved_at=timezone.now(), resolved_by=self.member
        )
        r = self.client.post(
            "/api/feedback/{}/reopen".format(feedback.pk), **self.auth(self.resolver())
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["resolved_at"])
        feedback.refresh_from_db()
        self.assertFalse(feedback.is_resolved)
        self.assertIsNone(feedback.resolved_by)

    def test_listing_shows_the_status(self):
        Feedback.objects.create(message="Erledigt", resolved_at=timezone.now())
        r = self.client.get("/api/feedback", **self.auth(self.reader))
        self.assertIsNotNone(r.json()[0]["resolved_at"])

    def test_str_shows_the_first_line_of_the_message(self):
        entry = Feedback.objects.create(message="  Erste Zeile\nZweite Zeile  ")
        self.assertEqual(str(entry), "Erste Zeile")

    def test_str_of_a_blank_message_says_so(self):
        # `message` is validated on the way in, but a row can still be blank if
        # it was written any other way — the inbox must not render an empty row.
        entry = Feedback.objects.create(message="   ")
        self.assertEqual(str(entry), str(_("(empty)")))

    # --- responding -------------------------------------------------------

    def respond(self, feedback, body, user=None):
        return self.client.post(
            "/api/feedback/{}/respond".format(feedback.pk),
            data=body,
            content_type="application/json",
            **self.auth(user or self.resolver()),
        )

    def other_sender(self, **fields):
        return Member.objects.create(
            prename="Hannah",
            lastname="Becker",
            birth_date=timezone.now().date(),
            gender=DIVERSE,
            **fields,
        )

    def test_responding_requires_the_change_permission(self):
        feedback = Feedback.objects.create(message="Offen", submitted_by=self.member)
        r = self.respond(feedback, {"message": "Danke!"}, user=self.reader)
        self.assertEqual(r.status_code, 403)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(feedback.responses.exists())

    def test_responding_mails_the_sender_and_keeps_the_answer(self):
        sender = self.other_sender(email="hannah@example.org")
        feedback = Feedback.objects.create(
            message="Der Kalender lädt nicht.\nZweite Zeile", submitted_by=sender
        )
        r = self.respond(feedback, {"message": "  Ist behoben, danke!  "})
        self.assertEqual(r.status_code, 200, r.content)

        self.assertEqual(len(mail.outbox), 1)
        sent = mail.outbox[0]
        self.assertEqual(sent.to, ["hannah@example.org"])
        self.assertEqual(sent.subject, str(_("Response to your feedback")))
        self.assertIn("Hallo Hannah,", sent.body)
        self.assertIn("Sender Test hat dir geantwortet:\n\nIst behoben, danke!", sent.body)
        self.assertIn("> Der Kalender lädt nicht.\n> Zweite Zeile", sent.body)
        self.assertNotIn(str(_("Your feedback is now marked as resolved.")), sent.body)

        body = r.json()
        self.assertIsNone(body["resolved_at"])
        self.assertEqual(len(body["responses"]), 1)
        self.assertEqual(body["responses"][0]["message"], "Ist behoben, danke!")
        self.assertEqual(body["responses"][0]["author"]["id"], self.member.pk)
        feedback.refresh_from_db()
        self.assertFalse(feedback.is_resolved)

    def test_responses_form_a_thread(self):
        feedback = Feedback.objects.create(message="Frage", submitted_by=self.member)
        self.respond(feedback, {"message": "Erste Antwort"})
        r = self.respond(feedback, {"message": "Zweite Antwort"})
        self.assertEqual(
            [row["message"] for row in r.json()["responses"]], ["Erste Antwort", "Zweite Antwort"]
        )
        self.assertEqual(len(mail.outbox), 2)

    def test_responding_can_resolve_in_the_same_step(self):
        feedback = Feedback.objects.create(message="Kaputt", submitted_by=self.member)
        r = self.respond(feedback, {"message": "Repariert.", "resolve": True})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["resolved_at"])
        self.assertEqual(r.json()["resolved_by"]["id"], self.member.pk)
        self.assertIn(str(_("Your feedback is now marked as resolved.")), mail.outbox[0].body)

    def test_responding_to_resolved_feedback_keeps_the_original_record(self):
        first = timezone.now() - datetime.timedelta(days=3)
        feedback = Feedback.objects.create(
            message="Schon erledigt", submitted_by=self.member, resolved_at=first
        )
        r = self.respond(feedback, {"message": "Noch ein Nachtrag.", "resolve": True})
        self.assertEqual(r.status_code, 200, r.content)
        feedback.refresh_from_db()
        self.assertEqual(feedback.resolved_at, first)
        self.assertIsNone(feedback.resolved_by)
        # It was resolved before, so the mail does not claim it just was.
        self.assertNotIn(str(_("Your feedback is now marked as resolved.")), mail.outbox[0].body)

    def test_a_long_note_is_quoted_shortened(self):
        feedback = Feedback.objects.create(message="a" * 600, submitted_by=self.member)
        self.respond(feedback, {"message": "Gelesen."})
        self.assertIn("> {} […]\n".format("a" * 500), mail.outbox[0].body)
        self.assertNotIn("a" * 501, mail.outbox[0].body)

    def test_a_responder_without_member_signs_with_the_account(self):
        self.reader.first_name, self.reader.last_name = "Rita", "Reader"
        self.reader.save()
        self.reader.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="change_feedback")
        )
        reader = User.objects.get(pk=self.reader.pk)
        feedback = Feedback.objects.create(message="Hallo", submitted_by=self.member)
        r = self.respond(feedback, {"message": "Hallo zurück."}, user=reader)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["responses"][0]["author"])
        self.assertIn("Rita Reader hat dir geantwortet", mail.outbox[0].body)

        reader.first_name = reader.last_name = ""
        reader.save()
        self.respond(feedback, {"message": "Nochmal."}, user=reader)
        self.assertIn("reader hat dir geantwortet", mail.outbox[1].body)

    def test_an_anonymous_note_cannot_be_answered(self):
        feedback = Feedback.objects.create(message="Ohne Konto")
        detail = self.client.get("/api/feedback/{}".format(feedback.pk), **self.auth(self.reader))
        self.assertFalse(detail.json()["can_respond"])
        r = self.respond(feedback, {"message": "Danke!"})
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(len(mail.outbox), 0)
        self.assertFalse(feedback.responses.exists())

    def test_a_sender_without_an_address_cannot_be_answered(self):
        feedback = Feedback.objects.create(message="Hm", submitted_by=self.other_sender())
        self.assertFalse(feedback.can_respond)
        r = self.respond(feedback, {"message": "Danke!", "resolve": True})
        self.assertEqual(r.status_code, 422, r.content)
        feedback.refresh_from_db()
        self.assertFalse(feedback.is_resolved)

    def test_an_alternative_address_is_enough(self):
        sender = self.other_sender(alternative_email="eltern@example.org")
        feedback = Feedback.objects.create(message="Hm", submitted_by=sender)
        self.assertTrue(feedback.can_respond)

    def test_an_empty_or_overlong_response_is_refused(self):
        feedback = Feedback.objects.create(message="Hm", submitted_by=self.member)
        for text in ("   ", "x" * 5001):
            r = self.respond(feedback, {"message": text})
            self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(len(mail.outbox), 0)

    @override_settings(EMAIL_BACKEND="feedback.no_such_backend.EmailBackend")
    def test_nothing_is_stored_when_the_mail_fails(self):
        feedback = Feedback.objects.create(message="Hm", submitted_by=self.member)
        r = self.respond(feedback, {"message": "Danke!", "resolve": True})
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(feedback.responses.exists())
        feedback.refresh_from_db()
        self.assertFalse(feedback.is_resolved)

    def test_reopening_keeps_the_responses(self):
        feedback = Feedback.objects.create(message="Hm", submitted_by=self.member)
        self.respond(feedback, {"message": "Erledigt.", "resolve": True})
        r = self.client.post(
            "/api/feedback/{}/reopen".format(feedback.pk), **self.auth(self.resolver())
        )
        self.assertEqual(len(r.json()["responses"]), 1)

    def test_response_str_shows_the_start_of_the_message(self):
        feedback = Feedback.objects.create(message="Hm")
        entry = FeedbackResponse.objects.create(feedback=feedback, message=" Danke " + "x" * 80)
        self.assertEqual(str(entry), ("Danke " + "x" * 80)[:60])
        blank = FeedbackResponse.objects.create(feedback=feedback, message="  ")
        self.assertEqual(str(blank), str(_("(empty)")))
