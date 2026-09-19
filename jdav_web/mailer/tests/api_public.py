"""End-to-end tests for the public mailer (unsubscribe) API.

These hit the unauthenticated endpoints that back the emailed unsubscribe link,
mirroring the guarantees of ``mailer.views.unsubscribe`` through the HTTP API.
"""

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Member


def make_member(email=None, newsletter=True):
    return Member.objects.create(
        prename="News",
        lastname="Letter",
        birth_date=timezone.now().date(),
        email=email or settings.TEST_MAIL,
        gender=DIVERSE,
        gets_newsletter=newsletter,
    )


class MailerPublicApiTestCase(TestCase):
    UNSUB = "/api/mailer/public/unsubscribe"

    # --- verify (non-destructive) ----------------------------------------

    def test_verify_valid_key(self):
        member = make_member()
        key = member.generate_key()
        r = self.client.get(self.UNSUB, {"key": key})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["email"], member.email)
        member.refresh_from_db()
        # Non-destructive: still subscribed, key intact.
        self.assertTrue(member.gets_newsletter)
        self.assertEqual(member.unsubscribe_key, key)

    def test_verify_invalid_key(self):
        make_member()
        r = self.client.get(self.UNSUB, {"key": "does-not-exist"})
        self.assertEqual(r.status_code, 404)

    def test_verify_empty_key_rejected(self):
        make_member()
        r = self.client.get(self.UNSUB, {"key": ""})
        self.assertEqual(r.status_code, 404)

    def test_verify_expired_key(self):
        member = make_member()
        member.generate_key()
        member.unsubscribe_expire = timezone.now() - timezone.timedelta(days=1)
        member.save()
        r = self.client.get(self.UNSUB, {"key": member.unsubscribe_key})
        self.assertEqual(r.status_code, 404)

    # --- confirm (destructive) -------------------------------------------

    def test_confirm_unsubscribes(self):
        member = make_member()
        key = member.generate_key()
        r = self.client.post(self.UNSUB, data={"key": key}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["email"], member.email)
        member.refresh_from_db()
        self.assertFalse(member.gets_newsletter)

    def test_confirm_unsubscribes_all_sharing_email(self):
        first = make_member(email="shared@example.com")
        second = make_member(email="shared@example.com")
        key = first.generate_key()
        r = self.client.post(self.UNSUB, data={"key": key}, content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        first.refresh_from_db()
        second.refresh_from_db()
        self.assertFalse(first.gets_newsletter)
        self.assertFalse(second.gets_newsletter)

    def test_confirm_invalid_key(self):
        r = self.client.post(self.UNSUB, data={"key": "nope"}, content_type="application/json")
        self.assertEqual(r.status_code, 404)
