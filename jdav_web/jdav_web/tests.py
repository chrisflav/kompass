from unittest.mock import Mock
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from startpage.models import Link

from jdav_web.views import custom_admin_view
from jdav_web.views import media_unprotected


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
        self.assertEqual(response["X-Accel-Redirect"], "/protected/folder/test%C3%A4%C3%B6%C3%BC.jpg")
        self.assertNotIn("Content-Type", response)

    def test_custom_admin_view(self):
        request = self.factory.get("/admin/")
        request.user = self.user
        with patch.object(admin.site, "get_app_list") as mock_get_app_list:
            mock_get_app_list.return_value = []
            response = custom_admin_view(request)
            self.assertEqual(response.status_code, 200)
            mock_get_app_list.assert_called_once_with(request)
