from unittest.mock import Mock
from unittest.mock import patch

from django.conf import settings
from django.contrib import admin
from django.contrib.auth.models import User
from django.test import override_settings
from django.test import RequestFactory
from django.test import TestCase

from logindata.oidc import MyOIDCAB

CLAIMS = {
    settings.OIDC_CLAIM_USERNAME: "testuser",
    "groups": [settings.OIDC_GROUP_STAFF, settings.OIDC_GROUP_SUPERUSER],
}
CLAIMS2 = {
    settings.OIDC_CLAIM_USERNAME: "foo",
}


class MyOIDCABTestCase(TestCase):
    """
    Test the OpenID Connect authentication backend.
    """
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
        self.assertTrue(
            User.objects.filter(username=CLAIMS2[settings.OIDC_CLAIM_USERNAME]).exists()
        )

    def test_update_user(self):
        self.ab.update_user(self.user, CLAIMS)
        self.assertTrue(self.user.is_staff)
        self.assertTrue(self.user.is_superuser)
