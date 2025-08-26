from unittest import skip
from http import HTTPStatus
from django.test import TestCase, Client
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from mailer.models import EmailAddress
from ..models import Member, Group, InvitationToGroup, MemberWaitingList, DIVERSE


class ConfirmInvitationViewTestCase(TestCase):
    def setUp(self):
        self.client = Client()

        # Create an email address for the group
        self.email_address = EmailAddress.objects.create(name='testmail')

        # Create a test group
        self.group = Group.objects.create(name='Test Group')
        self.group.contact_email = self.email_address
        self.group.save()

        # Create a waiting list entry
        self.waiter = MemberWaitingList.objects.create(
            prename='Waiter',
            lastname='User',
            birth_date=timezone.now().date(),
            email='waiter@example.com',
            gender=DIVERSE,
            wait_confirmation_key='test_wait_key',
            wait_confirmation_key_expire=timezone.now() + timezone.timedelta(days=1)
        )

        # Create an invitation
        self.invitation = InvitationToGroup.objects.create(
            waiter=self.waiter,
            group=self.group,
            key='test_invitation_key',
            date=timezone.now().date()
        )

    def test_confirm_invitation_get_valid_key(self):
        """Test GET request with valid key shows invitation confirmation page."""
        url = reverse('members:confirm_invitation')
        response = self.client.get(url, {'key': 'test_invitation_key'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Confirm trial group meeting invitation'))
        self.assertContains(response, self.group.name)

    def test_confirm_invitation_get_invalid_key(self):
        """Test GET request with invalid key shows invalid confirmation page."""
        url = reverse('members:confirm_invitation')

        # no key
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

        # invalid key
        response = self.client.get(url, {'key': 'invalid_key'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

    def test_confirm_invitation_get_rejected_invitation(self):
        """Test GET request with rejected invitation shows invalid confirmation page."""
        self.invitation.rejected = True
        self.invitation.save()

        url = reverse('members:confirm_invitation')
        response = self.client.get(url, {'key': self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

    def test_confirm_invitation_get_expired_invitation(self):
        """Test GET request with expired invitation shows invalid confirmation page."""
        # Set invitation date to more than 30 days ago to make it expired
        self.invitation.date = timezone.now().date() - timezone.timedelta(days=31)
        self.invitation.save()

        url = reverse('members:confirm_invitation')
        response = self.client.get(url, {'key': self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

    def test_confirm_invitation_post_invalid_key(self):
        """Test POST request with invalid key shows invalid confirmation page."""
        url = reverse('members:confirm_invitation')

        # no key
        response = self.client.post(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

        # invalid key
        response = self.client.post(url, {'key': 'invalid_key'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('This invitation is invalid or expired.'))

    def test_confirm_invitation_post_valid_key(self):
        """Test POST request with valid key confirms invitation and shows success page."""
        url = reverse('members:confirm_invitation')
        response = self.client.post(url, {'key': self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _('Invitation confirmed'))
        self.assertContains(response, self.group.name)

        # Verify invitation was not marked as rejected (confirm() sets rejected=False)
        self.invitation.refresh_from_db()
        self.assertFalse(self.invitation.rejected)
