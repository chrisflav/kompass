from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase
from startpage.models import Link

from jdav_web.views import custom_admin_view
from jdav_web.views import media_unprotected
from jdav_web.oidc import MyOIDCAB


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

    def test_custom_admin_view(self):
        request = self.factory.get("/admin/")
        request.user = self.user
        with patch.object(admin.site, "get_app_list") as mock_get_app_list:
            mock_get_app_list.return_value = []
            response = custom_admin_view(request)
            self.assertEqual(response.status_code, 200)
            mock_get_app_list.assert_called_once_with(request)


CLAIMS = {
    settings.OIDC_CLAIM_USERNAME: "testuser",
    "groups": [settings.OIDC_GROUP_STAFF, settings.OIDC_GROUP_SUPERUSER],
}
CLAIMS2 = {
    settings.OIDC_CLAIM_USERNAME: "foo",
}


class MyOIDCABTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username=CLAIMS[settings.OIDC_CLAIM_USERNAME])
        self.ab = MyOIDCAB()

    def test_filter_users_by_claims(self):
        self.assertQuerysetEqual(self.ab.filter_users_by_claims(CLAIMS), [self.user])

    def test_get_username(self):
        self.assertEqual(self.ab.get_username(CLAIMS), CLAIMS[settings.OIDC_CLAIM_USERNAME])
        # When the passed claims contain no username information, a hash is used as username.
        self.assertIsNotNone(self.ab.get_username({}))

    def test_create_user(self):
        self.ab.create_user(CLAIMS2)
        self.assertTrue(User.objects.filter(username=CLAIMS2[settings.OIDC_CLAIM_USERNAME]).exists())

    def test_update_user(self):
        self.ab.update_user(self.user, CLAIMS)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
