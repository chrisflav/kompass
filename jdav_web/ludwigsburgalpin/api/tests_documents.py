"""End-to-end tests for the ludwigsburgalpin document API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
standard Django model-permission gating for the ``Termin`` overview export,
which reuses ``TerminAdmin.make_overview``. The router is mounted centrally at
``/api/ludwigsburgalpin/documents``.
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

BASE = "/api/ludwigsburgalpin/documents"


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


class LudwigsburgalpinDocumentsApiTestCase(TestCase):
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

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def post_overview(self, user, payload=None):
        return self.client.post(
            BASE + "/termine/overview",
            data=payload if payload is not None else {},
            content_type="application/json",
            **self.auth(user),
        )

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        r = self.client.post(BASE + "/termine/overview", data={}, content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.post(
            BASE + "/termine/overview",
            data={},
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer nope",
        )
        self.assertEqual(r.status_code, 401)

    # --- overview export --------------------------------------------------

    def test_overview_forbidden_without_permission(self):
        make_termin()
        r = self.post_overview(self.plain_user)
        self.assertEqual(r.status_code, 403)

    def test_overview_all_with_permission(self):
        make_termin()
        make_termin(title="Matterhorn")
        r = self.post_overview(self.viewer_user)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/xlsx")
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertTrue(r.getvalue())

    def test_overview_selected_ids_with_permission(self):
        termin = make_termin()
        make_termin(title="Matterhorn")
        r = self.post_overview(self.viewer_user, payload={"termin_ids": [termin.pk]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/xlsx")

    def test_overview_empty_selection_is_valid(self):
        make_termin()
        r = self.post_overview(self.viewer_user, payload={"termin_ids": []})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/xlsx")

    def test_overview_invalid_payload_returns_422(self):
        make_termin()
        r = self.post_overview(self.viewer_user, payload={"termin_ids": "notalist"})
        self.assertEqual(r.status_code, 422)
