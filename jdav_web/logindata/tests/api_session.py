"""Signing out of the web interface: the token and the provider's session end together."""

import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone
from logindata.models import PersonalAccessToken
from logindata.models import TwoFactorElevation
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from oauth2_provider.models import get_refresh_token_model

AccessToken = get_access_token_model()
Application = get_application_model()
RefreshToken = get_refresh_token_model()
LOGOUT = "/api/logindata/logout"
CSRF = "/api/logindata/csrf"


class LogoutApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hannah", password="secret")
        self.frontend = Application.objects.create(
            name="Kompass",
            client_id=settings.FRONTEND_OAUTH_CLIENT_ID,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="test-secret",
        )
        self.token = self.access_token("frontend-token")
        # The frontend posts without a CSRF token whenever it has a working
        # bearer token, which needs none.
        self.client = Client(enforce_csrf_checks=True)
        # The provider's own sign-in, which the login page left in the browser.
        self.client.force_login(self.user)

    def access_token(self, token, hours=1, application=True):
        return AccessToken.objects.create(
            user=self.user,
            application=self.frontend if application else None,
            token=token,
            expires=timezone.now() + datetime.timedelta(hours=hours),
            scope="profile email",
        )

    def personal(self, token, read_only):
        access_token = self.access_token(token, hours=24, application=False)
        PersonalAccessToken.objects.create(
            access_token=access_token, name="Skript", read_only=read_only
        )
        return access_token

    def logout(self, token=None, csrf=None):
        headers = {}
        if token:
            headers["HTTP_AUTHORIZATION"] = "Bearer {}".format(token)
        if csrf:
            headers["HTTP_X_CSRFTOKEN"] = csrf
        return self.client.post(LOGOUT, **headers)

    def csrf(self):
        r = self.client.get(CSRF)
        self.assertEqual(r.status_code, 200)
        self.assertIn(settings.CSRF_COOKIE_NAME, r.cookies)
        return r.json()["token"]

    def assertSignedOut(self):
        self.assertNotIn("_auth_user_id", self.client.session)

    def assertSignedIn(self):
        self.assertIn("_auth_user_id", self.client.session)

    def test_ends_the_token_and_the_session(self):
        r = self.logout("frontend-token")
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(AccessToken.objects.filter(pk=self.token.pk).exists())
        self.assertSignedOut()

    def test_ends_the_two_factor_confirmation_with_it(self):
        TwoFactorElevation.objects.create(
            access_token=self.token, expires=timezone.now() + datetime.timedelta(minutes=10)
        )
        RefreshToken.objects.create(
            user=self.user, application=self.frontend, token="refresh", access_token=self.token
        )
        self.assertEqual(self.logout("frontend-token").status_code, 204)
        self.assertFalse(TwoFactorElevation.objects.exists())

    def test_ends_the_refresh_token_with_it(self):
        refresh = RefreshToken.objects.create(
            user=self.user, application=self.frontend, token="refresh", access_token=self.token
        )
        r = self.logout("frontend-token")
        self.assertEqual(r.status_code, 204, r.content)
        refresh.refresh_from_db()
        self.assertIsNotNone(refresh.revoked)
        self.assertFalse(AccessToken.objects.filter(pk=self.token.pk).exists())

    def test_ends_the_session_when_the_token_has_expired(self):
        expired = self.access_token("expired-token", hours=-1)
        r = self.logout("expired-token", csrf=self.csrf())
        self.assertEqual(r.status_code, 204, r.content)
        self.assertSignedOut()
        # Its refresh token would otherwise still mint new ones.
        self.assertFalse(AccessToken.objects.filter(pk=expired.pk).exists())

    def test_ends_the_session_without_any_token(self):
        r = self.logout(csrf=self.csrf())
        self.assertEqual(r.status_code, 204, r.content)
        self.assertSignedOut()
        self.assertTrue(AccessToken.objects.filter(pk=self.token.pk).exists())

    def test_a_session_alone_needs_the_csrf_token(self):
        # What a forged request from another page would look like.
        r = self.logout("expired-or-made-up")
        self.assertEqual(r.status_code, 403)
        self.assertSignedIn()

    def test_leaves_a_personal_token_alone(self):
        personal = self.personal("kompass_pat_script", read_only=False)
        r = self.logout("kompass_pat_script")
        self.assertEqual(r.status_code, 204, r.content)
        self.assertTrue(AccessToken.objects.filter(pk=personal.pk).exists())
        self.assertSignedOut()

    def test_a_read_only_personal_token_may_not_sign_out(self):
        personal = self.personal("kompass_pat_reader", read_only=True)
        r = self.logout("kompass_pat_reader")
        self.assertEqual(r.status_code, 403)
        self.assertTrue(AccessToken.objects.filter(pk=personal.pk).exists())
        self.assertSignedIn()

    def test_needs_a_token_or_a_session(self):
        self.client.logout()
        r = self.logout(csrf=self.csrf())
        self.assertEqual(r.status_code, 401)
        self.assertTrue(AccessToken.objects.filter(pk=self.token.pk).exists())


SESSION_REFRESH = "mozilla_django_oidc.middleware.SessionRefresh"


@override_settings(
    MIDDLEWARE=[m for m in settings.MIDDLEWARE if m != SESSION_REFRESH] + [SESSION_REFRESH],
    ROOT_URLCONF="logindata.tests.oidc_urls",
    OIDC_OP_AUTHORIZATION_ENDPOINT="https://idp.example.org/authorize",
    OIDC_RP_CLIENT_ID="kompass",
)
class LogoutWithOidcSessionTestCase(TestCase):
    """Signing out by session where the session came from an OIDC provider.

    Its id token has gone stale, so `SessionRefresh` sends GETs off for a
    silent re-login; a fetch cannot follow that, so the API must be spared.
    """

    def setUp(self):
        self.user = User.objects.create_user("hannah", password="secret")
        self.client = Client(enforce_csrf_checks=True)
        self.client.force_login(self.user, backend="logindata.oidc.MyOIDCAB")

    def test_the_rest_of_the_site_is_refreshed(self):
        # Without this the test below would pass with the middleware asleep.
        r = self.client.get("/de/")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://idp.example.org/authorize"))

    def test_signs_out_without_a_detour_to_the_provider(self):
        r = self.client.get(CSRF)
        self.assertEqual(r.status_code, 200)
        r = self.client.post(LOGOUT, HTTP_X_CSRFTOKEN=r.json()["token"])
        self.assertEqual(r.status_code, 204, r.content)
        self.assertNotIn("_auth_user_id", self.client.session)
