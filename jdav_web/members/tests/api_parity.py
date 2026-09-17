"""End-to-end tests for the admin-parity expansion of the members REST API.

These cover the endpoints and fields added to reach full Django-admin parity:
the dedicated registrations list, the new PATCH surfaces (waiters, excursions,
note-lists, klettertreff and the expanded member/training/group updates), the
per-field permission gates, the ActivityCategory / TrainingCategory selector
CRUD and the member choice-enum endpoint. Each new surface is exercised for an
authorized 200, an unauthorized 403 and (where applicable) a 422 validation
failure, mirroring ``members/tests/api.py``.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from members.models import ActivityCategory
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Klettertreff
from members.models import Member
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberWaitingList
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def make_member_user(username):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=username.title(),
        lastname="Test",
        birth_date=timezone.now().date(),
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    return user, member


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="members", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class MembersApiParityTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("owner")
        self.other_user, self.other = make_member_user("other")
        self.admin_user, self.admin = make_member_user("admin")
        self.admin_user = grant(
            self.admin_user,
            "list_global_member",
            "view_global_member",
            "change_global_member",
            "view_group",
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

    def patch(self, path, user, **data):
        return self.client.patch(
            path, data=data, content_type="application/json", **self.auth(user)
        )

    # --- registrations list ----------------------------------------------

    def make_unconfirmed(self, prename, group=None):
        member = Member.objects.create(
            prename=prename,
            lastname="Reg",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            confirmed=False,
            confirmed_mail=True,
        )
        if group is not None:
            member.group.add(group)
        return member

    def test_registrations_all_with_manage_permission(self):
        manager = grant(self.admin_user, "may_manage_all_registrations")
        reg = self.make_unconfirmed("Regone")
        r = self.client.get("/api/members/registrations", **self.auth(manager))
        self.assertEqual(r.status_code, 200)
        self.assertIn(reg.pk, {m["id"] for m in r.json()})

    def test_registrations_scoped_to_led_groups(self):
        self.group.leiters.add(self.owner)
        in_group = self.make_unconfirmed("InGroup", group=self.group)
        elsewhere = self.make_unconfirmed("Elsewhere")
        r = self.client.get("/api/members/registrations", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        ids = {m["id"] for m in r.json()}
        self.assertIn(in_group.pk, ids)
        self.assertNotIn(elsewhere.pk, ids)

    # --- waiter PATCH -----------------------------------------------------

    def make_waiter(self, prename="Wait"):
        return MemberWaitingList.objects.create(
            prename=prename,
            lastname="Applicant",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )

    def test_waiter_update_authorized(self):
        editor = grant(self.admin_user, "change_global_memberwaitinglist")
        waiter = self.make_waiter()
        r = self.patch("/api/members/waiters/{}".format(waiter.pk), editor, prename="Renamed")
        self.assertEqual(r.status_code, 200, r.content)
        waiter.refresh_from_db()
        self.assertEqual(waiter.prename, "Renamed")

    def test_waiter_update_forbidden(self):
        waiter = self.make_waiter()
        r = self.patch("/api/members/waiters/{}".format(waiter.pk), self.owner_user, prename="Nope")
        self.assertEqual(r.status_code, 403)

    def test_waiter_update_invalid_gender_422(self):
        editor = grant(self.admin_user, "change_global_memberwaitinglist")
        waiter = self.make_waiter()
        r = self.patch("/api/members/waiters/{}".format(waiter.pk), editor, gender=99)
        self.assertEqual(r.status_code, 422)

    # --- excursion PATCH + approval gating --------------------------------

    def make_excursion(self, leader=None):
        excursion = Freizeit.objects.create(
            name="Zugspitze",
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
        )
        if leader is not None:
            excursion.jugendleiter.add(leader)
        return excursion

    def test_excursion_update_base_field_authorized(self):
        excursion = self.make_excursion(leader=self.owner)
        r = self.patch(
            "/api/members/excursions/{}".format(excursion.pk),
            self.owner_user,
            name="Watzmann",
        )
        self.assertEqual(r.status_code, 200, r.content)
        excursion.refresh_from_db()
        self.assertEqual(excursion.name, "Watzmann")

    def test_excursion_update_forbidden_for_non_leader(self):
        excursion = self.make_excursion(leader=self.owner)
        r = self.patch(
            "/api/members/excursions/{}".format(excursion.pk),
            self.other_user,
            name="Nope",
        )
        self.assertEqual(r.status_code, 403)

    def test_excursion_approval_requires_permission(self):
        excursion = self.make_excursion(leader=self.owner)
        # Leader may change base fields but not the approval fields.
        r = self.patch(
            "/api/members/excursions/{}".format(excursion.pk),
            self.owner_user,
            approved=True,
        )
        self.assertEqual(r.status_code, 403)
        approver = grant(self.owner_user, "manage_approval_excursion")
        r = self.patch("/api/members/excursions/{}".format(excursion.pk), approver, approved=True)
        self.assertEqual(r.status_code, 200, r.content)
        excursion.refresh_from_db()
        self.assertTrue(excursion.approved)

    # --- note-list PATCH --------------------------------------------------

    def test_note_list_update_authorized(self):
        editor = grant(self.admin_user, "change_membernotelist")
        notelist = MemberNoteList.objects.create(title="Old", date=timezone.now().date())
        r = self.patch("/api/members/note-lists/{}".format(notelist.pk), editor, title="New")
        self.assertEqual(r.status_code, 200, r.content)
        notelist.refresh_from_db()
        self.assertEqual(notelist.title, "New")

    def test_note_list_update_forbidden(self):
        notelist = MemberNoteList.objects.create(title="Old", date=timezone.now().date())
        r = self.patch(
            "/api/members/note-lists/{}".format(notelist.pk), self.owner_user, title="New"
        )
        self.assertEqual(r.status_code, 403)

    # --- klettertreff PATCH -----------------------------------------------

    def make_klettertreff(self):
        return Klettertreff.objects.create(
            group=self.group, date=timezone.now().date(), location="Hall", topic="Bouldern"
        )

    def test_klettertreff_update_authorized(self):
        editor = grant(self.admin_user, "change_klettertreff")
        kt = self.make_klettertreff()
        r = self.patch("/api/members/klettertreff/{}".format(kt.pk), editor, topic="Toprope")
        self.assertEqual(r.status_code, 200, r.content)
        kt.refresh_from_db()
        self.assertEqual(kt.topic, "Toprope")

    def test_klettertreff_update_forbidden(self):
        kt = self.make_klettertreff()
        r = self.patch("/api/members/klettertreff/{}".format(kt.pk), self.owner_user, topic="Nope")
        self.assertEqual(r.status_code, 403)

    # --- member per-field permission gates --------------------------------

    def test_member_group_change_requires_permission(self):
        # The owner may change themselves (change_obj) but not the group field.
        r = self.patch(
            "/api/members/{}".format(self.owner.pk),
            self.owner_user,
            group_ids=[self.group.pk],
        )
        self.assertEqual(r.status_code, 403)
        allowed = grant(self.owner_user, "may_change_member_group")
        r = self.patch("/api/members/{}".format(self.owner.pk), allowed, group_ids=[self.group.pk])
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({g.pk for g in self.owner.group.all()}, {self.group.pk})

    def test_member_organizational_change_requires_permission(self):
        r = self.patch("/api/members/{}".format(self.owner.pk), self.owner_user, has_key=True)
        self.assertEqual(r.status_code, 403)
        allowed = grant(self.owner_user, "may_change_organizationals")
        r = self.patch("/api/members/{}".format(self.owner.pk), allowed, has_key=True)
        self.assertEqual(r.status_code, 200, r.content)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.has_key)

    def test_member_expanded_scalar_update(self):
        r = self.patch(
            "/api/members/{}".format(self.owner.pk),
            self.owner_user,
            dav_badge_no="12345",
            climbing_badge="Toprope",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.dav_badge_no, "12345")
        self.assertEqual(self.owner.climbing_badge, "Toprope")

    # --- training PATCH: category / activity ------------------------------

    def test_training_update_category_and_activity(self):
        cat_a = TrainingCategory.objects.create(name="Grundkurs", permission_needed=False)
        cat_b = TrainingCategory.objects.create(name="Aufbaukurs", permission_needed=False)
        activity = ActivityCategory.objects.create(
            name="Klettern", ljp_category="Klettern", description="x"
        )
        training = MemberTraining.objects.create(member=self.owner, title="Kurs", category=cat_a)
        r = self.patch(
            "/api/members/trainings/{}".format(training.pk),
            self.owner_user,
            category_id=cat_b.pk,
            activity_ids=[activity.pk],
        )
        self.assertEqual(r.status_code, 200, r.content)
        training.refresh_from_db()
        self.assertEqual(training.category_id, cat_b.pk)
        self.assertEqual({a.pk for a in training.activity.all()}, {activity.pk})

    # --- selector category CRUD -------------------------------------------

    def test_activity_categories_list_requires_permission(self):
        ActivityCategory.objects.create(name="Klettern", ljp_category="Klettern", description="x")
        r = self.client.get("/api/members/activity-categories", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)
        viewer = grant(self.owner_user, "view_activitycategory")
        r = self.client.get("/api/members/activity-categories", **self.auth(viewer))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(c["name"] == "Klettern" for c in r.json()))

    def test_activity_category_create_and_validation(self):
        creator = grant(self.owner_user, "add_activitycategory")
        r = self.client.post(
            "/api/members/activity-categories",
            data={"name": "Ski", "ljp_category": "Winter", "description": "d"},
            content_type="application/json",
            **self.auth(creator),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(ActivityCategory.objects.filter(name="Ski").exists())

    def test_activity_category_create_invalid_choice_422(self):
        creator = grant(self.owner_user, "add_activitycategory")
        r = self.client.post(
            "/api/members/activity-categories",
            data={"name": "Bad", "ljp_category": "NotAChoice", "description": "d"},
            content_type="application/json",
            **self.auth(creator),
        )
        self.assertEqual(r.status_code, 422)

    def test_training_categories_list_requires_permission(self):
        TrainingCategory.objects.create(name="Grundkurs", permission_needed=False)
        r = self.client.get("/api/members/training-categories", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)
        viewer = grant(self.owner_user, "view_trainingcategory")
        r = self.client.get("/api/members/training-categories", **self.auth(viewer))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(c["name"] == "Grundkurs" for c in r.json()))

    # --- enums ------------------------------------------------------------

    def test_member_enums_lists_gender_choices(self):
        r = self.client.get("/api/members/enums", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("gender", body)
        values = {opt["value"] for opt in body["gender"]}
        self.assertEqual(values, {0, 1, 2})

    # --- expanded brief / detail payloads ---------------------------------

    def test_member_brief_exposes_admin_columns(self):
        r = self.client.get("/api/members/", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        row = next(m for m in r.json() if m["id"] == self.owner.pk)
        for key in ("birth_date", "email", "phone_number", "echoed", "age", "activity_score"):
            self.assertIn(key, row)

    def test_member_detail_exposes_expanded_fields(self):
        r = self.client.get("/api/members/{}".format(self.owner.pk), **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        for key in (
            "gender_display",
            "good_conduct_certificate_valid",
            "skills",
            "activities",
            "allergies",
        ):
            self.assertIn(key, body)
