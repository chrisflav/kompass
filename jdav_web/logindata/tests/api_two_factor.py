"""Managing one's second factors through the API, and an administrator's reset."""

import datetime
import uuid

import pyotp
from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone
from logindata import two_factor
from logindata.api.two_factor_router import _use_up
from logindata.models import PersonalAccessToken
from logindata.models import TOTPDevice
from logindata.models import TwoFactorSetup
from logindata.models import WebAuthnCredential
from members.models import MALE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from oauth2_provider.models import get_refresh_token_model

from .authenticator import SoftAuthenticator
from .two_factor import add_key
from .two_factor import add_totp

AccessToken = get_access_token_model()
Application = get_application_model()
RefreshToken = get_refresh_token_model()
BASE = "/api/logindata/two-factor"
PASSWORD = "ein-langes-pw-42"


def add_member(user):
    return Member.objects.create(
        prename="Zora",
        lastname="Zwei",
        birth_date="1990-01-01",
        email=settings.TEST_MAIL,
        gender=MALE,
        user=user,
    )


class ApiTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("zweifach", password=PASSWORD)
        self.frontend = Application.objects.create(
            name="Kompass",
            client_id=settings.FRONTEND_OAUTH_CLIENT_ID,
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_AUTHORIZATION_CODE,
            client_secret="test-secret",
        )

    def token(self, user, application=None):
        return AccessToken.objects.create(
            user=user,
            application=application,
            token="t-{}".format(uuid.uuid4().hex),
            expires=timezone.now() + datetime.timedelta(hours=1),
            scope="read write",
        )

    def headers(self, user=None):
        token = self.token(user or self.user, self.frontend)
        return {"HTTP_AUTHORIZATION": "Bearer " + token.token}

    def call(self, method, path, data=None, user=None, headers=None):
        return getattr(self.client, method)(
            BASE + path,
            data=data,
            content_type="application/json",
            **(headers or self.headers(user)),
        )


class TwoFactorApiTestCase(ApiTestCase):
    def setup_totp(self):
        return self.call("post", "/totp/setup", {"password": PASSWORD}).json()

    def test_status_without_factors(self):
        data = self.call("get", "").json()
        self.assertEqual(
            data,
            {"available": True, "enabled": False, "factors": [], "recovery_codes_remaining": 0},
        )

    def test_only_the_frontend_sign_in_manages_factors(self):
        # A personal access token, say, is refused even for reading.
        pat = self.token(self.user)
        PersonalAccessToken.objects.create(access_token=pat, name="Skript", read_only=False)
        r = self.call("get", "", headers={"HTTP_AUTHORIZATION": "Bearer " + pat.token})
        self.assertEqual(r.status_code, 403)

    def test_adding_an_authenticator_app(self):
        setup = self.setup_totp()
        self.assertIn(setup["secret"], setup["uri"])
        code = pyotp.TOTP(setup["secret"]).now()
        r = self.call("post", "/totp", {"name": " Handy ", "code": code, "state": setup["state"]})
        self.assertEqual(r.status_code, 201, r.content)
        added = r.json()
        self.assertEqual(added["factor"]["name"], "Handy")
        self.assertEqual(added["factor"]["kind"], "totp")
        # The first factor comes with the recovery codes, shown this once.
        self.assertEqual(len(added["recovery_codes"]), 10)
        device = TOTPDevice.objects.get()
        self.assertNotIn(setup["secret"], device.encrypted_secret)
        # The code that confirmed the app cannot sign in afterwards.
        self.assertFalse(two_factor.verify_totp(self.user, code))
        status = self.call("get", "").json()
        self.assertTrue(status["enabled"])
        self.assertEqual(status["recovery_codes_remaining"], 10)

        # A second factor leaves the recovery codes as they are.
        setup = self.setup_totp()
        code = pyotp.TOTP(setup["secret"]).now()
        r = self.call("post", "/totp", {"name": "Tablet", "code": code, "state": setup["state"]})
        self.assertEqual(r.json()["recovery_codes"], [])

    def test_the_first_factor_ends_tokens_got_with_the_password_alone(self):
        script = Application.objects.create(
            name="Skript",
            client_id="skript",
            client_secret="skript-secret",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
        )
        old = self.token(self.user, script)
        RefreshToken.objects.create(
            user=self.user, application=script, token="r1", access_token=old
        )
        pat = self.token(self.user)
        PersonalAccessToken.objects.create(access_token=pat, name="Skript", read_only=True)
        session = self.token(self.user, self.frontend)
        RefreshToken.objects.create(
            user=self.user, application=self.frontend, token="r2", access_token=session
        )
        headers = {"HTTP_AUTHORIZATION": "Bearer " + session.token}

        setup = self.call("post", "/totp/setup", {"password": PASSWORD}, headers=headers).json()
        code = pyotp.TOTP(setup["secret"]).now()
        payload = {"name": "Handy", "code": code, "state": setup["state"]}
        self.assertEqual(self.call("post", "/totp", payload, headers=headers).status_code, 201)

        remaining = set(AccessToken.objects.filter(user=self.user).values_list("pk", flat=True))
        self.assertEqual(remaining, {pat.pk, session.pk})
        self.assertEqual(list(RefreshToken.objects.values_list("token", flat=True)), ["r2"])
        r = self.client.get(BASE, HTTP_AUTHORIZATION="Bearer " + old.token)
        self.assertEqual(r.status_code, 401)

        # A further factor leaves other sign-ins alone.
        later = self.token(self.user, self.frontend)
        setup = self.call("post", "/webauthn/setup", {"password": PASSWORD}, headers=headers).json()
        payload = {
            "name": "YubiKey",
            "credential": SoftAuthenticator().create(setup["options"]),
            "state": setup["state"],
        }
        self.assertEqual(self.call("post", "/webauthn", payload, headers=headers).status_code, 201)
        self.assertTrue(AccessToken.objects.filter(pk=later.pk).exists())

    def test_adding_an_app_needs_the_password(self):
        r = self.call("post", "/totp/setup", {"password": "falsch"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("password", r.json()["errors"])

    def test_adding_an_app_needs_a_valid_code_name_and_state(self):
        setup = self.setup_totp()
        code = pyotp.TOTP(setup["secret"]).now()
        cases = [
            ({"name": "Handy", "code": "000000x", "state": setup["state"]}, "code"),
            ({"name": "  ", "code": code, "state": setup["state"]}, "name"),
            ({"name": "x" * 101, "code": code, "state": setup["state"]}, "name"),
            ({"name": "Handy", "code": code, "state": "kaputt"}, "__all__"),
        ]
        for payload, field in cases:
            with self.subTest(field):
                r = self.call("post", "/totp", payload)
                self.assertEqual(r.status_code, 422)
                self.assertIn(field, r.json()["errors"])
        # Another account's setup, or the state of a security key, do not fit.
        other = User.objects.create_user("andere", password=PASSWORD)
        r = self.call(
            "post", "/totp", {"name": "Handy", "code": code, "state": setup["state"]}, user=other
        )
        self.assertEqual(r.status_code, 422)
        key_state = self.call("post", "/webauthn/setup", {"password": PASSWORD}).json()["state"]
        r = self.call("post", "/totp", {"name": "Handy", "code": code, "state": key_state})
        self.assertEqual(r.status_code, 422)
        self.assertFalse(TOTPDevice.objects.exists())

    def test_a_setup_works_once(self):
        setup = self.setup_totp()
        code = pyotp.TOTP(setup["secret"]).now()
        payload = {"name": "Handy", "code": code, "state": setup["state"]}
        self.assertEqual(self.call("post", "/totp", payload).status_code, 201)
        # Replaying the same request adds nothing.
        r = self.call("post", "/totp", payload)
        self.assertEqual(r.status_code, 422)
        self.assertEqual(TOTPDevice.objects.count(), 1)

    def test_a_setup_expires_and_a_new_one_replaces_it(self):
        old = self.setup_totp()
        new = self.setup_totp()
        code = pyotp.TOTP(old["secret"]).now()
        r = self.call("post", "/totp", {"name": "Handy", "code": code, "state": old["state"]})
        self.assertEqual(r.status_code, 422)
        TwoFactorSetup.objects.update(created=timezone.now() - datetime.timedelta(minutes=11))
        code = pyotp.TOTP(new["secret"]).now()
        r = self.call("post", "/totp", {"name": "Handy", "code": code, "state": new["state"]})
        self.assertEqual(r.status_code, 422)

    def test_of_two_racing_confirmations_only_one_uses_the_setup(self):
        self.setup_totp()
        setup = TwoFactorSetup.objects.get()
        _use_up(setup)
        # The other request had found the same setup before it was deleted.
        with self.assertRaises(ValidationError):
            _use_up(setup)

    def test_the_secret_waits_encrypted(self):
        setup = self.setup_totp()
        self.assertNotIn(setup["secret"], TwoFactorSetup.objects.get().encrypted_value)

    def test_adding_a_security_key(self):
        setup = self.call("post", "/webauthn/setup", {"password": PASSWORD}).json()
        options = setup["options"]
        self.assertEqual(options["rp"]["id"], settings.WEBAUTHN_RP_ID)
        authenticator = SoftAuthenticator()
        r = self.call(
            "post",
            "/webauthn",
            {
                "name": "YubiKey",
                "credential": authenticator.create(options),
                "state": setup["state"],
            },
        )
        self.assertEqual(r.status_code, 201, r.content)
        added = r.json()
        self.assertEqual(added["factor"]["kind"], "webauthn")
        self.assertTrue(added["factor"]["passwordless"])
        self.assertEqual(len(added["recovery_codes"]), 10)
        self.assertEqual(WebAuthnCredential.objects.get().credential_id, authenticator.id)

    def test_a_key_that_does_not_verify_is_not_added(self):
        setup = self.call("post", "/webauthn/setup", {"password": PASSWORD}).json()
        options = {**setup["options"], "challenge": "YW5kZXJz"}
        r = self.call(
            "post",
            "/webauthn",
            {
                "name": "YubiKey",
                "credential": SoftAuthenticator().create(options),
                "state": setup["state"],
            },
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(WebAuthnCredential.objects.exists())
        # The failed attempt left the setup for another try.
        r = self.call(
            "post",
            "/webauthn",
            {
                "name": "YubiKey",
                "credential": SoftAuthenticator().create(setup["options"]),
                "state": setup["state"],
            },
        )
        self.assertEqual(r.status_code, 201, r.content)

    def test_renaming_a_factor(self):
        add_totp(self.user)
        key = add_key(self.user)
        r = self.call("patch", "/webauthn/{}".format(key.pk), {"name": "Schlüsselbund"})
        self.assertEqual(r.json()["name"], "Schlüsselbund")
        factors = self.call("get", "").json()["factors"]
        self.assertEqual([f["name"] for f in factors], ["Handy", "Schlüsselbund"])
        # Only one's own.
        other = User.objects.create_user("andere", password=PASSWORD)
        r = self.call("patch", "/webauthn/{}".format(key.pk), {"name": "Meins"}, user=other)
        self.assertEqual(r.status_code, 404)

    def test_removing_factors(self):
        add_member(self.user)
        add_totp(self.user)
        key = add_key(self.user)
        two_factor.generate_recovery_codes(self.user)
        device = self.user.totp_devices.get()
        r = self.call("post", "/totp/{}/remove".format(device.pk), {"password": "falsch"})
        self.assertEqual(r.status_code, 422)
        r = self.call("post", "/totp/{}/remove".format(device.pk), {"password": PASSWORD})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.user.recovery_codes.count(), 10)
        # The user hears of it, in case it was not them.
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("„Handy“", mail.outbox[0].body)
        # With the last one go the recovery codes.
        r = self.call("post", "/webauthn/{}/remove".format(key.pk), {"password": PASSWORD})
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.call("get", "").json()["recovery_codes_remaining"], 0)

    def test_regenerating_recovery_codes(self):
        r = self.call("post", "/recovery-codes", {"password": PASSWORD})
        self.assertEqual(r.status_code, 422)
        add_totp(self.user)
        old = two_factor.generate_recovery_codes(self.user)
        r = self.call("post", "/recovery-codes", {"password": PASSWORD})
        codes = r.json()["codes"]
        self.assertEqual(len(codes), 10)
        self.assertFalse(two_factor.use_recovery_code(self.user, old[0]))
        self.assertTrue(two_factor.use_recovery_code(self.user, codes[0]))

    @override_settings(TWO_FACTOR_MAX_FAILURES=2)
    def test_wrong_passwords_lock_changes(self):
        for _i in range(2):
            self.call("post", "/totp/setup", {"password": "falsch"})
        r = self.call("post", "/totp/setup", {"password": PASSWORD})
        self.assertEqual(r.status_code, 403)
        self.assertTrue(r.json()["displayable"])

    @override_settings(TWO_FACTOR_MAX_FAILURES=2)
    def test_right_passwords_are_not_counted(self):
        for _i in range(3):
            self.assertEqual(
                self.call("post", "/totp/setup", {"password": PASSWORD}).status_code, 200
            )

    @override_settings(OIDC_ENABLED=True)
    def test_nothing_to_change_where_the_provider_signs_in(self):
        self.assertFalse(self.call("get", "").json()["available"])
        r = self.call("post", "/totp/setup", {"password": PASSWORD})
        self.assertEqual(r.status_code, 403)


class ResetTwoFactorTestCase(ApiTestCase):
    def setUp(self):
        super().setUp()
        add_totp(self.user)
        add_key(self.user)
        two_factor.generate_recovery_codes(self.user)
        self.admin = User.objects.create_user("verwalter", password=PASSWORD)
        self.admin.user_permissions.add(
            Permission.objects.get(content_type__app_label="auth", codename="change_user")
        )

    def reset(self, target, user):
        return self.client.post(
            "/api/logindata/users/{}/reset-two-factor".format(target.pk), **self.headers(user)
        )

    def test_a_user_manager_resets_the_factors(self):
        add_member(self.user)
        with self.assertLogs("logindata.api.admin_router", "WARNING"):
            r = self.reset(self.user, self.admin)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["two_factor_enabled"])
        self.assertFalse(two_factor.enabled_for(self.user))
        self.assertFalse(self.user.recovery_codes.exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("zurückgesetzt", mail.outbox[0].body)

    def test_without_the_permission_nothing_happens(self):
        other = User.objects.create_user("andere", password=PASSWORD)
        self.assertEqual(self.reset(self.user, other).status_code, 403)
        self.assertTrue(two_factor.enabled_for(self.user))

    def test_a_superuser_is_reset_only_by_a_superuser(self):
        self.user.is_superuser = True
        self.user.save()
        self.assertEqual(self.reset(self.user, self.admin).status_code, 403)
        boss = User.objects.create_superuser("chefin", password=PASSWORD)
        with self.assertLogs("logindata.api.admin_router", "WARNING"):
            self.assertEqual(self.reset(self.user, boss).status_code, 200)
        self.assertFalse(two_factor.enabled_for(self.user))
