"""Personal access tokens: creating, using, limiting and revoking them through the API."""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from feedback.models import Feedback
from logindata.models import PersonalAccessToken
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

AccessToken = get_access_token_model()
Application = get_application_model()
TOKENS = "/api/logindata/tokens"


def bearer(token):
    return {"HTTP_AUTHORIZATION": "Bearer {}".format(token)}


class PersonalAccessTokenApiTestCase(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user("owner", password="secret")
        self.owner.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="logindata", codename="create_personalaccesstoken"
            ),
            Permission.objects.get(content_type__app_label="feedback", codename="view_feedback"),
        )
        self.owner = User.objects.get(pk=self.owner.pk)
        self.other = User.objects.create_user("other", password="secret")
        self.frontend = Application.objects.create(
            name="Kompass",
            client_id=settings.FRONTEND_OAUTH_CLIENT_ID,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="test-secret",
        )

    def session(self, user, application=None):
        """A signed-in session's token, as the SPA holds one."""
        token = AccessToken.objects.create(
            user=user,
            application=application or self.frontend,
            token="session-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(hours=1),
            scope="profile email",
        )
        return bearer(token.token)

    def create(self, headers=None, **payload):
        payload = {"name": "Feedback abholen", "read_only": True, "days": 30, **payload}
        return self.client.post(
            TOKENS,
            data=payload,
            content_type="application/json",
            **(headers or self.session(self.owner)),
        )

    def test_creating_a_token_shows_it_once(self):
        before = timezone.now()
        r = self.create(days=7)
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertTrue(data["token"].startswith("kompass_pat_"))
        self.assertTrue(data["read_only"])
        expires = datetime.datetime.fromisoformat(data["expires"])
        self.assertAlmostEqual(
            (expires - before).total_seconds(), datetime.timedelta(days=7).total_seconds(), delta=60
        )
        # The listing names the token but never repeats its secret.
        listed = self.client.get(TOKENS, **self.session(self.owner)).json()
        self.assertEqual([t["name"] for t in listed], ["Feedback abholen"])
        self.assertNotIn("token", listed[0])
        self.assertEqual(listed[0]["created_by"], listed[0]["user"])

    def test_creating_a_token_takes_the_permission(self):
        r = self.create(headers=self.session(self.other))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(PersonalAccessToken.objects.exists())

    def test_a_token_needs_a_name_and_an_offered_lifetime(self):
        r = self.create(name="  ")
        self.assertEqual(r.status_code, 422)
        self.assertIn("name", r.json()["errors"])
        r = self.create(days=365)
        self.assertEqual(r.status_code, 422)
        self.assertIn("days", r.json()["errors"])
        self.assertFalse(PersonalAccessToken.objects.exists())

    def test_a_read_only_token_reads_but_does_not_write(self):
        token = self.create().json()["token"]
        self.assertEqual(self.client.get("/api/feedback", **bearer(token)).status_code, 200)
        r = self.client.post(
            "/api/feedback",
            data={"message": "Hallo"},
            content_type="application/json",
            **bearer(token),
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json()["displayable"])
        self.assertFalse(Feedback.objects.exists())

    def test_a_writing_token_writes(self):
        token = self.create(read_only=False).json()["token"]
        r = self.client.post(
            "/api/feedback",
            data={"message": "Hallo"},
            content_type="application/json",
            **bearer(token),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(Feedback.objects.exists())

    def test_a_token_cannot_manage_tokens(self):
        # Not even a writing one: it must not mint a wider or longer-lived
        # token, list the tokens, nor revoke its owner's others.
        token = self.create(read_only=False).json()["token"]
        r = self.create(headers=bearer(token))
        self.assertEqual(r.status_code, 403)
        self.assertEqual(PersonalAccessToken.objects.count(), 1)
        self.assertEqual(self.client.get(TOKENS, **bearer(token)).status_code, 403)
        own = PersonalAccessToken.objects.get()
        r = self.client.delete("{}/{}".format(TOKENS, own.pk), **bearer(token))
        self.assertEqual(r.status_code, 403)
        self.assertTrue(PersonalAccessToken.objects.exists())

    def test_another_applications_token_cannot_manage_tokens(self):
        # A token issued to a third-party application signing in with Kompass
        # acts as the user too, but must not turn into a permanent one.
        other_app = Application.objects.create(
            name="Wiki",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="test-secret",
        )
        r = self.create(headers=self.session(self.owner, application=other_app), days=None)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json()["displayable"])
        self.assertFalse(PersonalAccessToken.objects.exists())

    def test_a_deactivated_accounts_token_stops_working(self):
        token = self.create(days=None).json()["token"]
        self.owner.is_active = False
        self.owner.save()
        self.assertEqual(self.client.get("/api/feedback", **bearer(token)).status_code, 401)

    def test_revoking_a_token_ends_it_at_once(self):
        created = self.create().json()
        r = self.client.delete("{}/{}".format(TOKENS, created["id"]), **self.session(self.owner))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(PersonalAccessToken.objects.exists())
        self.assertFalse(AccessToken.objects.filter(token=created["token"]).exists())
        self.assertEqual(self.client.get(TOKENS, **bearer(created["token"])).status_code, 401)

    def test_only_the_owner_sees_and_revokes_a_token(self):
        created = self.create().json()
        self.assertEqual(self.client.get(TOKENS, **self.session(self.other)).json(), [])
        r = self.client.delete("{}/{}".format(TOKENS, created["id"]), **self.session(self.other))
        self.assertEqual(r.status_code, 404)
        self.assertTrue(PersonalAccessToken.objects.exists())

    def test_an_expired_token_is_refused(self):
        created = self.create().json()
        AccessToken.objects.filter(token=created["token"]).update(
            expires=timezone.now() - datetime.timedelta(minutes=1)
        )
        self.assertEqual(self.client.get(TOKENS, **bearer(created["token"])).status_code, 401)

    def test_a_token_may_never_expire(self):
        r = self.create(days=None)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["expires"])
        self.assertIsNone(self.client.get(TOKENS, **self.session(self.owner)).json()[0]["expires"])
        self.assertEqual(
            self.client.get("/api/feedback", **bearer(r.json()["token"])).status_code, 200
        )

    def test_a_superuser_creates_a_token_for_a_bot(self):
        admin = User.objects.create_superuser("admin", password="secret")
        bot = User.objects.create_user("feedback-bot")
        bot.user_permissions.add(
            Permission.objects.get(content_type__app_label="feedback", codename="view_feedback")
        )
        r = self.create(headers=self.session(admin), user_id=bot.pk, days=None)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["user"], {"id": bot.pk, "username": "feedback-bot"})
        self.assertEqual(r.json()["created_by"], {"id": admin.pk, "username": "admin"})
        # The token acts as the bot, with the bot's permissions.
        self.assertEqual(
            self.client.get("/api/feedback", **bearer(r.json()["token"])).status_code, 200
        )
        # The superuser, who manages every account's tokens, sees and revokes it.
        self.create()
        everyone = self.client.get(TOKENS, **self.session(admin)).json()
        self.assertEqual({t["user"]["username"] for t in everyone}, {"feedback-bot", "owner"})
        r = self.client.delete("{}/{}".format(TOKENS, r.json()["id"]), **self.session(admin))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(AccessToken.objects.filter(user=bot).exists())

    def test_only_a_superuser_creates_tokens_for_other_accounts(self):
        r = self.create(user_id=self.other.pk)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json()["displayable"])
        self.assertFalse(PersonalAccessToken.objects.exists())
        # Naming oneself is no other account.
        self.assertEqual(self.create(user_id=self.owner.pk).status_code, 201)

    def test_a_token_for_an_unknown_account_is_a_404(self):
        admin = User.objects.create_superuser("admin", password="secret")
        self.assertEqual(self.create(headers=self.session(admin), user_id=999999).status_code, 404)

    def test_a_token_is_named_by_its_name(self):
        self.create()
        self.assertEqual(str(PersonalAccessToken.objects.get()), "Feedback abholen")
