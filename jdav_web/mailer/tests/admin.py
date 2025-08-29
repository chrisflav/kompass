import json
import unittest
from http import HTTPStatus
from django.test import TestCase, override_settings
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory, Client
from django.contrib.auth.models import User, Permission
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
from django.conf import settings

from members.tests.utils import create_custom_user
from members.models import Member, MALE, DIVERSE, Group
from ..models import Message, Attachment, EmailAddress
from ..admin import MessageAdmin, submit_message
from ..mailutils import SENT, NOT_SENT, PARTLY_SENT


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

    def _add_middleware(self, request):
        """Add required middleware to request."""
        # Session middleware
        middleware = SessionMiddleware(lambda x: None)
        middleware.process_request(request)
        request.session.save()

        # Messages middleware
        messages_middleware = MessageMiddleware(lambda x: None)
        messages_middleware.process_request(request)
        request._messages = FallbackStorage(request)


class MessageAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(Message, MessageAdmin)

        # Create test data
        self.group = Group.objects.create(name='Test Group')
        self.email_address = EmailAddress.objects.create(name='testmail')

        # Create test member with internal email
        self.internal_member = Member.objects.create(
            prename='Internal',
            lastname='User',
            birth_date=timezone.now().date(),
            email=f'internal@{settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER[0]}',
            gender=DIVERSE
        )

        # Create test member with external email
        self.external_member = Member.objects.create(
            prename='External',
            lastname='User',
            birth_date=timezone.now().date(),
            email='external@example.com',
            gender=DIVERSE
        )

        # Create users for testing
        self.user_with_internal_member = User.objects.create_user(username='testuser', password='secret')
        self.user_with_internal_member.member = self.internal_member
        self.user_with_internal_member.save()

        self.user_with_external_member = User.objects.create_user(username='external_user', password='secret')
        self.user_with_external_member.member = self.external_member
        self.user_with_external_member.save()

        self.user_without_member = User.objects.create_user(username='no_member_user', password='secret')

        # Create test message
        self.message = Message.objects.create(
            subject='Test Message',
            content='Test content'
        )
        self.message.to_groups.add(self.group)
        self.message.to_members.add(self.internal_member)

    def test_save_model_sets_created_by(self):
        """Test that save_model sets created_by when creating new message."""
        request = self.factory.post('/admin/mailer/message/add/')
        request.user = self.user_with_internal_member

        # Create new message
        new_message = Message(subject='New Message', content='New content')

        # Test save_model for new object (change=False)
        self.admin.save_model(request, new_message, None, change=False)

        self.assertEqual(new_message.created_by, self.internal_member)

    def test_save_model_does_not_change_created_by_on_update(self):
        """Test that save_model doesn't change created_by when updating."""
        request = self.factory.post('/admin/mailer/message/1/change/')
        request.user = self.user_with_internal_member

        # Message already has created_by set
        self.message.created_by = self.external_member

        # Test save_model for existing object (change=True)
        self.admin.save_model(request, self.message, None, change=True)

        self.assertEqual(self.message.created_by, self.external_member)

    @patch('mailer.models.Message.submit')
    def test_submit_message_success(self, mock_submit):
        """Test submit_message with successful send."""
        mock_submit.return_value = SENT

        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test submit_message
        submit_message(self.message, request)

        # Verify submit was called with correct sender
        mock_submit.assert_called_once_with(self.internal_member)

        # Check success message
        messages_list = list(get_messages(request))
        self.assertEqual(len(messages_list), 1)
        self.assertIn(str(_('Successfully sent message')), str(messages_list[0]))

    @patch('mailer.models.Message.submit')
    def test_submit_message_not_sent(self, mock_submit):
        """Test submit_message when sending fails."""
        mock_submit.return_value = NOT_SENT

        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test submit_message
        submit_message(self.message, request)

        # Check error message
        messages_list = list(get_messages(request))
        self.assertEqual(len(messages_list), 1)
        self.assertIn(str(_('Failed to send message')), str(messages_list[0]))

    @patch('mailer.models.Message.submit')
    def test_submit_message_partly_sent(self, mock_submit):
        """Test submit_message when partially sent."""
        mock_submit.return_value = PARTLY_SENT

        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test submit_message
        submit_message(self.message, request)

        # Check warning message
        messages_list = list(get_messages(request))
        self.assertEqual(len(messages_list), 1)
        self.assertIn(str(_('Failed to send some messages')), str(messages_list[0]))

    def test_submit_message_user_has_no_member(self):
        """Test submit_message when user has no associated member."""
        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_without_member
        self._add_middleware(request)

        # Test submit_message
        submit_message(self.message, request)

        # Check error message
        messages_list = list(get_messages(request))
        self.assertEqual(len(messages_list), 1)
        self.assertIn(str(_('Your account is not connected to a member. Please contact your system administrator.')), str(messages_list[0]))

    def test_submit_message_user_has_external_email(self):
        """Test submit_message when user has external email."""
        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_with_external_member
        self._add_middleware(request)

        # Test submit_message
        submit_message(self.message, request)

        # Check error message
        messages_list = list(get_messages(request))
        self.assertEqual(len(messages_list), 1)
        self.assertIn(str(_('Your email address is not an internal email address. Please use an email address with one of the following domains: %(domains)s.') % {'domains': ", ".join(settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER)}), str(messages_list[0]))

    @patch('mailer.admin.submit_message')
    def test_send_message_action_confirmed(self, mock_submit_message):
        """Test send_message action when confirmed."""
        request = self.factory.post('/admin/mailer/message/', {'confirmed': 'true'})
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        queryset = Message.objects.filter(pk=self.message.pk)

        # Test send_message action
        result = self.admin.send_message(request, queryset)

        # Verify submit_message was called for each message
        mock_submit_message.assert_called_once_with(self.message, request)

        # Should return None when confirmed (no template response)
        self.assertIsNone(result)

    def test_send_message_action_not_confirmed(self):
        """Test send_message action when not confirmed (shows confirmation page)."""
        request = self.factory.post('/admin/mailer/message/')
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        queryset = Message.objects.filter(pk=self.message.pk)

        # Test send_message action
        result = self.admin.send_message(request, queryset)

        # Should return HttpResponse with confirmation template
        self.assertIsNotNone(result)
        self.assertEqual(result.status_code, HTTPStatus.OK)

    @patch('mailer.admin.submit_message')
    def test_response_change_with_send(self, mock_submit_message):
        """Test response_change when _send is in POST."""
        request = self.factory.post('/admin/mailer/message/1/change/', {'_send': 'Send'})
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test response_change
        with patch.object(self.admin.__class__.__bases__[2], 'response_change') as mock_super:
            mock_super.return_value = HttpResponseRedirect('/admin/')
            result = self.admin.response_change(request, self.message)

            # Verify submit_message was called
            mock_submit_message.assert_called_once_with(self.message, request)

            # Verify super method was called
            mock_super.assert_called_once()

    @patch('mailer.admin.submit_message')
    def test_response_change_without_send(self, mock_submit_message):
        """Test response_change when _send is not in POST."""
        request = self.factory.post('/admin/mailer/message/1/change/', {'_save': 'Save'})
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test response_change
        with patch.object(self.admin.__class__.__bases__[2], 'response_change') as mock_super:
            mock_super.return_value = HttpResponseRedirect('/admin/')
            result = self.admin.response_change(request, self.message)

            # Verify submit_message was NOT called
            mock_submit_message.assert_not_called()

            # Verify super method was called
            mock_super.assert_called_once()

    @patch('mailer.admin.submit_message')
    def test_response_add_with_send(self, mock_submit_message):
        """Test response_add when _send is in POST."""
        request = self.factory.post('/admin/mailer/message/add/', {'_send': 'Send'})
        request.user = self.user_with_internal_member
        self._add_middleware(request)

        # Test response_add
        with patch.object(self.admin.__class__.__bases__[2], 'response_add') as mock_super:
            mock_super.return_value = HttpResponseRedirect('/admin/')
            result = self.admin.response_add(request, self.message)

            # Verify submit_message was called
            mock_submit_message.assert_called_once_with(self.message, request)

            # Verify super method was called
            mock_super.assert_called_once()

    def test_get_form_with_members_param(self):
        """Test get_form when members parameter is provided."""
        # Create request with members parameter
        members_ids = [self.internal_member.pk, self.external_member.pk]
        request = self.factory.get(f'/admin/mailer/message/add/?members={json.dumps(members_ids)}')
        request.user = self.user_with_internal_member

        # Test get_form
        form_class = self.admin.get_form(request)
        form = form_class()

        # Verify initial members are set
        self.assertEqual(list(form.fields['to_members'].initial), [self.internal_member, self.external_member])

    def test_get_form_with_invalid_members_param(self):
        """Test get_form when members parameter is not a list."""
        # Create request with invalid members parameter
        request = self.factory.get('/admin/mailer/message/add/?members="not_a_list"')
        request.user = self.user_with_internal_member

        # Test get_form
        form_class = self.admin.get_form(request)

        # Should return form without modification
        self.assertIsNotNone(form_class)

    def test_get_form_without_members_param(self):
        """Test get_form when no members parameter is provided."""
        # Create request without members parameter
        request = self.factory.get('/admin/mailer/message/add/')
        request.user = self.user_with_internal_member

        # Test get_form
        form_class = self.admin.get_form(request)

        # Should return form without modification
        self.assertIsNotNone(form_class)
