"""End-to-end tests for the logindata administration API.

These cover the three model admins the SPA replaced: login accounts, permission
groups and the shared registration password. Each resource is walked through
its full list/create/read/update/delete cycle, and each is checked to refuse a
caller without the matching ``auth.*`` / ``logindata.*`` permission — those are
the same permissions ``UserAdmin`` and ``AuthGroupAdmin`` check.

The two places with behaviour rather than plumbing get their own cases: user
creation and password changes go through Django's own auth forms, so their
validators must surface as 422, and deleting a user must refuse to delete the
caller's own account.
"""

import datetime
import uuid

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from logindata.models import AuthGroup
from logindata.models import RegistrationPassword
from members.models import DIVERSE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def grant(user, *perms):
    """Grant ``app_label.codename`` permissions and return a cache-free user."""
    for perm in perms:
        app_label, codename = perm.split(".")
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label=app_label, codename=codename)
        )
    return User.objects.get(pk=user.pk)


class LogindataAdminApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="logindata-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.admin_user = User.objects.create_user("logindataadmin", password="secret")
        self.plain_user = User.objects.create_user("logindataplain", password="secret")
        self.subject = User.objects.create_user("subject", password="secret")
        self.group = AuthGroup.objects.create(name="Jugendleiter")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def as_admin(self, *perms):
        return self.auth(grant(self.admin_user, *perms))

    def post(self, path, payload, **headers):
        return self.client.post(path, data=payload, content_type="application/json", **headers)

    def patch(self, path, payload, **headers):
        return self.client.patch(path, data=payload, content_type="application/json", **headers)

    # --- users ------------------------------------------------------------

    def test_list_users(self):
        r = self.client.get("/api/logindata/users", **self.as_admin("auth.view_user"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("subject", {row["username"] for row in r.json()})

    def test_list_users_forbidden(self):
        r = self.client.get("/api/logindata/users", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_list_users_names_the_linked_member(self):
        # The list is the SPA's account overview, where an account is only
        # recognisable by the person behind it.
        member = Member.objects.create(
            prename="Hannah", lastname="Beckers", gender=DIVERSE, email="h@example.org"
        )
        member.user = self.subject
        member.save()

        r = self.client.get("/api/logindata/users", **self.as_admin("auth.view_user"))
        self.assertEqual(r.status_code, 200, r.content)
        row = next(row for row in r.json() if row["username"] == "subject")
        self.assertEqual(row["member_name"], member.name)

    def test_create_user(self):
        r = self.post(
            "/api/logindata/users",
            {
                "username": "neuling",
                "password1": "ein-langes-passwort-42",
                "password2": "ein-langes-passwort-42",
            },
            **self.as_admin("auth.add_user"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(User.objects.filter(username="neuling").exists())

    def test_create_user_surfaces_form_errors(self):
        # Django's own UserCreationForm validates this, and its complaint has to
        # reach the client per field rather than as a 500.
        r = self.post(
            "/api/logindata/users",
            {"username": "neuling", "password1": "abc", "password2": "xyz"},
            **self.as_admin("auth.add_user"),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("password2", r.json()["errors"])
        self.assertFalse(User.objects.filter(username="neuling").exists())

    def test_create_user_forbidden(self):
        r = self.post(
            "/api/logindata/users",
            {"username": "nope", "password1": "x", "password2": "x"},
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_retrieve_user(self):
        r = self.client.get(
            "/api/logindata/users/{}".format(self.subject.pk), **self.as_admin("auth.view_user")
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["username"], "subject")

    def test_update_user(self):
        r = self.patch(
            "/api/logindata/users/{}".format(self.subject.pk),
            {"is_staff": True, "username": "umbenannt", "group_ids": [self.group.pk]},
            **self.as_admin("auth.change_user"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.subject.refresh_from_db()
        self.assertTrue(self.subject.is_staff)
        self.assertEqual(self.subject.username, "umbenannt")
        self.assertEqual(list(self.subject.groups.all()), [self.group])

    def test_update_user_rejects_a_duplicate_username(self):
        r = self.patch(
            "/api/logindata/users/{}".format(self.subject.pk),
            {"username": self.plain_user.username},
            **self.as_admin("auth.change_user"),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.subject.refresh_from_db()
        self.assertEqual(self.subject.username, "subject")

    def test_update_user_forbidden(self):
        r = self.patch(
            "/api/logindata/users/{}".format(self.subject.pk),
            {"is_superuser": True},
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        self.subject.refresh_from_db()
        self.assertFalse(self.subject.is_superuser)

    def test_set_user_password(self):
        r = self.post(
            "/api/logindata/users/{}/set-password".format(self.subject.pk),
            {"new_password1": "noch-ein-langes-pw-7", "new_password2": "noch-ein-langes-pw-7"},
            **self.as_admin("auth.change_user"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.subject.refresh_from_db()
        self.assertTrue(self.subject.check_password("noch-ein-langes-pw-7"))

    def test_set_user_password_surfaces_validator_errors(self):
        r = self.post(
            "/api/logindata/users/{}/set-password".format(self.subject.pk),
            {"new_password1": "123", "new_password2": "123"},
            **self.as_admin("auth.change_user"),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("new_password2", r.json()["errors"])
        self.subject.refresh_from_db()
        self.assertFalse(self.subject.check_password("123"))

    def test_delete_user(self):
        r = self.client.delete(
            "/api/logindata/users/{}".format(self.subject.pk),
            **self.as_admin("auth.delete_user"),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(User.objects.filter(pk=self.subject.pk).exists())

    def test_delete_own_account_refused(self):
        # Locking yourself out is not an operation the API should offer.
        headers = self.as_admin("auth.delete_user")
        r = self.client.delete("/api/logindata/users/{}".format(self.admin_user.pk), **headers)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertTrue(User.objects.filter(pk=self.admin_user.pk).exists())

    def test_delete_user_forbidden(self):
        r = self.client.delete(
            "/api/logindata/users/{}".format(self.subject.pk), **self.auth(self.plain_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(User.objects.filter(pk=self.subject.pk).exists())

    # --- permission groups ------------------------------------------------

    def _some_permission(self):
        return Permission.objects.filter(content_type__app_label="members").first()

    def test_list_permission_groups(self):
        r = self.client.get("/api/logindata/permission-groups", **self.as_admin("auth.view_group"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("Jugendleiter", {row["name"] for row in r.json()})

    def test_create_permission_group(self):
        perm = self._some_permission()
        r = self.post(
            "/api/logindata/permission-groups",
            {"name": "Kassenwart", "permission_ids": [perm.pk]},
            **self.as_admin("auth.add_group"),
        )
        self.assertEqual(r.status_code, 201, r.content)
        created = AuthGroup.objects.get(name="Kassenwart")
        self.assertEqual(list(created.permissions.all()), [perm])

    def test_create_permission_group_rejects_a_duplicate_name(self):
        r = self.post(
            "/api/logindata/permission-groups",
            {"name": "Jugendleiter"},
            **self.as_admin("auth.add_group"),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_retrieve_permission_group_lists_its_permissions(self):
        perm = self._some_permission()
        self.group.permissions.add(perm)
        r = self.client.get(
            "/api/logindata/permission-groups/{}".format(self.group.pk),
            **self.as_admin("auth.view_group"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn(perm.pk, {p["id"] for p in r.json()["permissions"]})

    def test_update_permission_group(self):
        perm = self._some_permission()
        r = self.patch(
            "/api/logindata/permission-groups/{}".format(self.group.pk),
            {"name": "Betreuer", "permission_ids": [perm.pk]},
            **self.as_admin("auth.change_group"),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.group.refresh_from_db()
        self.assertEqual(self.group.name, "Betreuer")
        self.assertEqual(list(self.group.permissions.all()), [perm])

    def test_delete_permission_group(self):
        r = self.client.delete(
            "/api/logindata/permission-groups/{}".format(self.group.pk),
            **self.as_admin("auth.delete_group"),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(AuthGroup.objects.filter(pk=self.group.pk).exists())

    def test_permission_group_routes_forbidden(self):
        headers = self.auth(self.plain_user)
        self.assertEqual(
            self.client.get("/api/logindata/permission-groups", **headers).status_code, 403
        )
        self.assertEqual(
            self.post("/api/logindata/permission-groups", {"name": "x"}, **headers).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                "/api/logindata/permission-groups/{}".format(self.group.pk), **headers
            ).status_code,
            403,
        )

    def test_list_permissions_for_the_picker(self):
        r = self.client.get("/api/logindata/permissions", **self.as_admin("auth.view_group"))
        self.assertEqual(r.status_code, 200, r.content)
        codenames = {row["codename"] for row in r.json()}
        self.assertIn("members.view_group", codenames)

    def test_list_permissions_forbidden(self):
        r = self.client.get("/api/logindata/permissions", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    # --- registration password --------------------------------------------

    def test_registration_password_crud(self):
        headers = self.as_admin(
            "logindata.view_registrationpassword",
            "logindata.add_registrationpassword",
            "logindata.change_registrationpassword",
            "logindata.delete_registrationpassword",
        )
        created = self.post(
            "/api/logindata/registration-passwords", {"password": "geheim-123"}, **headers
        )
        self.assertEqual(created.status_code, 201, created.content)
        entry_id = created.json()["id"]

        listed = self.client.get("/api/logindata/registration-passwords", **headers)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(entry_id, {row["id"] for row in listed.json()})

        updated = self.patch(
            "/api/logindata/registration-passwords/{}".format(entry_id),
            {"password": "anders-456"},
            **headers,
        )
        self.assertEqual(updated.status_code, 200, updated.content)
        self.assertEqual(RegistrationPassword.objects.get(pk=entry_id).password, "anders-456")

        removed = self.client.delete(
            "/api/logindata/registration-passwords/{}".format(entry_id), **headers
        )
        self.assertEqual(removed.status_code, 204, removed.content)
        self.assertFalse(RegistrationPassword.objects.filter(pk=entry_id).exists())

    def test_registration_password_routes_forbidden(self):
        entry = RegistrationPassword.objects.create(password="geheim-789")
        headers = self.auth(self.plain_user)
        self.assertEqual(
            self.client.get("/api/logindata/registration-passwords", **headers).status_code, 403
        )
        self.assertEqual(
            self.post(
                "/api/logindata/registration-passwords", {"password": "x"}, **headers
            ).status_code,
            403,
        )
        self.assertEqual(
            self.patch(
                "/api/logindata/registration-passwords/{}".format(entry.pk),
                {"password": "x"},
                **headers,
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                "/api/logindata/registration-passwords/{}".format(entry.pk), **headers
            ).status_code,
            403,
        )
