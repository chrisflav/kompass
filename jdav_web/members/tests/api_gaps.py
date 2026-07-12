"""End-to-end tests for the parity-gap members REST API endpoints.

These cover the endpoints added to close admin/API parity gaps:

* the ``confirmed`` flag on the member listing,
* the training PATCH endpoint,
* the waiting-list group-invite action,
* the Klettertreff list/detail endpoints,
* the member note-list list/detail endpoints, and
* the group detail/edit endpoints.

They exercise the real OAuth2 bearer authentication path and the same
object/global permission gates the Django admin enforces, reusing the helpers
from :mod:`members.tests.api`.
"""

import datetime
import uuid

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from mailer.models import EmailAddress
from members.models import DIVERSE
from members.models import Group
from members.models import InvitationToGroup
from members.models import Klettertreff
from members.models import KlettertreffAttendee
from members.models import Member
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberWaitingList
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model

from .api import Application
from .api import grant
from .api import make_member_user

AccessToken = get_access_token_model()


class ApiGapsTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="gaps-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("gapowner")
        self.other_user, self.other = make_member_user("gapother")
        self.admin_user, self.admin = make_member_user("gapadmin")
        self.group = Group.objects.create(name="Gipfelstuermer", year_from=2010, year_to=2015)

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- confirmed flag on the member listing -----------------------------

    def test_member_list_exposes_confirmed_flag(self):
        admin = grant(self.admin_user, "list_global_member", "view_global_member")
        r = self.client.get("/api/members/", **self.auth(admin))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json())
        for entry in r.json():
            self.assertIn("confirmed", entry)
            self.assertTrue(entry["confirmed"])

    # --- training update --------------------------------------------------

    def _make_training(self, member):
        category = TrainingCategory.objects.create(name="Grundkurs", permission_needed=False)
        return MemberTraining.objects.create(member=member, title="Kletterkurs", category=category)

    def test_update_training_self_allowed(self):
        training = self._make_training(self.owner)
        r = self.client.patch(
            "/api/members/trainings/{}".format(training.pk),
            data={"title": "Aufbaukurs", "passed": True, "comments": "gut"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        training.refresh_from_db()
        self.assertEqual(training.title, "Aufbaukurs")
        self.assertTrue(training.passed)
        self.assertEqual(training.comments, "gut")

    def test_update_training_other_forbidden(self):
        training = self._make_training(self.owner)
        r = self.client.patch(
            "/api/members/trainings/{}".format(training.pk),
            data={"title": "Hijack"},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        training.refresh_from_db()
        self.assertEqual(training.title, "Kletterkurs")

    # --- waiting-list group invite ----------------------------------------

    def _make_waiter(self, prename="Applicant"):
        return MemberWaitingList.objects.create(
            prename=prename,
            lastname="Wait",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )

    def test_invite_waiter_forbidden_without_permission(self):
        waiter = self._make_waiter()
        r = self.client.post(
            "/api/members/waiters/{}/invite".format(waiter.pk),
            data={"group_id": self.group.pk},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(InvitationToGroup.objects.filter(waiter=waiter).exists())

    def test_invite_waiter_success(self):
        from django.core import mail

        manager = grant(self.admin_user, "change_global_memberwaitinglist")
        self.group.contact_email = EmailAddress.objects.create(name="gipfel")
        self.group.save()
        waiter = self._make_waiter()
        r = self.client.post(
            "/api/members/waiters/{}/invite".format(waiter.pk),
            data={"group_id": self.group.pk},
            content_type="application/json",
            **self.auth(manager),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(InvitationToGroup.objects.filter(waiter=waiter, group=self.group).exists())
        self.assertTrue(len(mail.outbox) >= 1)

    def test_invite_waiter_without_contact_email_rejected(self):
        manager = grant(self.admin_user, "change_global_memberwaitinglist")
        waiter = self._make_waiter()
        r = self.client.post(
            "/api/members/waiters/{}/invite".format(waiter.pk),
            data={"group_id": self.group.pk},
            content_type="application/json",
            **self.auth(manager),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(InvitationToGroup.objects.filter(waiter=waiter).exists())

    # --- klettertreff -----------------------------------------------------

    def _make_klettertreff(self):
        kt = Klettertreff.objects.create(location="Kletterhalle", topic="Toprope", group=self.group)
        kt.jugendleiter.add(self.owner)
        KlettertreffAttendee.objects.create(member=self.other, klettertreff=kt)
        return kt

    def test_klettertreff_list_forbidden_without_permission(self):
        r = self.client.get("/api/members/klettertreff", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_klettertreff_listed_with_permission(self):
        kt = self._make_klettertreff()
        viewer = grant(self.admin_user, "view_klettertreff")
        r = self.client.get("/api/members/klettertreff", **self.auth(viewer))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({k["id"] for k in r.json()}, {kt.pk})

    def test_klettertreff_detail_with_permission(self):
        kt = self._make_klettertreff()
        viewer = grant(self.admin_user, "view_klettertreff")
        r = self.client.get("/api/members/klettertreff/{}".format(kt.pk), **self.auth(viewer))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["location"], "Kletterhalle")
        self.assertEqual(body["group"]["id"], self.group.pk)
        self.assertEqual({j["id"] for j in body["jugendleiter"]}, {self.owner.pk})
        self.assertEqual({a["id"] for a in body["attendees"]}, {self.other.pk})

    def test_klettertreff_detail_forbidden_without_permission(self):
        kt = self._make_klettertreff()
        r = self.client.get(
            "/api/members/klettertreff/{}".format(kt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- member note lists ------------------------------------------------

    def _make_note_list(self):
        note_list = MemberNoteList.objects.create(title="Ausfahrt", date=timezone.now().date())
        note_list.add_members(Member.objects.filter(pk=self.owner.pk))
        return note_list

    def test_note_lists_forbidden_without_permission(self):
        r = self.client.get("/api/members/note-lists", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_note_lists_listed_with_permission(self):
        note_list = self._make_note_list()
        viewer = grant(self.admin_user, "view_membernotelist")
        r = self.client.get("/api/members/note-lists", **self.auth(viewer))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({n["id"] for n in r.json()}, {note_list.pk})

    def test_note_list_detail_with_permission(self):
        note_list = self._make_note_list()
        viewer = grant(self.admin_user, "view_membernotelist")
        r = self.client.get("/api/members/note-lists/{}".format(note_list.pk), **self.auth(viewer))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["title"], "Ausfahrt")
        self.assertEqual({m["id"] for m in body["members"]}, {self.owner.pk})

    def test_note_list_detail_forbidden_without_permission(self):
        note_list = self._make_note_list()
        r = self.client.get(
            "/api/members/note-lists/{}".format(note_list.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- group detail + edit ----------------------------------------------

    def test_group_detail_forbidden_without_permission(self):
        r = self.client.get(
            "/api/members/groups/{}".format(self.group.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_group_detail_with_permission(self):
        viewer = grant(self.admin_user, "view_group")
        r = self.client.get("/api/members/groups/{}".format(self.group.pk), **self.auth(viewer))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["name"], "Gipfelstuermer")

    def test_group_update_forbidden_without_permission(self):
        r = self.client.patch(
            "/api/members/groups/{}".format(self.group.pk),
            data={"description": "hijacked"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.group.refresh_from_db()
        self.assertNotEqual(self.group.description, "hijacked")

    def test_group_update_with_permission(self):
        editor = grant(self.admin_user, "view_group", "change_group")
        r = self.client.patch(
            "/api/members/groups/{}".format(self.group.pk),
            data={"description": "Bergsteiger", "year_from": 2000},
            content_type="application/json",
            **self.auth(editor),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.description, "Bergsteiger")
        self.assertEqual(self.group.year_from, 2000)
