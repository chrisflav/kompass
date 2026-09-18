"""End-to-end tests for the member-inline REST endpoints.

Exercises the real OAuth2 bearer auth path and the object-level permission
model for the ``EmergencyContact`` / ``MemberDocument`` / ``PermissionMember``
inlines nested under a member (authorized 200/201, unauthorized 403, and a
validation 422).
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import EmergencyContact
from members.models import Member
from members.models import MemberDocument
from members.models import MemberTraining
from members.models import PermissionMember
from members.models import TrainingCategory
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def make_member_user(username):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=username.title(),
        lastname="Test",
        birth_date=timezone.now().date(),
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    return user, member


class MemberInlineApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        # A member may view/change themselves (is_oneself), so the owner is
        # authorized on their own nested rows but not on another member's.
        self.owner_user, self.owner = make_member_user("owner")
        self.other_user, self.other = make_member_user("other")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- emergency contacts ----------------------------------------------

    def test_create_and_list_emergency_contact_self(self):
        r = self.client.post(
            "/api/members/{}/emergency-contacts".format(self.owner.pk),
            data={"prename": "Mom", "lastname": "Owner", "phone_number": "+49 1"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(EmergencyContact.objects.filter(member=self.owner, prename="Mom").exists())

        r = self.client.get(
            "/api/members/{}/emergency-contacts".format(self.owner.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual({c["prename"] for c in r.json()}, {"Mom"})

    def test_create_emergency_contact_other_forbidden(self):
        r = self.client.post(
            "/api/members/{}/emergency-contacts".format(self.other.pk),
            data={"prename": "Dad", "lastname": "Other", "phone_number": "+49 2"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(EmergencyContact.objects.filter(member=self.other).exists())

    def test_create_emergency_contact_validation(self):
        # ``prename`` max_length is 20 → full_clean raises → 422.
        r = self.client.post(
            "/api/members/{}/emergency-contacts".format(self.owner.pk),
            data={"prename": "x" * 21, "lastname": "Owner", "phone_number": "+49 1"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(EmergencyContact.objects.filter(member=self.owner).exists())

    def test_update_and_delete_emergency_contact(self):
        contact = EmergencyContact.objects.create(
            member=self.owner, prename="Mom", lastname="Owner", phone_number="+49 1"
        )
        r = self.client.patch(
            "/api/members/emergency-contacts/{}".format(contact.pk),
            data={"phone_number": "+49 999"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        contact.refresh_from_db()
        self.assertEqual(contact.phone_number, "+49 999")

        # Another member cannot touch it.
        r = self.client.patch(
            "/api/members/emergency-contacts/{}".format(contact.pk),
            data={"phone_number": "+49 000"},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

        r = self.client.delete(
            "/api/members/emergency-contacts/{}".format(contact.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(EmergencyContact.objects.filter(pk=contact.pk).exists())

    # --- member documents ------------------------------------------------

    def test_create_member_document_self(self):
        upload = SimpleUploadedFile("form.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(
            "/api/members/{}/documents".format(self.owner.pk),
            data={"f": upload},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(MemberDocument.objects.filter(member=self.owner).exists())

    def test_create_member_document_other_forbidden(self):
        upload = SimpleUploadedFile("form.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(
            "/api/members/{}/documents".format(self.other.pk),
            data={"f": upload},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(MemberDocument.objects.filter(member=self.other).exists())

    def test_create_member_document_wrong_type(self):
        upload = SimpleUploadedFile("evil.exe", b"MZ", content_type="application/octet-stream")
        r = self.client.post(
            "/api/members/{}/documents".format(self.owner.pk),
            data={"f": upload},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    # --- permission (ACL) rows -------------------------------------------

    def test_create_and_list_permission_member_self(self):
        r = self.client.post(
            "/api/members/{}/permission-members".format(self.owner.pk),
            data={"view_member_ids": [self.other.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        permission = PermissionMember.objects.get(member=self.owner)
        self.assertEqual(set(permission.view_members.values_list("pk", flat=True)), {self.other.pk})

        r = self.client.get(
            "/api/members/{}/permission-members".format(self.owner.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()[0]["view_member_ids"], [self.other.pk])

    def test_permission_member_other_forbidden(self):
        # Listing another member's ACL is a sensitive escalation surface → 403.
        r = self.client.get(
            "/api/members/{}/permission-members".format(self.other.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

        r = self.client.post(
            "/api/members/{}/permission-members".format(self.other.pk),
            data={"change_member_ids": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(PermissionMember.objects.filter(member=self.other).exists())

    def test_create_permission_member_duplicate_rejected(self):
        PermissionMember.objects.create(member=self.owner)
        r = self.client.post(
            "/api/members/{}/permission-members".format(self.owner.pk),
            data={},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    # --- file inlines: upload, replace and clear --------------------------
    #
    # Each of these three fields has its own content-type and size limit copied
    # from the model, so each is checked to accept what it declares and refuse
    # what it does not — the limits are easy to drift apart from the model.

    def _training(self, member=None):
        category = TrainingCategory.objects.create(
            name="Kat {}".format(uuid.uuid4().hex[:6]), permission_needed=False
        )
        return MemberTraining.objects.create(
            member=member or self.owner, title="Kletterkurs", category=category
        )

    def test_upload_and_clear_training_certificate(self):
        training = self._training()
        pdf = SimpleUploadedFile("urkunde.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/members/trainings/{}/certificate".format(training.pk),
            data={"f": pdf},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        training.refresh_from_db()
        self.assertTrue(training.certificate)

        r = self.client.delete(
            "/api/members/trainings/{}/certificate".format(training.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["certificate"])
        training.refresh_from_db()
        self.assertFalse(training.certificate)

    def test_upload_training_certificate_rejects_wrong_content_type(self):
        training = self._training()
        bad = SimpleUploadedFile("urkunde.txt", b"text", content_type="text/plain")
        r = self.client.post(
            "/api/members/trainings/{}/certificate".format(training.pk),
            data={"f": bad},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        training.refresh_from_db()
        self.assertFalse(training.certificate)

    def test_upload_training_certificate_for_another_member_forbidden(self):
        training = self._training(member=self.other)
        pdf = SimpleUploadedFile("urkunde.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/members/trainings/{}/certificate".format(training.pk),
            data={"f": pdf},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_upload_and_clear_registration_form(self):
        pdf = SimpleUploadedFile("anmeldung.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/members/{}/registration-form".format(self.owner.pk),
            data={"f": pdf},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.registration_form)

        r = self.client.delete(
            "/api/members/{}/registration-form".format(self.owner.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["registration_form"])
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.registration_form)

    def test_upload_registration_form_rejects_wrong_content_type(self):
        bad = SimpleUploadedFile("anmeldung.txt", b"text", content_type="text/plain")
        r = self.client.post(
            "/api/members/{}/registration-form".format(self.owner.pk),
            data={"f": bad},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.registration_form)

    def test_upload_registration_form_rejects_oversized_file(self):
        oversized = SimpleUploadedFile(
            "anmeldung.pdf", b"x" * (5 * 1024 * 1024 + 1), content_type="application/pdf"
        )
        r = self.client.post(
            "/api/members/{}/registration-form".format(self.owner.pk),
            data={"f": oversized},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("MiB", str(r.json()["detail"]))

    def test_upload_and_clear_member_image(self):
        png = SimpleUploadedFile("portrait.png", b"fakeimage", content_type="image/png")
        r = self.client.post(
            "/api/members/{}/image".format(self.owner.pk),
            data={"f": png},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.image)

        r = self.client.delete(
            "/api/members/{}/image".format(self.owner.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["image"])
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.image)

    def test_upload_member_image_rejects_a_pdf(self):
        # A portrait is an image; the registration form is the field that takes
        # a PDF. Mixing the two up is the mistake worth catching here.
        bad = SimpleUploadedFile("portrait.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/members/{}/image".format(self.owner.pk),
            data={"f": bad},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.owner.refresh_from_db()
        self.assertFalse(self.owner.image)

    # --- documents --------------------------------------------------------

    def test_list_and_delete_member_document(self):
        document = MemberDocument.objects.create(
            member=self.owner,
            f=SimpleUploadedFile("attest.pdf", b"fakepdf", content_type="application/pdf"),
        )
        listed = self.client.get(
            "/api/members/{}/documents".format(self.owner.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(document.pk, {row["id"] for row in listed.json()})

        r = self.client.delete(
            "/api/members/member-documents/{}".format(document.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(MemberDocument.objects.filter(pk=document.pk).exists())

    def test_delete_another_members_document_forbidden(self):
        document = MemberDocument.objects.create(
            member=self.other,
            f=SimpleUploadedFile("attest.pdf", b"fakepdf", content_type="application/pdf"),
        )
        r = self.client.delete(
            "/api/members/member-documents/{}".format(document.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(MemberDocument.objects.filter(pk=document.pk).exists())

    def test_upload_document_rejects_oversized_file(self):
        oversized = SimpleUploadedFile(
            "attest.pdf", b"x" * (10 * 1024 * 1024 + 1), content_type="application/pdf"
        )
        r = self.client.post(
            "/api/members/{}/documents".format(self.owner.pk),
            data={"f": oversized},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("MiB", str(r.json()["detail"]))

    # --- ACL rows ---------------------------------------------------------

    def test_update_and_delete_permission_member(self):
        permission = PermissionMember.objects.create(member=self.owner)
        r = self.client.patch(
            "/api/members/permission-members/{}".format(permission.pk),
            data={"view_member_ids": [self.other.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(list(permission.view_members.all()), [self.other])

        r = self.client.delete(
            "/api/members/permission-members/{}".format(permission.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(PermissionMember.objects.filter(pk=permission.pk).exists())

    def test_edit_another_members_acl_forbidden(self):
        # These rows grant object permissions, so the escalation guard matters
        # more here than anywhere else in the inline surface.
        permission = PermissionMember.objects.create(member=self.other)
        r = self.client.patch(
            "/api/members/permission-members/{}".format(permission.pk),
            data={"view_member_ids": [self.owner.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(list(permission.view_members.all()), [])

        r = self.client.delete(
            "/api/members/permission-members/{}".format(permission.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(PermissionMember.objects.filter(pk=permission.pk).exists())
