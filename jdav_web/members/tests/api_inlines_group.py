"""End-to-end tests for the group/klettertreff/waiter inline CRUD API.

These exercise the real OAuth2 bearer auth path and the parent-object change
permission gating of ``members/api/inlines_group.py``. Each surface is covered
with an authorized success, an unauthorized 403 and (where writable) a
validation 422.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Group
from members.models import InvitationToGroup
from members.models import Klettertreff
from members.models import KlettertreffAttendee
from members.models import Member
from members.models import MemberWaitingList
from members.models import PermissionGroup
from members.models import RegistrationPassword
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
            Permission.objects.get(content_type__app_label="members", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class GroupInlineApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.plain_user, self.plain = make_member_user("plain")
        editor_user, self.editor = make_member_user("editor")
        self.editor_user = grant(
            editor_user,
            "view_group",
            "change_group",
            "view_klettertreff",
            "change_klettertreff",
            "view_global_memberwaitinglist",
        )
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)
        self.klettertreff = Klettertreff.objects.create(
            date=timezone.now().date(), location="Halle", topic="Toprope", group=self.group
        )
        self.waiter = MemberWaitingList.objects.create(
            prename="Wanda", lastname="Waiter", gender=DIVERSE, email=settings.TEST_MAIL
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

    # --- registration passwords -------------------------------------------

    def test_create_registration_password_authorized(self):
        r = self.client.post(
            "/api/members/groups/{}/registration-passwords".format(self.group.pk),
            data={"password": "spring2026"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            RegistrationPassword.objects.filter(group=self.group, password="spring2026").exists()
        )

    def test_create_registration_password_forbidden(self):
        r = self.client.post(
            "/api/members/groups/{}/registration-passwords".format(self.group.pk),
            data={"password": "spring2026"},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_create_registration_password_duplicate_422(self):
        RegistrationPassword.objects.create(group=self.group, password="dup")
        r = self.client.post(
            "/api/members/groups/{}/registration-passwords".format(self.group.pk),
            data={"password": "dup"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_list_registration_passwords_authorized(self):
        RegistrationPassword.objects.create(group=self.group, password="one")
        r = self.client.get(
            "/api/members/groups/{}/registration-passwords".format(self.group.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual([p["password"] for p in r.json()], ["one"])

    def test_delete_registration_password_authorized(self):
        password = RegistrationPassword.objects.create(group=self.group, password="gone")
        r = self.client.delete(
            "/api/members/registration-passwords/{}".format(password.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(RegistrationPassword.objects.filter(pk=password.pk).exists())

    # --- group permission ACL (SENSITIVE) ---------------------------------

    def test_create_permission_group_authorized(self):
        r = self.client.post(
            "/api/members/groups/{}/permission-groups".format(self.group.pk),
            data={"view_member_ids": [self.plain.pk]},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 201)
        permission_group = PermissionGroup.objects.get(group=self.group)
        self.assertEqual(
            list(permission_group.view_members.values_list("id", flat=True)), [self.plain.pk]
        )

    def test_create_permission_group_forbidden(self):
        r = self.client.post(
            "/api/members/groups/{}/permission-groups".format(self.group.pk),
            data={"view_member_ids": [self.plain.pk]},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_create_permission_group_duplicate_422(self):
        PermissionGroup.objects.create(group=self.group)
        r = self.client.post(
            "/api/members/groups/{}/permission-groups".format(self.group.pk),
            data={},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_update_permission_group_authorized(self):
        permission_group = PermissionGroup.objects.create(group=self.group)
        r = self.client.patch(
            "/api/members/permission-groups/{}".format(permission_group.pk),
            data={"change_member_ids": [self.editor.pk]},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            list(permission_group.change_members.values_list("id", flat=True)), [self.editor.pk]
        )

    def test_list_permission_groups_forbidden_for_viewer(self):
        # SENSITIVE: even holders of the weaker view_group must not read the ACL.
        viewer_user, _viewer = make_member_user("viewer")
        viewer_user = grant(viewer_user, "view_group")
        PermissionGroup.objects.create(group=self.group)
        r = self.client.get(
            "/api/members/groups/{}/permission-groups".format(self.group.pk),
            **self.auth(viewer_user),
        )
        self.assertEqual(r.status_code, 403)

    # --- klettertreff attendees -------------------------------------------

    def test_add_klettertreff_attendee_authorized(self):
        r = self.client.post(
            "/api/members/klettertreff/{}/attendees".format(self.klettertreff.pk),
            data={"member_id": self.plain.pk},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 201)
        self.assertTrue(
            KlettertreffAttendee.objects.filter(
                klettertreff=self.klettertreff, member=self.plain
            ).exists()
        )

    def test_add_klettertreff_attendee_forbidden(self):
        r = self.client.post(
            "/api/members/klettertreff/{}/attendees".format(self.klettertreff.pk),
            data={"member_id": self.plain.pk},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_list_klettertreff_attendees_authorized(self):
        KlettertreffAttendee.objects.create(klettertreff=self.klettertreff, member=self.plain)
        r = self.client.get(
            "/api/members/klettertreff/{}/attendees".format(self.klettertreff.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual([a["member"]["id"] for a in r.json()], [self.plain.pk])

    def test_remove_klettertreff_attendee_authorized(self):
        attendee = KlettertreffAttendee.objects.create(
            klettertreff=self.klettertreff, member=self.plain
        )
        r = self.client.delete(
            "/api/members/attendees/{}".format(attendee.pk), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(KlettertreffAttendee.objects.filter(pk=attendee.pk).exists())

    # --- waiter invitations (read-only) -----------------------------------

    def test_list_waiter_invitations_authorized(self):
        invitation = InvitationToGroup.objects.create(waiter=self.waiter, group=self.group)
        r = self.client.get(
            "/api/members/waiters/{}/invitations".format(self.waiter.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual([i["id"] for i in body], [invitation.pk])
        self.assertEqual(body[0]["group"]["id"], self.group.pk)

    def test_list_waiter_invitations_forbidden(self):
        InvitationToGroup.objects.create(waiter=self.waiter, group=self.group)
        r = self.client.get(
            "/api/members/waiters/{}/invitations".format(self.waiter.pk),
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_update_registration_password(self):
        password = RegistrationPassword.objects.create(group=self.group, password="alt")
        other_group = Group.objects.create(name="Gemsen", year_from=2012, year_to=2016)
        r = self.client.patch(
            "/api/members/registration-passwords/{}".format(password.pk),
            data={"password": "neu2026", "group_id": other_group.pk},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        password.refresh_from_db()
        self.assertEqual(password.password, "neu2026")
        self.assertEqual(password.group, other_group)

    def test_update_registration_password_forbidden(self):
        password = RegistrationPassword.objects.create(group=self.group, password="alt")
        r = self.client.patch(
            "/api/members/registration-passwords/{}".format(password.pk),
            data={"password": "fremd"},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        password.refresh_from_db()
        self.assertEqual(password.password, "alt")

    def test_list_and_delete_permission_group(self):
        permission_group = PermissionGroup.objects.create(group=self.group)
        listed = self.client.get(
            "/api/members/groups/{}/permission-groups".format(self.group.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(permission_group.pk, {row["id"] for row in listed.json()})

        r = self.client.delete(
            "/api/members/permission-groups/{}".format(permission_group.pk),
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(PermissionGroup.objects.filter(pk=permission_group.pk).exists())

    def test_delete_permission_group_forbidden(self):
        # These rows grant object permissions, so the gate matters here.
        permission_group = PermissionGroup.objects.create(group=self.group)
        r = self.client.delete(
            "/api/members/permission-groups/{}".format(permission_group.pk),
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(PermissionGroup.objects.filter(pk=permission_group.pk).exists())
