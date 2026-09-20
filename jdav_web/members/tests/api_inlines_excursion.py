"""End-to-end tests for the excursion / note-list inline REST endpoints.

These cover the participant (``NewMemberOnList``) inline shared by ``Freizeit``
and ``MemberNoteList`` plus the ``LJPProposal`` / ``Intervention`` inlines,
exercising the real OAuth2 bearer auth path and the parent-scoped permission
gates (authorized write, unauthorized 403, validation 422).
"""

import datetime
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.http import Http404
from django.test import TestCase
from django.utils import timezone
from members.api.inlines_excursion import _authorize_participant_parent
from members.api.inlines_excursion import _validate_ljp_combination
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Intervention
from members.models import LJPProposal
from members.models import Member
from members.models import MemberNoteList
from members.models import NewMemberOnList
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


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="members", codename=codename)
        )
    return User.objects.get(pk=user.pk)


class ExcursionInlineApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.leader_user, self.leader = make_member_user("leader")
        self.other_user, self.other = make_member_user("other")
        self.participant = Member.objects.create(
            prename="Pat",
            lastname="Participant",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )
        self.excursion = Freizeit.objects.create(
            name="Zugspitze",
            tour_type=GEMEINSCHAFTS_TOUR,
            kilometers_traveled=10,
            difficulty=1,
        )
        # The leader leads the excursion (is_leader -> change_obj_freizeit).
        self.excursion.jugendleiter.add(self.leader)
        self.notelist = MemberNoteList.objects.create(title="Notes")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    # --- excursion participants -------------------------------------------

    def test_add_excursion_participant_authorized(self):
        r = self.client.post(
            "/api/members/excursions/{}/participants".format(self.excursion.pk),
            data={"member_id": self.participant.pk, "comments": "brings tent"},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["member"]["id"], self.participant.pk)
        self.assertTrue(
            NewMemberOnList.objects.filter(
                member=self.participant, object_id=self.excursion.pk
            ).exists()
        )

    def test_add_excursion_participant_forbidden(self):
        r = self.client.post(
            "/api/members/excursions/{}/participants".format(self.excursion.pk),
            data={"member_id": self.participant.pk},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(NewMemberOnList.objects.filter(object_id=self.excursion.pk).exists())

    def test_list_excursion_participants_authorized(self):
        self.excursion.add_members([self.participant])
        r = self.client.get(
            "/api/members/excursions/{}/participants".format(self.excursion.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual({p["member"]["id"] for p in r.json()}, {self.participant.pk})

    def test_update_participant_comment_authorized(self):
        self.excursion.add_members([self.participant])
        row = NewMemberOnList.objects.get(object_id=self.excursion.pk)
        r = self.client.patch(
            "/api/members/participants/{}".format(row.pk),
            data={"comments": "updated"},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 200)
        row.refresh_from_db()
        self.assertEqual(row.comments, "updated")

    def test_delete_participant_forbidden(self):
        self.excursion.add_members([self.participant])
        row = NewMemberOnList.objects.get(object_id=self.excursion.pk)
        r = self.client.delete(
            "/api/members/participants/{}".format(row.pk),
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(NewMemberOnList.objects.filter(pk=row.pk).exists())

    def test_delete_participant_authorized(self):
        self.excursion.add_members([self.participant])
        row = NewMemberOnList.objects.get(object_id=self.excursion.pk)
        r = self.client.delete(
            "/api/members/participants/{}".format(row.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(NewMemberOnList.objects.filter(pk=row.pk).exists())

    # --- note-list participants -------------------------------------------

    def test_add_notelist_participant_requires_permission(self):
        # Without members.change_membernotelist the leader may not edit it.
        r = self.client.post(
            "/api/members/note-lists/{}/participants".format(self.notelist.pk),
            data={"member_id": self.participant.pk},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 403)

        granted = grant(self.leader_user, "change_membernotelist")
        r = self.client.post(
            "/api/members/note-lists/{}/participants".format(self.notelist.pk),
            data={"member_id": self.participant.pk},
            content_type="application/json",
            **self.auth(granted),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(
            NewMemberOnList.objects.filter(
                member=self.participant, object_id=self.notelist.pk
            ).exists()
        )

    # --- LJP proposal + interventions -------------------------------------

    def test_create_ljp_proposal_authorized(self):
        r = self.client.post(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            data={
                "title": "Climbing course",
                "category": LJPProposal.LJP_EDUCATIONAL,
                "goal": LJPProposal.LJP_PARTICIPATION,
            },
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        proposal = LJPProposal.objects.get(excursion=self.excursion)
        self.assertEqual(proposal.title, "Climbing course")

    def test_create_ljp_proposal_falls_back_to_model_defaults(self):
        # Supplying neither leaves the model defaults in place — Qualification
        # with Educational programme — which the combination rule rejects. The
        # defaults are therefore not a usable pair, and that is worth knowing.
        r = self.client.post(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            data={"title": "Unvollstaendig"},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("__all__", r.json()["errors"])

    def test_create_ljp_proposal_forbidden(self):
        r = self.client.post(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            data={
                "category": LJPProposal.LJP_EDUCATIONAL,
                "goal": LJPProposal.LJP_PARTICIPATION,
            },
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertFalse(LJPProposal.objects.filter(excursion=self.excursion).exists())

    def test_create_ljp_proposal_invalid_combination_422(self):
        # goal=Qualification is only valid with category=Staff training.
        r = self.client.post(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            data={
                "category": LJPProposal.LJP_EDUCATIONAL,
                "goal": LJPProposal.LJP_QUALIFICATION,
            },
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 422)
        self.assertFalse(LJPProposal.objects.filter(excursion=self.excursion).exists())

    def test_add_intervention_authorized(self):
        proposal = LJPProposal.objects.create(
            excursion=self.excursion,
            category=LJPProposal.LJP_EDUCATIONAL,
            goal=LJPProposal.LJP_PARTICIPATION,
        )
        r = self.client.post(
            "/api/members/ljp-proposals/{}/interventions".format(proposal.pk),
            data={
                "date_start": "2026-07-12T10:00:00",
                "duration": "1.5",
                "activity": "Knots",
            },
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(proposal.intervention_set.count(), 1)

    def test_add_intervention_forbidden(self):
        proposal = LJPProposal.objects.create(
            excursion=self.excursion,
            category=LJPProposal.LJP_EDUCATIONAL,
            goal=LJPProposal.LJP_PARTICIPATION,
        )
        r = self.client.post(
            "/api/members/ljp-proposals/{}/interventions".format(proposal.pk),
            data={
                "date_start": "2026-07-12T10:00:00",
                "duration": "1.5",
                "activity": "Knots",
            },
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(proposal.intervention_set.count(), 0)

    # --- the rest of the LJP inline cycle ---------------------------------

    def _proposal(self):
        return LJPProposal.objects.create(
            excursion=self.excursion,
            title="Climbing course",
            category=LJPProposal.LJP_EDUCATIONAL,
            goal=LJPProposal.LJP_PARTICIPATION,
        )

    def _intervention(self, proposal):
        return Intervention.objects.create(
            ljp_proposal=proposal,
            date_start=timezone.now(),
            duration=2,
            activity="Knotenkunde",
        )

    def test_retrieve_ljp_proposal(self):
        proposal = self._proposal()
        r = self.client.get(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["id"], proposal.pk)

    def test_retrieve_ljp_proposal_404_when_there_is_none(self):
        r = self.client.get(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 404, r.content)

    def test_retrieve_ljp_proposal_forbidden(self):
        self._proposal()
        r = self.client.get(
            "/api/members/excursions/{}/ljp-proposal".format(self.excursion.pk),
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_update_ljp_proposal(self):
        proposal = self._proposal()
        r = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"title": "Kletterkurs", "goal_strategy": "Schrittweise"},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        proposal.refresh_from_db()
        self.assertEqual(proposal.title, "Kletterkurs")
        self.assertEqual(proposal.goal_strategy, "Schrittweise")

    def test_update_ljp_proposal_rejects_an_invalid_combination(self):
        # The same rule the create path enforces: Qualification only pairs with
        # Staff training, and editing must not be a way around it.
        proposal = self._proposal()
        r = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"goal": LJPProposal.LJP_QUALIFICATION},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        proposal.refresh_from_db()
        self.assertEqual(proposal.goal, LJPProposal.LJP_PARTICIPATION)

    def test_update_ljp_proposal_forbidden(self):
        proposal = self._proposal()
        r = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"title": "Fremd"},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)
        proposal.refresh_from_db()
        self.assertEqual(proposal.title, "Climbing course")

    def test_delete_ljp_proposal(self):
        proposal = self._proposal()
        r = self.client.delete(
            "/api/members/ljp-proposals/{}".format(proposal.pk), **self.auth(self.leader_user)
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(LJPProposal.objects.filter(pk=proposal.pk).exists())

    def test_delete_ljp_proposal_forbidden(self):
        proposal = self._proposal()
        r = self.client.delete(
            "/api/members/ljp-proposals/{}".format(proposal.pk), **self.auth(self.other_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(LJPProposal.objects.filter(pk=proposal.pk).exists())

    def test_list_and_update_interventions(self):
        proposal = self._proposal()
        intervention = self._intervention(proposal)
        listed = self.client.get(
            "/api/members/ljp-proposals/{}/interventions".format(proposal.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertIn(intervention.pk, {row["id"] for row in listed.json()})

        r = self.client.patch(
            "/api/members/interventions/{}".format(intervention.pk),
            data={"activity": "Standplatzbau", "duration": 3},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        intervention.refresh_from_db()
        self.assertEqual(intervention.activity, "Standplatzbau")

    def test_delete_intervention(self):
        proposal = self._proposal()
        intervention = self._intervention(proposal)
        r = self.client.delete(
            "/api/members/interventions/{}".format(intervention.pk),
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Intervention.objects.filter(pk=intervention.pk).exists())

    def test_intervention_routes_forbidden(self):
        proposal = self._proposal()
        intervention = self._intervention(proposal)
        self.assertEqual(
            self.client.patch(
                "/api/members/interventions/{}".format(intervention.pk),
                data={"activity": "Fremd"},
                content_type="application/json",
                **self.auth(self.other_user),
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.delete(
                "/api/members/interventions/{}".format(intervention.pk),
                **self.auth(self.other_user),
            ).status_code,
            403,
        )
        self.assertTrue(Intervention.objects.filter(pk=intervention.pk).exists())

    def test_list_notelist_participants(self):
        # A note list is not an excursion: it has no leader to inherit from, so
        # the plain `view_membernotelist` permission is what opens it.
        self.notelist.add_members(Member.objects.filter(pk=self.participant.pk))
        reader = grant(self.leader_user, "view_membernotelist")
        r = self.client.get(
            "/api/members/note-lists/{}/participants".format(self.notelist.pk),
            **self.auth(reader),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({row["member"]["id"] for row in r.json()}, {self.participant.pk})

    def test_an_orphaned_proposal_falls_back_to_the_global_permission(self):
        # `excursion` is SET_NULL, so a proposal can outlive its excursion. With
        # no excursion to inherit from, the global permission is what governs it.
        proposal = self._proposal()
        proposal.excursion = None
        proposal.save()

        refused = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"title": "Verwaist"},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(refused.status_code, 403, refused.content)

        editor = grant(self.leader_user, "change_global_freizeit")
        allowed = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"title": "Verwaist"},
            content_type="application/json",
            **self.auth(editor),
        )
        self.assertEqual(allowed.status_code, 200, allowed.content)
        proposal.refresh_from_db()
        self.assertEqual(proposal.title, "Verwaist")

    def test_a_goal_that_is_not_qualification_needs_the_educational_category(self):
        # The other arm of the same rule the create path already checks.
        proposal = self._proposal()
        r = self.client.patch(
            "/api/members/ljp-proposals/{}".format(proposal.pk),
            data={"category": LJPProposal.LJP_STAFF_TRAINING},
            content_type="application/json",
            **self.auth(self.leader_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        proposal.refresh_from_db()
        self.assertEqual(proposal.category, LJPProposal.LJP_EDUCATIONAL)


class LjpValidationHelpersTest(TestCase):
    """The two helpers whose defensive arms no route can reach.

    ``goal`` and ``category`` both carry non-null model defaults, so a proposal
    always has both by the time a route validates it; and only a ``Freizeit`` or
    a ``MemberNoteList`` is ever passed as a participant list. Both helpers still
    accept the other case, and these pin what they do with it.
    """

    def test_a_missing_goal_or_category_has_no_combination_to_check(self):
        self.assertIsNone(_validate_ljp_combination(None, None))
        self.assertIsNone(_validate_ljp_combination(LJPProposal.LJP_QUALIFICATION, None))
        self.assertIsNone(_validate_ljp_combination(None, LJPProposal.LJP_EDUCATIONAL))

    def test_an_unknown_participant_list_is_a_404(self):
        with self.assertRaises(Http404):
            _authorize_participant_parent(None, object(), write=False)
