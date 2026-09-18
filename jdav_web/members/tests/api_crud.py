"""Create/update/delete coverage for the members REST API.

The read paths and the interesting permission gates are covered by
:mod:`members.tests.api`, :mod:`members.tests.api_gaps` and
:mod:`members.tests.api_parity`. What was left untested is the plainer half of
each resource: the POST that creates it, the PATCH that edits it and the DELETE
that removes it, plus the handful of ``request-*`` actions that just send a
mail.

Each resource gets the same three questions — does the write happen, does it
come back as the right status, and is it refused without the permission — so
the file reads as one table rather than thirty unrelated cases.
"""

import datetime
import uuid

from django.conf import settings
from django.core import mail
from django.test import TestCase
from django.utils import timezone
from members.models import ActivityCategory
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Klettertreff
from members.models import MALE
from members.models import Member
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberUnconfirmedProxy
from members.models import MemberWaitingList
from members.models import MUSKELKRAFT_ANREISE
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model

from .api import Application
from .api import grant
from .api import make_member_user

AccessToken = get_access_token_model()


class MembersCrudApiTestCase(TestCase):
    """One authenticated caller, granted exactly the permission under test."""

    def setUp(self):
        self.application = Application.objects.create(
            name="crud-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.user, self.member = make_member_user("crudadmin")
        self.plain_user, self.plain = make_member_user("crudplain")
        self.group = Group.objects.create(name="Steinboecke", year_from=2010, year_to=2015)

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def as_admin(self, *codenames):
        return self.auth(grant(self.user, *codenames))

    def post(self, path, payload, **headers):
        return self.client.post(path, data=payload, content_type="application/json", **headers)

    def patch(self, path, payload, **headers):
        return self.client.patch(path, data=payload, content_type="application/json", **headers)

    # --- groups -----------------------------------------------------------

    def test_create_group(self):
        r = self.post(
            "/api/members/groups",
            {"name": "Gemsen", "year_from": 2012, "year_to": 2016, "leiter_ids": []},
            **self.as_admin("add_group"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        group = Group.objects.get(name="Gemsen")
        self.assertEqual(group.year_from, 2012)

    def test_create_group_applies_leiters(self):
        r = self.post(
            "/api/members/groups",
            {"name": "Murmeltiere", "leiter_ids": [self.member.pk]},
            **self.as_admin("add_group"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(list(Group.objects.get(name="Murmeltiere").leiters.all()), [self.member])

    def test_create_group_forbidden(self):
        r = self.post("/api/members/groups", {"name": "Nope"}, **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Group.objects.filter(name="Nope").exists())

    def test_update_group(self):
        r = self.patch(
            "/api/members/groups/{}".format(self.group.pk),
            {"description": "Klettern", "leiter_ids": [self.member.pk]},
            **self.as_admin("change_group"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.description, "Klettern")
        self.assertEqual(list(self.group.leiters.all()), [self.member])

    def test_delete_group(self):
        r = self.client.delete(
            "/api/members/groups/{}".format(self.group.pk), **self.as_admin("delete_group")
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Group.objects.filter(pk=self.group.pk).exists())

    def test_delete_group_forbidden(self):
        r = self.client.delete(
            "/api/members/groups/{}".format(self.group.pk), **self.auth(self.plain_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Group.objects.filter(pk=self.group.pk).exists())

    # --- members ----------------------------------------------------------

    def test_create_member(self):
        r = self.post(
            "/api/members/",
            {
                "prename": "Neue",
                "lastname": "Person",
                "gender": MALE,
                "email": settings.TEST_MAIL,
                "group_ids": [self.group.pk],
            },
            **self.as_admin("add_global_member"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        created = Member.objects.get(prename="Neue", lastname="Person")
        self.assertEqual(list(created.group.all()), [self.group])

    def test_create_member_forbidden(self):
        r = self.post(
            "/api/members/",
            {"prename": "Nicht", "lastname": "Erlaubt", "gender": DIVERSE},
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_delete_member(self):
        victim = Member.objects.create(
            prename="Weg", lastname="Damit", gender=DIVERSE, email=settings.TEST_MAIL
        )
        r = self.client.delete(
            "/api/members/{}".format(victim.pk), **self.as_admin("delete_global_member")
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Member.objects.filter(pk=victim.pk).exists())

    def test_retrieve_me(self):
        r = self.client.get("/api/members/me", **self.auth(self.user))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["member_id"], self.member.pk)
        self.assertEqual(body["user_id"], self.user.pk)

    # --- excursions -------------------------------------------------------

    def _excursion(self):
        return Freizeit.objects.create(
            name="Hochtour",
            difficulty=1,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            date=timezone.localtime(),
        )

    def test_create_excursion(self):
        r = self.post(
            "/api/members/excursions",
            {
                "name": "Skitour",
                "difficulty": 2,
                "tour_type": GEMEINSCHAFTS_TOUR,
                "tour_approach": MUSKELKRAFT_ANREISE,
                "group_ids": [self.group.pk],
                "jugendleiter_ids": [self.member.pk],
            },
            **self.as_admin("add_global_freizeit"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        excursion = Freizeit.objects.get(name="Skitour")
        self.assertEqual(list(excursion.groups.all()), [self.group])
        self.assertEqual(list(excursion.jugendleiter.all()), [self.member])

    def test_create_excursion_forbidden(self):
        r = self.post(
            "/api/members/excursions",
            {"name": "Nope", "difficulty": 1, "tour_type": GEMEINSCHAFTS_TOUR},
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_update_excursion(self):
        excursion = self._excursion()
        excursion.jugendleiter.add(self.member)
        r = self.patch(
            "/api/members/excursions/{}".format(excursion.pk),
            {"place": "Zillertal", "kilometers_traveled": 120},
            **self.auth(self.user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        excursion.refresh_from_db()
        self.assertEqual(excursion.place, "Zillertal")
        self.assertEqual(excursion.kilometers_traveled, 120)

    def test_delete_excursion(self):
        excursion = self._excursion()
        r = self.client.delete(
            "/api/members/excursions/{}".format(excursion.pk),
            **self.as_admin("delete_global_freizeit"),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Freizeit.objects.filter(pk=excursion.pk).exists())

    # --- trainings --------------------------------------------------------

    def _category(self, permission_needed=False):
        return TrainingCategory.objects.create(
            name="Kategorie {}".format(uuid.uuid4().hex[:6]),
            permission_needed=permission_needed,
        )

    def test_create_training(self):
        category = self._category()
        r = self.post(
            "/api/members/trainings",
            {
                "title": "Kletterschein",
                "member_id": self.member.pk,
                "category_id": category.pk,
            },
            **self.as_admin("add_global_membertraining"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(
            MemberTraining.objects.filter(member=self.member, title="Kletterschein").exists()
        )

    def test_create_training_for_someone_else_forbidden(self):
        category = self._category()
        r = self.post(
            "/api/members/trainings",
            {"title": "Fremd", "member_id": self.plain.pk, "category_id": category.pk},
            **self.auth(self.user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(MemberTraining.objects.filter(title="Fremd").exists())

    def test_list_trainings(self):
        MemberTraining.objects.create(
            member=self.member, title="Eigenes", category=self._category()
        )
        r = self.client.get("/api/members/trainings", **self.auth(self.user))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("Eigenes", {t["title"] for t in r.json()})

    def test_delete_training(self):
        training = MemberTraining.objects.create(
            member=self.member, title="Weg", category=self._category()
        )
        r = self.client.delete(
            "/api/members/trainings/{}".format(training.pk), **self.auth(self.user)
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(MemberTraining.objects.filter(pk=training.pk).exists())

    # --- categories -------------------------------------------------------

    def test_activity_category_crud(self):
        headers = self.as_admin(
            "add_activitycategory",
            "view_activitycategory",
            "change_activitycategory",
            "delete_activitycategory",
        )
        created = self.post(
            "/api/members/activity-categories",
            {"name": "Kletterabend", "ljp_category": "Klettern", "description": "Halle"},
            **headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        category_id = created.json()["id"]

        fetched = self.client.get(
            "/api/members/activity-categories/{}".format(category_id), **headers
        )
        self.assertEqual(fetched.status_code, 200, fetched.content)
        self.assertEqual(fetched.json()["name"], "Kletterabend")

        updated = self.patch(
            "/api/members/activity-categories/{}".format(category_id),
            {"description": "Fels"},
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(ActivityCategory.objects.get(pk=category_id).description, "Fels")

        removed = self.client.delete(
            "/api/members/activity-categories/{}".format(category_id), **headers
        )
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(ActivityCategory.objects.filter(pk=category_id).exists())

    def test_training_category_crud(self):
        headers = self.as_admin(
            "add_trainingcategory",
            "view_trainingcategory",
            "change_trainingcategory",
            "delete_trainingcategory",
        )
        created = self.post(
            "/api/members/training-categories",
            {"name": "Grundkurs", "permission_needed": False},
            **headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        category_id = created.json()["id"]

        fetched = self.client.get(
            "/api/members/training-categories/{}".format(category_id), **headers
        )
        self.assertEqual(fetched.status_code, 200, fetched.content)

        updated = self.patch(
            "/api/members/training-categories/{}".format(category_id),
            {"permission_needed": True},
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertTrue(TrainingCategory.objects.get(pk=category_id).permission_needed)

        removed = self.client.delete(
            "/api/members/training-categories/{}".format(category_id), **headers
        )
        self.assertEqual(removed.status_code, 204, removed.content)

    # --- Klettertreff -----------------------------------------------------

    def test_klettertreff_crud(self):
        headers = self.as_admin(
            "add_klettertreff", "change_klettertreff", "delete_klettertreff", "view_klettertreff"
        )
        created = self.post(
            "/api/members/klettertreff",
            {"group_id": self.group.pk, "location": "Halle", "topic": "Vorstieg"},
            **headers,
        )
        self.assertEqual(created.status_code, 201, created.content)
        treff_id = created.json()["id"]

        updated = self.patch(
            "/api/members/klettertreff/{}".format(treff_id), {"topic": "Toprope"}, **headers
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(Klettertreff.objects.get(pk=treff_id).topic, "Toprope")

        removed = self.client.delete("/api/members/klettertreff/{}".format(treff_id), **headers)
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(Klettertreff.objects.filter(pk=treff_id).exists())

    # --- note lists -------------------------------------------------------

    def test_note_list_crud(self):
        headers = self.as_admin(
            "add_membernotelist", "delete_membernotelist", "view_membernotelist"
        )
        created = self.post("/api/members/note-lists", {"title": "Ausfahrt"}, **headers)
        self.assertEqual(created.status_code, 201, created.content)
        list_id = created.json()["id"]
        self.assertEqual(MemberNoteList.objects.get(pk=list_id).title, "Ausfahrt")

        removed = self.client.delete("/api/members/note-lists/{}".format(list_id), **headers)
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(MemberNoteList.objects.filter(pk=list_id).exists())

    # --- registrations ----------------------------------------------------

    def _registration(self):
        member = Member.objects.create(
            prename="Neu",
            lastname="Angemeldet",
            gender=DIVERSE,
            email=settings.TEST_MAIL,
            confirmed=False,
        )
        member.group.add(self.group)
        return MemberUnconfirmedProxy.objects.get(pk=member.pk)

    def test_list_and_retrieve_registration(self):
        registration = self._registration()
        headers = self.as_admin("may_manage_all_registrations")
        listed = self.client.get("/api/members/registrations", **headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(registration.pk, {row["id"] for row in listed.json()})

        fetched = self.client.get(
            "/api/members/registrations/{}".format(registration.pk), **headers
        )
        self.assertEqual(fetched.status_code, 200, fetched.content)

    def test_update_registration(self):
        registration = self._registration()
        r = self.patch(
            "/api/members/registrations/{}".format(registration.pk),
            {"town": "Ludwigsburg"},
            **self.as_admin("may_manage_all_registrations"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        registration.refresh_from_db()
        self.assertEqual(registration.town, "Ludwigsburg")

    def test_delete_registration(self):
        registration = self._registration()
        r = self.client.delete(
            "/api/members/registrations/{}".format(registration.pk),
            **self.as_admin("delete_global_member", "may_manage_all_registrations"),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Member.objects.filter(pk=registration.pk).exists())

    # --- waiters ----------------------------------------------------------

    def _waiter(self):
        return MemberWaitingList.objects.create(
            prename="Warte",
            lastname="Person",
            gender=DIVERSE,
            email=settings.TEST_MAIL,
            birth_date=timezone.now().date(),
        )

    def test_list_and_retrieve_waiter(self):
        waiter = self._waiter()
        headers = self.as_admin("list_global_memberwaitinglist", "view_global_memberwaitinglist")
        listed = self.client.get("/api/members/waiters", **headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(waiter.pk, {row["id"] for row in listed.json()})

        fetched = self.client.get("/api/members/waiters/{}".format(waiter.pk), **headers)
        self.assertEqual(fetched.status_code, 200, fetched.content)

    def test_delete_waiter(self):
        waiter = self._waiter()
        r = self.client.delete(
            "/api/members/waiters/{}".format(waiter.pk),
            **self.as_admin("delete_global_memberwaitinglist"),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(MemberWaitingList.objects.filter(pk=waiter.pk).exists())

    def test_request_wait_confirmation_sends_mail(self):
        waiter = self._waiter()
        mail.outbox = []
        r = self.post(
            "/api/members/waiters/{}/request-wait-confirmation".format(waiter.pk),
            {},
            **self.as_admin("change_global_memberwaitinglist", "view_global_memberwaitinglist"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_waiter_mail_confirmation_sends_mail(self):
        waiter = self._waiter()
        waiter.mail_confirmed = False
        waiter.save()
        mail.outbox = []
        r = self.post(
            "/api/members/waiters/{}/request-mail-confirmation".format(waiter.pk),
            {},
            **self.as_admin("change_global_memberwaitinglist", "view_global_memberwaitinglist"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)

    # --- member-scoped mail actions ---------------------------------------

    def test_request_echo_sends_mail(self):
        mail.outbox = []
        r = self.post(
            "/api/members/{}/request-echo".format(self.member.pk),
            {},
            **self.as_admin("change_global_member", "view_global_member"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)

    def test_request_registration_form_sends_mail(self):
        mail.outbox = []
        r = self.post(
            "/api/members/{}/request-registration-form".format(self.member.pk),
            {},
            **self.as_admin("change_global_member", "view_global_member"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)
