"""End-to-end tests for the members document-generation API.

Each generator endpoint is checked for the permission gate the admin enforces
(``403`` for an unauthorized user, success for an authorized one) and, where the
artifact can be produced with pure-Python tooling, for the correct
``Content-Type``. Generators that shell out to ``pdflatex`` / ``pandoc`` guard
the heavy generation path with :func:`unittest.skipUnless` so the suite still
runs (and still verifies the gate) on hosts without those binaries installed.

Mirrors the OAuth2 bearer / ``grant`` fixtures of ``members/tests/api.py``.
"""

import datetime
import shutil
import uuid
from unittest import skipUnless

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.utils import timezone
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Member
from members.models import MemberNoteList
from members.models import NewMemberOnList
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

HAS_PDFLATEX = shutil.which("pdflatex") is not None
HAS_PANDOC = shutil.which("pandoc") is not None


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
            Permission.objects.get(content_type__app_label="members", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class MembersDocumentsApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        # A plain member with no permissions and no relation to the fixtures.
        self.owner_user, self.owner = make_member_user("owner")
        # The member placed on every list; the owner may not view them.
        self.other_user, self.other = make_member_user("other")
        # Global-view user: may view every member and every group.
        self.viewer_user, self.viewer = make_member_user("viewer")
        self.viewer_user = grant(self.viewer_user, "view_global_member", "view_group")
        self.group = Group.objects.create(name="Alpenfuechse", year_from=2010, year_to=2015)

    # --- helpers ----------------------------------------------------------

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def make_excursion(self, name="Seminar"):
        excursion = Freizeit.objects.create(
            name=name,
            place="Alpen",
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
        )
        content_type = ContentType.objects.get_for_model(Freizeit)
        NewMemberOnList.objects.create(
            member=self.other, content_type=content_type, object_id=excursion.pk
        )
        return excursion

    def make_notelist(self, title="Liste"):
        notelist = MemberNoteList.objects.create(title=title)
        content_type = ContentType.objects.get_for_model(MemberNoteList)
        NewMemberOnList.objects.create(
            member=self.other, content_type=content_type, object_id=notelist.pk
        )
        return notelist

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        self.assertEqual(
            self.client.post("/api/members/documents/groups/overview").status_code, 401
        )

    # --- group overview (pure python, always generatable) -----------------

    def test_group_overview_forbidden_without_permission(self):
        r = self.client.post("/api/members/documents/groups/overview", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_group_overview_allowed_with_permission(self):
        r = self.client.post(
            "/api/members/documents/groups/overview", **self.auth(self.viewer_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/xlsx")

    # --- group checklist (pdflatex) ---------------------------------------

    def test_group_checklist_forbidden_without_permission(self):
        r = self.client.post(
            "/api/members/documents/groups/checklist", **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_group_checklist_allowed_with_permission(self):
        r = self.client.post(
            "/api/members/documents/groups/checklist", **self.auth(self.viewer_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    # --- excursion crisis intervention list (pdflatex) --------------------

    def test_excursion_crisis_list_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/crisis-intervention-list".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_excursion_crisis_list_allowed(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/crisis-intervention-list".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    # --- excursion notes list (pdflatex) ----------------------------------

    def test_excursion_notes_list_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/notes-list".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_excursion_notes_list_allowed(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/notes-list".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    # --- note-list summary (pdflatex) -------------------------------------

    def test_note_list_summary_forbidden(self):
        notelist = self.make_notelist()
        r = self.client.post(
            "/api/members/documents/note-lists/{}/summary".format(notelist.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_note_list_summary_allowed(self):
        notelist = self.make_notelist()
        r = self.client.post(
            "/api/members/documents/note-lists/{}/summary".format(notelist.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    # --- ad-hoc crisis intervention list (pdflatex) -----------------------

    def _adhoc_payload(self, member):
        return {
            "activity": "Klettern",
            "place": "Halle",
            "start_date": "2026-07-12",
            "end_date": "2026-07-12",
            "description": "Ad-hoc",
            "member_ids": [member.pk],
        }

    def test_adhoc_crisis_list_forbidden(self):
        r = self.client.post(
            "/api/members/documents/crisis-intervention-list",
            data=self._adhoc_payload(self.other),
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_adhoc_crisis_list_empty_selection_rejected(self):
        payload = self._adhoc_payload(self.other)
        payload["member_ids"] = []
        r = self.client.post(
            "/api/members/documents/crisis-intervention-list",
            data=payload,
            content_type="application/json",
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 422)

    @skipUnless(HAS_PDFLATEX, "pdflatex not available")
    def test_adhoc_crisis_list_allowed(self):
        r = self.client.post(
            "/api/members/documents/crisis-intervention-list",
            data=self._adhoc_payload(self.other),
            content_type="application/json",
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r["Content-Type"], "application/pdf")

    # --- LJP / seminar documents (require an LJP proposal) ----------------
    #
    # The member gate runs before the LJP-proposal guard, so an unauthorized
    # user is rejected with 403 while an authorized user hitting an excursion
    # without a proposal gets 422 — both without invoking pdflatex/pandoc.

    def test_seminar_vbk_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-vbk".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_seminar_vbk_without_ljp_proposal_rejected(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-vbk".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_seminar_report_docx_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-report-docx".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_seminar_report_docx_without_ljp_proposal_rejected(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-report-docx".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_seminar_report_costs_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-report-costs".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_seminar_report_costs_without_ljp_proposal_rejected(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/seminar-report-costs".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_ljp_proofs_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/ljp-proofs".format(excursion.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_ljp_proofs_without_ljp_proposal_rejected(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/ljp-proofs".format(excursion.pk),
            **self.auth(self.viewer_user),
        )
        self.assertEqual(r.status_code, 422)

    # --- SJR application --------------------------------------------------

    def test_sjr_application_forbidden(self):
        excursion = self.make_excursion()
        r = self.client.post(
            "/api/members/documents/excursions/{}/sjr-application".format(excursion.pk),
            data={"bill_id": None},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
