"""Tests for the admin-parity additions to the material REST API.

Covers the expanded ``MaterialPartBrief``/``MaterialPartOut`` (owners overview
and the description/buy_date/lifetime/photo list columns), the multipart photo
update route, and the ``full_clean`` driven 422 on ``PATCH /parts/{id}``.
"""

import datetime
import tempfile
import uuid
from datetime import date
from decimal import Decimal

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone
from material.models import MaterialCategory
from material.models import MaterialPart
from material.models import Ownership
from members.models import MALE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

BASE = "/api/material"


def make_user(username):
    return User.objects.create_user(username=username, password="secret")


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="material", codename=codename)
        )
    return User.objects.get(pk=user.pk)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MaterialPartParityTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.category = MaterialCategory.objects.create(name="Ropes")
        self.part = MaterialPart.objects.create(
            name="Dynamic Rope",
            description="60m rope",
            quantity=5,
            buy_date=date(2023, 1, 2),
            lifetime=Decimal("8"),
        )
        self.part.material_cat.add(self.category)
        self.member = Member.objects.create(
            prename="John",
            lastname="Doe",
            birth_date=date(1990, 1, 1),
            email="john@example.com",
            gender=MALE,
        )
        self.ownership = Ownership.objects.create(material=self.part, owner=self.member, count=3)

        self.viewer_user = grant(make_user("viewer"), "view_materialpart")
        self.editor_user = grant(make_user("editor"), "view_materialpart", "change_materialpart")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- list / brief parity ---------------------------------------------

    def test_part_brief_exposes_new_columns_and_owners(self):
        r = self.client.get(BASE + "/parts", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        row = next(p for p in r.json() if p["id"] == self.part.pk)
        self.assertEqual(row["description"], "60m rope")
        self.assertEqual(row["buy_date"], "2023-01-02")
        self.assertIn(row["lifetime"], ("8", 8))
        self.assertIsNone(row["photo"])
        owner = row["owners"][0]
        self.assertEqual(owner["id"], self.ownership.pk)
        self.assertEqual(owner["owner_id"], self.member.pk)
        self.assertEqual(owner["owner_name"], str(self.member))
        self.assertEqual(owner["count"], 3)

    # --- detail / out parity ---------------------------------------------

    def test_part_detail_exposes_owners(self):
        r = self.client.get(BASE + "/parts/{}".format(self.part.pk), **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        owners = r.json()["owners"]
        self.assertEqual(owners[0]["owner_id"], self.member.pk)
        self.assertEqual(owners[0]["count"], 3)

    # --- photo update -----------------------------------------------------

    def test_photo_update_forbidden_for_viewer(self):
        photo = SimpleUploadedFile("p.png", b"filecontent", content_type="image/png")
        r = self.client.post(
            BASE + "/parts/{}/photo".format(self.part.pk),
            data={"photo": photo},
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_photo_update_allowed_for_editor(self):
        photo = SimpleUploadedFile("p.png", b"filecontent", content_type="image/png")
        r = self.client.post(
            BASE + "/parts/{}/photo".format(self.part.pk),
            data={"photo": photo},
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.part.refresh_from_db()
        self.assertTrue(self.part.photo)

    def test_photo_update_rejects_bad_type(self):
        bad = SimpleUploadedFile("p.txt", b"nope", content_type="text/plain")
        r = self.client.post(
            BASE + "/parts/{}/photo".format(self.part.pk),
            data={"photo": bad},
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        self.part.refresh_from_db()
        self.assertFalse(self.part.photo)

    # --- validation (422) -------------------------------------------------

    def test_update_rejects_out_of_range_lifetime(self):
        r = self.client.patch(
            BASE + "/parts/{}".format(self.part.pk),
            data={"lifetime": "1000"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        self.part.refresh_from_db()
        self.assertEqual(self.part.lifetime, Decimal("8"))
