"""End-to-end tests for the finance ledger REST API.

``Ledger`` is registered with a plain :class:`admin.ModelAdmin`, so it uses the
default Django model permissions (``finance.view_ledger`` / ``add_ledger`` /
``change_ledger`` / ``delete_ledger``) checked globally. These tests exercise the
real OAuth2 bearer authentication path and assert the authorized-200 /
unauthorized-403 behaviour for each endpoint.

The ledger router is mounted centrally at ``/api/finance/ledgers``.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from finance.models import Ledger
from members.models import DIVERSE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def make_member_user(username):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=username.title(),
        lastname="Test",
        birth_date=timezone.now().date(),
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    return user, member


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="finance", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


class FinanceLedgerApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # A short secret; the default 128-char one exceeds bcrypt's 72-byte
            # limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.plain_user, self.plain = make_member_user("plain")
        self.manager_user, self.manager = make_member_user("manager")
        self.manager_user = grant(
            self.manager_user,
            "view_ledger",
            "add_ledger",
            "change_ledger",
            "delete_ledger",
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
        self.assertEqual(self.client.get("/api/finance/ledgers/").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get("/api/finance/ledgers/", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- list -------------------------------------------------------------

    def test_list_requires_view_permission(self):
        Ledger.objects.create(name="Bank")
        r = self.client.get("/api/finance/ledgers/", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_list_with_permission(self):
        bank = Ledger.objects.create(name="Bank")
        cash = Ledger.objects.create(name="Cash")
        r = self.client.get("/api/finance/ledgers/", **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({item["id"] for item in r.json()}, {bank.pk, cash.pk})

    # --- retrieve ---------------------------------------------------------

    def test_retrieve_requires_view_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.get(
            "/api/finance/ledgers/{}".format(ledger.pk), **self.auth(self.plain_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_retrieve_with_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.get(
            "/api/finance/ledgers/{}".format(ledger.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], ledger.pk)
        self.assertEqual(body["name"], "Bank")

    def test_retrieve_missing_returns_404(self):
        r = self.client.get("/api/finance/ledgers/999999", **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 404)

    # --- create -----------------------------------------------------------

    def test_create_requires_add_permission(self):
        r = self.client.post(
            "/api/finance/ledgers/",
            data={"name": "Bank"},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Ledger.objects.filter(name="Bank").exists())

    def test_create_with_permission(self):
        r = self.client.post(
            "/api/finance/ledgers/",
            data={"name": "Bank"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        ledger = Ledger.objects.get(pk=r.json()["id"])
        self.assertEqual(ledger.name, "Bank")

    def test_create_missing_name_rejected(self):
        r = self.client.post(
            "/api/finance/ledgers/",
            data={},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422)

    # --- update -----------------------------------------------------------

    def test_update_requires_change_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.patch(
            "/api/finance/ledgers/{}".format(ledger.pk),
            data={"name": "Renamed"},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        ledger.refresh_from_db()
        self.assertEqual(ledger.name, "Bank")

    def test_update_with_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.patch(
            "/api/finance/ledgers/{}".format(ledger.pk),
            data={"name": "Renamed"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        ledger.refresh_from_db()
        self.assertEqual(ledger.name, "Renamed")

    # --- delete -----------------------------------------------------------

    def test_delete_requires_delete_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.delete(
            "/api/finance/ledgers/{}".format(ledger.pk), **self.auth(self.plain_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Ledger.objects.filter(pk=ledger.pk).exists())

    def test_delete_with_permission(self):
        ledger = Ledger.objects.create(name="Bank")
        r = self.client.delete(
            "/api/finance/ledgers/{}".format(ledger.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Ledger.objects.filter(pk=ledger.pk).exists())
