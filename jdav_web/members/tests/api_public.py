"""End-to-end tests for the members app's PUBLIC (unauthenticated) API.

These exercise the secret-key self-service flows (``members/api/public.py``)
without any OAuth token — the possession of a valid secret token is the whole
authorization, exactly as the underlying views in ``members/views.py`` operate.
Each flow is covered on its happy path and its invalid-key path.
"""

import datetime
import shutil
from unittest import skipUnless

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Group
from members.models import InvitationToGroup
from members.models import Member
from members.models import MemberWaitingList
from members.models import RegistrationPassword

BASE = "/api/members/public"


def json_post(client, url, payload):
    return client.post(url, data=payload, content_type="application/json")


CONTACTS = [{"prename": "Anna", "lastname": "Contact", "phone_number": "+49 1", "email": ""}]


HAS_PDFLATEX = shutil.which("pdflatex") is not None


class PublicEchoApiTestCase(TestCase):
    def setUp(self):
        self.member = Member.objects.create(
            prename="Echo",
            lastname="Test",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            birth_date=datetime.date(2005, 4, 3),
            echo_key="echokey123",
            echo_expire=timezone.now() + datetime.timedelta(days=5),
            confirmed=True,
        )
        self.password = self.member.echo_password

    def test_verify_valid_key(self):
        r = self.client.get("{}/echo/{}".format(BASE, self.member.echo_key))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["valid"])

    def test_verify_invalid_key(self):
        r = self.client.get("{}/echo/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_no_auth_required(self):
        # No Authorization header at all still succeeds (auth=None).
        r = self.client.get("{}/echo/{}".format(BASE, self.member.echo_key))
        self.assertEqual(r.status_code, 200)

    def test_prefill_correct_password(self):
        r = json_post(
            self.client,
            "{}/echo/{}/prefill".format(BASE, self.member.echo_key),
            {"password": self.password},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["member"]["prename"], "Echo")

    def test_prefill_wrong_password(self):
        r = json_post(
            self.client,
            "{}/echo/{}/prefill".format(BASE, self.member.echo_key),
            {"password": "wrong"},
        )
        self.assertEqual(r.status_code, 422)

    def test_prefill_expired_key(self):
        self.member.echo_expire = timezone.now() - datetime.timedelta(days=1)
        self.member.save()
        r = json_post(
            self.client,
            "{}/echo/{}/prefill".format(BASE, self.member.echo_key),
            {"password": self.password},
        )
        self.assertEqual(r.status_code, 422)

    def test_submit_updates_member_and_contacts(self):
        r = json_post(
            self.client,
            "{}/echo/{}".format(BASE, self.member.echo_key),
            {
                "password": self.password,
                "prename": "Echo",
                "lastname": "Test",
                "gender": DIVERSE,
                "street": "Mainstreet 1",
                "plz": "71634",
                "town": "Ludwigsburg",
                "phone_number": "+49 700",
                "photos_may_be_taken": True,
                "emergency_contacts": CONTACTS,
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.member.refresh_from_db()
        self.assertEqual(self.member.town, "Ludwigsburg")
        self.assertTrue(self.member.echoed)
        self.assertEqual(self.member.emergencycontact_set.count(), 1)
        # No registration form yet, so the caller is pointed at the upload flow.
        self.assertTrue(r.json()["needs_registration_form_upload"])
        self.assertTrue(r.json()["upload_registration_form_key"])

    def _submit_payload(self, **overrides):
        payload = {
            "password": self.password,
            "prename": "Echo",
            "lastname": "Test",
            "gender": DIVERSE,
            "street": "Mainstreet 1",
            "plz": "71634",
            "town": "Ludwigsburg",
            "phone_number": "+49 700",
            "photos_may_be_taken": True,
            "emergency_contacts": CONTACTS,
        }
        payload.update(overrides)
        return payload

    def test_submit_wrong_password(self):
        r = json_post(
            self.client,
            "{}/echo/{}".format(BASE, self.member.echo_key),
            self._submit_payload(password="falsch"),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.member.refresh_from_db()
        # `echoed` defaults to True, so the tell is that nothing was written.
        self.assertEqual(self.member.town, "")

    def test_submit_expired_key(self):
        self.member.echo_expire = timezone.now() - datetime.timedelta(days=1)
        self.member.save()
        r = json_post(
            self.client,
            "{}/echo/{}".format(BASE, self.member.echo_key),
            self._submit_payload(),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.member.refresh_from_db()
        self.assertEqual(self.member.town, "")

    def test_submit_without_emergency_contacts(self):
        r = json_post(
            self.client,
            "{}/echo/{}".format(BASE, self.member.echo_key),
            self._submit_payload(emergency_contacts=[]),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_submit_with_a_registration_form_already_on_file(self):
        # The other arm of the success response: nothing left to upload, so the
        # caller is not pointed at the upload flow.
        self.member.registration_form = SimpleUploadedFile(
            "anmeldung.pdf", b"fakepdf", content_type="application/pdf"
        )
        self.member.save()
        r = json_post(
            self.client,
            "{}/echo/{}".format(BASE, self.member.echo_key),
            self._submit_payload(),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["needs_registration_form_upload"])

    def test_submit_invalid_key(self):
        r = json_post(
            self.client,
            "{}/echo/nope".format(BASE),
            {
                "password": self.password,
                "prename": "Echo",
                "lastname": "Test",
                "gender": DIVERSE,
                "emergency_contacts": CONTACTS,
            },
        )
        self.assertEqual(r.status_code, 404)


class PublicRegisterApiTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)
        self.reg_password = RegistrationPassword.objects.create(
            group=self.group, password="letmein"
        )

    def register_payload(self, **overrides):
        payload = {
            "password": "letmein",
            "prename": "New",
            "lastname": "Member",
            "gender": DIVERSE,
            "email": settings.TEST_MAIL,
            "street": "Mainstreet 1",
            "plz": "71634",
            "town": "Ludwigsburg",
            "birth_date": "2010-01-01",
            "emergency_contacts": CONTACTS,
        }
        payload.update(overrides)
        return payload

    def test_verify_correct_password(self):
        r = json_post(self.client, "{}/register/verify".format(BASE), {"password": "letmein"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["group"]["name"], "Alpenfuechse")

    def test_verify_wrong_password(self):
        r = json_post(self.client, "{}/register/verify".format(BASE), {"password": "nope"})
        self.assertEqual(r.status_code, 422)

    def test_submit_creates_member(self):
        r = json_post(self.client, "{}/register".format(BASE), self.register_payload())
        self.assertEqual(r.status_code, 200, r.content)
        member = Member.all_objects.get(prename="New", lastname="Member")
        self.assertFalse(member.confirmed)
        self.assertIn(self.group, member.group.all())
        self.assertEqual(member.emergencycontact_set.count(), 1)
        self.assertEqual(
            r.json()["upload_registration_form_key"], member.upload_registration_form_key
        )

    def test_submit_wrong_password(self):
        r = json_post(
            self.client, "{}/register".format(BASE), self.register_payload(password="nope")
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(Member.all_objects.filter(prename="New").exists())


class PublicInvitedRegistrationApiTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)
        self.waiter = MemberWaitingList.objects.create(
            prename="Invited",
            lastname="Waiter",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            birth_date=datetime.date(2010, 5, 5),
        )
        self.invitation = InvitationToGroup.objects.create(
            waiter=self.waiter, group=self.group, key="invkey123"
        )

    def test_prefill_valid_key(self):
        r = self.client.get("{}/invited-registration/{}".format(BASE, self.invitation.key))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["group"]["name"], "Alpenfuechse")
        self.assertEqual(body["member"]["prename"], "Invited")

    def test_prefill_invalid_key(self):
        r = self.client.get("{}/invited-registration/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_prefill_expired_invitation(self):
        self.invitation.date = (timezone.now() - datetime.timedelta(days=40)).date()
        self.invitation.save()
        r = self.client.get("{}/invited-registration/{}".format(BASE, self.invitation.key))
        self.assertEqual(r.status_code, 422)

    def test_submit_registers_into_group(self):
        payload = {
            "prename": "Invited",
            "lastname": "Waiter",
            "gender": DIVERSE,
            "email": settings.TEST_MAIL,
            "street": "Mainstreet 1",
            "plz": "71634",
            "town": "Ludwigsburg",
            "birth_date": "2010-05-05",
            "emergency_contacts": CONTACTS,
        }
        r = json_post(
            self.client,
            "{}/invited-registration/{}".format(BASE, self.invitation.key),
            payload,
        )
        self.assertEqual(r.status_code, 200, r.content)
        member = Member.all_objects.get(prename="Invited", lastname="Waiter")
        self.assertIn(self.group, member.group.all())
        # The waiter is consumed by the registration.
        self.assertFalse(MemberWaitingList.objects.filter(pk=self.waiter.pk).exists())

    def test_submit_stores_an_alternative_email(self):
        # Parents often register with a second address; it is optional, so the
        # field is only written when it was actually supplied.
        r = json_post(
            self.client,
            "{}/invited-registration/{}".format(BASE, self.invitation.key),
            {
                "prename": "Invited",
                "lastname": "Waiter",
                "gender": DIVERSE,
                "email": settings.TEST_MAIL,
                "alternative_email": settings.TEST_MAIL,
                "street": "Mainstreet 1",
                "plz": "71634",
                "town": "Ludwigsburg",
                "birth_date": "2010-05-05",
                "emergency_contacts": CONTACTS,
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        member = Member.all_objects.get(prename="Invited", lastname="Waiter")
        self.assertEqual(member.alternative_email, settings.TEST_MAIL)

    def test_submit_with_an_unknown_key(self):
        # A complete payload on purpose: the schema is validated before the
        # handler runs, so an incomplete one would 422 and never reach the key.
        r = json_post(
            self.client,
            "{}/invited-registration/nope".format(BASE),
            {
                "prename": "Invited",
                "lastname": "Waiter",
                "gender": DIVERSE,
                "email": settings.TEST_MAIL,
                "street": "Mainstreet 1",
                "plz": "71634",
                "town": "Ludwigsburg",
                "birth_date": "2010-05-05",
                "emergency_contacts": CONTACTS,
            },
        )
        self.assertEqual(r.status_code, 404)


class PublicUploadRegistrationFormApiTestCase(TestCase):
    def setUp(self):
        self.member = Member.all_objects.create(
            prename="Upload",
            lastname="Test",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            confirmed=False,
            upload_registration_form_key="uploadkey123",
        )

    def test_verify_valid_key(self):
        r = self.client.get("{}/upload-registration-form/{}".format(BASE, "uploadkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["name"], "Upload")
        self.assertFalse(r.json()["has_registration_form"])

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_download_the_form_to_sign(self):
        # Without this there is nothing for the member to sign and upload, so
        # the download shares the upload's key rather than needing its own.
        r = self.client.get("{}/registration-form/{}".format(BASE, "uploadkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    def test_download_the_form_with_an_unknown_key(self):
        r = self.client.get("{}/registration-form/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_verify_invalid_key(self):
        r = self.client.get("{}/upload-registration-form/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_submit_valid_file(self):
        upload = SimpleUploadedFile("form.pdf", b"%PDF-1.4 dummy", content_type="application/pdf")
        r = self.client.post(
            "{}/upload-registration-form/{}".format(BASE, "uploadkey123"),
            {"registration_form": upload},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.member.refresh_from_db()
        self.assertTrue(self.member.registration_form)
        # validate_registration_form clears the upload key.
        self.assertEqual(self.member.upload_registration_form_key, "")

    def test_submit_oversized_file(self):
        oversized = SimpleUploadedFile(
            "anmeldung.pdf", b"x" * (5 * 1024 * 1024 + 1), content_type="application/pdf"
        )
        r = self.client.post(
            "{}/upload-registration-form/{}".format(BASE, "uploadkey123"),
            data={"registration_form": oversized},
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.member.refresh_from_db()
        self.assertFalse(self.member.registration_form)

    def test_submit_invalid_filetype(self):
        upload = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(
            "{}/upload-registration-form/{}".format(BASE, "uploadkey123"),
            {"registration_form": upload},
        )
        self.assertEqual(r.status_code, 422)

    def test_submit_invalid_key(self):
        upload = SimpleUploadedFile("form.pdf", b"%PDF", content_type="application/pdf")
        r = self.client.post(
            "{}/upload-registration-form/nope".format(BASE),
            {"registration_form": upload},
        )
        self.assertEqual(r.status_code, 404)


class PublicWaitingListApiTestCase(TestCase):
    def test_register_creates_waiter(self):
        r = json_post(
            self.client,
            "{}/waiting-list".format(BASE),
            {
                "prename": "Wait",
                "lastname": "Applicant",
                "gender": DIVERSE,
                "email": settings.TEST_MAIL,
                "birth_date": "2011-02-02",
                "application_text": "Please add me",
            },
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(
            MemberWaitingList.objects.filter(prename="Wait", lastname="Applicant").exists()
        )


class PublicConfirmWaitingApiTestCase(TestCase):
    def setUp(self):
        self.waiter = MemberWaitingList.objects.create(
            prename="Confirm",
            lastname="Waiter",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            wait_confirmation_key="waitkey123",
            wait_confirmation_key_expire=timezone.now() + datetime.timedelta(days=5),
            sent_reminders=1,
        )

    def test_confirm_success(self):
        r = self.client.post("{}/confirm-waiting/{}".format(BASE, "waitkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["already_confirmed"])
        self.waiter.refresh_from_db()
        self.assertEqual(self.waiter.sent_reminders, 0)

    def test_confirm_invalid_key(self):
        r = self.client.post("{}/confirm-waiting/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_confirm_an_already_confirmed_waiter(self):
        # Both the applicant and a parent may click the same link; the second
        # click has to read as "already done", not as an error. Reaching that
        # arm needs the key spent *and* no reminder outstanding — which is
        # exactly the state the first click leaves behind.
        self.waiter.sent_reminders = 0
        self.waiter.wait_confirmation_key_expire = timezone.now() - datetime.timedelta(days=1)
        self.waiter.save()
        r = self.client.post("{}/confirm-waiting/{}".format(BASE, "waitkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["already_confirmed"])

    def test_confirm_an_expired_link(self):
        self.waiter.wait_confirmation_key_expire = timezone.now() - datetime.timedelta(days=1)
        self.waiter.save()
        r = self.client.post("{}/confirm-waiting/{}".format(BASE, "waitkey123"))
        self.assertEqual(r.status_code, 422, r.content)


class PublicLeaveWaitinglistApiTestCase(TestCase):
    def setUp(self):
        self.waiter = MemberWaitingList.objects.create(
            prename="Leave",
            lastname="Waiter",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            leave_key="leavekey123",
        )

    def test_verify_valid_key(self):
        r = self.client.get("{}/leave-waitinglist/{}".format(BASE, "leavekey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["name"], self.waiter.name)

    def test_verify_invalid_key(self):
        r = self.client.get("{}/leave-waitinglist/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_submit_removes_waiter(self):
        r = self.client.post("{}/leave-waitinglist/{}".format(BASE, "leavekey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(MemberWaitingList.objects.filter(pk=self.waiter.pk).exists())

    def test_submit_invalid_key(self):
        r = self.client.post("{}/leave-waitinglist/nope".format(BASE))
        self.assertEqual(r.status_code, 404)


class PublicRejectInvitationApiTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)
        self.waiter = MemberWaitingList.objects.create(
            prename="Reject", lastname="Waiter", email=settings.TEST_MAIL, gender=DIVERSE
        )
        self.invitation = InvitationToGroup.objects.create(
            waiter=self.waiter, group=self.group, key="rejkey123"
        )

    def test_verify_valid_key(self):
        r = self.client.get("{}/reject-invitation/{}".format(BASE, "rejkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["groupname"], "Alpenfuechse")

    def test_verify_invalid_key(self):
        r = self.client.get("{}/reject-invitation/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_verify_rejected_is_invalid(self):
        self.invitation.rejected = True
        self.invitation.save()
        r = self.client.get("{}/reject-invitation/{}".format(BASE, "rejkey123"))
        self.assertEqual(r.status_code, 422)

    def test_submit_reject(self):
        r = json_post(
            self.client,
            "{}/reject-invitation/{}".format(BASE, "rejkey123"),
            {"action": "reject"},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["left_waitinglist"])
        self.invitation.refresh_from_db()
        self.assertTrue(self.invitation.rejected)

    def test_submit_leave_waitinglist(self):
        r = json_post(
            self.client,
            "{}/reject-invitation/{}".format(BASE, "rejkey123"),
            {"action": "leave"},
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["left_waitinglist"])
        self.assertFalse(MemberWaitingList.objects.filter(pk=self.waiter.pk).exists())

    def test_submit_invalid_key(self):
        r = json_post(self.client, "{}/reject-invitation/nope".format(BASE), {"action": "reject"})
        self.assertEqual(r.status_code, 404)

    def test_submit_unknown_action(self):
        r = json_post(
            self.client,
            "{}/reject-invitation/{}".format(BASE, "rejkey123"),
            {"action": "vielleicht"},
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.invitation.refresh_from_db()
        self.assertFalse(self.invitation.rejected)
        self.assertTrue(MemberWaitingList.objects.filter(pk=self.waiter.pk).exists())


class PublicConfirmInvitationApiTestCase(TestCase):
    def setUp(self):
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)
        self.waiter = MemberWaitingList.objects.create(
            prename="Confirm", lastname="Waiter", email=settings.TEST_MAIL, gender=DIVERSE
        )
        self.invitation = InvitationToGroup.objects.create(
            waiter=self.waiter, group=self.group, key="confkey123"
        )

    def test_verify_valid_key(self):
        r = self.client.get("{}/confirm-invitation/{}".format(BASE, "confkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["groupname"], "Alpenfuechse")

    def test_verify_invalid_key(self):
        r = self.client.get("{}/confirm-invitation/nope".format(BASE))
        self.assertEqual(r.status_code, 404)

    def test_verify_a_rejected_invitation_is_no_longer_valid(self):
        self.invitation.rejected = True
        self.invitation.save()
        r = self.client.get("{}/confirm-invitation/{}".format(BASE, "confkey123"))
        self.assertEqual(r.status_code, 422, r.content)

    def test_submit_confirms(self):
        # Force it into a rejected state first to observe confirm() flipping it back.
        self.invitation.rejected = True
        self.invitation.save()
        r = self.client.post("{}/confirm-invitation/{}".format(BASE, "confkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.invitation.refresh_from_db()
        self.assertFalse(self.invitation.rejected)

    def test_submit_invalid_key(self):
        r = self.client.post("{}/confirm-invitation/nope".format(BASE))
        self.assertEqual(r.status_code, 404)


class PublicConfirmMailApiTestCase(TestCase):
    def setUp(self):
        self.member = Member.all_objects.create(
            prename="Mailer",
            lastname="Test",
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            confirmed=False,
            confirmed_mail=False,
            confirm_mail_key="mailkey123",
        )

    def test_confirm_success(self):
        r = self.client.post("{}/confirm-mail/{}".format(BASE, "mailkey123"))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["email"], settings.TEST_MAIL)
        self.member.refresh_from_db()
        self.assertTrue(self.member.confirmed_mail)

    def test_confirm_invalid_key(self):
        r = self.client.post("{}/confirm-mail/nope".format(BASE))
        self.assertEqual(r.status_code, 404)
