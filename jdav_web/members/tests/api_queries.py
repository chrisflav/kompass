"""Query-count tests for the members API list and detail endpoints.

Each test serializes a response for some rows, triples the rows and checks
that the number of database queries stays the same: the relations a schema
resolves must be loaded in bulk, not once per row.
"""

import datetime
import uuid

from django.contrib.auth.models import User
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
from members.models import Klettertreff
from members.models import KlettertreffAttendee
from members.models import Member
from members.models import MemberTraining
from members.models import NewMemberOnList
from members.models import PermissionGroup
from members.models import PermissionMember
from members.models import RegistrationPassword
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

from .api import grant
from .api import make_member_user

Application = get_application_model()
AccessToken = get_access_token_model()


class QueryCountMixin:
    """Shared fixtures for a ``TestCase``: an authenticated client and a query counter."""

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

    def make_group(self):
        self.counter += 1
        return Group.objects.create(name="Gruppe {}".format(self.counter))

    def make_activity(self):
        self.counter += 1
        return ActivityCategory.objects.create(
            name="Akt {}".format(self.counter), ljp_category="Klettern", description=""
        )

    def make_excursion(
        self, participants=(), leaders=(), groups=(), activities=(), difficulty=2, days_ago=30
    ):
        self.counter += 1
        excursion = Freizeit.objects.create(
            name="Tour {}".format(self.counter),
            place="Alpen",
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=difficulty,
            date=timezone.now() - datetime.timedelta(days=days_ago),
            end=timezone.now() - datetime.timedelta(days=days_ago - 2),
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


class MembersApiQueryCountTestCase(QueryCountMixin, TestCase):
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
        alone, first, second, future, unused = (self.make_activity() for _ in range(5))
        self.make_excursion(participants=[member], activities=[alone])
        # Both activities of one excursion score its difficulty.
        self.make_excursion(participants=[member], activities=[first, second], difficulty=3)
        # A coming excursion is an activity but scores nothing yet.
        self.make_excursion(participants=[member], activities=[future], days_ago=-10)
        expected = {c.name: 0 for c in ActivityCategory.objects.all()}
        expected.update({alone.name: 6, first.name: 9, second.name: 9})

        def make_rows(n):
            for _ in range(n):
                activity = self.make_activity()
                self.make_excursion(
                    participants=[member, self.make_member()],
                    leaders=[leader],
                    groups=[self.make_group()],
                    activities=[activity],
                )
                expected[activity.name] = 6

        body = self.assertConstantQueries(
            "/api/members/{}".format(member.pk), self.admin_user, make_rows
        )
        self.assertEqual(body["skills"], expected)
        self.assertIn(unused.name, body["skills"])
        self.assertEqual(body["skills"][future.name], 0)
        self.assertEqual(len(body["activities"]), 3 + 9)
        excursion = next(e for e in body["activities"] if e["groups"])
        self.assertEqual(len(excursion["groups"]), 1)
        self.assertEqual(len(excursion["participant_ids"]), 3)

    def test_list_trainings(self):
        def make_rows(n):
            for _ in range(n):
                self.counter += 1
                category = TrainingCategory.objects.create(
                    name="Kat {}".format(self.counter), permission_needed=False
                )
                activity = self.make_activity()
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


class ScopedMembersApiQueryCountTestCase(QueryCountMixin, TestCase):
    """The member-scoped lists of a youth leader without global permissions.

    The leader's own group may list and view the members of the youth groups,
    and the leader may list a few members individually. Each row adds such a
    group; the number of queries must not depend on how many there are.
    """

    def setUp(self):
        super().setUp()
        self.leader_user, self.leader = make_member_user("leader")
        leaders_group = self.make_group()
        self.leader.group.set([leaders_group])
        self.group_permissions = PermissionGroup.objects.create(group=leaders_group)
        self.own_permissions = PermissionMember.objects.create(member=self.leader)
        self.listable = {self.leader.pk}
        # Never listable: in a group nobody granted the leader.
        stranger = self.make_member("stranger")
        stranger.group.set([self.make_group()])

    def make_rows(self, n):
        for _ in range(n):
            group = self.make_group()
            self.group_permissions.list_groups.add(group)
            self.group_permissions.view_groups.add(group)
            members = [self.make_member(), self.make_member()]
            for member in members:
                member.group.set([group])
                category = TrainingCategory.objects.create(
                    name="Kat {}".format(self.counter), permission_needed=False
                )
                MemberTraining.objects.create(member=member, title="Kurs", category=category)
            listed = self.make_member("listed")
            self.own_permissions.list_members.add(listed)
            self.listable |= {m.pk for m in members} | {listed.pk}

    def test_list_members(self):
        body = self.assertConstantQueries("/api/members/", self.leader_user, self.make_rows)
        self.assertEqual({m["id"] for m in body}, self.listable)

    def test_list_trainings(self):
        body = self.assertConstantQueries(
            "/api/members/trainings", self.leader_user, self.make_rows
        )
        self.assertEqual(len(body), 2 * 9)
        self.assertTrue({t["member_id"] for t in body} <= self.listable)


class KlettertreffApiQueryCountTestCase(QueryCountMixin, TestCase):
    """The Klettertreff list, detail and attendees, as superuser and as viewer.

    Each row adds a Klettertreff to the list, or youth leaders and attendees to
    the detail; the number of queries must not depend on how many there are.
    """

    def setUp(self):
        super().setUp()
        self.superuser = User.objects.create_superuser("root", password="secret")
        viewer_user, _ = make_member_user("viewer")
        self.viewer = grant(viewer_user, "view_klettertreff")

    def make_member(self, prefix="m", groups=0, confirmed=True):
        member = super().make_member(prefix)
        if not confirmed:
            member.confirmed = False
            member.save()
        member.group.set([self.make_group() for _ in range(groups)])
        return member

    def make_klettertreff(self):
        self.counter += 1
        return Klettertreff.objects.create(
            location="Halle {}".format(self.counter), topic="Toprope", group=self.make_group()
        )

    def check_list(self, user):
        # An unconfirmed youth leader is hidden by the default manager.
        hidden = self.make_klettertreff()
        hidden.jugendleiter.set([self.make_member(), self.make_member(confirmed=False)])
        expected = {hidden.pk: (hidden.group.name, {hidden.jugendleiter.get().name})}

        def make_rows(n):
            for _ in range(n):
                klettertreff = self.make_klettertreff()
                leaders = [self.make_member(), self.make_member()]
                klettertreff.jugendleiter.set(leaders)
                expected[klettertreff.pk] = (
                    klettertreff.group.name,
                    {leader.name for leader in leaders},
                )

        body = self.assertConstantQueries("/api/members/klettertreff", user, make_rows)
        self.assertEqual(
            {k["id"]: (k["group"]["name"], set(k["jugendleiter"])) for k in body}, expected
        )

    def test_list_superuser(self):
        self.check_list(self.superuser)

    def test_list_viewer(self):
        self.check_list(self.viewer)

    def make_people(self, klettertreff, n):
        """Add ``n`` youth leaders and ``n`` attendees, each in two groups."""
        klettertreff.jugendleiter.add(*[self.make_member("leader", groups=2) for _ in range(n)])
        for _ in range(n):
            KlettertreffAttendee.objects.create(
                klettertreff=klettertreff, member=self.make_member(groups=2)
            )

    def expected_people(self, klettertreff):
        def brief(member):
            return (member.name, set(member.group.values_list("name", flat=True)))

        leaders = {m.pk: brief(m) for m in klettertreff.jugendleiter.all()}
        attendees = {
            a.member.pk: brief(a.member) for a in klettertreff.klettertreffattendee_set.all()
        }
        return leaders, attendees

    def check_retrieve(self, user):
        klettertreff = self.make_klettertreff()
        # An unconfirmed leader stays hidden; an unconfirmed attendee is shown.
        klettertreff.jugendleiter.add(self.make_member("leader", groups=1, confirmed=False))
        KlettertreffAttendee.objects.create(
            klettertreff=klettertreff, member=self.make_member(groups=1, confirmed=False)
        )
        body = self.assertConstantQueries(
            "/api/members/klettertreff/{}".format(klettertreff.pk),
            user,
            lambda n: self.make_people(klettertreff, n),
        )
        leaders, attendees = self.expected_people(klettertreff)
        self.assertEqual(len(leaders), 9)
        self.assertEqual(len(attendees), 10)
        self.assertEqual(body["group"]["name"], klettertreff.group.name)
        self.assertEqual(
            {m["id"]: (m["name"], set(m["groups"])) for m in body["jugendleiter"]}, leaders
        )
        self.assertEqual(
            {m["id"]: (m["name"], set(m["groups"])) for m in body["attendees"]}, attendees
        )

    def test_retrieve_superuser(self):
        self.check_retrieve(self.superuser)

    def test_retrieve_viewer(self):
        self.check_retrieve(self.viewer)

    def check_attendees(self, user):
        klettertreff = self.make_klettertreff()
        # Another Klettertreff's attendees are not listed.
        self.make_people(self.make_klettertreff(), 1)
        body = self.assertConstantQueries(
            "/api/members/klettertreff/{}/attendees".format(klettertreff.pk),
            user,
            lambda n: self.make_people(klettertreff, n),
        )
        expected = list(klettertreff.klettertreffattendee_set.order_by("id"))
        self.assertEqual([a["id"] for a in body], [a.pk for a in expected])
        self.assertTrue(all(a["klettertreff_id"] == klettertreff.pk for a in body))
        self.assertEqual(
            [(a["member"]["id"], set(a["member"]["groups"])) for a in body],
            [(a.member.pk, set(a.member.group.values_list("name", flat=True))) for a in expected],
        )

    def test_attendees_superuser(self):
        self.check_attendees(self.superuser)

    def test_attendees_viewer(self):
        self.check_attendees(self.viewer)
