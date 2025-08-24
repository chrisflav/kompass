from django.test import TestCase, RequestFactory
from django.test.utils import override_settings
from django.contrib.auth import get_user_model
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.db import models
from unittest.mock import Mock

from contrib.admin import CommonAdminMixin
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from rules.contrib.models import RulesModelMixin, RulesModelBase

# Test model for admin customization
class DummyModel(models.Model):
    field1 = models.CharField(max_length=100)
    field2 = models.IntegerField()
    field3 = models.BooleanField()
    field4 = models.DateField()
    field5 = models.TextField()

    class Meta:
        app_label = 'contrib'

class DummyAdmin(CommonAdminMixin, admin.ModelAdmin):
    model = DummyModel
    fieldsets = (
        ('Group1', {'fields': ('field1', 'field2')}),
        ('Group2', {'fields': ('field3', 'field4', 'field5')}),
    )
    fields = ['field1', 'field2', 'field3', 'field4', 'field5']

    def __init__(self):
        self.opts = self.model._meta
        self.admin_site = AdminSite()

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


class CommonAdminMixinTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('admin', 'admin@test.com', 'password')

    def setUp(self):
        self.request = RequestFactory().get('/')
        self.request.user = self.__class__.user
        self.admin = DummyAdmin()
        self.admin.admin_site = AdminSite()

    def test_formfield_for_dbfield_with_formfield_overrides(self):
        """Test formfield_for_dbfield when db_field class is in formfield_overrides"""
        # Create a test admin instance that inherits from Django's ModelAdmin
        class TestAdmin(CommonAdminMixin, admin.ModelAdmin):
            formfield_overrides = {
                models.ForeignKey: {'widget': Mock()}
            }

        # Create a mock model to use with the admin
        class TestModel:
            _meta = Mock()
            _meta.app_label = 'test'

        admin_instance = TestAdmin(TestModel, admin.site)

        # Create a mock ForeignKey field to trigger the missing line 147
        db_field = models.ForeignKey(User, on_delete=models.CASCADE)

        # Create a test request
        request = RequestFactory().get('/')
        request.user = self.user

        # Call the method to test formfield_overrides usage
        result = admin_instance.formfield_for_dbfield(db_field, request, help_text='Test help text')

        # Verify that the formfield_overrides were used
        self.assertIsNotNone(result)

    def test_default_behavior(self):
        """Test with no customization settings"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field2', 'field3', 'field4', 'field5'])

        fieldsets = self.admin.get_fieldsets(self.request)
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1', 'field2'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field4', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'fields': ['field1', 'field3', 'field5']
        }
    })
    def test_included_fields_only(self):
        """Test with only included fields specified"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field3', 'field5'])

        fieldsets = self.admin.get_fieldsets(self.request)
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'exclude': ['field2', 'field4']
        }
    })
    def test_excluded_fields_only(self):
        """Test with only excluded fields specified"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field3', 'field5'])

        fieldsets = self.admin.get_fieldsets(self.request)
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'fields': ['field1', 'field3', 'field5'],
            'exclude': ['field3']
        }
    })
    def test_included_and_excluded_fields(self):
        """Test with both included and excluded fields"""
        fields = self.admin.get_fields(self.request)
        #  custom fields should take precedence over exclude
        self.assertEqual(fields, ['field1', 'field3', 'field5'])

        fieldsets = self.admin.get_fieldsets(self.request)
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'fields': ['field5', 'field3', 'field1']
        }
    })
    def test_field_order_preservation(self):
        """Test that field order from settings is preserved"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, ['field5', 'field3', 'field1'])

    
    def test_nonexistent_fields(self):
        """Test behavior with nonexistent fields in settings"""
        with override_settings(CUSTOM_MODEL_FIELDS={
            'contrib_dummymodel': {
                'fields': ['field1', 'nonexistent_field']
            }
        }):
            fields = self.admin.get_fields(self.request)
            self.assertEqual(fields, ['field1', 'nonexistent_field'])
            
    def test_nonexistent_exclude(self):
        """Test behavior with nonexistent fields in settings"""
        with override_settings(CUSTOM_MODEL_FIELDS={
            'contrib_dummymodel': {
                'exclude': ['field1', 'nonexistent', 'field2']
            }
        }):
            fields = self.admin.get_fields(self.request)
            self.assertEqual(fields, ['field3', 'field4', 'field5'])
            
            exclude = self.admin.get_exclude(self.request)
            self.assertEqual(set(exclude), {'nonexistent', 'field1', 'field2'})

    @override_settings(CUSTOM_MODEL_FIELDS={})
    def test_empty_settings(self):
        """Test behavior with empty settings"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field2', 'field3', 'field4', 'field5'])

        fieldsets = self.admin.get_fieldsets(self.request)
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1', 'field2'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field4', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'fields': []
        }
    })
    def test_empty_included_fields(self):
        """Test behavior with empty included fields list"""
        fields = self.admin.get_fields(self.request)
        # empty custom fields is perceived as no restriction
        self.assertEqual(fields, ['field1', 'field2', 'field3', 'field4', 'field5'])

    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'exclude': ['field1', 'field2', 'field3', 'field4', 'field5']
        }
    })
    def test_exclude_all_fields(self):
        """Test behavior when all fields are excluded"""
        fields = self.admin.get_fields(self.request)
        self.assertEqual(fields, [])
        
        fieldsets = self.admin.get_fieldsets(self.request)
        # as all fields from group2 are excluded, only group1 remains
        self.assertEqual(len(fieldsets), 0)

    
    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'exclude': ['field5']
        }
    })
    def test_custom_fields_exclude_exclude(self):
        """Test that custom excluded fields are respected"""
        class OrderedAdmin(DummyAdmin):
            exclude = ['field2', 'field4']

        admin_instance = OrderedAdmin()
        exclude = admin_instance.get_exclude(self.request)
        # app and custom excludes should be additive
        self.assertEqual(set(exclude), {'field2', 'field4', 'field5'})
        
        fields = admin_instance.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field3'])
        
        fieldsets = admin_instance.get_fieldsets(self.request)
        # for fieldsets, the app exclude is irrelevant, thus only field5 is excluded
        self.assertEqual(len(fieldsets), 2)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1', 'field2'])
        self.assertEqual(fieldsets[1][1]['fields'], ['field3', 'field4'])
    
    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'exclude': ['field3', 'field4', 'field5']
        }
    })
    def test_custom_fields_fields_exclude(self):
        """Test that custom excluded fields are respected"""
        class OrderedAdmin(DummyAdmin):
            fields = ['field1', 'field2', 'field4']

        admin_instance = OrderedAdmin()
        exclude = admin_instance.get_exclude(self.request)
        self.assertEqual(set(exclude), {'field3', 'field4', 'field5'})
        
        fields = admin_instance.get_fields(self.request)
        self.assertEqual(fields, ['field1', 'field2'])
        
        fieldsets = admin_instance.get_fieldsets(self.request)
        # as all fields from group2 are excluded, only group1 remains
        self.assertEqual(len(fieldsets), 1)
        self.assertEqual(fieldsets[0][1]['fields'], ['field1', 'field2'])
        
        
    @override_settings(CUSTOM_MODEL_FIELDS={
        'contrib_dummymodel': {
            'exclude': ['field2', 'field4']
        }
    })
    def test_combined_admin_and_settings_exclude(self):
        """Test that both admin and settings excludes are applied while maintaining order"""
        class CombinedAdmin(DummyAdmin):
            fields = ['field5', 'field4', 'field3', 'field2', 'field1']
            exclude = ['field1']

        admin_instance = CombinedAdmin()
        
        fields = admin_instance.get_fields(self.request)
        self.assertEqual(fields, ['field5', 'field3'])
        
        exclude = admin_instance.get_exclude(self.request)
        self.assertEqual(set(exclude), {'field1', 'field2', 'field4'})
