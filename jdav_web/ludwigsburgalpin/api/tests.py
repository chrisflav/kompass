"""End-to-end tests for the ludwigsburgalpin REST API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
standard Django model-permission gating for ``Termin``. The router is mounted
centrally at ``/api/ludwigsburgalpin`` (mirroring ``/api/members``).
"""

import datetime
import uuid

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from ludwigsburgalpin.models import Termin
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

BASE = "/api/ludwigsburgalpin"


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="ludwigsburgalpin", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


def make_termin(title="Zugspitze"):
    return Termin.objects.create(
        title=title,
        subtitle="Untertitel",
        start_date=datetime.date(2026, 7, 1),
        end_date=datetime.date(2026, 7, 3),
        group="ASG",
        responsible="Max Mustermann",
        email="max@example.com",
        category="BW",
    )


class LudwigsburgalpinApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # Provide a short secret; the default 128-char one exceeds bcrypt's
            # 72-byte limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.plain_user = User.objects.create_user(username="plain", password="secret")
        self.viewer_user = grant(
            User.objects.create_user(username="viewer", password="secret"),
            "view_termin",
        )
        self.editor_user = grant(
            User.objects.create_user(username="editor", password="secret"),
            "view_termin",
            "add_termin",
            "change_termin",
            "delete_termin",
        )

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        self.assertEqual(self.client.get(BASE + "/termine").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get(BASE + "/termine", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- list -------------------------------------------------------------

    def test_list_forbidden_without_permission(self):
        make_termin()
        r = self.client.get(BASE + "/termine", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_list_with_permission(self):
        termin = make_termin()
        r = self.client.get(BASE + "/termine", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual({t["id"] for t in body}, {termin.pk})
        self.assertEqual(body[0]["group_display"], "Alpinsportgruppe")
        self.assertEqual(body[0]["category_display"], "Bergwandern")

    # --- retrieve ---------------------------------------------------------

    def test_retrieve_forbidden_without_permission(self):
        termin = make_termin()
        r = self.client.get("{}/termine/{}".format(BASE, termin.pk), **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_retrieve_with_permission(self):
        termin = make_termin()
        r = self.client.get("{}/termine/{}".format(BASE, termin.pk), **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], termin.pk)
        self.assertEqual(body["title"], "Zugspitze")
        self.assertEqual(body["klassifizierung_display"], "Gemeinschaftstour")

    def test_retrieve_missing_returns_404(self):
        r = self.client.get(BASE + "/termine/999999", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 404)

    # --- create -----------------------------------------------------------

    def test_create_forbidden_without_permission(self):
        r = self.client.post(
            BASE + "/termine",
            data={
                "title": "Neuer Termin",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "group": "JUG",
                "responsible": "Erika",
                "email": "erika@example.com",
            },
            content_type="application/json",
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Termin.objects.filter(title="Neuer Termin").exists())

    def test_create_with_permission(self):
        r = self.client.post(
            BASE + "/termine",
            data={
                "title": "Neuer Termin",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "group": "JUG",
                "responsible": "Erika",
                "email": "erika@example.com",
                "category": "KL",
            },
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        termin = Termin.objects.get(title="Neuer Termin")
        self.assertEqual(termin.group, "JUG")
        self.assertEqual(termin.category, "KL")
        # Defaults applied for the fields not sent.
        self.assertEqual(termin.max_participants, 10)
        self.assertEqual(termin.condition, "mittel")

    # --- update -----------------------------------------------------------

    def test_update_forbidden_without_permission(self):
        termin = make_termin()
        r = self.client.patch(
            "{}/termine/{}".format(BASE, termin.pk),
            data={"title": "Geaendert"},
            content_type="application/json",
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 403)
        termin.refresh_from_db()
        self.assertEqual(termin.title, "Zugspitze")

    def test_update_with_permission(self):
        termin = make_termin()
        r = self.client.patch(
            "{}/termine/{}".format(BASE, termin.pk),
            data={"title": "Geaendert", "max_participants": 5},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        termin.refresh_from_db()
        self.assertEqual(termin.title, "Geaendert")
        self.assertEqual(termin.max_participants, 5)
        # Untouched fields are preserved.
        self.assertEqual(termin.group, "ASG")

    # --- delete -----------------------------------------------------------

    def test_delete_forbidden_without_permission(self):
        termin = make_termin()
        r = self.client.delete(
            "{}/termine/{}".format(BASE, termin.pk), **self.auth(self.viewer_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Termin.objects.filter(pk=termin.pk).exists())

    def test_delete_with_permission(self):
        termin = make_termin()
        r = self.client.delete(
            "{}/termine/{}".format(BASE, termin.pk), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Termin.objects.filter(pk=termin.pk).exists())
