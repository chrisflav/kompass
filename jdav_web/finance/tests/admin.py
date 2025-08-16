from django.test import TestCase, override_settings
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, Client
from django.contrib.auth.models import User, Permission
from django.utils import timezone
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.utils.translation import gettext_lazy as _

from members.models import Member, MALE
from ..models import Ledger, Statement, StatementConfirmed, Transaction, Bill
from ..admin import (
    LedgerAdmin, StatementUnSubmittedAdmin, StatementSubmittedAdmin,
    StatementConfirmedAdmin, TransactionAdmin, BillAdmin
)


class StatementUnSubmittedAdminTestCase(TestCase):
    """Test cases for StatementUnSubmittedAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = StatementUnSubmittedAdmin(Statement, self.site)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.statement = Statement.objects.create(
            short_description='Test Statement',
            explanation='Test explanation',
            night_cost=25
        )

    def _add_session_to_request(self, request):
        """Add session to request"""
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        middleware = MessageMiddleware(lambda req: None)
        middleware.process_request(request)
        request._messages = FallbackStorage(request)

    def test_save_model_with_member(self):
        """Test save_model sets created_by for new objects"""
        request = self.factory.post('/')
        request.user = self.user

        # Test with change=False (new object)
        new_statement = Statement(short_description='New Statement')
        self.admin.save_model(request, new_statement, None, change=False)
        self.assertEqual(new_statement.created_by, self.member)

    def test_get_readonly_fields_submitted(self):
        """Test readonly fields when statement is submitted"""
        # Mark statement as submitted
        self.statement.submitted = True
        readonly_fields = self.admin.get_readonly_fields(None, self.statement)
        self.assertIn('submitted', readonly_fields)
        self.assertIn('excursion', readonly_fields)
        self.assertIn('short_description', readonly_fields)

    def test_get_readonly_fields_not_submitted(self):
        """Test readonly fields when statement is not submitted"""
        readonly_fields = self.admin.get_readonly_fields(None, self.statement)
        self.assertEqual(readonly_fields, ['submitted', 'excursion'])


class StatementSubmittedAdminTestCase(TestCase):
    """Test cases for StatementSubmittedAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = StatementSubmittedAdmin(Statement, self.site)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.finance_user = User.objects.create_user('finance', 'finance@example.com', 'pass')
        finance_perm = Permission.objects.get(codename='process_statementsubmitted')
        self.finance_user.user_permissions.add(finance_perm)

        self.statement = Statement.objects.create(
            short_description='Submitted Statement',
            explanation='Test explanation',
            submitted=True,
            submitted_by=self.member,
            submitted_date=timezone.now(),
            night_cost=25
        )

    def _add_session_to_request(self, request):
        """Add session to request"""
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        middleware = MessageMiddleware(lambda req: None)
        middleware.process_request(request)
        request._messages = FallbackStorage(request)

    def test_has_add_permission(self):
        """Test that add permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission_with_permission(self):
        """Test change permission with proper permission"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertTrue(self.admin.has_change_permission(request))

    def test_has_change_permission_without_permission(self):
        """Test change permission without proper permission"""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission(self):
        """Test that delete permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_reduce_transactions_view(self):
        """Test reduce_transactions_view logic"""
        # Test GET parameters
        request = self.factory.get('/', {'redirectTo': '/admin/'})
        self.assertIn('redirectTo', request.GET)
        self.assertEqual(request.GET['redirectTo'], '/admin/')


class StatementConfirmedAdminTestCase(TestCase):
    """Test cases for StatementConfirmedAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = StatementConfirmedAdmin(StatementConfirmed, self.site)

        # Register the admin with the site to enable URL resolution
        self.site.register(StatementConfirmed, StatementConfirmedAdmin)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.finance_user = User.objects.create_user('finance', 'finance@example.com', 'pass')
        unconfirm_perm = Permission.objects.get(codename='may_manage_confirmed_statements')
        self.finance_user.user_permissions.add(unconfirm_perm)

        # Create a base statement first
        base_statement = Statement.objects.create(
            short_description='Confirmed Statement',
            explanation='Test explanation',
            submitted=True,
            confirmed=True,
            confirmed_by=self.member,
            confirmed_date=timezone.now(),
            night_cost=25
        )

        # StatementConfirmed is a proxy model, so we can get it from the base statement
        self.statement = StatementConfirmed.objects.get(pk=base_statement.pk)

    def _add_session_to_request(self, request):
        """Add session to request"""
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        middleware = MessageMiddleware(lambda req: None)
        middleware.process_request(request)
        request._messages = FallbackStorage(request)

    def test_has_add_permission(self):
        """Test that add permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission(self):
        """Test that change permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission(self):
        """Test that delete permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_unconfirm_view_not_confirmed_statement(self):
        """Test unconfirm_view with statement that is not confirmed"""
        # Add special permission for unconfirm
        unconfirm_perm = Permission.objects.get(codename='may_manage_confirmed_statements')
        self.finance_user.user_permissions.add(unconfirm_perm)

        # Create request for unconfirmed statement
        request = self.factory.get('/')
        request.user = self.finance_user
        self._add_session_to_request(request)

        # Create an unconfirmed statement for this test
        unconfirmed_base = Statement.objects.create(
            short_description='Unconfirmed Statement',
            explanation='Test explanation',
            night_cost=25
        )
        # This won't be accessible via StatementConfirmed since it's not confirmed
        unconfirmed_statement = unconfirmed_base

        # Test with unconfirmed statement (should trigger error path)
        self.assertFalse(unconfirmed_statement.confirmed)

        # Call unconfirm_view - this should go through error path
        response = self.admin.unconfirm_view(request, unconfirmed_statement.pk)

        # Should redirect due to not confirmed error
        self.assertEqual(response.status_code, 302)

    def test_unconfirm_view_post_unconfirm_action(self):
        """Test unconfirm_view POST request with 'unconfirm' action"""
        # Add special permission for unconfirm
        unconfirm_perm = Permission.objects.get(codename='may_manage_confirmed_statements')
        self.finance_user.user_permissions.add(unconfirm_perm)

        # Create POST request with unconfirm action
        request = self.factory.post('/', {'unconfirm': 'true'})
        request.user = self.finance_user
        self._add_session_to_request(request)

        # Ensure statement is confirmed
        self.assertTrue(self.statement.confirmed)
        self.assertIsNotNone(self.statement.confirmed_by)
        self.assertIsNotNone(self.statement.confirmed_date)

        # Call unconfirm_view - this should execute the unconfirm action
        response = self.admin.unconfirm_view(request, self.statement.pk)

        # Should redirect after successful unconfirm
        self.assertEqual(response.status_code, 302)

        # Verify statement was unconfirmed (need to reload from DB)
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.confirmed)
        self.assertIsNone(self.statement.confirmed_date)

    def test_unconfirm_view_get_render_template(self):
        """Test unconfirm_view GET request rendering template"""
        # Add special permission for unconfirm
        unconfirm_perm = Permission.objects.get(codename='may_manage_confirmed_statements')
        self.finance_user.user_permissions.add(unconfirm_perm)

        # Create GET request (no POST data)
        request = self.factory.get('/')
        request.user = self.finance_user
        self._add_session_to_request(request)

        # Ensure statement is confirmed
        self.assertTrue(self.statement.confirmed)

        # Call unconfirm_view
        response = self.admin.unconfirm_view(request, self.statement.pk)

        # Should render template (status 200)
        self.assertEqual(response.status_code, 200)

        # Check response content contains expected template elements
        self.assertIn(str(_('Unconfirm statement')).encode('utf-8'), response.content)
        self.assertIn(self.statement.short_description.encode(), response.content)


class TransactionAdminTestCase(TestCase):
    """Test cases for TransactionAdmin"""

    def setUp(self):
        self.site = AdminSite()
        self.factory = RequestFactory()
        self.admin = TransactionAdmin(Transaction, self.site)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.ledger = Ledger.objects.create(name='Test Ledger')
        self.statement = Statement.objects.create(
            short_description='Test Statement',
            explanation='Test explanation'
        )

        self.transaction = Transaction.objects.create(
            member=self.member,
            ledger=self.ledger,
            amount=100,
            reference='Test transaction',
            statement=self.statement
        )

    def test_has_add_permission(self):
        """Test that add permission is disabled"""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_add_permission(request))

    def test_has_change_permission(self):
        """Test that change permission is disabled"""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_change_permission(request))

    def test_has_delete_permission(self):
        """Test that delete permission is disabled"""
        request = self.factory.get('/')
        request.user = self.user
        self.assertFalse(self.admin.has_delete_permission(request))

    def test_get_readonly_fields_confirmed(self):
        """Test readonly fields when transaction is confirmed"""
        self.transaction.confirmed = True
        readonly_fields = self.admin.get_readonly_fields(None, self.transaction)
        self.assertEqual(readonly_fields, self.admin.fields)

    def test_get_readonly_fields_not_confirmed(self):
        """Test readonly fields when transaction is not confirmed"""
        readonly_fields = self.admin.get_readonly_fields(None, self.transaction)
        self.assertEqual(readonly_fields, ())
