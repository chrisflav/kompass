"""The shared API plumbing, at the edges its callers rarely reach.

These are the branches under ``contrib/api`` and ``jdav_web/api.py`` that every
endpoint depends on but no endpoint test exercises directly: what a bearer token
resolves to when it is unknown, what happens to an account with no member behind
it, and the unauthenticated liveness probe.
"""

import datetime
import uuid

from contrib.api.auth import user_for_token
from contrib.api.perms import Forbidden
from contrib.api.perms import get_member
from contrib.permissions import scope_queryset
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


class BearerTokenTest(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="edge-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.user = User.objects.create_user("edgeuser", password="secret")

    def test_a_known_token_resolves_to_its_user(self):
        token = AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token="tok-{}".format(uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        self.assertEqual(user_for_token(token.token), self.user)

    def test_an_unknown_token_resolves_to_nobody(self):
        # A forged or already-deleted token must not raise its way out of the
        # authenticator; it simply identifies no one.
        self.assertIsNone(user_for_token("does-not-exist"))

    def test_an_expired_token_resolves_to_nobody(self):
        token = AccessToken.objects.create(
            user=self.user,
            application=self.application,
            token="tok-{}".format(uuid.uuid4().hex[:8]),
            expires=timezone.now() - datetime.timedelta(seconds=1),
            scope="read write",
        )
        self.assertIsNone(user_for_token(token.token))


class GetMemberTest(TestCase):
    def test_an_account_without_a_member_is_refused_with_a_reason(self):
        # The whole object-permission model is expressed in terms of a member,
        # so this refusal is the one the user needs to be able to read.
        request = type("R", (), {"user": User.objects.create_user("lonely", password="x")})()
        with self.assertRaises(Forbidden):
            get_member(request)

    def test_an_account_with_a_member_returns_it(self):
        user = User.objects.create_user("linked", password="x")
        member = Member.objects.create(
            prename="Linked", lastname="Person", gender=DIVERSE, email="linked@example.org"
        )
        member.user = user
        member.save()
        request = type("R", (), {"user": User.objects.get(pk=user.pk)})()
        self.assertEqual(get_member(request), member)


class ScopeQuerysetTest(TestCase):
    def test_the_model_is_taken_from_the_queryset_when_not_given(self):
        # Callers may pass `model=` explicitly for a proxy; without it the
        # queryset's own model has to be used.
        user = User.objects.create_user("scoper", password="x")
        scoped = scope_queryset(user, Member.objects.all())
        self.assertEqual(scoped.model, Member)


class PingTest(TestCase):
    def test_ping_answers_without_a_token(self):
        # The liveness probe is the one route that must work before anyone has
        # authenticated at all.
        r = self.client.get("/api/ping")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "ok")
