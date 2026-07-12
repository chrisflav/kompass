"""End-to-end tests for the public logindata (registration) API.

Mirrors ``logindata.tests.views`` but exercises the REST endpoints that set a
member's login credentials from an emailed invite link (new account + reset).
"""

from django.contrib.auth.models import Group
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from logindata.models import RegistrationPassword
from members.models import DIVERSE
from members.models import Member


class LogindataPublicApiTestCase(TestCase):
    REGISTER = "/api/logindata/register"

    def setUp(self):
        self.member = Member.objects.create(
            prename="Test",
            lastname="User",
            birth_date=timezone.now().date(),
            email="test@example.com",
            gender=DIVERSE,
            invite_as_user_key="invite_key_new",
        )
        self.reset_member = Member.objects.create(
            prename="Reset",
            lastname="Person",
            birth_date=timezone.now().date(),
            email="reset@example.com",
            gender=DIVERSE,
            invite_as_user_key="invite_key_reset",
        )
        self.reset_user = User.objects.create_user(username="reset.person", password="oldpass123")
        self.reset_member.user = self.reset_user
        self.reset_member.save()
        RegistrationPassword.objects.create(password="invite-secret")
        Group.objects.get_or_create(name="Standard")

    def _post(self, **data):
        return self.client.post(self.REGISTER, data=data, content_type="application/json")

    # --- verify -----------------------------------------------------------

    def test_verify_new_key(self):
        r = self.client.get(self.REGISTER, {"key": self.member.invite_as_user_key})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["name"], self.member.name)
        self.assertFalse(body["is_reset_mode"])
        self.assertEqual(body["suggested_username"], self.member.suggested_username())

    def test_verify_reset_key(self):
        r = self.client.get(self.REGISTER, {"key": self.reset_member.invite_as_user_key})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["is_reset_mode"])

    def test_verify_invalid_key(self):
        r = self.client.get(self.REGISTER, {"key": "nope"})
        self.assertEqual(r.status_code, 404)

    def test_verify_empty_key(self):
        r = self.client.get(self.REGISTER, {"key": ""})
        self.assertEqual(r.status_code, 404)

    # --- set password: new account ---------------------------------------

    def test_wrong_registration_password_rejected(self):
        r = self._post(
            key=self.member.invite_as_user_key,
            registration_password="wrong",
            new_password1="Str0ngPass!x",
            new_password2="Str0ngPass!x",
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(User.objects.filter(username=self.member.suggested_username()).exists())

    def test_create_user_success(self):
        r = self._post(
            key=self.member.invite_as_user_key,
            registration_password="invite-secret",
            username="testuser",
            new_password1="Str0ngPass!x",
            new_password2="Str0ngPass!x",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["is_reset_mode"])
        user = User.objects.get(username="testuser")
        self.assertTrue(user.is_staff)
        self.member.refresh_from_db()
        self.assertEqual(self.member.user, user)
        self.assertEqual(self.member.invite_as_user_key, "")

    def test_create_user_defaults_username(self):
        r = self._post(
            key=self.member.invite_as_user_key,
            registration_password="invite-secret",
            new_password1="Str0ngPass!x",
            new_password2="Str0ngPass!x",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(User.objects.filter(username=self.member.suggested_username()).exists())

    def test_create_user_password_mismatch_rejected(self):
        r = self._post(
            key=self.member.invite_as_user_key,
            registration_password="invite-secret",
            username="mismatch",
            new_password1="Str0ngPass!x",
            new_password2="Different!y9",
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(User.objects.filter(username="mismatch").exists())

    def test_create_user_missing_standard_group_fails(self):
        Group.objects.filter(name="Standard").delete()
        r = self._post(
            key=self.member.invite_as_user_key,
            registration_password="invite-secret",
            username="nogroup",
            new_password1="Str0ngPass!x",
            new_password2="Str0ngPass!x",
        )
        self.assertEqual(r.status_code, 422)

    def test_invalid_key_on_set_password(self):
        r = self._post(
            key="nope",
            registration_password="invite-secret",
            new_password1="Str0ngPass!x",
            new_password2="Str0ngPass!x",
        )
        self.assertEqual(r.status_code, 404)

    # --- set password: reset mode ----------------------------------------

    def test_reset_password_success(self):
        r = self._post(
            key=self.reset_member.invite_as_user_key,
            registration_password="invite-secret",
            new_password1="Res3tPass!x",
            new_password2="Res3tPass!x",
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["is_reset_mode"])
        self.reset_user.refresh_from_db()
        self.assertTrue(self.reset_user.check_password("Res3tPass!x"))
        self.reset_member.refresh_from_db()
        self.assertEqual(self.reset_member.invite_as_user_key, "")

    def test_reset_password_mismatch_rejected(self):
        r = self._post(
            key=self.reset_member.invite_as_user_key,
            registration_password="invite-secret",
            new_password1="Res3tPass!x",
            new_password2="Other!Pass9",
        )
        self.assertEqual(r.status_code, 422)
        self.reset_user.refresh_from_db()
        self.assertTrue(self.reset_user.check_password("oldpass123"))
