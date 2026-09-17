"""End-to-end tests for the startpage REST API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
standard Django permission gating used by the plain startpage content models,
mirroring the structure of ``members/tests/api.py``.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Group
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from startpage.models import FAQ
from startpage.models import Image
from startpage.models import Link
from startpage.models import MemberOnPost
from startpage.models import Post
from startpage.models import Section

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


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="startpage", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


class StartpageApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # Short secret: the default 128-char one exceeds bcrypt's 72-byte
            # limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.plain_user, self.plain_member = make_member_user("plain")
        self.editor_user, self.editor_member = make_member_user("editor")
        self.editor_user = grant(
            self.editor_user,
            "view_section",
            "add_section",
            "change_section",
            "delete_section",
            "view_post",
            "add_post",
            "change_post",
            "delete_post",
            "view_faq",
            "add_faq",
            "change_faq",
            "delete_faq",
            "view_link",
            "add_link",
            "change_link",
            "delete_link",
            "view_image",
            "add_image",
            "change_image",
            "delete_image",
            "view_memberonpost",
            "add_memberonpost",
            "change_memberonpost",
            "delete_memberonpost",
        )
        self.section = Section.objects.create(title="Aktuelles", urlname="aktuelles")
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/startpage/sections").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get("/api/startpage/sections", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- permission gating ------------------------------------------------

    def test_list_forbidden_without_permission(self):
        r = self.client.get("/api/startpage/sections", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    def test_list_allowed_with_permission(self):
        r = self.client.get("/api/startpage/sections", **self.auth(self.editor_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({s["id"] for s in r.json()}, {self.section.pk})

    def test_create_forbidden_without_permission(self):
        r = self.client.post(
            "/api/startpage/sections",
            data={"title": "Neu", "urlname": "neu"},
            content_type="application/json",
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Section.objects.filter(urlname="neu").exists())

    # --- sections ---------------------------------------------------------

    def test_section_crud(self):
        r = self.client.post(
            "/api/startpage/sections",
            data={"title": "Ausbildung", "urlname": "ausbildung"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        section_id = r.json()["id"]
        self.assertTrue(Section.objects.filter(pk=section_id, title="Ausbildung").exists())

        r = self.client.put(
            "/api/startpage/sections/{}".format(section_id),
            data={"title": "Kurse", "urlname": "ausbildung", "show_in_navigation": False},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        section = Section.objects.get(pk=section_id)
        self.assertEqual(section.title, "Kurse")
        self.assertFalse(section.show_in_navigation)

        r = self.client.delete(
            "/api/startpage/sections/{}".format(section_id), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Section.objects.filter(pk=section_id).exists())

    # --- posts (M2M groups + section FK) ----------------------------------

    def test_post_create_with_groups_and_section(self):
        r = self.client.post(
            "/api/startpage/posts",
            data={
                "title": "Tour",
                "urlname": "tour",
                "section_id": self.section.pk,
                "group_ids": [self.group.pk],
            },
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["section"]["id"], self.section.pk)
        self.assertEqual({g["id"] for g in body["groups"]}, {self.group.pk})
        post = Post.objects.get(pk=body["id"])
        self.assertEqual(list(post.groups.all()), [self.group])

    def test_post_update_replaces_groups(self):
        post = Post.objects.create(title="Alt", urlname="alt", section=self.section)
        post.groups.add(self.group)
        other_group = Group.objects.create(name="Adler", year_from=2000, year_to=2005)

        r = self.client.put(
            "/api/startpage/posts/{}".format(post.pk),
            data={
                "title": "Neu",
                "urlname": "alt",
                "section_id": self.section.pk,
                "group_ids": [other_group.pk],
            },
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        post.refresh_from_db()
        self.assertEqual(post.title, "Neu")
        self.assertEqual(list(post.groups.all()), [other_group])

    # --- faqs -------------------------------------------------------------

    def test_faq_crud(self):
        r = self.client.post(
            "/api/startpage/faqs",
            data={"question": "Wann?", "answer": "Montags."},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        faq_id = r.json()["id"]
        self.assertEqual(FAQ.objects.get(pk=faq_id).answer, "Montags.")

        r = self.client.get("/api/startpage/faqs/{}".format(faq_id), **self.auth(self.editor_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["question"], "Wann?")

    # --- links (incl. icon upload with content-type constraint) -----------

    def test_link_crud(self):
        r = self.client.post(
            "/api/startpage/links",
            data={"title": "DAV", "url": "https://dav.de"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        link_id = r.json()["id"]
        self.assertEqual(Link.objects.get(pk=link_id).url, "https://dav.de")

    def test_link_icon_upload_valid(self):
        link = Link.objects.create(title="DAV", url="https://dav.de")
        icon = SimpleUploadedFile("icon.png", b"fakeimage", content_type="image/png")
        r = self.client.post(
            "/api/startpage/links/{}/icon".format(link.pk),
            data={"icon": icon},
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        link.refresh_from_db()
        self.assertTrue(link.icon)

    def test_link_icon_upload_rejects_wrong_content_type(self):
        link = Link.objects.create(title="DAV", url="https://dav.de")
        bad = SimpleUploadedFile("icon.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/startpage/links/{}/icon".format(link.pk),
            data={"icon": bad},
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        link.refresh_from_db()
        self.assertFalse(link.icon)

    # --- images (file upload) ---------------------------------------------

    def test_image_create_and_delete(self):
        post = Post.objects.create(title="Tour", urlname="tour", section=self.section)
        f = SimpleUploadedFile("pic.jpg", b"fakeimage", content_type="image/jpeg")
        r = self.client.post(
            "/api/startpage/images",
            data={"post_id": post.pk, "f": f},
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        image_id = r.json()["id"]
        image = Image.objects.get(pk=image_id)
        self.assertEqual(image.post, post)
        self.assertTrue(image.f)

        r = self.client.delete(
            "/api/startpage/images/{}".format(image_id), **self.auth(self.editor_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Image.objects.filter(pk=image_id).exists())

    def test_image_create_forbidden_without_permission(self):
        post = Post.objects.create(title="Tour", urlname="tour", section=self.section)
        f = SimpleUploadedFile("pic.jpg", b"fakeimage", content_type="image/jpeg")
        r = self.client.post(
            "/api/startpage/images",
            data={"post_id": post.pk, "f": f},
            **self.auth(self.plain_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Image.objects.exists())

    # --- members on posts (M2M members) -----------------------------------

    def test_member_on_post_crud(self):
        post = Post.objects.create(title="Tour", urlname="tour", section=self.section)
        r = self.client.post(
            "/api/startpage/member-on-posts",
            data={
                "post_id": post.pk,
                "description": "Gipfelfoto",
                "tag": "gipfel",
                "member_ids": [self.plain_member.pk],
            },
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual({m["id"] for m in body["members"]}, {self.plain_member.pk})
        mop = MemberOnPost.objects.get(pk=body["id"])
        self.assertEqual(mop.tag, "gipfel")
        self.assertEqual(list(mop.members.all()), [self.plain_member])
