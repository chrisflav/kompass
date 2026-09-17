"""End-to-end tests for the material REST API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
standard Django model permissions that gate the material endpoints, mirroring
the structure of ``members/tests/api.py``.
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
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


@override_settings(MEDIA_ROOT=tempfile.mkdtemp())
class MaterialApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # Short secret: the default 128-char one exceeds bcrypt's 72-byte
            # limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.category = MaterialCategory.objects.create(name="Ropes")
        self.part = MaterialPart.objects.create(
            name="Dynamic Rope",
            description="60m rope",
            quantity=5,
            buy_date=date.today(),
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

        self.noperm_user = make_user("noperm")
        self.viewer_user = grant(
            make_user("viewer"),
            "view_materialcategory",
            "view_materialpart",
            "view_ownership",
        )
        self.editor_user = grant(
            make_user("editor"),
            "view_materialcategory",
            "add_materialcategory",
            "change_materialcategory",
            "delete_materialcategory",
            "view_materialpart",
            "add_materialpart",
            "change_materialpart",
            "delete_materialpart",
            "view_ownership",
            "add_ownership",
            "change_ownership",
            "delete_ownership",
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
        self.assertEqual(self.client.get(BASE + "/categories").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get(BASE + "/categories", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- categories -------------------------------------------------------

    def test_category_list_forbidden_without_permission(self):
        r = self.client.get(BASE + "/categories", **self.auth(self.noperm_user))
        self.assertEqual(r.status_code, 403)

    def test_category_list_allowed_with_permission(self):
        r = self.client.get(BASE + "/categories", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({c["id"] for c in r.json()}, {self.category.pk})

    def test_category_retrieve_lists_parts(self):
        r = self.client.get(
            BASE + "/categories/{}".format(self.category.pk), **self.auth(self.viewer_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual({p["id"] for p in r.json()["material_parts"]}, {self.part.pk})

    def test_category_create_forbidden_for_viewer(self):
        r = self.client.post(
            BASE + "/categories",
            data={"name": "Hardware"},
            content_type="application/json",
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_category_create_allowed_for_editor(self):
        r = self.client.post(
            BASE + "/categories",
            data={"name": "Hardware"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(MaterialCategory.objects.filter(name="Hardware").exists())

    def test_category_update(self):
        r = self.client.put(
            BASE + "/categories/{}".format(self.category.pk),
            data={"name": "Renamed"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.category.refresh_from_db()
        self.assertEqual(self.category.name, "Renamed")

    def test_category_delete(self):
        r = self.client.delete(
            BASE + "/categories/{}".format(self.category.pk), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(MaterialCategory.objects.filter(pk=self.category.pk).exists())

    # --- parts ------------------------------------------------------------

    def test_part_list_forbidden_without_permission(self):
        r = self.client.get(BASE + "/parts", **self.auth(self.noperm_user))
        self.assertEqual(r.status_code, 403)

    def test_part_list_exposes_computed_fields(self):
        r = self.client.get(BASE + "/parts", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        row = next(p for p in r.json() if p["id"] == self.part.pk)
        self.assertEqual(row["quantity_real"], "3/5")
        self.assertTrue(row["not_too_old"])

    def test_part_retrieve_detail(self):
        r = self.client.get(BASE + "/parts/{}".format(self.part.pk), **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], self.part.pk)
        self.assertIsNone(body["photo"])
        self.assertEqual({c["id"] for c in body["categories"]}, {self.category.pk})

    def test_part_create_forbidden_for_viewer(self):
        r = self.client.post(
            BASE + "/parts",
            data={
                "name": "Helmet",
                "quantity": 2,
                "buy_date": "2023-01-01",
                "lifetime": "5",
            },
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_part_create_with_photo(self):
        photo = SimpleUploadedFile("p.png", b"filecontent", content_type="image/png")
        r = self.client.post(
            BASE + "/parts",
            data={
                "name": "Helmet",
                "description": "climbing helmet",
                "quantity": 2,
                "buy_date": "2023-01-01",
                "lifetime": "5",
                "material_cat": [self.category.pk],
                "photo": photo,
            },
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        part = MaterialPart.objects.get(name="Helmet")
        self.assertTrue(part.photo)
        self.assertEqual({c.pk for c in part.material_cat.all()}, {self.category.pk})

    def test_part_create_without_photo(self):
        r = self.client.post(
            BASE + "/parts",
            data={
                "name": "Sling",
                "quantity": 4,
                "buy_date": "2023-01-01",
                "lifetime": "3",
            },
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(MaterialPart.objects.filter(name="Sling").exists())

    def test_part_create_rejects_bad_photo_type(self):
        bad = SimpleUploadedFile("p.txt", b"nope", content_type="text/plain")
        r = self.client.post(
            BASE + "/parts",
            data={
                "name": "Bad",
                "quantity": 1,
                "buy_date": "2023-01-01",
                "lifetime": "1",
                "photo": bad,
            },
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(MaterialPart.objects.filter(name="Bad").exists())

    def test_part_update(self):
        r = self.client.patch(
            BASE + "/parts/{}".format(self.part.pk),
            data={"quantity": 9, "description": "updated"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantity, 9)
        self.assertEqual(self.part.description, "updated")

    def test_part_delete(self):
        r = self.client.delete(
            BASE + "/parts/{}".format(self.part.pk), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(MaterialPart.objects.filter(pk=self.part.pk).exists())

    # --- ownerships -------------------------------------------------------

    def test_ownership_list_forbidden_without_permission(self):
        r = self.client.get(BASE + "/ownerships", **self.auth(self.noperm_user))
        self.assertEqual(r.status_code, 403)

    def test_ownership_list_exposes_count_and_owner(self):
        r = self.client.get(BASE + "/ownerships", **self.auth(self.viewer_user))
        self.assertEqual(r.status_code, 200)
        row = next(o for o in r.json() if o["id"] == self.ownership.pk)
        self.assertEqual(row["count"], 3)
        self.assertEqual(row["owner"]["id"], self.member.pk)
        self.assertEqual(row["material"]["id"], self.part.pk)

    def test_ownership_create(self):
        r = self.client.post(
            BASE + "/ownerships",
            data={"material": self.part.pk, "owner": self.member.pk, "count": 7},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            Ownership.objects.filter(material=self.part, owner=self.member, count=7).exists()
        )

    def test_ownership_update_count(self):
        r = self.client.patch(
            BASE + "/ownerships/{}".format(self.ownership.pk),
            data={"count": 12},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.ownership.refresh_from_db()
        self.assertEqual(self.ownership.count, 12)

    def test_ownership_delete(self):
        r = self.client.delete(
            BASE + "/ownerships/{}".format(self.ownership.pk), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Ownership.objects.filter(pk=self.ownership.pk).exists())
