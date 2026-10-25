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
