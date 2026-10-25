"""The classic admin's user and rights-group pages grant no more than the caller holds.

The same rules as the logindata admin API (see ``logindata.rights``), checked
through the admin's own views: the superuser flag and single permissions are
read-only for everyone else, an account holding rights the caller lacks can be
looked at but not changed, given a password or deleted, and a rights group or
group membership only hands out permissions the caller holds.
"""

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from logindata.models import AuthGroup

# The session is opened through the model backend, so where OIDC is configured
# `SessionRefresh` does not send these GETs to the provider.
BACKEND = "django.contrib.auth.backends.ModelBackend"

STAFF_PERMISSIONS = (
    "view_logindatum",
    "add_logindatum",
    "change_logindatum",
    "delete_logindatum",
    "view_authgroup",
    "add_authgroup",
    "change_authgroup",
)


class RightsAdminTestCase(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("verwaltung", password="secret", is_staff=True)
        self.staff.user_permissions.add(
            *Permission.objects.filter(
                content_type__app_label="logindata", codename__in=STAFF_PERMISSIONS
            )
        )
        self.superuser = User.objects.create_superuser("chef", password="secret")
        self.subject = User.objects.create_user("subject", password="secret")
        self.perm = Permission.objects.filter(content_type__app_label="members").first()
        self.group = AuthGroup.objects.create(name="Jugendleiter")
        self.group.permissions.add(self.perm)

    def login(self, user):
        self.client.force_login(user, backend=BACKEND)

    def user_url(self, view, user):
        # `UserAdmin` names its password page after `auth.User`, whatever the model.
        name = (
            "auth_user_password_change"
            if view == "password_change"
            else ("logindata_logindatum_{}".format(view))
        )
        return reverse("admin:{}".format(name), args=[user.pk])

    def user_form(self, user, **extra):
        data = {
            "username": user.username,
            "is_active": "on",
            "date_joined_0": "2026-01-05",
            "date_joined_1": "08:00:00",
            "last_login_0": "",
            "last_login_1": "",
        }
        data.update(extra)
        return data

    # --- users ------------------------------------------------------------

    def test_the_superuser_fields_are_read_only_to_everyone_else(self):
        self.login(self.staff)
        r = self.client.get(self.user_url("change", self.subject))
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'name="is_superuser"')
        self.assertNotContains(r, 'name="user_permissions"')

        self.login(self.superuser)
        r = self.client.get(self.user_url("change", self.subject))
        self.assertContains(r, 'name="is_superuser"')
        self.assertContains(r, 'name="user_permissions"')

    def test_a_posted_superuser_flag_is_ignored(self):
        self.login(self.staff)
        r = self.client.post(
            self.user_url("change", self.subject),
            self.user_form(self.subject, is_superuser="on", user_permissions=[self.perm.pk]),
        )
        self.assertEqual(r.status_code, 302)
        self.subject.refresh_from_db()
        self.assertFalse(self.subject.is_superuser)
        self.assertFalse(self.subject.user_permissions.exists())

    def assertAccountRefused(self, user):
        self.login(self.staff)
        r = self.client.post(self.user_url("change", user), self.user_form(user, username="x"))
        self.assertEqual(r.status_code, 403)
        r = self.client.post(
            self.user_url("password_change", user),
            {"password1": "noch-ein-langes-pw-7", "password2": "noch-ein-langes-pw-7"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(
            self.client.post(self.user_url("delete", user), {"post": "yes"}).status_code, 403
        )
        user.refresh_from_db()
        self.assertNotEqual(user.username, "x")
        self.assertTrue(user.check_password("secret"))

    def test_a_superuser_account_is_left_to_superusers(self):
        self.assertAccountRefused(self.superuser)

    def test_a_stronger_account_is_left_alone(self):
        self.subject.groups.add(self.group)
        self.assertAccountRefused(self.subject)

    def test_a_stronger_account_can_still_be_looked_at(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(self.user_url("change", self.superuser)).status_code, 200)

    def test_a_superuser_may_change_any_account(self):
        other = User.objects.create_superuser("chefin", password="secret")
        self.login(self.superuser)
        r = self.client.post(
            self.user_url("password_change", other),
            {"password1": "noch-ein-langes-pw-7", "password2": "noch-ein-langes-pw-7"},
        )
        self.assertEqual(r.status_code, 302)
        r = self.client.post(self.user_url("delete", other), {"post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(User.objects.filter(pk=other.pk).exists())

    def test_a_weaker_account_may_be_changed_and_deleted(self):
        self.login(self.staff)
        r = self.client.post(
            self.user_url("change", self.subject), self.user_form(self.subject, username="neu")
        )
        self.assertEqual(r.status_code, 302)
        r = self.client.post(self.user_url("delete", self.subject), {"post": "yes"})
        self.assertEqual(r.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.subject.pk).exists())

    def bulk_delete(self, *users):
        return self.client.post(
            reverse("admin:logindata_logindatum_changelist"),
            {
                "action": "delete_selected",
                "_selected_action": [u.pk for u in users],
                "post": "yes",
            },
        )

    def test_the_bulk_delete_refuses_a_stronger_account(self):
        self.login(self.staff)
        self.assertEqual(self.bulk_delete(self.subject, self.superuser).status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.superuser.pk).exists())
        self.assertTrue(User.objects.filter(pk=self.subject.pk).exists())

    def test_the_bulk_delete_removes_weaker_accounts(self):
        self.login(self.staff)
        self.assertEqual(self.bulk_delete(self.subject).status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.subject.pk).exists())

    def test_a_group_with_permissions_the_caller_lacks_cannot_be_added(self):
        self.login(self.staff)
        r = self.client.post(
            self.user_url("change", self.subject),
            self.user_form(self.subject, groups=[self.group.pk]),
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("groups", r.context["adminform"].form.errors)
        self.assertFalse(self.subject.groups.exists())

    def test_a_group_with_held_permissions_can_be_added(self):
        self.staff.user_permissions.add(self.perm)
        self.login(self.staff)
        r = self.client.post(
            self.user_url("change", self.subject),
            self.user_form(self.subject, groups=[self.group.pk]),
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(list(self.subject.groups.all()), [self.group])

    def test_an_account_can_still_be_created(self):
        self.login(self.staff)
        r = self.client.post(
            reverse("admin:logindata_logindatum_add"),
            {
                "username": "neuling",
                "password1": "ein-langes-pw-42",
                "password2": "ein-langes-pw-42",
            },
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(User.objects.filter(username="neuling").exists())

    # --- rights groups ----------------------------------------------------

    def test_a_group_cannot_be_given_permissions_the_caller_lacks(self):
        self.login(self.staff)
        r = self.client.post(
            reverse("admin:logindata_authgroup_add"),
            {"name": "Kassenwart", "permissions": [self.perm.pk]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertIn("permissions", r.context["adminform"].form.errors)
        self.assertFalse(AuthGroup.objects.filter(name="Kassenwart").exists())

        empty = AuthGroup.objects.create(name="Leer")
        r = self.client.post(
            reverse("admin:logindata_authgroup_change", args=[empty.pk]),
            {"name": "Leer", "permissions": [self.perm.pk]},
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(empty.permissions.exists())

    def test_a_group_keeps_permissions_the_caller_lacks_on_rename(self):
        self.login(self.staff)
        r = self.client.post(
            reverse("admin:logindata_authgroup_change", args=[self.group.pk]),
            {"name": "Betreuer", "permissions": [self.perm.pk]},
        )
        self.assertEqual(r.status_code, 302)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "Betreuer")

    def test_a_group_can_be_given_held_permissions(self):
        self.staff.user_permissions.add(self.perm)
        self.login(self.staff)
        r = self.client.post(
            reverse("admin:logindata_authgroup_add"),
            {"name": "Kassenwart", "permissions": [self.perm.pk]},
        )
        self.assertEqual(r.status_code, 302)
        self.assertTrue(AuthGroup.objects.filter(name="Kassenwart").exists())

    def test_a_superuser_may_give_a_group_any_permission(self):
        self.login(self.superuser)
        r = self.client.post(
            reverse("admin:logindata_authgroup_add"),
            {"name": "Kassenwart", "permissions": [self.perm.pk]},
        )
        self.assertEqual(r.status_code, 302)
