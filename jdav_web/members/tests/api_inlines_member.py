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
from members.models import PermissionMember
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
