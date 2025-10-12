import unittest
from http import HTTPStatus
from django.test import TestCase, override_settings
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, Client
from django.contrib.auth.models import User, Permission
from django.contrib.auth import models as authmodels
from django.utils import timezone
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.messages.middleware import MessageMiddleware
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.messages import get_messages
from django.utils.translation import gettext_lazy as _
from django.urls import reverse, reverse_lazy
from django.http import HttpResponseRedirect, HttpResponse
from unittest.mock import Mock, patch
from django.test.utils import override_settings
from django.urls import path, include
from django.contrib import admin as django_admin

from members.tests.utils import create_custom_user
from members.models import Member, MALE, Freizeit, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE
from ..models import (
    Ledger, Statement, StatementUnSubmitted, StatementConfirmed, Transaction, Bill,
    StatementSubmitted
)
from ..admin import (
    LedgerAdmin, StatementAdmin, TransactionAdmin, BillAdmin
)


class AdminTestCase(TestCase):
    def setUp(self, model, admin):
        self.factory = RequestFactory()
        self.model = model
        if model is not None and admin is not None:
            self.admin = admin(model, AdminSite())
        superuser = User.objects.create_superuser(
            username='superuser', password='secret'
        )
        standard = create_custom_user('standard', ['Standard'], 'Paul', 'Wulter')
        trainer = create_custom_user('trainer', ['Standard', 'Trainings'], 'Lise', 'Lotte')
        treasurer = create_custom_user('treasurer', ['Standard', 'Finance'], 'Lara', 'Litte')
        materialwarden = create_custom_user('materialwarden', ['Standard', 'Material'], 'Loro', 'Lutte')

    def _login(self, name):
        c = Client()
        res = c.login(username=name, password='secret')
        # make sure we logged in
        assert res
        return c


class StatementUnSubmittedAdminTestCase(AdminTestCase):
    """Test cases for StatementAdmin in the case of unsubmitted statements"""

    def setUp(self):
        super().setUp(model=Statement, admin=StatementAdmin)

        self.superuser = User.objects.get(username='superuser')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.superuser
        )

        self.statement = StatementUnSubmitted.objects.create(
            short_description='Test Statement',
            explanation='Test explanation',
            night_cost=25
        )

        # Create excursion for testing
        self.excursion = Freizeit.objects.create(
            name='Test Excursion',
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1
        )

        # Create confirmed statement with excursion
        self.statement_with_excursion = StatementUnSubmitted.objects.create(
            short_description='With Excursion',
            explanation='Test explanation',
            night_cost=25,
            excursion=self.excursion,
        )

    def test_save_model_with_member(self):
        """Test save_model sets created_by for new objects"""
        request = self.factory.post('/')
        request.user = self.superuser

        # Test with change=False (new object)
        new_statement = Statement(short_description='New Statement')
        self.admin.save_model(request, new_statement, None, change=False)
        self.assertEqual(new_statement.created_by, self.member)

    def test_has_delete_permission(self):
        """Test if unsubmitted statements may be deleted"""
        request = self.factory.post('/')
        request.user = self.superuser
        self.assertTrue(self.admin.has_delete_permission(request, self.statement))

    def test_get_inlines(self):
        """Test get_inlines"""
        request = self.factory.post('/')
        request.user = self.superuser
        self.assertEqual(len(self.admin.get_inlines(request, self.statement)), 1)

    def test_get_readonly_fields_submitted(self):
        """Test readonly fields when statement is submitted"""
        # Mark statement as submitted
        self.statement.status = Statement.SUBMITTED
        readonly_fields = self.admin.get_readonly_fields(None, self.statement)
        self.assertIn('status', readonly_fields)
        self.assertIn('excursion', readonly_fields)
        self.assertIn('short_description', readonly_fields)

    def test_get_readonly_fields_not_submitted(self):
        """Test readonly fields when statement is not submitted"""
        readonly_fields = self.admin.get_readonly_fields(None, self.statement)
        self.assertEqual(readonly_fields, ['status', 'excursion'])

    def test_submit_view_insufficient_permission(self):
        url = reverse('admin:finance_statement_submit',
                      args=(self.statement.pk,))
        c = self._login('standard')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Insufficient permissions.'))

    def test_submit_view_get(self):
        url = reverse('admin:finance_statement_submit',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Submit statement'))

    def test_submit_view_get_with_excursion(self):
        url = reverse('admin:finance_statement_submit',
                      args=(self.statement_with_excursion.pk,))
        c = self._login('superuser')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Finance overview'))

    def test_submit_view_post(self):
        url = reverse('admin:finance_statement_submit',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'apply': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        text = _("Successfully submited %(name)s. The finance department will notify the requestors as soon as possible.") % {'name': str(self.statement)}
        self.assertContains(response, text)


class StatementSubmittedAdminTestCase(AdminTestCase):
    """Test cases for StatementAdmin in the case of submitted statements"""

    def setUp(self):
        super().setUp(model=Statement, admin=StatementAdmin)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.finance_user = User.objects.create_user('finance', 'finance@example.com', 'pass')
        self.finance_user.groups.add(authmodels.Group.objects.get(name='Finance'),
                                     authmodels.Group.objects.get(name='Standard'))

        self.statement = Statement.objects.create(
            short_description='Submitted Statement',
            explanation='Test explanation',
            status=Statement.SUBMITTED,
            submitted_by=self.member,
            submitted_date=timezone.now(),
            night_cost=25
        )
        self.statement_unsubmitted = StatementUnSubmitted.objects.create(
            short_description='Submitted Statement',
            explanation='Test explanation',
            night_cost=25
        )
        self.transaction = Transaction.objects.create(
            reference='verylonglong' * 14,
            amount=3,
            statement=self.statement,
            member=self.member,
        )

        # Create commonly used test objects
        self.ledger = Ledger.objects.create(name='Test Ledger')
        self.excursion = Freizeit.objects.create(
            name='Test Excursion',
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1
        )
        self.other_member = Member.objects.create(
            prename="Other", lastname="Member", birth_date=timezone.now().date(),
            email="other@example.com", gender=MALE
        )

        # Create statements for generate transactions tests
        self.statement_no_trans_success = Statement.objects.create(
            short_description='No Transactions Success',
            explanation='Test explanation',
            status=Statement.SUBMITTED,
            submitted_by=self.member,
            submitted_date=timezone.now(),
            night_cost=25
        )
        self.statement_no_trans_error = Statement.objects.create(
            short_description='No Transactions Error',
            explanation='Test explanation',
            status=Statement.SUBMITTED,
            submitted_by=self.member,
            submitted_date=timezone.now(),
            night_cost=25
        )

        # Create bills for generate transactions tests
        self.bill_for_success = Bill.objects.create(
            statement=self.statement_no_trans_success,
            short_description='Test Bill Success',
            amount=50,
            paid_by=self.member,
            costs_covered=True
        )
        self.bill_for_error = Bill.objects.create(
            statement=self.statement_no_trans_error,
            short_description='Test Bill Error',
            amount=50,
            paid_by=None,  # No payer will cause generate_transactions to fail
            costs_covered=True,
        )

    def _create_matching_bill(self, statement=None, amount=None):
        """Helper method to create a bill that matches transaction amount"""
        return Bill.objects.create(
            statement=statement or self.statement,
            short_description='Test Bill',
            amount=amount or self.transaction.amount,
            paid_by=self.member,
            costs_covered=True
        )

    def _create_non_matching_bill(self, statement=None, amount=100):
        """Helper method to create a bill that doesn't match transaction amount"""
        return Bill.objects.create(
            statement=statement or self.statement,
            short_description='Non-matching Bill',
            amount=amount,
            paid_by=self.member
        )

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

    def test_readonly_fields(self):
        self.assertNotIn('explanation',
                         self.admin.get_readonly_fields(None, self.statement_unsubmitted))

    def test_change(self):
        url = reverse('admin:finance_statement_change',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_overview_view(self):
        url = reverse('admin:finance_statement_overview',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('View submitted statement'))

    def test_overview_view_statement_not_found(self):
        """Test overview_view with statement that can't be found in StatementSubmitted queryset"""
        # When trying to access an unsubmitted statement via StatementSubmitted admin,
        # the decorator will fail to find it and show "Statement not found"
        self.statement.status = Statement.UNSUBMITTED
        self.statement.save()

        url = reverse('admin:finance_statement_overview', args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        messages = list(get_messages(response.wsgi_request))
        expected_text = str(_("Statement not found."))
        self.assertTrue(any(expected_text in str(msg) for msg in messages))

    def test_overview_view_transaction_execution_confirm(self):
        """Test overview_view transaction execution confirm"""
        # Set up statement to be valid for confirmation
        self.transaction.ledger = self.ledger
        self.transaction.save()

        # Create a bill that matches the transaction amount to make it valid
        self._create_matching_bill()

        url = reverse('admin:finance_statement_overview', args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'transaction_execution_confirm': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        success_text = _("Successfully confirmed %(name)s. I hope you executed the associated transactions, I wont remind you again.") % {'name': str(self.statement)}
        self.assertContains(response, success_text)
        self.statement.refresh_from_db()
        self.assertTrue(self.statement.confirmed)

    def test_overview_view_transaction_execution_confirm_and_send(self):
        """Test overview_view transaction execution confirm and send"""
        # Set up statement to be valid for confirmation
        self.transaction.ledger = self.ledger
        self.transaction.save()

        # Create a bill that matches the transaction amount to make it valid
        self._create_matching_bill()

        url = reverse('admin:finance_statement_overview', args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'transaction_execution_confirm_and_send': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        success_text = _("Successfully sent receipt to the office.")
        self.assertContains(response, success_text)

    def test_overview_view_confirm_valid(self):
        """Test overview_view confirm with valid statement"""
        # Create a statement with valid configuration
        # Set up transaction with ledger to make it valid
        self.transaction.ledger = self.ledger
        self.transaction.save()

        # Create a bill that matches the transaction amount to make total valid
        self._create_matching_bill()

        url = reverse('admin:finance_statement_overview',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, data={'confirm': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Statement confirmed'))

    def test_overview_view_confirm_non_matching_transactions(self):
        """Test overview_view confirm with non-matching transactions"""
        # Create a bill that doesn't match the transaction
        self._create_non_matching_bill()

        url = reverse('admin:finance_statement_overview',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'confirm': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        error_text = _("Transactions do not match the covered expenses. Please correct the mistakes listed below.")
        self.assertContains(response, error_text)

    def test_overview_view_confirm_missing_ledger(self):
        """Test overview_view confirm with missing ledger"""
        # Ensure transaction has no ledger (ledger=None)
        self.transaction.ledger = None
        self.transaction.save()

        # Create a bill that matches the transaction amount to pass the first check
        self._create_matching_bill()

        url = reverse('admin:finance_statement_overview',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'confirm': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check the Django messages for the error
        messages = list(get_messages(response.wsgi_request))
        expected_text = str(_("Some transactions have no ledger configured. Please fill in the gaps."))
        self.assertTrue(any(expected_text in str(msg) for msg in messages))

    def test_overview_view_confirm_invalid_allowance_to(self):
        """Test overview_view confirm with invalid allowance"""
        # Create excursion and set up invalid allowance configuration
        self.statement.excursion = self.excursion
        self.statement.save()

        # Add allowance recipient who is not a youth leader for this excursion
        self.statement_no_trans_success.allowance_to.add(self.other_member)

        # Generate required transactions
        self.statement_no_trans_success.generate_transactions()
        for trans in self.statement_no_trans_success.transaction_set.all():
            trans.ledger = self.ledger
            trans.save()

        # Check validity obstruction is allowances
        self.assertEqual(self.statement_no_trans_success.validity, Statement.INVALID_ALLOWANCE_TO)

        url = reverse('admin:finance_statement_overview',
                      args=(self.statement_no_trans_success.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'confirm': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check the Django messages for the error
        messages = list(get_messages(response.wsgi_request))
        expected_text = str(_("The configured recipients for the allowance don't match the regulations. Please correct this on the excursion."))
        self.assertTrue(any(expected_text in str(msg) for msg in messages))

    def test_overview_view_reject(self):
        """Test overview_view reject statement"""
        url = reverse('admin:finance_statement_overview', args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'reject': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        success_text = _("Successfully rejected %(name)s. The requestor can reapply, when needed.") %\
            {'name': str(self.statement)}
        self.assertContains(response, success_text)

        # Verify statement was rejected
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.submitted)

    def test_overview_view_generate_transactions_existing(self):
        """Test overview_view generate transactions with existing transactions"""
        # Ensure there's already a transaction
        self.assertTrue(self.statement.transaction_set.count() > 0)

        url = reverse('admin:finance_statement_overview', args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'generate_transactions': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        error_text = _("%(name)s already has transactions. Please delete them first, if you want to generate new ones") % {'name': str(self.statement)}
        self.assertContains(response, error_text)

    def test_overview_view_generate_transactions_success(self):
        """Test overview_view generate transactions successfully"""
        url = reverse('admin:finance_statement_overview',
                      args=(self.statement_no_trans_success.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'generate_transactions': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        success_text = _("Successfully generated transactions for %(name)s") %\
            {'name': str(self.statement_no_trans_success)}
        self.assertContains(response, success_text)

    def test_overview_view_generate_transactions_error(self):
        """Test overview_view generate transactions with error"""
        url = reverse('admin:finance_statement_overview',
                      args=(self.statement_no_trans_error.pk,))
        c = self._login('superuser')
        response = c.post(url, follow=True, data={'generate_transactions': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        messages = list(get_messages(response.wsgi_request))
        expected_text = str(_("Error while generating transactions for %(name)s. Do all bills have a payer and, if this statement is attached to an excursion, was a person selected that receives the subsidies?") %\
            {'name': str(self.statement_no_trans_error)})
        self.assertTrue(any(expected_text in str(msg) for msg in messages))

    def test_reduce_transactions_view(self):
        url = reverse('admin:finance_statement_reduce_transactions',
                      args=(self.statement.pk,))
        c = self._login('superuser')
        response = c.get(url, data={'redirectTo': reverse('admin:finance_statement_changelist')},
                         follow=True)
        self.assertContains(response,
                            _("Successfully reduced transactions for %(name)s.") %\
                            {'name': str(self.statement)})


class StatementConfirmedAdminTestCase(AdminTestCase):
    """Test cases for StatementAdmin in the case of confirmed statements"""

    def setUp(self):
        super().setUp(model=Statement, admin=StatementAdmin)

        self.user = User.objects.create_user('testuser', 'test@example.com', 'pass')
        self.member = Member.objects.create(
            prename="Test", lastname="User", birth_date=timezone.now().date(),
            email="test@example.com", gender=MALE, user=self.user
        )

        self.finance_user = User.objects.create_user('finance', 'finance@example.com', 'pass')
        self.finance_user.groups.add(authmodels.Group.objects.get(name='Finance'),
                                     authmodels.Group.objects.get(name='Standard'))

        # Create a base statement first
        base_statement = Statement.objects.create(
            short_description='Confirmed Statement',
            explanation='Test explanation',
            status=Statement.CONFIRMED,
            confirmed_by=self.member,
            confirmed_date=timezone.now(),
            night_cost=25
        )

        # StatementConfirmed is a proxy model, so we can get it from the base statement
        self.statement = StatementConfirmed.objects.get(pk=base_statement.pk)

        # Create an unconfirmed statement for testing
        self.unconfirmed_statement = Statement.objects.create(
            short_description='Unconfirmed Statement',
            explanation='Test explanation',
            status=Statement.SUBMITTED,
            night_cost=25
        )

        # Create excursion for testing
        self.excursion = Freizeit.objects.create(
            name='Test Excursion',
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1
        )

        # Create confirmed statement with excursion
        confirmed_with_excursion_base = Statement.objects.create(
            short_description='Confirmed with Excursion',
            explanation='Test explanation',
            status=Statement.CONFIRMED,
            confirmed_by=self.member,
            confirmed_date=timezone.now(),
            excursion=self.excursion,
            night_cost=25
        )
        self.statement_with_excursion = StatementConfirmed.objects.get(pk=confirmed_with_excursion_base.pk)

    def _add_session_to_request(self, request):
        """Add session to request"""
        middleware = SessionMiddleware(lambda req: None)
        middleware.process_request(request)
        request.session.save()

        middleware = MessageMiddleware(lambda req: None)
        middleware.process_request(request)
        request._messages = FallbackStorage(request)

    def test_has_change_permission(self):
        """Test that change permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_change_permission(request, self.statement))

    def test_has_delete_permission(self):
        """Test that delete permission is disabled"""
        request = self.factory.get('/')
        request.user = self.finance_user
        self.assertFalse(self.admin.has_delete_permission(request, self.statement))

    def test_unconfirm_view_not_confirmed_statement(self):
        """Test unconfirm_view with statement that is not confirmed"""
        # Create request for unconfirmed statement
        request = self.factory.get('/')
        request.user = self.finance_user
        self._add_session_to_request(request)

        # Test with unconfirmed statement (should trigger error path)
        self.assertFalse(self.unconfirmed_statement.confirmed)

        # Call unconfirm_view - this should go through error path
        response = self.admin.unconfirm_view(request, self.unconfirmed_statement.pk)

        # Should redirect due to not confirmed error
        self.assertEqual(response.status_code, 302)

    def test_unconfirm_view_post_unconfirm_action(self):
        """Test unconfirm_view POST request with 'unconfirm' action"""
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

    def test_statement_summary_view_insufficient_permission(self):
        url = reverse('admin:finance_statement_summary',
                      args=(self.statement_with_excursion.pk,))
        c = self._login('standard')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Insufficient permissions.'))

    def test_statement_summary_view_unconfirmed(self):
        url = reverse('admin:finance_statement_summary',
                      args=(self.unconfirmed_statement.pk,))
        c = self._login('superuser')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Statement not found.'))

    def test_statement_summary_view_confirmed_with_excursion(self):
        """Test statement_summary_view when statement is confirmed with excursion"""
        url = reverse('admin:finance_statement_summary',
                      args=(self.statement_with_excursion.pk,))
        c = self._login('superuser')
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.headers['Content-Type'], 'application/pdf')


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
