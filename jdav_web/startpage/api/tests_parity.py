"""Tests for the admin-parity additions to the startpage API.

Covers ``absolute_urlname`` now exposed in ``SectionBrief`` and ``PostBrief``,
and the ``section_title`` column mirrored into ``PostBrief`` from the admin
``section`` list column. The OAuth2 bearer-token auth path and permission
gating mirror ``tests.py``.
"""

import datetime
import uuid

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from startpage.models import Post
from startpage.models import Section

Application = get_application_model()
AccessToken = get_access_token_model()

BASE = "/api/startpage"


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="startpage", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class StartpageParityTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.plain_user = User.objects.create_user(username="plain", password="secret")
        self.editor_user = grant(
            User.objects.create_user(username="editor", password="secret"),
            "view_section",
            "add_section",
            "view_post",
        )
        self.section = Section.objects.create(title="Aktuelles", urlname="aktuelles")
        self.post = Post.objects.create(
            title="Bericht",
            urlname="bericht",
            date=datetime.date(2026, 7, 1),
            section=self.section,
        )

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- section brief ----------------------------------------------------

    def test_section_brief_exposes_absolute_urlname(self):
        r = self.client.get(BASE + "/sections", **self.auth(self.editor_user))
        self.assertEqual(r.status_code, 200, r.content)
        entry = next(s for s in r.json() if s["id"] == self.section.pk)
        self.assertIn("absolute_urlname", entry)
        self.assertIsInstance(entry["absolute_urlname"], str)

    def test_section_list_forbidden_without_permission(self):
        r = self.client.get(BASE + "/sections", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    # --- post brief -------------------------------------------------------

    def test_post_brief_exposes_section_title_and_urlname(self):
        r = self.client.get(BASE + "/posts", **self.auth(self.editor_user))
        self.assertEqual(r.status_code, 200, r.content)
        entry = next(p for p in r.json() if p["id"] == self.post.pk)
        self.assertEqual(entry["section_id"], self.section.pk)
        self.assertEqual(entry["section_title"], "Aktuelles")
        self.assertIn("absolute_urlname", entry)
        self.assertIsInstance(entry["absolute_urlname"], str)

    def test_post_brief_section_title_none_when_no_section(self):
        orphan = Post.objects.create(title="Solo", urlname="solo", section=None)
        r = self.client.get(BASE + "/posts", **self.auth(self.editor_user))
        self.assertEqual(r.status_code, 200)
        entry = next(p for p in r.json() if p["id"] == orphan.pk)
        self.assertIsNone(entry["section_title"])

    def test_post_list_forbidden_without_permission(self):
        r = self.client.get(BASE + "/posts", **self.auth(self.plain_user))
        self.assertEqual(r.status_code, 403)

    # --- validation (422) -------------------------------------------------

    def test_create_section_blank_title_returns_422(self):
        r = self.client.post(
            BASE + "/sections",
            data={"title": "", "urlname": "neu"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertFalse(Section.objects.filter(urlname="neu").exists())
