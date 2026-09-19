"""End-to-end tests for the public ludwigsburgalpin (Termin submission) API and
for the ``full_clean`` hardening added to the authenticated management router.

The public endpoint is named ``tests_public`` (not ``api_public``) so Django's
``test*.py`` discovery picks it up, mirroring the sibling ``api/tests.py``.
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


class LudwigsburgalpinPublicApiTestCase(TestCase):
    SUBMIT = BASE + "/public/termine"

    def valid_payload(self, **overrides):
        payload = {
            "title": "Oeffentliche Tour",
            "subtitle": "Untertitel",
            "start_date": "2026-08-01",
            "end_date": "2026-08-03",
            "group": "ASG",
            "category": "BW",
            "condition": "mittel",
            "technik": "leicht",
            "saison": "Sommer",
            "eventart": "Einzeltermin",
            "klassifizierung": "Gemeinschaftstour",
            "anforderung_hoehe": 500,
            "anforderung_strecke": 12,
            "anforderung_dauer": 6,
            "max_participants": 15,
            "responsible": "Max Mustermann",
            "email": "max@example.com",
        }
        payload.update(overrides)
        return payload

    def test_submit_creates_termin_without_auth(self):
        r = self.client.post(
            self.SUBMIT, data=self.valid_payload(), content_type="application/json"
        )
        self.assertEqual(r.status_code, 201, r.content)
        termin = Termin.objects.get(title="Oeffentliche Tour")
        self.assertEqual(termin.group, "ASG")
        self.assertEqual(termin.category, "BW")
        self.assertEqual(termin.max_participants, 15)
        self.assertEqual(r.json()["group_display"], "Alpinsportgruppe")

    def test_submit_optional_contact_fields_default_blank(self):
        payload = self.valid_payload()
        del payload["responsible"]
        del payload["email"]
        r = self.client.post(self.SUBMIT, data=payload, content_type="application/json")
        self.assertEqual(r.status_code, 201, r.content)
        termin = Termin.objects.get(title="Oeffentliche Tour")
        self.assertEqual(termin.responsible, "")
        self.assertEqual(termin.email, "")

    def test_submit_missing_required_field_rejected(self):
        payload = self.valid_payload()
        del payload["group"]
        r = self.client.post(self.SUBMIT, data=payload, content_type="application/json")
        self.assertEqual(r.status_code, 422)


class LudwigsburgalpinHardeningApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client-hardening",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.editor = grant(
            User.objects.create_user(username="lba-editor", password="secret"),
            "add_termin",
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

    def test_create_rejects_invalid_choice(self):
        r = self.client.post(
            BASE + "/termine",
            data={
                "title": "Bad",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "group": "NOPE",  # not a valid GRUPPE choice
                "responsible": "Erika",
                "email": "erika@example.com",
            },
            content_type="application/json",
            **self.auth(self.editor),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(Termin.objects.filter(title="Bad").exists())

    def test_create_accepts_valid(self):
        r = self.client.post(
            BASE + "/termine",
            data={
                "title": "Good",
                "start_date": "2026-08-01",
                "end_date": "2026-08-02",
                "group": "JUG",
                "responsible": "Erika",
                "email": "erika@example.com",
                "category": "KL",
            },
            content_type="application/json",
            **self.auth(self.editor),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(Termin.objects.filter(title="Good").exists())

    def test_update_rejects_invalid_choice(self):
        termin = Termin.objects.create(
            title="Editable",
            start_date=datetime.date(2026, 7, 1),
            end_date=datetime.date(2026, 7, 3),
            group="ASG",
            responsible="Max",
            email="max@example.com",
            category="BW",
        )
        r = self.client.patch(
            "{}/termine/{}".format(BASE, termin.pk),
            data={"condition": "unbekannt"},  # not a valid KONDITION choice
            content_type="application/json",
            **self.auth(self.editor),
        )
        self.assertEqual(r.status_code, 422, r.content)
        termin.refresh_from_db()
        self.assertEqual(termin.condition, "mittel")
