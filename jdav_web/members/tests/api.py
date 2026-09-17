"""End-to-end tests for the members REST API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
object/row-level permission model, mirroring the guarantees of
``members/tests/rules.py`` but through the HTTP API.
"""

import base64
import datetime
import hashlib
import secrets
import uuid
from urllib.parse import parse_qs
from urllib.parse import urlencode
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Group
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

CLIENT_ID = "kompass-frontend-dev"
REDIRECT_URI = "https://kompass.example.org/callback"


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
            Permission.objects.get(content_type__app_label="members", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


class MembersApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # Provide a short secret; the default 128-char one exceeds bcrypt's
            # 72-byte limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("owner")
        self.other_user, self.other = make_member_user("other")
        self.admin_user, self.admin = make_member_user("admin")
        self.admin_user = grant(
            self.admin_user,
            "list_global_member",
            "view_global_member",
            "view_group",
        )
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)

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
        self.assertEqual(self.client.get("/api/members/").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get("/api/members/", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- list scoping -----------------------------------------------------

    def test_list_scoped_to_self_without_permissions(self):
        r = self.client.get("/api/members/", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        ids = {m["id"] for m in r.json()}
        self.assertEqual(ids, {self.owner.pk})

    def test_list_all_with_global_permission(self):
        r = self.client.get("/api/members/", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)
        ids = {m["id"] for m in r.json()}
        self.assertEqual(ids, {self.owner.pk, self.other.pk, self.admin.pk})

    # --- object retrieval -------------------------------------------------

    def test_retrieve_self_allowed(self):
        r = self.client.get("/api/members/{}".format(self.owner.pk), **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], self.owner.pk)
        self.assertEqual(body["name"], self.owner.name)

    def test_retrieve_other_forbidden(self):
        r = self.client.get("/api/members/{}".format(self.other.pk), **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_retrieve_other_allowed_with_global_permission(self):
        r = self.client.get("/api/members/{}".format(self.other.pk), **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)

    # --- groups -----------------------------------------------------------

    def test_groups_forbidden_without_permission(self):
        r = self.client.get("/api/members/groups", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_groups_listed_with_permission(self):
        r = self.client.get("/api/members/groups", **self.auth(self.admin_user))
        self.assertEqual(r.status_code, 200)
        names = {g["name"] for g in r.json()}
        self.assertIn("Alpenfuechse", names)

    # --- OAuth2 Authorization-Code + PKCE login (the SPA's flow) ----------

    def _pkce_pair(self):
        """A verifier and its S256 challenge, exactly as the SPA derives them."""
        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        return verifier, challenge

    def _authorize(self, challenge, redirect_uri):
        """Run the authorize leg as a logged-in user; returns the code."""
        self.client.force_login(self.owner_user)
        res = self.client.get(
            "/o/authorize/",
            {
                "response_type": "code",
                "client_id": CLIENT_ID,
                "redirect_uri": redirect_uri,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "scope": "profile email",
            },
        )
        # skip_authorization means the provider redirects straight back rather
        # than rendering a consent form for our own first-party frontend.
        self.assertEqual(res.status_code, 302, res.content)
        self.client.logout()
        return parse_qs(urlparse(res["Location"]).query)["code"][0]

    def test_authorization_code_pkce_login_then_api_access(self):
        call_command("ensure_frontend_oauth_app", "--redirect-uri", REDIRECT_URI)
        verifier, challenge = self._pkce_pair()
        code = self._authorize(challenge, REDIRECT_URI)

        res = self.client.post(
            "/o/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                    "code_verifier": verifier,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(res.status_code, 200, res.content)
        token = res.json()["access_token"]

        r = self.client.get("/api/members/", HTTP_AUTHORIZATION="Bearer {}".format(token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({m["id"] for m in r.json()}, {self.owner.pk})

    def test_authorization_code_without_verifier_is_refused(self):
        # The whole point of PKCE: a stolen code is useless on its own.
        call_command("ensure_frontend_oauth_app", "--redirect-uri", REDIRECT_URI)
        _verifier, challenge = self._pkce_pair()
        code = self._authorize(challenge, REDIRECT_URI)

        res = self.client.post(
            "/o/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_authorization_code_with_wrong_verifier_is_refused(self):
        call_command("ensure_frontend_oauth_app", "--redirect-uri", REDIRECT_URI)
        _verifier, challenge = self._pkce_pair()
        code = self._authorize(challenge, REDIRECT_URI)
        other_verifier, _ = self._pkce_pair()

        res = self.client.post(
            "/o/token/",
            data=urlencode(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                    "client_id": CLIENT_ID,
                    "code_verifier": other_verifier,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertEqual(res.status_code, 400, res.content)

    def test_password_grant_is_no_longer_accepted(self):
        # The SPA no longer handles passwords, and neither should the provider.
        call_command("ensure_frontend_oauth_app", "--redirect-uri", REDIRECT_URI)
        self.owner_user.set_password("secret123")
        self.owner_user.save()

        res = self.client.post(
            "/o/token/",
            data=urlencode(
                {
                    "grant_type": "password",
                    "username": self.owner_user.username,
                    "password": "secret123",
                    "client_id": CLIENT_ID,
                }
            ),
            content_type="application/x-www-form-urlencoded",
        )
        self.assertNotEqual(res.status_code, 200)

    def test_ensure_frontend_oauth_app_adds_a_new_origin(self):
        # A deployment re-runs the command to register another frontend origin.
        call_command("ensure_frontend_oauth_app", "--redirect-uri", REDIRECT_URI)
        call_command(
            "ensure_frontend_oauth_app",
            "--redirect-uri",
            REDIRECT_URI,
            "--redirect-uri",
            "https://neu.example.org/callback",
        )
        app = Application.objects.get(client_id=CLIENT_ID)
        self.assertEqual(Application.objects.filter(client_id=CLIENT_ID).count(), 1)
        self.assertIn("https://neu.example.org/callback", app.redirect_uris)
        self.assertEqual(app.client_type, Application.CLIENT_PUBLIC)
        self.assertEqual(app.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE)

    # --- member update (write) -------------------------------------------

    def test_update_self_allowed(self):
        r = self.client.patch(
            "/api/members/{}".format(self.owner.pk),
            data={"phone_number": "+49 111", "town": "Ludwigsburg"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.phone_number, "+49 111")
        self.assertEqual(self.owner.town, "Ludwigsburg")

    def test_update_null_on_blank_string_field_coerced(self):
        # ``iban`` is ``blank=True, null=False``; an explicit ``null`` from the
        # client must be stored as "" rather than raising an IntegrityError.
        r = self.client.patch(
            "/api/members/{}".format(self.owner.pk),
            data={"iban": None},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.iban, "")

    def test_update_other_forbidden(self):
        r = self.client.patch(
            "/api/members/{}".format(self.other.pk),
            data={"phone_number": "+49 222"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.other.refresh_from_db()
        self.assertNotEqual(self.other.phone_number, "+49 222")

    # --- excursions -------------------------------------------------------

    def test_excursion_listing_scoped_to_leadership(self):
        from members.models import Freizeit
        from members.models import GEMEINSCHAFTS_TOUR

        excursion = Freizeit.objects.create(
            name="Zugspitze", tour_type=GEMEINSCHAFTS_TOUR, kilometers_traveled=10, difficulty=1
        )
        excursion.jugendleiter.add(self.owner)

        # The leader sees it...
        r = self.client.get("/api/members/excursions", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({e["id"] for e in r.json()}, {excursion.pk})

        # ...an unrelated member does not.
        r = self.client.get("/api/members/excursions", **self.auth(self.other_user))
        self.assertEqual(r.json(), [])

    def test_excursion_detail_authorized(self):
        from members.models import Freizeit
        from members.models import GEMEINSCHAFTS_TOUR

        excursion = Freizeit.objects.create(
            name="Zugspitze", tour_type=GEMEINSCHAFTS_TOUR, kilometers_traveled=10, difficulty=1
        )
        excursion.jugendleiter.add(self.owner)

        r = self.client.get(
            "/api/members/excursions/{}".format(excursion.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["code"], excursion.code)

        r = self.client.get(
            "/api/members/excursions/{}".format(excursion.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- trainings --------------------------------------------------------

    def test_training_retrieve_own_vs_other(self):
        from members.models import MemberTraining
        from members.models import TrainingCategory

        category = TrainingCategory.objects.create(name="Grundkurs", permission_needed=False)
        training = MemberTraining.objects.create(
            member=self.owner, title="Kletterkurs", category=category
        )

        # The owner may view their own training (is_oneself)...
        r = self.client.get(
            "/api/members/trainings/{}".format(training.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["category"], "Grundkurs")

        # ...another member may not.
        r = self.client.get(
            "/api/members/trainings/{}".format(training.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- workflow actions -------------------------------------------------

    def make_unconfirmed(self, prename, mail_confirmed=True):
        """An unconfirmed registration (``confirmed=False`` → in the proxy qs)."""
        return Member.objects.create(
            prename=prename,
            lastname="Reg",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            confirmed=False,
            confirmed_mail=mail_confirmed,
            confirmed_alternative_mail=mail_confirmed,
        )

    def test_request_echo_self_allowed(self):
        from django.core import mail

        r = self.client.post(
            "/api/members/{}/request-echo".format(self.owner.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(len(mail.outbox) >= 1)

    def test_request_echo_other_forbidden(self):
        r = self.client.post(
            "/api/members/{}/request-echo".format(self.other.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_request_echo_without_newsletter_rejected(self):
        self.owner.gets_newsletter = False
        self.owner.save()
        r = self.client.post(
            "/api/members/{}/request-echo".format(self.owner.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 422)

    def test_unconfirm_self_allowed(self):
        r = self.client.post(
            "/api/members/{}/unconfirm".format(self.owner.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.confirmed)

    def test_unconfirm_other_forbidden(self):
        r = self.client.post(
            "/api/members/{}/unconfirm".format(self.other.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_invite_as_user_forbidden_without_permission(self):
        r = self.client.post(
            "/api/members/{}/invite-as-user".format(self.other.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_invite_as_user_success(self):
        from django.core import mail

        inviter = grant(self.admin_user, "may_invite_as_user")
        domain = settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER[0]
        member = Member.objects.create(
            prename="Invitee",
            lastname="Test",
            birth_date=timezone.now().date(),
            email="invitee@{}".format(domain),
            gender=DIVERSE,
        )
        r = self.client.post(
            "/api/members/{}/invite-as-user".format(member.pk), **self.auth(inviter)
        )
        self.assertEqual(r.status_code, 200, r.content)
        member.refresh_from_db()
        self.assertTrue(member.invite_as_user_key)
        self.assertTrue(len(mail.outbox) >= 1)

    def test_invite_as_user_rejected_for_external_email(self):
        inviter = grant(self.admin_user, "may_invite_as_user")
        # self.other has the (external) TEST_MAIL address → cannot be invited.
        r = self.client.post(
            "/api/members/{}/invite-as-user".format(self.other.pk), **self.auth(inviter)
        )
        self.assertEqual(r.status_code, 422)

    def test_request_password_reset_requires_linked_user(self):
        inviter = grant(self.admin_user, "may_invite_as_user")
        domain = settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER[0]
        member = Member.objects.create(
            prename="NoUser",
            lastname="Test",
            birth_date=timezone.now().date(),
            email="nouser@{}".format(domain),
            gender=DIVERSE,
        )
        r = self.client.post(
            "/api/members/{}/request-password-reset".format(member.pk), **self.auth(inviter)
        )
        self.assertEqual(r.status_code, 422)

    def test_confirm_registration_success(self):
        manager = grant(self.admin_user, "may_manage_all_registrations")
        reg = self.make_unconfirmed("Confirmable", mail_confirmed=True)
        r = self.client.post("/api/members/{}/confirm".format(reg.pk), **self.auth(manager))
        self.assertEqual(r.status_code, 200, r.content)
        reg.refresh_from_db()
        self.assertTrue(reg.confirmed)

    def test_confirm_registration_rejected_with_unconfirmed_mail(self):
        manager = grant(self.admin_user, "may_manage_all_registrations")
        reg = self.make_unconfirmed("Pending", mail_confirmed=False)
        r = self.client.post("/api/members/{}/confirm".format(reg.pk), **self.auth(manager))
        self.assertEqual(r.status_code, 422)
        reg.refresh_from_db()
        self.assertFalse(reg.confirmed)

    def test_confirm_registration_forbidden_without_permission(self):
        reg = self.make_unconfirmed("Guarded")
        r = self.client.post("/api/members/{}/confirm".format(reg.pk), **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_demote_to_waiter_success(self):
        from members.models import MemberWaitingList

        manager = grant(self.admin_user, "may_manage_all_registrations")
        reg = self.make_unconfirmed("Demotable")
        r = self.client.post(
            "/api/members/{}/demote-to-waiter".format(reg.pk), **self.auth(manager)
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Member.objects.filter(pk=reg.pk).exists())
        self.assertTrue(MemberWaitingList.objects.filter(prename="Demotable").exists())

    def test_request_mail_confirmation_success(self):
        from django.core import mail

        manager = grant(self.admin_user, "may_manage_all_registrations")
        reg = self.make_unconfirmed("Reminded", mail_confirmed=False)
        r = self.client.post(
            "/api/members/{}/request-mail-confirmation".format(reg.pk), **self.auth(manager)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(len(mail.outbox) >= 1)
