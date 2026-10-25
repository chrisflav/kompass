"""A member record is no way into a stronger account.

Whoever controls a member's linked account or its primary email decides who
can sign in as that account: the invite and password-reset mails carry a link
that sets its password. So linking an account, changing the primary email of a
linked member and requesting a password reset are refused where the account
(or, for a link, the member record) holds rights the caller lacks -- in the
API and in the classic admin alike -- and the login link is never mailed to
``alternative_email``.
"""

import datetime
import uuid

from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.core import mail
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from logindata.rights import member_has_rights
from logindata.rights import MEMBER_RIGHTS
from logindata.rights import SUPERUSER_ACCOUNT
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Member
from members.models import MemberUnconfirmedProxy
from members.models import MUSKELKRAFT_ANREISE
from members.models import PermissionGroup
from members.models import PermissionMember
from oauth2_provider.models import get_access_token_model

from .api import Application
from .api import grant
from .api import make_member_user

AccessToken = get_access_token_model()

DOMAIN = "test-organization.org"


def linked_member(username, **account):
    """A member with an internal address, linked to a new account."""
    user = User.objects.create_user(username, password="secret", **account)
    member = Member.objects.create(
        prename=username.title(),
        lastname="Konto",
        birth_date=timezone.now().date(),
        gender=DIVERSE,
        email="{}@{}".format(username, DOMAIN),
        alternative_email="{}@elsewhere.example".format(username),
    )
    member.user = user
    member.save()
    return user, member


@override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=[DOMAIN])
class AccountTakeoverApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="takeover-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.actor, self.actor_member = make_member_user("verwalter")
        self.actor = grant(
            self.actor,
            "change_global_member",
            "view_global_member",
            "may_set_auth_user",
            "may_invite_as_user",
        )
        self.superuser = User.objects.create_superuser("root", password="secret")
        self.chef, self.chef_member = linked_member("chef", is_superuser=True)
        self.plain, self.plain_member = linked_member("plain")
        self.target = Member.objects.create(
            prename="Ohne", lastname="Konto", gender=DIVERSE, email="ohne@{}".format(DOMAIN)
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

    def patch(self, member, payload, user):
        return self.client.patch(
            "/api/members/{}".format(member.pk),
            data=payload,
            content_type="application/json",
            **self.auth(user),
        )

    def assertRefused(self, response, message):
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["detail"], str(message))
        self.assertTrue(response.json()["displayable"])

    # --- linking an account ----------------------------------------------

    def test_a_stronger_account_cannot_be_linked(self):
        self.chef_member.user = None
        self.chef_member.save()
        r = self.patch(self.target, {"user_id": self.chef.pk}, self.actor)
        self.assertRefused(r, SUPERUSER_ACCOUNT)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.user)

    def test_a_member_with_rights_cannot_be_linked(self):
        # The account would get the member's rights, here leading a group.
        Group.objects.create(name="Gemsen").leiters.add(self.target)
        account = User.objects.create_user("frei", password="secret")
        r = self.patch(self.target, {"user_id": account.pk}, self.actor)
        self.assertRefused(r, MEMBER_RIGHTS)
        self.target.refresh_from_db()
        self.assertIsNone(self.target.user)

    def test_a_superuser_may_link_any_account(self):
        self.chef_member.user = None
        self.chef_member.save()
        Group.objects.create(name="Gemsen").leiters.add(self.target)
        r = self.patch(self.target, {"user_id": self.chef.pk}, self.superuser)
        self.assertEqual(r.status_code, 200, r.content)
        self.target.refresh_from_db()
        self.assertEqual(self.target.user, self.chef)

    def test_relinking_the_same_account_is_no_change(self):
        r = self.patch(self.chef_member, {"user_id": self.chef.pk}, self.actor)
        self.assertNotEqual(r.status_code, 403, r.content)

    def test_an_unknown_account_is_left_to_validation(self):
        r = self.patch(self.target, {"user_id": 987654}, self.actor)
        self.assertEqual(r.status_code, 422, r.content)

    # --- changing the primary email ---------------------------------------

    def test_the_email_of_a_stronger_account_cannot_be_changed(self):
        r = self.patch(self.chef_member, {"email": "mine@{}".format(DOMAIN)}, self.actor)
        self.assertRefused(r, SUPERUSER_ACCOUNT)
        self.chef_member.refresh_from_db()
        self.assertEqual(self.chef_member.email, "chef@{}".format(DOMAIN))

    def test_the_email_of_an_account_with_member_rights_cannot_be_changed(self):
        PermissionMember.objects.create(member=self.plain_member).view_members.add(self.target)
        r = self.patch(self.plain_member, {"email": "mine@{}".format(DOMAIN)}, self.actor)
        self.assertRefused(r, MEMBER_RIGHTS)

    def test_the_email_of_a_weaker_account_may_be_changed(self):
        r = self.patch(self.plain_member, {"email": "neu@{}".format(DOMAIN)}, self.actor)
        self.assertEqual(r.status_code, 200, r.content)

    def test_ones_own_email_may_be_changed(self):
        Group.objects.create(name="Gemsen").leiters.add(self.actor_member)
        r = self.patch(self.actor_member, {"email": "neu@{}".format(DOMAIN)}, self.actor)
        self.assertEqual(r.status_code, 200, r.content)

    def test_other_fields_of_a_stronger_account_may_be_changed(self):
        r = self.patch(
            self.chef_member, {"email": self.chef_member.email, "prename": "Neu"}, self.actor
        )
        self.assertEqual(r.status_code, 200, r.content)

    def test_a_superuser_may_change_any_email(self):
        r = self.patch(self.chef_member, {"email": "neu@{}".format(DOMAIN)}, self.superuser)
        self.assertEqual(r.status_code, 200, r.content)

    # --- password reset and invitation -------------------------------------

    def reset(self, member, user):
        return self.client.post(
            "/api/members/{}/request-password-reset".format(member.pk), **self.auth(user)
        )

    def test_a_reset_for_a_stronger_account_is_refused(self):
        mail.outbox = []
        self.assertRefused(self.reset(self.chef_member, self.actor), SUPERUSER_ACCOUNT)
        self.assertEqual(mail.outbox, [])
        self.chef_member.refresh_from_db()
        self.assertEqual(self.chef_member.invite_as_user_key, "")

    def test_the_reset_link_goes_to_the_primary_address_only(self):
        mail.outbox = []
        r = self.reset(self.plain_member, self.actor)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["plain@{}".format(DOMAIN)])

    def test_a_superuser_may_reset_any_account(self):
        mail.outbox = []
        r = self.reset(self.chef_member, self.superuser)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(mail.outbox[0].to, ["chef@{}".format(DOMAIN)])

    def test_the_invitation_goes_to_the_primary_address_only(self):
        self.target.alternative_email = "ohne@elsewhere.example"
        self.target.save()
        mail.outbox = []
        r = self.client.post(
            "/api/members/{}/invite-as-user".format(self.target.pk), **self.auth(self.actor)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(mail.outbox[0].to, ["ohne@{}".format(DOMAIN)])

    # --- freeing a record with rights for an invitation ----------------------

    def lead(self, member):
        Group.objects.create(name="Gemsen-{}".format(member.pk)).leiters.add(member)

    def invite(self, member, user):
        return self.client.post(
            "/api/members/{}/invite-as-user".format(member.pk), **self.auth(user)
        )

    def test_a_stronger_account_cannot_be_unlinked(self):
        self.assertRefused(
            self.patch(self.chef_member, {"user_id": None}, self.actor), SUPERUSER_ACCOUNT
        )
        self.chef_member.refresh_from_db()
        self.assertEqual(self.chef_member.user, self.chef)

    def test_an_account_with_member_rights_cannot_be_unlinked(self):
        self.lead(self.plain_member)
        self.assertRefused(
            self.patch(self.plain_member, {"user_id": None}, self.actor), MEMBER_RIGHTS
        )
        self.plain_member.refresh_from_db()
        self.assertEqual(self.plain_member.user, self.plain)

    def test_ones_own_record_with_rights_cannot_go_to_another_account(self):
        self.lead(self.actor_member)
        other = User.objects.create_user("zweitkonto", password="secret")
        r = self.patch(self.actor_member, {"user_id": other.pk}, self.actor)
        self.assertRefused(r, MEMBER_RIGHTS)
        self.actor_member.refresh_from_db()
        self.assertEqual(self.actor_member.user, self.actor)

    def test_a_weaker_account_may_be_unlinked(self):
        r = self.patch(self.plain_member, {"user_id": None}, self.actor)
        self.assertEqual(r.status_code, 200, r.content)
        self.plain_member.refresh_from_db()
        self.assertIsNone(self.plain_member.user)

    def test_the_email_of_an_unlinked_record_with_rights_cannot_be_changed(self):
        self.lead(self.target)
        r = self.patch(self.target, {"email": "mine@{}".format(DOMAIN)}, self.actor)
        self.assertRefused(r, MEMBER_RIGHTS)
        self.target.refresh_from_db()
        self.assertEqual(self.target.email, "ohne@{}".format(DOMAIN))

    def test_the_email_of_an_unlinked_record_without_rights_may_be_changed(self):
        r = self.patch(self.target, {"email": "neu@{}".format(DOMAIN)}, self.actor)
        self.assertEqual(r.status_code, 200, r.content)

    def test_a_record_with_rights_cannot_be_invited(self):
        self.lead(self.target)
        mail.outbox = []
        self.assertRefused(self.invite(self.target, self.actor), MEMBER_RIGHTS)
        self.assertEqual(mail.outbox, [])
        self.target.refresh_from_db()
        self.assertEqual(self.target.invite_as_user_key, "")

    def test_a_superuser_may_invite_a_record_with_rights(self):
        self.lead(self.target)
        mail.outbox = []
        r = self.invite(self.target, self.superuser)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)


class MemberRightsTestCase(TestCase):
    """What counts as rights through a member record."""

    def setUp(self):
        self.member = Member.objects.create(
            prename="Jule", lastname="Leiter", gender=DIVERSE, email="jule@example.org"
        )
        self.other = Member.objects.create(
            prename="Ole", lastname="Teil", gender=DIVERSE, email="ole@example.org"
        )
        self.group = Group.objects.create(name="Gemsen")

    def test_a_plain_member_has_none(self):
        self.assertFalse(member_has_rights(self.member))

    def test_an_empty_access_list_grants_nothing(self):
        PermissionMember.objects.create(member=self.member)
        self.assertFalse(member_has_rights(self.member))

    def test_an_own_access_list(self):
        PermissionMember.objects.create(member=self.member).change_groups.add(self.group)
        self.assertTrue(member_has_rights(self.member))

    def test_the_access_list_of_a_group_the_member_is_in(self):
        self.member.group.add(self.group)
        PermissionGroup.objects.create(group=self.group).list_members.add(self.other)
        self.assertTrue(member_has_rights(self.member))

    def test_leading_a_group(self):
        self.group.leiters.add(self.member)
        self.assertTrue(member_has_rights(self.member))

    def test_leading_an_excursion(self):
        excursion = Freizeit.objects.create(
            name="Tour",
            date=timezone.localtime(),
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        excursion.jugendleiter.add(self.member)
        self.assertTrue(member_has_rights(self.member))


@override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=[DOMAIN])
class AccountTakeoverAdminTestCase(TestCase):
    """The same rules in the member admin's form and its password-reset button."""

    def setUp(self):
        self.factory = RequestFactory()
        self.actor = User.objects.create_user("verwalter", password="secret", is_staff=True)
        self.actor = grant(
            self.actor,
            "change_global_member",
            "view_global_member",
            "may_set_auth_user",
            "may_invite_as_user",
        )
        self.superuser = User.objects.create_superuser("root", password="secret")
        self.chef, self.chef_member = linked_member("chef", is_superuser=True)
        self.target = Member.objects.create(
            prename="Ohne", lastname="Konto", gender=DIVERSE, email="ohne@{}".format(DOMAIN)
        )

    def clean(self, model, member, actor, changes):
        """Run the admin form's ``clean`` for ``changes`` on ``member``."""
        request = self.factory.post("/")
        request.user = actor
        form = admin.site._registry[model].get_form(request, member)(instance=member)
        form.cleaned_data = changes
        return form.clean()

    def test_a_stronger_account_cannot_be_linked(self):
        self.chef_member.user = None
        self.chef_member.save()
        for model in (Member, MemberUnconfirmedProxy):
            with self.subTest(model=model.__name__):
                with self.assertRaisesMessage(ValidationError, str(SUPERUSER_ACCOUNT)):
                    self.clean(model, self.target, self.actor, {"user": self.chef})

    def test_the_email_of_a_stronger_account_cannot_be_changed(self):
        with self.assertRaisesMessage(ValidationError, str(SUPERUSER_ACCOUNT)):
            self.clean(Member, self.chef_member, self.actor, {"email": "mine@{}".format(DOMAIN)})

    def test_harmless_changes_pass(self):
        changes = {"user": None, "email": "neu@{}".format(DOMAIN)}
        self.assertEqual(self.clean(Member, self.target, self.actor, changes), changes)
        self.assertEqual(self.clean(Member, self.chef_member, self.superuser, changes), changes)

    def reset(self, user):
        """Press the change page's reset button; return the messages it leaves."""
        self.client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
        mail.outbox = []
        response = self.client.post(
            reverse("admin:members_member_inviteasuser", args=(self.chef_member.pk,)),
            {"apply": ""},
        )
        self.assertEqual(response.status_code, 302)
        return [str(m) for m in get_messages(response.wsgi_request)]

    def test_the_reset_button_refuses_a_stronger_account(self):
        self.assertIn(str(SUPERUSER_ACCOUNT), self.reset(self.actor))
        self.assertEqual(mail.outbox, [])

    def test_the_reset_button_works_for_a_superuser(self):
        self.assertIn(
            _("Password reset email sent to %(name)s.") % {"name": str(self.chef_member)},
            self.reset(self.superuser),
        )
        self.assertEqual(mail.outbox[0].to, ["chef@{}".format(DOMAIN)])

    def test_unlinking_a_stronger_account_is_refused(self):
        with self.assertRaisesMessage(ValidationError, str(SUPERUSER_ACCOUNT)):
            self.clean(Member, self.chef_member, self.actor, {"user": None})

    def test_the_email_of_an_unlinked_record_with_rights_cannot_be_changed(self):
        Group.objects.create(name="Gemsen").leiters.add(self.target)
        with self.assertRaisesMessage(ValidationError, str(MEMBER_RIGHTS)):
            self.clean(Member, self.target, self.actor, {"email": "mine@{}".format(DOMAIN)})

    def invite_action(self, user, *members):
        request = self.factory.post("/")
        request.user = user
        SessionMiddleware(lambda r: None).process_request(request)
        request._messages = FallbackStorage(request)
        mail.outbox = []
        admin.site._registry[Member].invite_as_user(
            request, Member.objects.filter(pk__in=[m.pk for m in members])
        )
        return [str(m) for m in get_messages(request)]

    def test_the_invite_action_skips_a_record_with_rights(self):
        Group.objects.create(name="Gemsen").leiters.add(self.target)
        plain = Member.objects.create(
            prename="Neu", lastname="Ling", gender=DIVERSE, email="neu@{}".format(DOMAIN)
        )
        messages = self.invite_action(self.actor, self.target, plain)
        self.assertIn("{}: {}".format(self.target.name, MEMBER_RIGHTS), messages)
        self.assertEqual([m.to for m in mail.outbox], [["neu@{}".format(DOMAIN)]])

    def test_the_invite_action_lets_a_superuser_invite_a_record_with_rights(self):
        Group.objects.create(name="Gemsen").leiters.add(self.target)
        self.invite_action(self.superuser, self.target)
        self.assertEqual([m.to for m in mail.outbox], [["ohne@{}".format(DOMAIN)]])


@override_settings(ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER=[DOMAIN])
class LoginKeyTestCase(TestCase):
    """A login key is valid for a limited time, and only for its own account."""

    REGISTER = "/api/logindata/register"

    def setUp(self):
        self.member = Member.objects.create(
            prename="Neu", lastname="Ling", gender=DIVERSE, email="neu@{}".format(DOMAIN)
        )
        self.account, self.linked = linked_member("konto")

    def test_an_invitation_lasts_a_week_and_a_reset_a_day(self):
        now = timezone.now()
        self.assertTrue(self.member.invite_as_user())
        self.assertAlmostEqual(
            self.member.invite_as_user_key_expire,
            now + Member.INVITE_KEY_VALIDITY,
            delta=datetime.timedelta(minutes=1),
        )
        self.assertTrue(self.linked.request_password_reset())
        self.assertAlmostEqual(
            self.linked.invite_as_user_key_expire,
            now + Member.RESET_KEY_VALIDITY,
            delta=datetime.timedelta(minutes=1),
        )
        self.assertEqual(self.linked.invite_as_user_key_user, self.account)
        self.assertEqual(Member.for_login_key(self.member.invite_as_user_key), self.member)
        self.assertEqual(Member.for_login_key(self.linked.invite_as_user_key), self.linked)

    def test_an_expired_key_is_refused(self):
        self.member.invite_as_user()
        Member.objects.filter(pk=self.member.pk).update(
            invite_as_user_key_expire=timezone.now() - datetime.timedelta(seconds=1)
        )
        self.assertIsNone(Member.for_login_key(self.member.invite_as_user_key))
        r = self.client.get(self.REGISTER, {"key": self.member.invite_as_user_key})
        self.assertEqual(r.status_code, 404)

    def test_a_key_without_an_expiry_is_refused(self):
        # Keys issued before keys expired.
        Member.objects.filter(pk=self.member.pk).update(invite_as_user_key="alt")
        self.assertIsNone(Member.for_login_key("alt"))

    def test_unknown_and_empty_keys_are_refused(self):
        self.assertIsNone(Member.for_login_key(""))
        self.assertIsNone(Member.for_login_key("unbekannt"))

    def test_an_invitation_does_not_become_a_reset(self):
        # Linked behind `save`'s back: the key is still bound to no account.
        self.member.invite_as_user()
        other = User.objects.create_user("spaeter", password="secret")
        Member.objects.filter(pk=self.member.pk).update(user=other)
        self.assertIsNone(Member.for_login_key(self.member.invite_as_user_key))
        r = self.client.get(self.REGISTER, {"key": self.member.invite_as_user_key})
        self.assertEqual(r.status_code, 404)

    def test_changing_the_email_or_the_account_clears_the_key(self):
        for change in (
            {"email": "anders@{}".format(DOMAIN)},
            {"user": User.objects.create_user("anders", password="secret")},
        ):
            with self.subTest(change=sorted(change)):
                member = Member.objects.get(pk=self.member.pk)
                member.invite_as_user()
                for field, value in change.items():
                    setattr(member, field, value)
                member.save()
                member.refresh_from_db()
                self.assertEqual(member.invite_as_user_key, "")
                self.assertIsNone(member.invite_as_user_key_expire)
                member.user = None
                member.email = "neu@{}".format(DOMAIN)
                member.save()

    def test_a_partial_save_of_the_email_clears_the_key_too(self):
        self.member.invite_as_user()
        self.member.email = "anders@{}".format(DOMAIN)
        self.member.save(update_fields=["email"])
        self.member.refresh_from_db()
        self.assertEqual(self.member.invite_as_user_key, "")

    def test_other_changes_keep_the_key(self):
        self.member.invite_as_user()
        key = self.member.invite_as_user_key
        self.member.prename = "Anders"
        self.member.save()
        self.assertEqual(Member.for_login_key(key), self.member)
