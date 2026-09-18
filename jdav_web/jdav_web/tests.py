from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from startpage.models import Link

from jdav_web.settings import _load_toml
from jdav_web.views import custom_admin_view
from jdav_web.views import custom_app_index
from jdav_web.views import media_protected
from jdav_web.views import media_unprotected


class LoadTomlTestCase(TestCase):
    def test_returns_empty_dict_for_missing_file(self):
        self.assertEqual(_load_toml("/nonexistent/path/settings.toml"), {})


class ViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user("testuser", "test@example.com", "password")
        Link.objects.create(title="Test Link", url="https://example.com")

    @override_settings(DEBUG=True)
    def test_media_unprotected_debug_true(self):
        request = self.factory.get("/media/test.jpg")
        with patch("jdav_web.views.serve") as mock_serve:
            mock_serve.return_value = Mock()
            media_unprotected(request, "test.jpg")
            mock_serve.assert_called_once()

    @override_settings(DEBUG=False)
    def test_media_unprotected_debug_false(self):
        request = self.factory.get("/media/test.jpg")
        response = media_unprotected(request, "test.jpg")
        self.assertEqual(response["X-Accel-Redirect"], "/protected/test.jpg")
        self.assertNotIn("Content-Type", response)

    @override_settings(DEBUG=False)
    def test_media_unprotected_with_umlauts(self):
        request = self.factory.get("/media/testäöü.jpg")
        response = media_unprotected(request, "testäöü.jpg")
        self.assertEqual(response["X-Accel-Redirect"], "/protected/test%C3%A4%C3%B6%C3%BC.jpg")
        self.assertNotIn("Content-Type", response)

    @override_settings(DEBUG=False)
    def test_media_unprotected_with_path_and_umlauts(self):
        request = self.factory.get("/media/folder/testäöü.jpg")
        response = media_unprotected(request, "folder/testäöü.jpg")
        self.assertEqual(
            response["X-Accel-Redirect"], "/protected/folder/test%C3%A4%C3%B6%C3%BC.jpg"
        )
        self.assertNotIn("Content-Type", response)

    def test_custom_app_index_with_documentation_url(self):
        request = self.factory.get("/admin/members/")
        request.user = self.user
        with patch("jdav_web.views._original_app_index") as mock_app_index:
            mock_app_index.return_value = Mock()
            custom_app_index(request, "members")
            args = mock_app_index.call_args[0]
            self.assertIn("documentation_url", args[3])

    def test_custom_app_index_without_documentation_url(self):
        request = self.factory.get("/admin/auth/")
        request.user = self.user
        with patch("jdav_web.views._original_app_index") as mock_app_index:
            mock_app_index.return_value = Mock()
            custom_app_index(request, "auth")
            args = mock_app_index.call_args[0]
            self.assertNotIn("documentation_url", args[3])

    def test_custom_admin_view(self):
        request = self.factory.get("/admin/")
        request.user = self.user
        with patch.object(admin.site, "get_app_list") as mock_get_app_list:
            mock_get_app_list.return_value = []
            response = custom_admin_view(request)
            self.assertEqual(response.status_code, 200)
            mock_get_app_list.assert_called_once_with(request)


class MediaProtectedTestCase(TestCase):
    """The staff gate on protected media.

    It used to be ``@staff_member_required``; that decorator redirects at
    ``admin:login``, which stopped reversing when the admin was unmounted, so
    the check is now spelled out against ``LOGIN_URL``.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _request(self, user):
        request = self.factory.get("/media/bills/proof.pdf")
        request.user = user
        return request

    def test_anonymous_is_redirected_to_login(self):
        response = media_protected(self._request(AnonymousUser()), "bills/proof.pdf")
        self.assertEqual(response.status_code, 302)
        # Whichever login page is configured — the OIDC provider's, or Django's
        # own form where OIDC is off. Naming one of them here pinned the test to
        # a deployment choice it does not care about.
        self.assertIn(settings.LOGIN_URL, response["Location"])

    def test_non_staff_is_redirected_to_login(self):
        user = User.objects.create_user("member", "member@example.com", "pw")
        response = media_protected(self._request(user), "bills/proof.pdf")
        self.assertEqual(response.status_code, 302)

    def test_inactive_staff_is_redirected_to_login(self):
        user = User.objects.create_user("gone", "gone@example.com", "pw")
        user.is_staff = True
        user.is_active = False
        user.save()
        response = media_protected(self._request(user), "bills/proof.pdf")
        self.assertEqual(response.status_code, 302)

    @override_settings(DEBUG=False)
    def test_staff_is_served_the_file(self):
        user = User.objects.create_user("staff", "staff@example.com", "pw")
        user.is_staff = True
        user.save()
        response = media_protected(self._request(user), "bills/proof.pdf")
        self.assertEqual(response["X-Accel-Redirect"], "/protected/bills/proof.pdf")


class BuiltinLoginPageTestCase(TestCase):
    """Whether a password form is served depends on the deployment.

    The OAuth2 authorization endpoint sends an anonymous visitor to
    ``settings.LOGIN_URL``. Where an identity provider is configured that is the
    provider's own page and this form must not exist; where one is not, Django's
    form stands in, because the admin's own login lives under ``/kompass`` —
    which the new frontend's router owns on its domain — and anything inside
    ``i18n_patterns`` is answered with a locale redirect into that router.
    """

    @override_settings(OIDC_ENABLED=True)
    def test_an_identity_provider_leaves_no_password_form_reachable(self):
        # ModelBackend is always in AUTHENTICATION_BACKENDS, so a form served
        # here would be a way around the provider's MFA and deprovisioning for
        # anyone still holding a local password.
        # The view's 404 makes LocaleMiddleware retry the prefixed path, which
        # is not mounted either; what matters is that following the whole chain
        # never arrives at something taking a password.
        page = self.client.get("/accounts/login/", follow=True)
        self.assertEqual(page.status_code, 404)
        self.assertNotContains(page, 'name="password"', status_code=404)

    @override_settings(OIDC_ENABLED=False)
    def test_without_one_the_builtin_form_renders(self):
        page = self.client.get("/accounts/login/")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'name="username"')
        self.assertContains(page, 'name="password"')
        self.assertContains(page, "csrfmiddlewaretoken")

    @override_settings(OIDC_ENABLED=False)
    def test_the_form_signs_a_user_in(self):
        User.objects.create_user("anmelder", "anmelder@example.com", "ein-langes-pw-42")
        r = self.client.post(
            "/accounts/login/", {"username": "anmelder", "password": "ein-langes-pw-42"}
        )
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], settings.LOGIN_REDIRECT_URL)

    @override_settings(OIDC_ENABLED=False)
    def test_the_form_is_not_behind_a_locale_prefix(self):
        # A redirect to /de/accounts/login/ would land on the frontend's router
        # when this is reached through the frontend's own domain.
        self.assertEqual(self.client.get("/de/accounts/login/").status_code, 404)
