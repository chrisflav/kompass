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
from django.conf import settings
from django.contrib.auth.models import User
from django.http import HttpResponse
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from django.utils import timezone
from django.utils import translation
from members.models import DIVERSE
from members.models import Member
from members.models.ljp import LJPProposal
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

from jdav_web.middleware import ApiLocaleMiddleware
from jdav_web.middleware import ForwardedProtoForHostsMiddleware

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


class ApiLocaleTest(TestCase):
    """The API answers in the site language, whatever the client asks for."""

    def _language_during(self, path, active="en"):
        seen = {}

        def capture(request):
            seen["lang"] = translation.get_language()
            return HttpResponse()

        translation.activate(active)
        try:
            ApiLocaleMiddleware(capture)(RequestFactory().get(path))
        finally:
            translation.deactivate()
        return seen["lang"]

    def test_an_api_request_is_answered_in_the_site_language(self):
        self.assertEqual(self._language_during("/api/members/"), settings.LANGUAGE_CODE)

    def test_a_request_outside_the_api_keeps_its_negotiated_language(self):
        # Pages under i18n_patterns take their language from the URL prefix and
        # must keep doing so; this middleware is only about the unprefixed API.
        self.assertEqual(self._language_during("/de/kompass/"), "en")

    def test_the_language_cookie_no_longer_decides_the_api_language(self):
        # The regression. LocaleMiddleware reads `django_language` before
        # `Accept-Language`, so ForceLangMiddleware's header rewrite lost to a
        # browser holding the cookie, and the SPA — whose own labels are
        # hardcoded German — showed English values beside them.
        self.client.cookies[settings.LANGUAGE_COOKIE_NAME] = "en"
        response = self.client.get("/api/ping")
        self.assertEqual(response.headers.get("Content-Language"), settings.LANGUAGE_CODE)

    def test_a_choice_label_reads_german_during_an_api_request(self):
        # What the user actually sees: the LJP tab's dropdown values.
        proposal = LJPProposal(category=LJPProposal.LJP_EDUCATIONAL)
        seen = {}

        def capture(request):
            seen["label"] = str(proposal.get_category_display())
            return HttpResponse()

        translation.activate("en")
        try:
            ApiLocaleMiddleware(capture)(RequestFactory().get("/api/members/excursions"))
        finally:
            translation.deactivate()
        self.assertEqual(seen["label"], "Themenorientierte Bildungsmaßnahme")


class ForwardedProtoForHostsTest(TestCase):
    """The proxy-scheme trust must reach the named host and no other."""

    def _scheme_for(self, host, hosts, header="https"):
        with override_settings(
            TRUST_FORWARDED_PROTO_HOSTS=hosts, ALLOWED_HOSTS=["neu.example.org", "alt.example.org"]
        ):
            seen = {}

            def capture(request):
                seen["secure"] = request.is_secure()
                return HttpResponse()

            middleware = ForwardedProtoForHostsMiddleware(capture)
            request = RequestFactory().post("/accounts/login/", HTTP_HOST=host)
            if header is not None:
                request.META["HTTP_X_FORWARDED_PROTO"] = header
            middleware(request)
            return seen["secure"]

    def test_a_named_host_behind_the_proxy_is_secure(self):
        self.assertTrue(self._scheme_for("neu.example.org", ["neu.example.org"]))

    def test_the_old_domain_is_left_exactly_as_it_was(self):
        # The whole point: the domain that has always run without this keeps
        # `is_secure()` False, so its CSRF Referer checking does not tighten.
        self.assertFalse(self._scheme_for("alt.example.org", ["neu.example.org"]))

    def test_an_empty_list_trusts_nobody(self):
        self.assertFalse(self._scheme_for("neu.example.org", []))

    def test_a_request_without_the_header_is_untouched(self):
        self.assertFalse(self._scheme_for("neu.example.org", ["neu.example.org"], header=None))

    def test_a_plain_http_forwarded_proto_is_not_upgraded(self):
        self.assertFalse(self._scheme_for("neu.example.org", ["neu.example.org"], header="http"))

    def test_a_host_outside_allowed_hosts_does_not_raise(self):
        # `get_host()` raises DisallowedHost; the request is refused later
        # anyway, so the middleware must not turn that into a 500 of its own.
        self.assertFalse(self._scheme_for("evil.example.org", ["neu.example.org"]))
