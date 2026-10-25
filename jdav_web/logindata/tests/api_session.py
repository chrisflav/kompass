"""Signing out of the web interface: the token and the provider's session end together."""

import datetime

from django.conf import settings
from django.contrib.auth.models import User
from django.test import Client
from django.test import TestCase
from django.utils import timezone
from logindata.models import PersonalAccessToken
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

AccessToken = get_access_token_model()
Application = get_application_model()
LOGOUT = "/api/logindata/logout"


class LogoutApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("hannah", password="secret")
        frontend = Application.objects.create(
            name="Kompass",
            client_id=settings.FRONTEND_OAUTH_CLIENT_ID,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="test-secret",
        )
        self.token = AccessToken.objects.create(
            user=self.user,
            application=frontend,
            token="frontend-token",
            expires=timezone.now() + datetime.timedelta(hours=1),
            scope="profile email",
        )
        # The frontend posts without a CSRF token; bearer auth needs none.
        self.client = Client(enforce_csrf_checks=True)
        # The provider's own sign-in, which the login page left in the browser.
        self.client.force_login(self.user)

    def logout(self, token):
        return self.client.post(LOGOUT, HTTP_AUTHORIZATION="Bearer {}".format(token))

    def test_ends_the_token_and_the_session(self):
        r = self.logout("frontend-token")
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(AccessToken.objects.filter(pk=self.token.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_leaves_a_personal_token_alone(self):
        personal = AccessToken.objects.create(
            user=self.user,
            token="kompass_pat_script",
            expires=timezone.now() + datetime.timedelta(days=30),
            scope="",
        )
        PersonalAccessToken.objects.create(access_token=personal, name="Skript", read_only=False)
        r = self.logout("kompass_pat_script")
        self.assertEqual(r.status_code, 204, r.content)
        self.assertTrue(AccessToken.objects.filter(pk=personal.pk).exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_needs_a_token(self):
        r = self.client.post(LOGOUT)
        self.assertEqual(r.status_code, 401)
        # A session cookie on its own signs nobody out.
        self.assertIn("_auth_user_id", self.client.session)
        self.assertTrue(AccessToken.objects.filter(pk=self.token.pk).exists())
