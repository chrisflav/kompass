from datetime import timedelta
from unittest.mock import Mock
from unittest.mock import patch

from contrib.admin import CommonAdminMixin
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import models
from django.test import RequestFactory
from django.test import TestCase
from django.utils.translation import gettext_lazy as _
from rules.contrib.models import RulesModelBase
from rules.contrib.models import RulesModelMixin
from utils import file_size_validator
from utils import mondays_until_nth
from utils import RestrictedFileField

User = get_user_model()


class CommonModelTestCase(TestCase):
    def test_common_model_abstract_base(self):
        """Test that CommonModel provides the correct meta attributes"""
        meta = CommonModel._meta
        self.assertTrue(meta.abstract)
        expected_permissions = (
            "add_global",
            "change_global",
            "view_global",
            "delete_global",
            "list_global",
            "view",
        )
        self.assertEqual(meta.default_permissions, expected_permissions)

    def test_common_model_inheritance(self):
        """Test that CommonModel has rules mixin functionality"""
        # Test that CommonModel has the expected functionality
        # Since it's abstract, we can't instantiate it directly
        # but we can check its metaclass and mixins
        self.assertTrue(issubclass(CommonModel, RulesModelMixin))
        self.assertEqual(CommonModel.__class__, RulesModelBase)


class GlobalPermissionRulesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_has_global_perm_predicate_creation(self):
        """Test that has_global_perm creates a predicate function"""
        # has_global_perm is a decorator factory, not a direct predicate
        predicate = has_global_perm("auth.add_user")
        self.assertTrue(callable(predicate))

    def test_has_global_perm_with_superuser(self):
        """Test that superusers have global permissions"""
        self.user.is_superuser = True
        self.user.save()

        predicate = has_global_perm("auth.add_user")
        result = predicate(self.user, None)
        self.assertTrue(result)

    def test_has_global_perm_with_regular_user(self):
        """Test that regular users don't automatically have global permissions"""
        predicate = has_global_perm("auth.add_user")
        result = predicate(self.user, None)
        self.assertFalse(result)


class CommonAdminMixinTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")

    def test_formfield_for_dbfield_with_formfield_overrides(self):
        """Test formfield_for_dbfield when db_field class is in formfield_overrides"""

        # Create a test admin instance that inherits from Django's ModelAdmin
        class TestAdmin(CommonAdminMixin, admin.ModelAdmin):
            formfield_overrides = {models.ForeignKey: {"widget": Mock()}}

        # Create a mock model to use with the admin
        class TestModel:
            _meta = Mock()
            _meta.app_label = "test"

        admin_instance = TestAdmin(TestModel, admin.site)

        # Create a mock ForeignKey field to trigger the missing line 147
        db_field = models.ForeignKey(User, on_delete=models.CASCADE)

        # Create a test request
        request = RequestFactory().get("/")
        request.user = self.user

        # Call the method to test formfield_overrides usage
        result = admin_instance.formfield_for_dbfield(db_field, request, help_text="Test help text")

        # Verify that the formfield_overrides were used
        self.assertIsNotNone(result)


class UtilsTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass123"
        )

    def test_file_size_validator_exceeds_limit(self):
        """Test file_size_validator when file exceeds size limit"""
        validator = file_size_validator(1)  # 1MB limit

        # Create a mock file that exceeds the limit (2MB)
        mock_file = Mock()
        mock_file.size = 2 * 1024 * 1024  # 2MB

        with self.assertRaises(ValidationError) as cm:
            validator(mock_file)

        # Check for the translated error message
        expected_message = str(
            _("Please keep filesize under {} MiB. Current filesize: {:10.2f} MiB.").format(1, 2.00)
        )
        self.assertIn(expected_message, str(cm.exception))

    def test_restricted_file_field_content_type_not_supported(self):
        """Test RestrictedFileField when content type is not supported"""
        field = RestrictedFileField(content_types=["image/jpeg"])

        # Create mock data with unsupported content type
        mock_data = Mock()
        mock_data.file = Mock()
        mock_data.file.content_type = "text/plain"

        # Mock the super().clean() to return our mock data
        with patch.object(models.FileField, "clean", return_value=mock_data):
            with self.assertRaises(ValidationError) as cm:
                field.clean("dummy")

            # Check for the translated error message
            expected_message = str(_("Filetype not supported."))
            self.assertIn(expected_message, str(cm.exception))

    def test_restricted_file_field_size_exceeds_limit(self):
        """Test RestrictedFileField when file size exceeds limit"""
        field = RestrictedFileField(max_upload_size=1)  # 1 byte limit

        # Create mock data with file that exceeds size limit
        mock_data = Mock()
        mock_data.file = Mock()
        mock_data.file.content_type = "text/plain"
        mock_data.file._size = 2  # 2 bytes, exceeds limit

        # Mock the super().clean() to return our mock data
        with patch.object(models.FileField, "clean", return_value=mock_data):
            with self.assertRaises(ValidationError) as cm:
                field.clean("dummy")

            # Check for the translated error message
            expected_message = str(
                _("Please keep filesize under {}. Current filesize: {}").format(1, 2)
            )
            self.assertIn(expected_message, str(cm.exception))

    def test_mondays_until_nth(self):
        """Test mondays_until_nth function"""
        # Test with n=2 to get 3 Mondays (including the 0th)
        result = mondays_until_nth(2)

        # Should return a list of 3 dates
        self.assertEqual(len(result), 3)

        # All dates should be Mondays (weekday 0)
        for date in result:
            self.assertEqual(date.weekday(), 0)  # Monday is 0

        # Dates should be consecutive weeks
        self.assertEqual(result[1] - result[0], timedelta(days=7))
        self.assertEqual(result[2] - result[1], timedelta(days=7))
