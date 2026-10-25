"""Second factors: the building blocks, the login's second step and the passkey login."""

import base64
import hashlib
import json
import time
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlsplit

import pyotp
from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.core.management import call_command
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone
from logindata import login_views
from logindata import two_factor
from logindata.login_views import PENDING_KEY
from logindata.models import TOTPDevice
from logindata.models import TwoFactorAttempts
from logindata.models import WebAuthnCredential
from members.models import MALE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from webauthn.helpers.structs import UserVerificationRequirement

from .authenticator import b64
from .authenticator import SoftAuthenticator

AccessToken = get_access_token_model()
Application = get_application_model()
PASSWORD = "ein-langes-pw-42"


def add_totp(user, secret=None, name="Handy"):
    secret = secret or pyotp.random_base32()
    TOTPDevice.objects.create(
        user=user, name=name, encrypted_secret=two_factor.encrypt_secret(secret)
    )
    return secret


def next_code(secret, steps=0):
    """A valid code of the current time step, or ``steps`` later (within the drift)."""
    return pyotp.TOTP(secret).at(timezone.now(), counter_offset=steps)


def add_key(user, authenticator=None, name="Schlüssel"):
    """Register ``authenticator`` for ``user`` through the real registration ceremony."""
    authenticator = authenticator or SoftAuthenticator()
    options, challenge = two_factor.registration_options(user)
    return two_factor.register_credential(user, name, authenticator.create(options), challenge)


class TwoFactorModuleTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("zweifach", password=PASSWORD)

    def test_secrets_are_stored_encrypted_and_survive_a_key_rotation(self):
        token = two_factor.encrypt_secret("GEHEIM")
        self.assertNotIn("GEHEIM", token)
        self.assertEqual(two_factor.decrypt_secret(token), "GEHEIM")
        with override_settings(
            SECRET_KEY="ein-neuer-schluessel", SECRET_KEY_FALLBACKS=[settings.SECRET_KEY]
        ):
            self.assertEqual(two_factor.decrypt_secret(token), "GEHEIM")
        with override_settings(SECRET_KEY="ein-ganz-anderer-schluessel"):
            self.assertIsNone(two_factor.decrypt_secret(token))

    def test_a_totp_code_is_accepted_once(self):
        secret = add_totp(self.user)
        code = next_code(secret)
        self.assertTrue(two_factor.verify_totp(self.user, code))
        self.assertFalse(two_factor.verify_totp(self.user, code))
        self.assertFalse(two_factor.verify_totp(self.user, "000000x"))
        # The next time step is still within the allowed drift.
        self.assertTrue(two_factor.verify_totp(self.user, next_code(secret, 1)))
        self.assertIsNotNone(TOTPDevice.objects.get().last_used)

    def test_a_secret_no_key_decrypts_matches_nothing(self):
        TOTPDevice.objects.create(user=self.user, name="Alt", encrypted_secret="kaputt")
        with self.assertLogs("logindata.two_factor", "ERROR") as logs:
            self.assertFalse(two_factor.verify_totp(self.user, "123456"))
        self.assertIn("SECRET_KEY_FALLBACKS", logs.output[0])

    def test_the_uri_names_the_account_and_the_issuer(self):
        uri = two_factor.totp_uri("JBSWY3DPEHPK3PXP", self.user)
        self.assertTrue(uri.startswith("otpauth://totp/"))
        self.assertIn("zweifach", uri)
        self.assertIn("issuer=", uri)

    def test_recovery_codes_are_hashed_and_used_once(self):
        codes = two_factor.generate_recovery_codes(self.user)
        self.assertEqual(len(codes), 10)
        self.assertEqual(len(set(codes)), 10)
        self.assertRegex(codes[0], r"^[a-z2-7]{4}(-[a-z2-7]{4}){3}$")
        stored = list(self.user.recovery_codes.values_list("code_hash", flat=True))
        self.assertNotIn(codes[0], stored)
        # Typed in capitals and without dashes, it still counts.
        self.assertTrue(two_factor.use_recovery_code(self.user, codes[0].upper().replace("-", "")))
        self.assertFalse(two_factor.use_recovery_code(self.user, codes[0]))
        self.assertEqual(self.user.recovery_codes.count(), 9)
        # New codes replace the old ones.
        two_factor.generate_recovery_codes(self.user)
        self.assertFalse(two_factor.use_recovery_code(self.user, codes[1]))

    def lock_seconds(self):
        locked_until = TwoFactorAttempts.objects.get(user=self.user).locked_until
        return round((locked_until - timezone.now()).total_seconds() / 60) * 60

    def unlock(self):
        TwoFactorAttempts.objects.update(locked_until=timezone.now() - timedelta(seconds=1))

    @override_settings(TWO_FACTOR_MAX_FAILURES=3)
    def test_attempts_lock_the_account_for_longer_each_time(self):
        self.assertEqual([two_factor.claim_attempt(self.user) for _i in range(3)], [1, 2, 3])
        self.assertIsNone(two_factor.claim_attempt(self.user))
        self.assertEqual(self.lock_seconds(), 900)
        # The count goes on after the lock, and the next lock is twice as long.
        self.unlock()
        self.assertEqual([two_factor.claim_attempt(self.user) for _i in range(3)], [4, 5, 6])
        self.assertEqual(self.lock_seconds(), 1800)
        # At most a day.
        TwoFactorAttempts.objects.update(failures=29, locked_until=None)
        two_factor.claim_attempt(self.user)
        self.assertEqual(self.lock_seconds(), 24 * 3600)
        # Only a second factor starts the count again.
        two_factor.record_success(self.user)
        self.assertEqual(two_factor.claim_attempt(self.user), 1)

    @override_settings(TWO_FACTOR_MAX_FAILURES=2)
    def test_a_right_password_is_taken_back(self):
        two_factor.refund_attempt(self.user, two_factor.claim_attempt(self.user))
        self.assertEqual(TwoFactorAttempts.objects.get().failures, 0)
        two_factor.claim_attempt(self.user)
        # The attempt that would have locked the account lifts the lock again.
        two_factor.refund_attempt(self.user, two_factor.claim_attempt(self.user))
        self.assertEqual(two_factor.claim_attempt(self.user), 2)

    @override_settings(TWO_FACTOR_MAX_FAILURES=2)
    def test_the_first_lock_is_mailed(self):
        Member.objects.create(
            prename="Zora",
            lastname="Zwei",
            birth_date="1990-01-01",
            email=settings.TEST_MAIL,
            gender=MALE,
            user=self.user,
        )
        for _i in range(4):
            number = two_factor.claim_attempt(self.user)
            two_factor.attempt_failed(self.user, number)
            self.unlock()
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("Zora", mail.outbox[0].body)
        self.assertIn("gesperrt", mail.outbox[0].body)

    def test_no_mail_without_a_member(self):
        two_factor.notify(self.user, "Betreff", "Hallo {name}")
        self.assertEqual(mail.outbox, [])

    def test_whether_a_login_needs_a_second_step(self):
        self.assertFalse(two_factor.required_for(self.user))
        # Recovery codes alone are no second factor.
        two_factor.generate_recovery_codes(self.user)
        self.assertFalse(two_factor.enabled_for(self.user))
        add_totp(self.user)
        self.assertTrue(two_factor.required_for(self.user))

    def test_removing_the_last_factor_takes_the_recovery_codes(self):
        add_totp(self.user)
        add_key(self.user)
        two_factor.generate_recovery_codes(self.user)
        self.user.totp_devices.all().delete()
        two_factor.factor_removed(self.user)
        self.assertEqual(self.user.recovery_codes.count(), 10)
        self.user.webauthn_credentials.all().delete()
        two_factor.factor_removed(self.user)
        self.assertEqual(self.user.recovery_codes.count(), 0)

    def test_remove_all(self):
        add_totp(self.user)
        add_key(self.user)
        two_factor.generate_recovery_codes(self.user)
        two_factor.claim_attempt(self.user)
        two_factor.remove_all(self.user)
        self.assertFalse(two_factor.enabled_for(self.user))
        self.assertFalse(self.user.recovery_codes.exists())
        self.assertFalse(TwoFactorAttempts.objects.exists())

    def test_factors_are_named(self):
        add_totp(self.user, name="Handy")
        self.assertEqual(str(TOTPDevice.objects.get()), "Handy")
        self.assertEqual(str(add_key(self.user, name="YubiKey")), "YubiKey")

    def test_registering_a_key(self):
        key = add_key(self.user)
        self.assertTrue(key.discoverable)
        self.assertEqual(key.sign_count, 0)
        options, _challenge = two_factor.registration_options(self.user)
        # Asks for a resident key without insisting, and excludes keys already there.
        self.assertEqual(options["authenticatorSelection"]["residentKey"], "preferred")
        self.assertEqual(options["excludeCredentials"][0]["id"], key.credential_id)
        self.assertEqual(options["extensions"], {"credProps": True})

    def test_a_key_without_resident_credential_or_verification_is_no_passkey(self):
        self.assertFalse(add_key(self.user, SoftAuthenticator(resident=False)).discoverable)
        self.assertFalse(
            add_key(self.user, SoftAuthenticator(user_verification=False)).discoverable
        )

    def test_registration_refuses_a_wrong_answer(self):
        authenticator = SoftAuthenticator()
        options, challenge = two_factor.registration_options(self.user)
        other_options, _other = two_factor.registration_options(self.user)
        with self.assertRaises(two_factor.InvalidCredential):
            two_factor.register_credential(
                self.user, "x", authenticator.create(other_options), challenge
            )
        with self.assertRaises(two_factor.InvalidCredential):
            two_factor.register_credential(
                self.user,
                "x",
                authenticator.create(options, origin="https://evil.example"),
                challenge,
            )
        with self.assertRaises(two_factor.InvalidCredential):
            two_factor.register_credential(self.user, "x", {"id": "kaputt"}, challenge)
        two_factor.register_credential(self.user, "x", authenticator.create(options), challenge)
        # The same key a second time.
        with self.assertRaises(two_factor.InvalidCredential):
            two_factor.register_credential(self.user, "y", authenticator.create(options), challenge)

    def test_authenticating_with_a_key(self):
        authenticator = SoftAuthenticator()
        key = add_key(self.user, authenticator)
        credentials = WebAuthnCredential.objects.all()
        options, challenge = two_factor.authentication_options(
            [key], UserVerificationRequirement.PREFERRED
        )
        self.assertEqual(options["allowCredentials"][0]["id"], key.credential_id)
        stored = two_factor.authenticate_credential(
            credentials, authenticator.get(options), challenge, True
        )
        self.assertEqual(stored, key)
        stored.refresh_from_db()
        self.assertEqual(stored.sign_count, 1)
        self.assertIsNotNone(stored.last_used)

    def test_authentication_refuses_a_wrong_answer(self):
        authenticator = SoftAuthenticator(user_verification=False)
        add_key(self.user, authenticator)
        credentials = WebAuthnCredential.objects.all()
        options, challenge = two_factor.authentication_options(
            [], UserVerificationRequirement.REQUIRED
        )
        cases = {
            "unknown key": SoftAuthenticator().get(options),
            "no user verification": authenticator.get(options),
            "another account": {
                **authenticator.get(options),
                "response": {
                    **authenticator.get(options)["response"],
                    "userHandle": b64(b"999"),
                },
            },
            "malformed": {"id": authenticator.id},
        }
        for case, credential in cases.items():
            with self.subTest(case), self.assertRaises(two_factor.InvalidCredential):
                two_factor.authenticate_credential(credentials, credential, challenge, True)
        # The account check also applies to a key that verifies its user.
        verifying = SoftAuthenticator()
        add_key(self.user, verifying)
        with self.assertRaises(two_factor.InvalidCredential):
            two_factor.authenticate_credential(
                credentials, verifying.get(options, user_handle=b64(b"999")), challenge, True
            )

    def test_challenges_are_used_once_and_for_one_purpose(self):
        session = {}
        two_factor.store_challenge(session, "login", "abc")
        self.assertIsNone(two_factor.pop_challenge(session, "passkey"))
        self.assertIsNone(two_factor.pop_challenge(session, "login"))
        two_factor.store_challenge(session, "login", "abc")
        self.assertEqual(two_factor.pop_challenge(session, "login"), "abc")
        self.assertIsNone(two_factor.pop_challenge(session, "login"))
        two_factor.store_challenge(session, "login", "abc")
        session["two_factor_challenge"]["expires"] = time.time() - 1
        self.assertIsNone(two_factor.pop_challenge(session, "login"))


@override_settings(OIDC_ENABLED=False)
class SecondStepLoginTestCase(TestCase):
    """After the password, a user with a second factor is not logged in yet."""

    def setUp(self):
        self.user = User.objects.create_user("zweifach", password=PASSWORD)
        self.secret = add_totp(self.user)

    def password(self, next_url=""):
        data = {"username": "zweifach", "password": PASSWORD}
        if next_url:
            data["next"] = next_url
        return self.client.post("/accounts/login/", data)

    def assertLoggedIn(self, user=None):
        self.assertEqual(self.client.session.get("_auth_user_id"), str((user or self.user).pk))

    def assertNotLoggedIn(self):
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_without_a_second_factor_the_password_suffices(self):
        User.objects.create_user("einfach", password=PASSWORD)
        r = self.client.post("/accounts/login/", {"username": "einfach", "password": PASSWORD})
        self.assertEqual(r["Location"], settings.LOGIN_REDIRECT_URL)
        self.assertIn("_auth_user_id", self.client.session)

    def test_the_password_leads_to_the_second_step_only(self):
        r = self.password()
        self.assertRedirects(r, "/accounts/login/two-factor/", fetch_redirect_response=False)
        self.assertNotLoggedIn()
        # Nothing behind a login sees the user yet.
        self.assertEqual(self.client.get("/de/kompass/").status_code, 302)
        page = self.client.get("/accounts/login/two-factor/")
        self.assertContains(page, 'name="code"')
        self.assertContains(page, 'value="recovery"')
        # Without a key, no button for one.
        self.assertNotContains(page, "data-webauthn-form")

    def test_a_code_finishes_the_login(self):
        self.password(next_url="/de/kompass/members/")
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "totp", "code": next_code(self.secret)}
        )
        self.assertEqual(r["Location"], "/de/kompass/members/")
        self.assertLoggedIn()
        self.assertNotIn(PENDING_KEY, self.client.session)

    def test_a_recovery_code_finishes_the_login_once(self):
        codes = two_factor.generate_recovery_codes(self.user)
        self.password()
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "recovery", "code": codes[0]}
        )
        self.assertEqual(r["Location"], settings.LOGIN_REDIRECT_URL)
        self.assertLoggedIn()
        self.client.logout()
        self.password()
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "recovery", "code": codes[0]}
        )
        self.assertEqual(r.status_code, 200)
        self.assertNotLoggedIn()

    @override_settings(TWO_FACTOR_MAX_FAILURES=3)
    def test_wrong_codes_lock_the_second_step(self):
        self.password()
        for _i in range(3):
            r = self.client.post(
                "/accounts/login/two-factor/", {"method": "totp", "code": "000000"}
            )
            self.assertEqual(r.context["error"], login_views.WRONG)
        # Even the right code is refused now, from any session.
        self.client.logout()
        self.password()
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "totp", "code": next_code(self.secret)}
        )
        self.assertEqual(r.context["error"], login_views.LOCKED)
        self.assertNotLoggedIn()

    def test_an_app_no_key_decrypts_is_not_counted_against_the_user(self):
        TOTPDevice.objects.update(encrypted_secret="kaputt")
        self.password()
        with self.assertLogs("logindata.two_factor", "ERROR"):
            r = self.client.post(
                "/accounts/login/two-factor/", {"method": "totp", "code": "123456"}
            )
        self.assertEqual(r.context["error"], login_views.UNREADABLE)
        self.assertFalse(TwoFactorAttempts.objects.exists())

    def test_the_second_step_expires(self):
        self.password()
        session = self.client.session
        session[PENDING_KEY]["expires"] = time.time() - 1
        session.save()
        r = self.client.get("/accounts/login/two-factor/")
        self.assertEqual(r["Location"], settings.LOGIN_URL)
        self.assertNotIn(PENDING_KEY, self.client.session)

    def test_a_password_change_ends_the_second_step(self):
        self.password()
        self.user.set_password("ein-anderes-pw-43")
        self.user.save()
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "totp", "code": next_code(self.secret)}
        )
        self.assertEqual(r["Location"], settings.LOGIN_URL)
        self.assertNotLoggedIn()

    def test_without_a_password_there_is_no_second_step(self):
        r = self.client.get("/accounts/login/two-factor/")
        self.assertEqual(r["Location"], settings.LOGIN_URL)
        self.assertEqual(self.client.post("/accounts/login/two-factor/options/").status_code, 404)

    def test_a_security_key_finishes_the_login(self):
        authenticator = SoftAuthenticator(user_verification=False, resident=False)
        add_key(self.user, authenticator)
        self.password()
        page = self.client.get("/accounts/login/two-factor/")
        self.assertContains(page, "data-webauthn-form")
        options = self.client.post("/accounts/login/two-factor/options/").json()["publicKey"]
        self.assertEqual(options["userVerification"], "preferred")
        self.assertEqual(len(options["allowCredentials"]), 1)
        credential = json.dumps(authenticator.get(options))
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "webauthn", "credential": credential}
        )
        self.assertEqual(r["Location"], settings.LOGIN_REDIRECT_URL)
        self.assertLoggedIn()

    def test_a_key_answer_without_a_challenge_or_in_pieces_fails(self):
        authenticator = SoftAuthenticator()
        add_key(self.user, authenticator)
        self.password()
        options = self.client.post("/accounts/login/two-factor/options/").json()["publicKey"]
        for credential in ("kein json", "[1]"):
            with self.subTest(credential):
                r = self.client.post(
                    "/accounts/login/two-factor/", {"method": "webauthn", "credential": credential}
                )
                self.assertEqual(r.status_code, 200)
        # The challenge was used up by the first attempt.
        credential = json.dumps(authenticator.get(options))
        self.client.post(
            "/accounts/login/two-factor/", {"method": "webauthn", "credential": credential}
        )
        self.assertNotLoggedIn()
        # Another user's key does not stand in for one's own.
        other = User.objects.create_user("andere", password=PASSWORD)
        stranger = SoftAuthenticator()
        add_key(other, stranger)
        options = self.client.post("/accounts/login/two-factor/options/").json()["publicKey"]
        credential = json.dumps(stranger.get(options))
        self.client.post(
            "/accounts/login/two-factor/", {"method": "webauthn", "credential": credential}
        )
        self.assertNotLoggedIn()


@override_settings(OIDC_ENABLED=False)
class PasskeyLoginTestCase(TestCase):
    """One tap on a passkey signs in without a password."""

    def setUp(self):
        self.user = User.objects.create_user("schluessel", password=PASSWORD)
        self.authenticator = SoftAuthenticator()
        add_key(self.user, self.authenticator)

    def answer(self, authenticator=None):
        options = self.client.post("/accounts/login/passkey/options/").json()["publicKey"]
        return json.dumps((authenticator or self.authenticator).get(options))

    def test_the_login_page_offers_it(self):
        page = self.client.get("/accounts/login/")
        self.assertContains(page, 'action="/accounts/login/passkey/"')
        self.assertContains(page, "webauthn-login.js")

    def test_a_passkey_signs_in(self):
        options = self.client.post("/accounts/login/passkey/options/").json()["publicKey"]
        self.assertEqual(options["userVerification"], "required")
        self.assertEqual(options["allowCredentials"], [])
        credential = json.dumps(self.authenticator.get(options))
        r = self.client.post(
            "/accounts/login/passkey/", {"credential": credential, "next": "/de/kompass/members/"}
        )
        self.assertEqual(r["Location"], "/de/kompass/members/")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.user.pk))

    def test_a_foreign_next_is_not_followed(self):
        r = self.client.post(
            "/accounts/login/passkey/",
            {"credential": self.answer(), "next": "https://evil.example/"},
        )
        self.assertEqual(r["Location"], settings.LOGIN_REDIRECT_URL)

    def test_a_plain_security_key_does_not_sign_in_alone(self):
        plain = SoftAuthenticator(resident=False)
        add_key(self.user, plain)
        r = self.client.post("/accounts/login/passkey/", {"credential": self.answer(plain)})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.context["passkey_error"], login_views.PASSKEY_FAILED)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_deactivated_account_does_not_sign_in(self):
        self.user.is_active = False
        self.user.save()
        r = self.client.post("/accounts/login/passkey/", {"credential": self.answer()})
        self.assertEqual(r.status_code, 400)

    def test_without_a_challenge_nothing_happens(self):
        options = {"rpId": settings.WEBAUTHN_RP_ID, "challenge": b64(b"selbst-gemacht")}
        credential = json.dumps(self.authenticator.get(options))
        r = self.client.post("/accounts/login/passkey/", {"credential": credential})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.client.get("/accounts/login/passkey/").status_code, 405)


class LoginWithIdentityProviderTestCase(TestCase):
    @override_settings(OIDC_ENABLED=True)
    def test_no_second_step_or_passkey_where_the_provider_signs_in(self):
        self.assertEqual(self.client.get("/accounts/login/two-factor/").status_code, 404)
        for path in (
            "/accounts/login/two-factor/options/",
            "/accounts/login/passkey/",
            "/accounts/login/passkey/options/",
        ):
            with self.subTest(path):
                self.assertEqual(self.client.post(path).status_code, 404)


class AdminLoginTestCase(TestCase):
    """The admin's own password form is gone; it sends everyone to LOGIN_URL."""

    def test_anonymous_visitors_go_to_the_login_page(self):
        r = self.client.get("/de/kompass/login/?next=/de/kompass/members/")
        self.assertEqual(r["Location"], settings.LOGIN_URL + "?next=/de/kompass/members/")
        # A password posted there logs no one in.
        User.objects.create_user("admin", password=PASSWORD, is_staff=True)
        self.client.post("/de/kompass/login/", {"username": "admin", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_foreign_next_is_replaced(self):
        r = self.client.get("/de/kompass/login/?next=https://evil.example/")
        self.assertEqual(r["Location"], settings.LOGIN_URL + "?next=/de/kompass")

    def test_signed_in_staff_go_straight_on(self):
        self.client.force_login(User.objects.create_user("staff", is_staff=True))
        r = self.client.get("/de/kompass/login/?next=/de/kompass/members/")
        self.assertEqual(r["Location"], "/de/kompass/members/")


@override_settings(OIDC_ENABLED=False)
class AuthorizeWithSecondFactorTestCase(TestCase):
    """The whole way of the frontend's sign-in, with an authenticator app."""

    def test_authorize_login_second_step_token(self):
        user = User.objects.create_user("zweifach", password=PASSWORD)
        secret = add_totp(user)
        client_id = settings.FRONTEND_OAUTH_CLIENT_ID
        redirect_uri = "http://localhost:5173/callback"
        call_command(
            "ensure_frontend_oauth_app", "--client-id", client_id, "--redirect-uri", redirect_uri
        )
        verifier = "v" * 64
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        authorize = "/de/o/authorize/?" + urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "profile email",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "state": "xyz",
            }
        )

        # Anonymous: sent to the login form.
        r = self.client.get(authorize)
        login_url = urlsplit(r["Location"])
        self.assertEqual(login_url.path, settings.LOGIN_URL)
        next_url = parse_qs(login_url.query)["next"][0]

        # The password leads to the second step, and /o/authorize/ still sees no one.
        r = self.client.post(
            settings.LOGIN_URL, {"username": "zweifach", "password": PASSWORD, "next": next_url}
        )
        self.assertEqual(r["Location"], "/accounts/login/two-factor/")
        self.assertEqual(urlsplit(self.client.get(authorize)["Location"]).path, settings.LOGIN_URL)

        # The code finishes the login and returns to the authorization request.
        r = self.client.post(
            "/accounts/login/two-factor/", {"method": "totp", "code": next_code(secret)}
        )
        self.assertEqual(r["Location"], next_url)
        r = self.client.get(next_url)
        callback = urlsplit(r["Location"])
        self.assertEqual(
            "{}://{}{}".format(callback.scheme, callback.netloc, callback.path), redirect_uri
        )
        code = parse_qs(callback.query)["code"][0]

        token = self.client.post(
            "/o/token/",
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        self.assertEqual(token.status_code, 200, token.content)
        access = token.json()["access_token"]
        me = self.client.get("/api/logindata/two-factor", HTTP_AUTHORIZATION="Bearer " + access)
        self.assertTrue(me.json()["enabled"])


class PasswordGrantTestCase(TestCase):
    """The OAuth password grant swaps a password for a token, with no second step."""

    def setUp(self):
        Application.objects.create(
            name="Skript",
            client_id="skript",
            client_secret="skript-secret",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
        )

    def token(self, username):
        return self.client.post(
            "/o/token/",
            {
                "grant_type": "password",
                "username": username,
                "password": PASSWORD,
                "client_id": "skript",
                "client_secret": "skript-secret",
            },
        )

    def test_an_account_without_a_second_factor_gets_a_token(self):
        User.objects.create_user("einfach", password=PASSWORD)
        r = self.token("einfach")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("access_token", r.json())

    def test_a_wrong_password_is_refused(self):
        User.objects.create_user("einfach", password="ein-anderes-pw-43")
        self.assertEqual(self.token("einfach").status_code, 400)

    def test_an_account_with_one_is_refused(self):
        add_totp(User.objects.create_user("zweifach", password=PASSWORD))
        r = self.token("zweifach")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "invalid_grant")
        self.assertFalse(AccessToken.objects.exists())

    def test_an_error_refuses_too(self):
        User.objects.create_user("einfach", password=PASSWORD)
        with (
            patch.object(two_factor, "required_for", side_effect=RuntimeError),
            self.assertLogs("logindata.oauth", "ERROR"),
        ):
            r = self.token("einfach")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(AccessToken.objects.exists())
