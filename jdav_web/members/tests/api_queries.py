"""Query-count tests for the members API list and detail endpoints.

Each test serializes a response for some rows, triples the rows and checks
that the number of database queries stays the same: the relations a schema
resolves must be loaded in bulk, not once per row.
"""

import datetime
import uuid

from django.contrib.contenttypes.models import ContentType
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from mailer.models import EmailAddress
from members.models import ActivityCategory
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Member
from members.models import MemberTraining
from members.models import NewMemberOnList
from members.models import RegistrationPassword
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

from .api import grant
from .api import make_member_user

Application = get_application_model()
AccessToken = get_access_token_model()


class QueryCountTestCase(TestCase):
    """Shared fixtures: an authenticated client and a query counter."""

    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.counter = 0

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def count_queries(self, url, user):
        """Return the number of queries a GET of ``url`` runs, and its body."""
        headers = self.auth(user)
        with CaptureQueriesContext(connection) as ctx:
            r = self.client.get(url, **headers)
        self.assertEqual(r.status_code, 200, r.content)
        return len(ctx.captured_queries), r.json()

    def assertConstantQueries(self, url, user, make_rows, rows=3):
        """GET ``url`` with ``rows`` and with ``3 * rows`` rows; same query count."""
        make_rows(rows)
        # Warm the per-process caches (content types, …) so they don't skew
        # the first measurement.
        self.count_queries(url, user)
        few, _ = self.count_queries(url, user)
        make_rows(2 * rows)
        many, body = self.count_queries(url, user)
        self.assertEqual(
            few,
            many,
            "{}: {} queries for {} rows, {} for {}".format(url, few, rows, many, 3 * rows),
        )
        return body

    def make_member(self, prefix="m"):
        self.counter += 1
        return Member.objects.create(
            prename="{}{}".format(prefix, self.counter),
            lastname="Test",
            birth_date=datetime.date(2010, 1, 1),
            email="{}{}@example.org".format(prefix, self.counter),
            gender=DIVERSE,
        )

    def make_excursion(self, participants=(), leaders=(), groups=(), activities=()):
        self.counter += 1
        excursion = Freizeit.objects.create(
            name="Tour {}".format(self.counter),
            place="Alpen",
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=2,
            date=timezone.now() - datetime.timedelta(days=30),
            end=timezone.now() - datetime.timedelta(days=28),
        )
        content_type = ContentType.objects.get_for_model(Freizeit)
        for member in participants:
            NewMemberOnList.objects.create(
                member=member, content_type=content_type, object_id=excursion.pk
            )
        excursion.jugendleiter.set(leaders)
        excursion.groups.set(groups)
        excursion.activity.set(activities)
        return excursion


class MembersApiQueryCountTestCase(QueryCountTestCase):
    def setUp(self):
        super().setUp()
        self.admin_user, self.admin = make_member_user("admin")
        self.admin_user = grant(
            self.admin_user,
            "list_global_member",
            "view_global_member",
            "list_global_membertraining",
            "view_global_membertraining",
            "list_global_freizeit",
            "view_global_freizeit",
            "view_group",
        )

    def make_group(self):
        self.counter += 1
        return Group.objects.create(name="Gruppe {}".format(self.counter))

    def test_list_members(self):
        def make_rows(n):
            for _ in range(n):
                member = self.make_member()
                member.group.set([self.make_group(), self.make_group()])

        body = self.assertConstantQueries("/api/members/", self.admin_user, make_rows)
        self.assertEqual(len(body), 10)
        self.assertTrue(all(len(m["groups"]) == 2 for m in body if m["id"] != self.admin.pk))

    def test_retrieve_member(self):
        member = self.make_member()
        member.group.set([self.make_group()])
        leader = self.make_member("leader")

        def make_rows(n):
            for _ in range(n):
                category = ActivityCategory.objects.create(
                    name="Akt {}".format(self.counter), ljp_category="Klettern", description=""
                )
                self.make_excursion(
                    participants=[member, self.make_member()],
                    leaders=[leader],
                    groups=[self.make_group()],
                    activities=[category],
                )

        body = self.assertConstantQueries(
            "/api/members/{}".format(member.pk), self.admin_user, make_rows
        )
        self.assertEqual(len(body["activities"]), 9)
        # Nine past excursions of difficulty 2, one activity each: 3 * 2 apiece.
        self.assertEqual(sum(body["skills"].values()), 9 * 6)
        excursion = body["activities"][0]
        self.assertEqual(len(excursion["groups"]), 1)
        self.assertEqual(len(excursion["participant_ids"]), 3)

    def test_list_trainings(self):
        def make_rows(n):
            for _ in range(n):
                self.counter += 1
                category = TrainingCategory.objects.create(
                    name="Kat {}".format(self.counter), permission_needed=False
                )
                activity = ActivityCategory.objects.create(
                    name="Akt {}".format(self.counter), ljp_category="Klettern", description=""
                )
                training = MemberTraining.objects.create(
                    member=self.make_member(), title="Kurs", category=category
                )
                training.activity.set([activity])

        body = self.assertConstantQueries("/api/members/trainings", self.admin_user, make_rows)
        self.assertEqual(len(body), 9)
        self.assertTrue(all(len(t["activities"]) == 1 for t in body))

    def test_list_groups(self):
        def make_rows(n):
            for _ in range(n):
                group = self.make_group()
                group.contact_email = EmailAddress.objects.create(
                    name="gruppe{}".format(self.counter)
                )
                group.save()
                group.leiters.set([self.make_member(), self.make_member()])
                RegistrationPassword.objects.create(
                    group=group, password="pw{}".format(self.counter)
                )

        body = self.assertConstantQueries("/api/members/groups", self.admin_user, make_rows)
        self.assertEqual(len(body), 9)
        self.assertTrue(all(len(g["leiters"]) == 2 for g in body))
        self.assertTrue(all(g["has_registration_password"] for g in body))
        self.assertTrue(all(g["contact_email_display"] for g in body))

    def test_retrieve_group(self):
        group = self.make_group()
        group.contact_email = EmailAddress.objects.create(name="gruppe")
        group.save()

        def make_rows(n):
            group.leiters.add(*[self.make_member() for _ in range(n)])

        body = self.assertConstantQueries(
            "/api/members/groups/{}".format(group.pk), self.admin_user, make_rows
        )
        self.assertEqual(len(body["leiters"]), 9)
        self.assertFalse(body["has_registration_password"])

    def test_list_excursions(self):
        def make_rows(n):
            for _ in range(n):
                self.make_excursion(
                    participants=[self.make_member()],
                    leaders=[self.make_member()],
                    groups=[self.make_group()],
                )

        body = self.assertConstantQueries("/api/members/excursions", self.admin_user, make_rows)
        self.assertEqual(len(body), 9)
        self.assertTrue(all(len(e["participant_ids"]) == 2 for e in body))
