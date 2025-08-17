from unittest import skip, mock
from http import HTTPStatus
from django.urls import reverse
from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.core.files.uploadedfile import SimpleUploadedFile
from members.models import Member, Group, DIVERSE, Freizeit, MemberNoteList, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE
from mailer.models import EmailAddress, EmailAddressForm, Message, MessageForm, Attachment
from mailer.mailutils import SENT, NOT_SENT, PARTLY_SENT
from .utils import BasicMailerTestCase


class IndexTestCase(BasicMailerTestCase):
    def test_index(self):
        url = reverse('mailer:index')
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)


class UnsubscribeTestCase(BasicMailerTestCase):
    def test_unsubscribe(self):
        url = reverse('mailer:unsubscribe')
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Here you can unsubscribe from the newsletter"))

    def test_unsubscribe_key_invalid(self):
        url = reverse('mailer:unsubscribe')

        # invalid key
        response = self.client.get(url, data={'key': 'invalid'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Can't verify this link. Try again!"))

        # expired key
        self.fritz.unsubscribe_expire = timezone.now()
        self.fritz.save()
        response = self.client.get(url, data={'key': self.fritz.unsubscribe_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Can't verify this link. Try again!"))

    def test_unsubscribe_key(self):
        url = reverse('mailer:unsubscribe')
        response = self.client.get(url, data={'key': self.fritz.unsubscribe_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Successfully unsubscribed from the newsletter for "))

    def test_unsubscribe_post_incomplete(self):
        url = reverse('mailer:unsubscribe')
        response = self.client.post(url, data={'post': True})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Please fill in every field"))

        response = self.client.post(url, data={'post': True, 'email': 'foobar@notexisting.com'})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Please fill in every field"))

    def test_unsubscribe_post(self):
        url = reverse('mailer:unsubscribe')
        response = self.client.post(url, data={'post': True, 'email': self.fritz.email})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Sent confirmation mail to"))
