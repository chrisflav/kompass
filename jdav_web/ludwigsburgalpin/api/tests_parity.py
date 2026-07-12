"""Tests for the admin-parity additions to the ludwigsburgalpin API.

Covers the ``responsible`` column now exposed in ``TerminBrief`` and the new
``GET /enums`` endpoint that surfaces the Termin choice-field options. The
OAuth2 bearer-token auth path and permission gating mirror ``tests.py``.
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


class LudwigsburgalpinParityTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
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
            "change_termin",
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

    # --- brief now exposes responsible ------------------------------------

    def test_brief_exposes_responsible(self):
        make_termin()
        r = self.client.get(BASE + "/termine", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["responsible"], "Max Mustermann")

    # --- enums ------------------------------------------------------------

    def test_enums_forbidden_without_permission(self):
        r = self.client.get(BASE + "/enums", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_enums_requires_authentication(self):
        self.assertEqual(self.client.get(BASE + "/enums").status_code, 401)

    def test_enums_with_permission(self):
        r = self.client.get(BASE + "/enums", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(
            set(body.keys()),
            {
                "group",
                "category",
                "condition",
                "technik",
                "saison",
                "eventart",
                "klassifizierung",
            },
        )
        self.assertIn({"value": "ASG", "label": "Alpinsportgruppe"}, body["group"])
        self.assertIn({"value": "BW", "label": "Bergwandern"}, body["category"])
        self.assertIn(
            {"value": "Gemeinschaftstour", "label": "Gemeinschaftstour"},
            body["klassifizierung"],
        )

    def test_enums_route_not_shadowed_by_termin_id(self):
        # ``/enums`` must resolve to the enum endpoint, not the /{termin_id}
        # detail route (which would 422 on the non-int segment).
        r = self.client.get(BASE + "/enums", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)

    # --- validation (422) -------------------------------------------------

    def test_update_invalid_choice_returns_422(self):
        termin = make_termin()
        r = self.client.patch(
            "{}/termine/{}".format(BASE, termin.pk),
            data={"group": "NOPE"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        termin.refresh_from_db()
        self.assertEqual(termin.group, "ASG")
