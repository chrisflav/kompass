from django.test import TestCase, RequestFactory, override_settings
from django.contrib.auth.models import User
from django.contrib import admin
from unittest.mock import Mock, patch
from jdav_web.views import media_unprotected, custom_admin_view
from startpage.models import Link


class ViewsTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.user = User.objects.create_user('testuser', 'test@example.com', 'password')
        Link.objects.create(title='Test Link', url='https://example.com')

    @override_settings(DEBUG=True)
    def test_media_unprotected_debug_true(self):
        request = self.factory.get('/media/test.jpg')
        with patch('jdav_web.views.serve') as mock_serve:
            mock_serve.return_value = Mock()
            result = media_unprotected(request, 'test.jpg')
            mock_serve.assert_called_once()

    def test_custom_admin_view(self):
        request = self.factory.get('/admin/')
        request.user = self.user
        with patch.object(admin.site, 'get_app_list') as mock_get_app_list:
            mock_get_app_list.return_value = []
            response = custom_admin_view(request)
            self.assertEqual(response.status_code, 200)
            mock_get_app_list.assert_called_once_with(request)
