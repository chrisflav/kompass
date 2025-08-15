from django.test import TestCase
from django.contrib.auth import get_user_model
from contrib.models import CommonModel
from contrib.rules import has_global_perm

User = get_user_model()

class CommonModelTestCase(TestCase):
    def test_common_model_abstract_base(self):
        """Test that CommonModel provides the correct meta attributes"""
        meta = CommonModel._meta
        self.assertTrue(meta.abstract)
        expected_permissions = (
            'add_global', 'change_global', 'view_global', 'delete_global', 'list_global', 'view',
        )
        self.assertEqual(meta.default_permissions, expected_permissions)

    def test_common_model_inheritance(self):
        """Test that CommonModel has rules mixin functionality"""
        # Test that CommonModel has the expected functionality
        # Since it's abstract, we can't instantiate it directly
        # but we can check its metaclass and mixins
        from rules.contrib.models import RulesModelMixin, RulesModelBase

        self.assertTrue(issubclass(CommonModel, RulesModelMixin))
        self.assertEqual(CommonModel.__class__, RulesModelBase)


class GlobalPermissionRulesTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

    def test_has_global_perm_predicate_creation(self):
        """Test that has_global_perm creates a predicate function"""
        # has_global_perm is a decorator factory, not a direct predicate
        predicate = has_global_perm('auth.add_user')
        self.assertTrue(callable(predicate))

    def test_has_global_perm_with_superuser(self):
        """Test that superusers have global permissions"""
        self.user.is_superuser = True
        self.user.save()

        predicate = has_global_perm('auth.add_user')
        result = predicate(self.user, None)
        self.assertTrue(result)

    def test_has_global_perm_with_regular_user(self):
        """Test that regular users don't automatically have global permissions"""
        predicate = has_global_perm('auth.add_user')
        result = predicate(self.user, None)
        self.assertFalse(result)
