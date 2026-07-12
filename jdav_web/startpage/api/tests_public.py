"""Tests for the startpage public read API and the write-hardening (full_clean).

The ``/public/*`` endpoints are unauthenticated (``auth=None``) and mirror the
public website views in ``startpage/views.py``; the hardening tests exercise the
``full_clean`` validation added to the authenticated create/update endpoints,
which the root API maps to HTTP 422.
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Group
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model
from startpage.models import FAQ
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
    return User.objects.get(pk=user.pk)


class StartpagePublicReadApiTestCase(TestCase):
    """The unauthenticated ``/public/*`` read surface."""

    def setUp(self):
        self.recent = Section.objects.create(title="Aktuelles", urlname=settings.RECENT_SECTION)
        self.reports = Section.objects.create(title="Berichte", urlname=settings.REPORTS_SECTION)
        self.root = Section.objects.create(title="Verein", urlname=settings.ROOT_SECTION)
        self.recent_post = Post.objects.create(
            title="Neue Tour",
            urlname="neue-tour",
            section=self.recent,
            website_text="Wir waren unterwegs.",
            date=datetime.date(2026, 1, 1),
        )
        self.report_post = Post.objects.create(
            title="Rückblick",
            urlname="rueckblick",
            section=self.reports,
            website_text="Ein schöner Bericht.",
            date=datetime.date(2026, 2, 1),
        )
        self.visible_group = Group.objects.create(
            name="Alpenfuechse", year_from=2010, year_to=2015, show_website=True
        )
        self.hidden_group = Group.objects.create(
            name="Geheim", year_from=2000, year_to=2005, show_website=False
        )
        self.leiter_user, self.leiter = make_member_user("leiter")
        self.visible_group.leiters.add(self.leiter)

    # --- no authentication required ---------------------------------------

    def test_public_endpoint_needs_no_auth(self):
        r = self.client.get("/api/startpage/public/navigation")
        self.assertEqual(r.status_code, 200)

    # --- navigation -------------------------------------------------------

    def test_public_navigation(self):
        r = self.client.get("/api/startpage/public/navigation")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn(self.recent.pk, {s["id"] for s in body["sections"]})
        group_ids = {g["id"] for g in body["groups"]}
        self.assertIn(self.visible_group.pk, group_ids)
        self.assertNotIn(self.hidden_group.pk, group_ids)
        self.assertEqual(body["root_section"]["urlname"], settings.ROOT_SECTION)

    # --- index ------------------------------------------------------------

    def test_public_index(self):
        r = self.client.get("/api/startpage/public/index")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual({p["id"] for p in body["recent_posts"]}, {self.recent_post.pk})
        self.assertEqual({p["id"] for p in body["reports"]}, {self.report_post.pk})
        self.assertEqual(body["recent_posts"][0]["website_text"], "Wir waren unterwegs.")

    # --- aktuelles / berichte ---------------------------------------------

    def test_public_aktuelles(self):
        r = self.client.get("/api/startpage/public/aktuelles")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["section"]["urlname"], settings.RECENT_SECTION)
        self.assertEqual({p["id"] for p in body["posts"]}, {self.recent_post.pk})

    def test_public_berichte(self):
        r = self.client.get("/api/startpage/public/berichte")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["section"]["urlname"], settings.REPORTS_SECTION)
        self.assertEqual({p["id"] for p in body["posts"]}, {self.report_post.pk})

    def test_public_aktuelles_missing_section_404(self):
        Section.objects.filter(urlname=settings.RECENT_SECTION).delete()
        r = self.client.get("/api/startpage/public/aktuelles")
        self.assertEqual(r.status_code, 404)

    # --- faqs -------------------------------------------------------------

    def test_public_faqs(self):
        FAQ.objects.create(question="Wann?", answer="Montags.")
        r = self.client.get("/api/startpage/public/faqs")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["answer"], "Montags.")

    # --- groups -----------------------------------------------------------

    def test_public_groups_lists_only_visible(self):
        r = self.client.get("/api/startpage/public/groups")
        self.assertEqual(r.status_code, 200)
        ids = {g["id"] for g in r.json()}
        self.assertEqual(ids, {self.visible_group.pk})

    def test_public_group_detail(self):
        r = self.client.get("/api/startpage/public/groups/{}".format(self.visible_group.name))
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["name"], "Alpenfuechse")
        self.assertEqual({p["id"] for p in body["people"]}, {self.leiter.pk})

    def test_public_group_detail_hidden_404(self):
        r = self.client.get("/api/startpage/public/groups/{}".format(self.hidden_group.name))
        self.assertEqual(r.status_code, 404)

    def test_public_group_detail_unknown_404(self):
        r = self.client.get("/api/startpage/public/groups/DoesNotExist")
        self.assertEqual(r.status_code, 404)

    # --- sections ---------------------------------------------------------

    def test_public_sections(self):
        r = self.client.get("/api/startpage/public/sections")
        self.assertEqual(r.status_code, 200)
        ids = {s["id"] for s in r.json()}
        self.assertTrue({self.recent.pk, self.reports.pk, self.root.pk} <= ids)

    def test_public_section_detail(self):
        self.root.website_text = "Über uns."
        self.root.save()
        r = self.client.get("/api/startpage/public/sections/{}".format(settings.ROOT_SECTION))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["website_text"], "Über uns.")

    def test_public_section_detail_unknown_404(self):
        r = self.client.get("/api/startpage/public/sections/nope-nope")
        self.assertEqual(r.status_code, 404)

    # --- post detail ------------------------------------------------------

    def test_public_post_detail(self):
        self.recent_post.groups.add(self.visible_group)
        member_user, member = make_member_user("teilnehmer")
        member.group.add(self.visible_group)
        mop = MemberOnPost.objects.create(
            post=self.recent_post, description="Gipfelfoto", tag="gipfel"
        )
        mop.members.add(member)

        r = self.client.get(
            "/api/startpage/public/sections/{}/posts/{}".format(
                settings.RECENT_SECTION, self.recent_post.urlname
            )
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["title"], "Neue Tour")
        self.assertEqual(body["section"]["urlname"], settings.RECENT_SECTION)
        self.assertEqual({p["id"] for p in body["people"]}, {member.pk})
        self.assertEqual(len(body["people_on_post"]), 1)
        self.assertEqual(body["people_on_post"][0]["tag"], "gipfel")
        self.assertEqual({m["id"] for m in body["people_on_post"][0]["members"]}, {member.pk})

    def test_public_post_detail_unknown_404(self):
        r = self.client.get(
            "/api/startpage/public/sections/{}/posts/missing".format(settings.RECENT_SECTION)
        )
        self.assertEqual(r.status_code, 404)


class StartpageWriteHardeningTestCase(TestCase):
    """``full_clean`` on the authenticated create/update endpoints (HTTP 422)."""

    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.editor_user, _ = make_member_user("editor")
        self.editor_user = grant(
            self.editor_user,
            "add_section",
            "change_section",
            "add_post",
            "add_link",
        )
        self.section = Section.objects.create(title="Aktuelles", urlname="aktuelles")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def test_create_section_rejects_duplicate_urlname(self):
        r = self.client.post(
            "/api/startpage/sections",
            data={"title": "Zweitens", "urlname": "aktuelles"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertEqual(Section.objects.filter(urlname="aktuelles").count(), 1)

    def test_create_link_rejects_invalid_url(self):
        r = self.client.post(
            "/api/startpage/links",
            data={"title": "Kaputt", "url": "not a url"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_create_post_rejects_missing_section(self):
        r = self.client.post(
            "/api/startpage/posts",
            data={"title": "Tour", "urlname": "tour"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(Post.objects.filter(urlname="tour").exists())

    def test_update_section_keeps_own_urlname(self):
        r = self.client.put(
            "/api/startpage/sections/{}".format(self.section.pk),
            data={"title": "Neu", "urlname": "aktuelles"},
            content_type="application/json",
            **self.auth(self.editor_user),
        )
        self.assertEqual(r.status_code, 200)
        self.section.refresh_from_db()
        self.assertEqual(self.section.title, "Neu")
