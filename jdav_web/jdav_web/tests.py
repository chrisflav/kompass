from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase

from jdav_web.settings import _load_toml
from jdav_web.views import media_protected
from jdav_web.views import media_unprotected


class LoadTomlTestCase(TestCase):
    def test_returns_empty_dict_for_missing_file(self):
        self.assertEqual(_load_toml("/nonexistent/path/settings.toml"), {})


class ViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

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
