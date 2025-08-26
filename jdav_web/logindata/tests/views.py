from http import HTTPStatus
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.contrib.auth.models import User, Group

from members.models import Member, DIVERSE
from ..models import RegistrationPassword, initial_user_setup


class RegistrationPasswordTestCase(TestCase):
    def test_str_method(self):
        """Test RegistrationPassword __str__ method returns password"""
        reg_password = RegistrationPassword.objects.create(password="test123")
        self.assertEqual(str(reg_password), "test123")


class RegisterViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create a test member with invite key
        self.member = Member.objects.create(
            prename='Test',
            lastname='User',
            birth_date=timezone.now().date(),
            email='test@example.com',
            gender=DIVERSE,
            invite_as_user_key='test_key_123'
        )

        # Create a registration password
        self.registration_password = RegistrationPassword.objects.create(
            password='test_password'
        )

        # Get or create Standard group for user setup
        self.standard_group, created = Group.objects.get_or_create(name='Standard')

    def test_register_get_without_key_redirects(self):
        """Test GET request without key redirects to startpage."""
        url = reverse('logindata:register')
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_register_post_without_key_redirects(self):
        """Test POST request without key redirects to startpage."""
        url = reverse('logindata:register')
        response = self.client.post(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_register_get_with_empty_key_shows_failed(self):
        """Test GET request with empty key shows registration failed page."""
        url = reverse('logindata:register')
        response = self.client.get(url, {'key': ''})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Something went wrong. The registration key is invalid or has expired.'))

    def test_register_get_with_invalid_key_shows_failed(self):
        """Test GET request with invalid key shows registration failed page."""
        url = reverse('logindata:register')
        response = self.client.get(url, {'key': 'invalid_key'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Something went wrong. The registration key is invalid or has expired.'))

    def test_register_get_with_valid_key_shows_password_form(self):
        """Test GET request with valid key shows password entry form."""
        url = reverse('logindata:register')
        response = self.client.get(url, {'key': self.member.invite_as_user_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Set login data'))
        self.assertContains(response, _('Welcome, '))
        self.assertContains(response, self.member.prename)

    def test_register_post_without_password_shows_failed(self):
        """Test POST request without password shows registration failed page."""
        url = reverse('logindata:register')
        response = self.client.post(url, {'key': self.member.invite_as_user_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Something went wrong. The registration key is invalid or has expired.'))

    def test_register_post_with_wrong_password_shows_error(self):
        """Test POST request with wrong password shows error message."""
        url = reverse('logindata:register')
        response = self.client.post(url, {
            'key': self.member.invite_as_user_key,
            'password': 'wrong_password'
        })
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('You entered a wrong password.'))

    def test_register_post_with_correct_password_shows_form(self):
        """Test POST request with correct password shows user creation form."""
        url = reverse('logindata:register')
        response = self.client.post(url, {
            'key': self.member.invite_as_user_key,
            'password': self.registration_password.password
        })
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Set login data'))
        self.assertContains(response, self.member.suggested_username())

    def test_register_post_with_save_and_invalid_form_shows_errors(self):
        """Test POST request with save but invalid form shows form errors."""
        url = reverse('logindata:register')
        response = self.client.post(url, {
            'key': self.member.invite_as_user_key,
            'password': self.registration_password.password,
            'save': 'true',
            'username': '',  # Invalid - empty username
            'password1': 'testpass123',
            'password2': 'different_pass'  # Invalid - passwords don't match
        })
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Set login data'))

    def test_register_post_with_save_and_valid_form_shows_success(self):
        """Test POST request with save and valid form shows success page."""
        url = reverse('logindata:register')
        response = self.client.post(url, {
            'key': self.member.invite_as_user_key,
            'password': self.registration_password.password,
            'save': 'true',
            'username': 'testuser',
            'password1': 'testpass123',
            'password2': 'testpass123'
        })
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('You successfully set your login data. You can now proceed to'))

        # Verify user was created and associated with member
        user = User.objects.get(username='testuser')
        self.assertEqual(user.is_staff, True)
        self.member.refresh_from_db()
        self.assertEqual(self.member.user, user)
        self.assertEqual(self.member.invite_as_user_key, '')

    def test_register_post_with_save_and_no_standard_group_shows_failed(self):
        """Test POST request with save but no Standard group shows failed page."""
        # Delete the Standard group
        self.standard_group.delete()

        url = reverse('logindata:register')
        response = self.client.post(url, {
            'key': self.member.invite_as_user_key,
            'password': self.registration_password.password,
            'save': 'true',
            'username': 'testuser',
            'password1': 'testpass123',
            'password2': 'testpass123'
        })
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Something went wrong. The registration key is invalid or has expired.'))