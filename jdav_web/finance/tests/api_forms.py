"""The endpoints that speak in declarations rather than in columns.

``/form`` asks the section's rules what to ask a person, ``/preflight`` asks
them what is still wrong, ``/approval`` asks them who has to sign — and the
``inputs`` half of ``PATCH /statements/{id}`` reads the answers back, validating
each against the declaration it belongs to rather than against a hand-written
list of the four columns Heidelberg happens to have.

``Statement.inputs`` is the whole record now: the four Heidelberg columns were
migrated into it by ``0021`` and dropped by ``0022``, so an answer that arrives
here is stored under the key the rules declared and read back from there.
"""

import datetime
import uuid
from decimal import Decimal
from unittest.mock import patch

from django import forms
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils import timezone
from django.utils.translation import gettext as _
from finance.api.tests import AccessToken
from finance.api.tests import Application
from finance.api.tests import grant
from finance.api.tests import make_member_user
from finance.inputs import clean_value
from finance.inputs import form_field
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.rules_api import Choice
from finance.rules_api import Input
from finance.rules_api import Member as RuleMember
from finance.rules_api import MemberId
from finance.testing import answer
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList


class FinanceFormApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client-forms",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("fowner")
        self.leader_user, self.leader = make_member_user("fleader")
        self.manager_user, self.manager = make_member_user("fmanager")
        self.manager_user = grant(
            self.manager_user,
            "view_global_statement",
            "change_global_statement",
            "process_statementsubmitted",
        )
        self.excursion = Freizeit.objects.create(
            name="Formfahrt",
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.excursion.jugendleiter.add(self.leader)
        # Four participants, so the section approves two youth leaders: the
        # allowance declaration's `max` comes from that ratio.
        for index in range(4):
            _user, participant = make_member_user(f"fteil{index}")
            NewMemberOnList.objects.create(member=participant, memberlist=self.excursion)
        self.statement = Statement.objects.create(
            short_description="Formular", excursion=self.excursion, created_by=self.owner
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

    # --- the form ---------------------------------------------------------

    def test_the_form_comes_from_the_rules_with_the_options_resolved(self):
        r = self.client.get(
            "/api/finance/statements/{}/form".format(self.statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["statement_id"], self.statement.pk)
        keys = [declaration["key"] for declaration in body["inputs"]]
        self.assertEqual(keys, ["night_cost", "allowance_to", "subsidy_to", "ljp_to"])
        allowance = body["inputs"][1]
        self.assertEqual(allowance["type"], "member_set")
        self.assertFalse(allowance["required"])
        self.assertEqual(allowance["options"], [{"id": self.leader.pk, "name": self.leader.name}])
        self.assertEqual(allowance["max"], self.excursion.approved_staff_count)
        self.assertIn("Übernachtung", body["inputs"][0]["label"])

    def test_a_statement_without_a_trip_offers_nobody(self):
        statement = Statement.objects.create(short_description="Ohne Fahrt", created_by=self.owner)
        r = self.client.get(
            "/api/finance/statements/{}/form".format(statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        for declaration in r.json()["inputs"]:
            self.assertEqual(declaration["options"], [])

    # --- the answers ------------------------------------------------------

    def test_the_form_hands_back_the_answers_it_asks_about(self):
        answer(self.statement, night_cost="12.50", subsidy_to=self.leader.pk, retired="alt")
        r = self.client.get(
            "/api/finance/statements/{}/form".format(self.statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        answers = r.json()["answers"]
        self.assertEqual(answers["night_cost"], "12.50")
        self.assertEqual(answers["subsidy_to"], self.leader.pk)
        self.assertIsNone(answers["ljp_to"])
        # A key the rules do not ask for is not handed back to be re-submitted
        # — which it would then be refused for.
        self.assertNotIn("retired", answers)

    def test_an_answer_lands_under_the_key_the_rules_declared(self):
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={
                "inputs": {
                    "night_cost": "12.50",
                    "allowance_to": [self.leader.pk],
                    "subsidy_to": self.leader.pk,
                    "ljp_to": self.leader.pk,
                }
            },
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.statement.refresh_from_db()
        self.assertEqual(self.statement.inputs["night_cost"], "12.50")
        self.assertEqual(self.statement.inputs["allowance_to"], [self.leader.pk])
        self.assertEqual(self.statement.inputs["subsidy_to"], self.leader.pk)
        self.assertEqual(self.statement.inputs["ljp_to"], self.leader.pk)
        # And read back by the accessors the pages that narrate the payout use.
        self.assertEqual(self.statement.night_cost, Decimal("12.50"))
        self.assertEqual(self.statement.subsidy_to, self.leader)
        self.assertEqual(self.statement.ljp_to, self.leader)
        self.assertEqual(self.statement.allowance_to, [self.leader])

    def test_an_answer_this_request_leaves_out_is_left_alone(self):
        answer(self.statement, subsidy_to=self.leader.pk)
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"night_cost": "3.00"}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.statement.refresh_from_db()
        self.assertEqual(self.statement.inputs["subsidy_to"], self.leader.pk)

    def test_a_refusal_names_the_answer_it_is_about(self):
        """The 422 carries an ``errors`` map keyed by the declaration.

        Neuter it — raise the message without the key — and this goes red while
        ``test_an_answer_naming_somebody_the_rules_did_not_offer`` stays green,
        which is the difference between a message on the field and a toast over
        the whole form.
        """
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"subsidy_to": self.owner.pk}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("Leiter*innen", " ".join(r.json()["errors"]["subsidy_to"]))

    def _leaders(self, count):
        """``count`` extra youth leaders on the excursion, by ascending id."""
        extra = []
        for index in range(count):
            _user, member = make_member_user(f"fextra{index}")
            self.excursion.jugendleiter.add(member)
            extra.append(member)
        return extra

    def test_naming_the_same_person_twice_pays_them_once(self):
        """A set is a set, and the money says so.

        The ``ManyToManyField`` this replaced collapsed duplicates behind a
        unique constraint, so this was unreachable before. Without the
        deduplication ``[leader, leader]`` passes a bound of two — two ≤ two —
        and ``submit`` freezes two obligation rows paying the same person,
        which is a youth leader doubling their own allowance with one
        ``PATCH``. Neuter it (``sorted(int(pk) for pk in picked)``) and the
        transfer count below goes from one to two.
        """
        self._leaders(1)
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"allowance_to": [self.leader.pk, self.leader.pk]}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.statement.refresh_from_db()
        paid = [
            transfer
            for transfer in self.statement.rule_result.of_category("allowance")
            if transfer.destination == RuleMember(MemberId(self.leader.pk))
        ]
        self.assertEqual(len(paid), 1, "the same person was paid twice")
        self.assertEqual(self.statement.inputs["allowance_to"], [self.leader.pk])

    def test_the_order_people_were_picked_in_does_not_decide_who_pays(self):
        """Whoever is billed the organisation fee is not a click order.

        Heidelberg charges it to ``first_of(subsidy_to, *allowance_to)``, so the
        first element of the set decides. The SPA appends in click order and the
        admin sends option order, and before the columns were dropped
        ``statement_inputs`` sorted by primary key unconditionally — so the two
        orders have to come out the same. Neuter the sort in either
        ``_clean_members`` or ``coerce_input`` and the two assertions below
        disagree.
        """
        other = self._leaders(1)[0]
        pair = sorted([self.leader.pk, other.pk])
        paid = []
        for order in (pair, list(reversed(pair))):
            with self.subTest(order=order):
                r = self.client.patch(
                    "/api/finance/statements/{}".format(self.statement.pk),
                    data={"inputs": {"allowance_to": order}},
                    content_type="application/json",
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.status_code, 200, r.content)
                statement = Statement.objects.get(pk=self.statement.pk)
                paid.append(
                    [
                        transfer.destination.id
                        for transfer in statement.rule_result.of_category("allowance")
                    ]
                )
                # Stored canonically too, so the two UIs show the same
                # selection back and `/form` echoes one order rather than
                # whichever one last arrived. Guarded separately because the
                # read side would otherwise hide it: `coerce_input` sorts as
                # well, so the transfers above come out right either way.
                self.assertEqual(statement.inputs["allowance_to"], pair)
                r = self.client.get(
                    "/api/finance/statements/{}/form".format(self.statement.pk),
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.json()["answers"]["allowance_to"], pair)
        self.assertEqual(paid[0], paid[1], "the click order reached the rules")
        self.assertEqual(paid[0], pair, "ascending ids, as the column always gave")

    def test_an_amount_finer_than_a_cent_or_larger_than_the_books(self):
        """What the engine cannot pay and the books cannot hold.

        ``quantize`` floors to cents, so a third decimal place is dropped
        rather than paid, and an unbounded amount is one ``0021``'s reverse
        cannot write back into the ``max_digits=5`` column it came from.

        ``"1E+1000000"`` is the exponent form of the same thing and belongs
        here because it took a different route: ``normalize()`` applies the
        decimal context and raised ``Overflow``, an ``ArithmeticError`` that is
        not an ``InvalidOperation``, so it came out as a 500. Money is sent as
        text on this API, so there is nothing exotic about it. ``1e400`` is an
        ordinary JSON *number* that arrives as ``float('inf')``.
        """
        for value in ("1.234", "100000.00", "nan", "inf", "1E+1000000", 1e400):
            with self.subTest(value=value):
                r = self.client.patch(
                    "/api/finance/statements/{}".format(self.statement.pk),
                    data={"inputs": {"night_cost": value}},
                    content_type="application/json",
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.status_code, 422, r.content)
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"night_cost": "99999.99"}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)

    def test_an_answer_that_no_longer_fits_its_type_is_an_error_not_a_crash(self):
        """A section changed a question; the old answer is still stored.

        That is the thing this whole feature exists for, so it must not be a
        500 — least of all on ``/form``, which is the only way to put a new
        answer in. Neuter the ``except`` in ``coerce_input`` and all three
        requests below become unhandled ``InvalidOperation``.
        """
        # With a subsidy recipient, because that is the rule that reads the
        # price per night — an answer nothing reads is inert, which is itself
        # worth knowing.
        answer(
            self.statement,
            night_cost={"was": "once a number"},
            subsidy_to=self.leader.pk,
        )
        for path in ("", "/form", "/preflight"):
            with self.subTest(path=path):
                r = self.client.get(
                    "/api/finance/statements/{}{}".format(self.statement.pk, path),
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.status_code, 200, r.content)
        # And it is reported as what it is, on the statement, by the rules.
        self.assertTrue(
            any("night_cost" in error for error in self.statement.rule_result.errors),
            self.statement.rule_result.errors,
        )

    def test_an_answer_that_is_not_a_person_at_all_is_refused_not_a_crash(self):
        """A 422, which is what pydantic used to give for these.

        ``subsidy_to_id`` was typed as an ``int`` on the schema, so anything
        else never reached the code. The answers arrive as a free-form ``dict``
        now and this is the only thing that looks at them, so the shapes a
        client can send have to come back as refusals rather than as 500s.
        Neuter ``_as_member`` — ``int(value)`` bare — and every row below
        becomes an unhandled ``ValueError`` or ``TypeError``. The last two are
        there because the seven before them are all *non-numeric*, which is how
        a number that overflows got through: ``1e400`` is ordinary JSON and
        arrives as ``float('inf')``, whose ``int()`` raises ``OverflowError``,
        which is neither of the two that were caught.
        """
        cases = [
            {"subsidy_to": "abc"},
            {"subsidy_to": [1]},
            {"subsidy_to": {"a": 1}},
            {"allowance_to": [None]},
            {"allowance_to": [[1]]},
            {"allowance_to": {"a": 1}},
            {"allowance_to": "abc"},
            {"subsidy_to": 1e400},
            {"allowance_to": [1e400]},
        ]
        for answers in cases:
            with self.subTest(answers=answers):
                r = self.client.patch(
                    "/api/finance/statements/{}".format(self.statement.pk),
                    data={"inputs": answers},
                    content_type="application/json",
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.status_code, 422, r.content)

    def test_an_answer_naming_somebody_the_rules_did_not_offer(self):
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"subsidy_to": self.owner.pk}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertIn("Leiter*innen", r.content.decode())

    def test_more_recipients_than_the_section_approved(self):
        for index in range(3):
            _user, member = make_member_user(f"extra{index}")
            self.excursion.jugendleiter.add(member)
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={
                "inputs": {
                    "allowance_to": list(self.excursion.jugendleiter.values_list("pk", flat=True))
                }
            },
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_an_answer_to_a_question_the_rules_do_not_ask(self):
        r = self.client.patch(
            "/api/finance/statements/{}".format(self.statement.pk),
            data={"inputs": {"lieblingsfarbe": "blau"}},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_an_amount_that_is_not_one(self):
        for value in ("zwölf", "-1"):
            with self.subTest(value=value):
                r = self.client.patch(
                    "/api/finance/statements/{}".format(self.statement.pk),
                    data={"inputs": {"night_cost": value}},
                    content_type="application/json",
                    **self.auth(self.owner_user),
                )
                self.assertEqual(r.status_code, 422, r.content)

    # --- the preflight ----------------------------------------------------

    def test_the_preflight_lists_what_is_still_wrong(self):
        Bill.objects.create(
            statement=self.statement,
            short_description="Hütte",
            amount=Decimal("10.00"),
            costs_covered=True,
        )
        answer(self.statement, ljp_to=self.leader.pk)
        self.statement.save()
        r = self.client.get(
            "/api/finance/statements/{}/preflight".format(self.statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertFalse(body["ok"])
        # The LJP check (no picture) and the payerless receipt (an error).
        self.assertTrue(any("Bild" in check["message"] for check in body["failing"]))
        self.assertTrue(any("Beleg" in error for error in body["errors"]))
        self.assertGreaterEqual(len(body["checks"]), len(body["failing"]))

    def test_a_statement_with_nothing_wrong_passes_its_preflight(self):
        r = self.client.get(
            "/api/finance/statements/{}/preflight".format(self.statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertTrue(r.json()["ok"])

    # --- the signatures ---------------------------------------------------

    def test_the_approval_endpoint_names_who_may_still_sign(self):
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.leader,
        )
        self.statement.submit(self.owner)
        r = self.client.get(
            "/api/finance/statements/{}/approval".format(self.statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertFalse(body["approved"])
        self.assertTrue(body["may_approve"])
        # Heidelberg asks for one signature, so this manager's signature is the
        # one that pays the statement out — which is what the page needs to know
        # before offering the act, because signing and paying out are the same
        # click here and two different clicks where a section asks for more.
        self.assertTrue(body["completes_approval"])
        constraint = body["constraints"][0]
        self.assertEqual(constraint["name"], "Freigabe")
        self.assertEqual(constraint["required"], 1)
        self.assertTrue(constraint["applicable"])
        self.assertFalse(constraint["satisfied"])
        self.assertTrue(constraint["open"])
        self.assertEqual(constraint["missing"], 1)
        self.assertEqual([m["id"] for m in constraint["eligible"]], [self.manager.pk])
        self.assertEqual(body["signatures"], [])

    def test_the_approval_endpoint_survives_a_snapshot_whose_body_raises(self):
        """A section's broken rules must not take its finance pages down.

        A snapshot whose module body raises — the section's own `ValueError`
        at import time, which is what a bad configuration repository looks
        like once it is stored — used to come straight out of
        `loaded_ruleset`, which caught only the two exceptions a *refused*
        snapshot raises. With the call also sitting outside
        `_rows_from_the_same_rules`' own `try`, the gate propagated it, and
        this endpoint and the admin's approval page answered 500 instead of
        falling back to the frozen rows they are built around. Both halves are
        fixed (#547, #553); this is the page, asserted from outside.
        """
        self.statement.submit(self.owner)
        statement = Statement.objects.get(pk=self.statement.pk)
        frozen = [row.name for row in statement.approval_constraint_set.all()]
        self.assertTrue(frozen, "there are rows to fall back to, which makes this a test")
        snapshot = dict(statement.ruleset_snapshot)
        snapshot["sources"] = {"__init__.py": "raise ValueError('kaputt')\n"}
        Statement.objects.filter(pk=statement.pk).update(ruleset_snapshot=snapshot)
        r = self.client.get(
            "/api/finance/statements/{}/approval".format(self.statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual([c["name"] for c in r.json()["constraints"]], frozen)
        self.assertFalse(r.json()["approved"], "and the payout is still stuck, not waved through")

    def test_signing_a_statement_off_through_the_api(self):
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.leader,
        )
        self.statement.submit(self.owner)
        self.statement.generate_transactions()
        self.statement.transaction_set.update(ledger=Ledger.objects.create(name="Konto"))
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(self.statement.pk),
            data={"note": "geprüft"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["approved"])
        self.assertFalse(body["may_approve"], "there is nothing left to sign")
        self.assertEqual(body["signatures"][0]["member"]["id"], self.manager.pk)
        self.assertEqual(body["signatures"][0]["note"], "geprüft")
        self.assertTrue(Statement.objects.get(pk=self.statement.pk).confirmed)

    def test_the_settled_payload_after_a_signature_from_mid_flight(self):
        """What a settled statement says when the person who signed it arrived late.

        Ordinary Heidelberg, nothing corrupted: the statement is handed in, a
        treasurer is appointed while it waits, signs, and it pays out. The
        payload then reads the **record** — the frozen rows, because nothing
        should re-run a section's rules to render a settled statement — and
        the record recomputed `satisfied` as `signed ∩ frozen eligible`, a set
        a mid-flight signer is by construction not in. So it answered
        `approved: true` beside the one step reported open and missing a
        signature, while the frozen row it was reading said `satisfied`.
        """
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.leader,
        )
        self.statement.submit(self.owner)
        self.statement.generate_transactions()
        self.statement.transaction_set.update(ledger=Ledger.objects.create(name="Konto"))
        frozen = self.statement.approval_constraint_set.get()
        self.assertEqual(frozen.eligible_member_ids, [self.manager.pk])
        appointed_user, appointed = make_member_user("fspaet")
        appointed_user = grant(appointed_user, "process_statementsubmitted")
        signed = self.client.post(
            "/api/finance/statements/{}/approve".format(self.statement.pk),
            data={"note": "spät"},
            content_type="application/json",
            **self.auth(appointed_user),
        )
        self.assertEqual(signed.status_code, 200, signed.content)
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(statement.confirmed, "the gate let the appointed treasurer in")
        r = self.client.get(
            "/api/finance/statements/{}/approval".format(self.statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["approved"])
        constraint = body["constraints"][0]
        self.assertTrue(constraint["satisfied"], "the payload agrees with `approved`")
        self.assertFalse(constraint["open"])
        self.assertEqual(constraint["missing"], 0)
        self.assertEqual(constraint["state_display"], _("Signed"))
        self.assertTrue(statement.approval_constraint_set.get().satisfied, "and with the row")
        # `eligible` and `signed_by` stay what the rules named when the
        # statement was handed in, which is the question an audit asks of a
        # record; who actually signed it is reported under `signatures`.
        self.assertEqual([member["id"] for member in constraint["eligible"]], [self.manager.pk])
        self.assertEqual(constraint["signed_by"], [])
        self.assertEqual([s["member"]["id"] for s in body["signatures"]], [appointed.pk])

    def test_somebody_without_the_capability_cannot_sign(self):
        self.statement.submit(self.owner)
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(self.statement.pk),
            data={"note": ""},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403, r.content)

    def test_overriding_a_step_through_the_api(self):
        self.statement.submit(self.owner)
        url = "/api/finance/statements/{}/override-approval".format(self.statement.pk)
        r = self.client.post(
            url,
            data={"name": "Freigabe", "reason": ""},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, "an override has to say why")
        r = self.client.post(
            url,
            data={"name": "Gibt es nicht", "reason": "weil"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        r = self.client.post(
            url,
            data={"name": "Freigabe", "reason": "Fristende"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        constraint = r.json()["constraints"][0]
        self.assertTrue(constraint["overridden"])
        self.assertEqual(constraint["override_reason"], "Fristende")
        self.assertEqual(constraint["overridden_by"]["id"], self.manager.pk)

    def test_an_override_by_somebody_a_forbid_excludes_is_refused(self):
        """The endpoint asks before it writes.

        Heidelberg declares no forbids, so the rule itself is tested on the
        model (:mod:`finance.tests.approval`). What this pins is that the
        endpoint answers 422 rather than returning 200 with nothing changed,
        which is what it would do if it left `override_approval` to refuse on
        its own.
        """
        self.statement.submit(self.owner)
        with patch.object(Statement, "forbids_approval_by", return_value=True):
            r = self.client.post(
                "/api/finance/statements/{}/override-approval".format(self.statement.pk),
                data={"name": "Freigabe", "reason": "Fristende"},
                content_type="application/json",
                **self.auth(self.manager_user),
            )
        self.assertEqual(r.status_code, 422, r.content)
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertFalse(statement.approval_constraint_set.get().overridden)

    def test_an_override_of_a_step_that_is_not_being_asked_for_is_refused(self):
        """The sixth refusal, which is the one that had no endpoint test.

        The model learnt to refuse a waiver for a step that does not apply —
        such a step is not in the way, so the request has nothing to grant —
        and the endpoint went on restating five refusals of its own, so this
        one answered **200** with ``overridden: false`` beside
        ``approved: true``, which reads as success. That is #548 again, and
        why the refusals now live in one place
        (:meth:`finance.models.Statement.override_refusal`).

        Heidelberg's one step always applies, so the row is made inapplicable
        directly — which is the state a section's own threshold writes, as
        :mod:`finance.tests.approval` exercises end to end. What this pins is
        the status code.
        """
        self.statement.submit(self.owner)
        self.statement.approval_constraint_set.update(applicable=False)
        r = self.client.post(
            "/api/finance/statements/{}/override-approval".format(self.statement.pk),
            data={"name": "Freigabe", "reason": "Fristende"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertFalse(statement.approval_constraint_set.get().overridden)
        self.assertFalse(statement.confirmed)

    #: A section whose forbid broke *after* a statement was handed in. The
    #: step keeps its name, so it is the frozen "Freigabe" row that can no
    #: longer be resolved — which is what makes the override refusable.
    BROKEN_FORBID = (
        "from kompass.rules import Constraint, Forbid, Ruleset, SECTION, PARTICIPANTS\n"
        "\n"
        "\n"
        "def kaputt(member):\n"
        "    raise ValueError('der Vorstand ist unbekannt')\n"
        "\n"
        "\n"
        "class BrokenForbid(Ruleset):\n"
        "    name = 'broken-forbid'\n"
        "    permissions = ('finance.process_statementsubmitted',)\n"
        "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
        "\n"
        "    def inputs(self, ctx):\n"
        "        return []\n"
        "\n"
        "    def transfers(self, ctx):\n"
        "        return [], []\n"
        "\n"
        "    def approval(self, ctx, transfers):\n"
        "        signers = ctx.permission_holders('finance.process_statementsubmitted')\n"
        "        return (\n"
        "            [\n"
        "                Constraint(\n"
        "                    name='Freigabe',\n"
        "                    description='Eine Unterschrift',\n"
        "                    applicable=True,\n"
        "                    required=1,\n"
        "                    eligible=signers,\n"
        "                )\n"
        "            ],\n"
        "            [Forbid('kaputt', applies_to=kaputt)],\n"
        "        )\n"
        "\n"
        "\n"
        "ruleset = BrokenForbid()\n"
    )

    def test_an_override_of_a_step_the_rules_cannot_resolve_is_refused_loudly(self):
        """The refusal that used to answer 200 with ``overridden: false``.

        A broken forbid is a rule that failed to say who is excluded, so there
        is no answer to "may this person sign it off" and the payout stays
        stuck — the model's rule, tested on the model in
        :mod:`finance.tests.approval`. What this pins is the endpoint: its
        other four refusals raise and answer 422, this one left
        `override_approval` to refuse on its own and reported the refusal only
        as a field in a 200 body, which a client has to diff against what it
        sent to notice.
        """
        self.statement.submit(self.owner)
        statement = Statement.objects.get(pk=self.statement.pk)
        snapshot = dict(statement.ruleset_snapshot)
        snapshot["sources"] = {"__init__.py": self.BROKEN_FORBID}
        Statement.objects.filter(pk=statement.pk).update(ruleset_snapshot=snapshot)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(
            statement.approval_cannot_be_resolved("Freigabe"),
            "the forbid broke, which is the premise of this test",
        )
        r = self.client.post(
            "/api/finance/statements/{}/override-approval".format(self.statement.pk),
            data={"name": "Freigabe", "reason": "Fristende"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        settled = Statement.objects.get(pk=self.statement.pk)
        self.assertFalse(settled.approval_constraint_set.get().overridden)
        self.assertFalse(settled.confirmed)

    def test_a_draft_cannot_be_overridden(self):
        r = self.client.post(
            "/api/finance/statements/{}/override-approval".format(self.statement.pk),
            data={"name": "Freigabe", "reason": "weil"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)


class InputValueTestCase(SimpleTestCase):
    """One answer against one declaration, for every type there is.

    Heidelberg asks for money and for people, so the rest of the vocabulary a
    declaration may use would otherwise first be exercised by the section that
    starts using it — on a live statement. ``clean_value`` is public for that
    reason: a type's conversion is checkable without a statement, a ruleset or
    a request.
    """

    def test_a_whole_number_within_the_bound_it_declared(self):
        declaration = Input("nights", "Nächte", "int", max=7)
        self.assertEqual(clean_value(declaration, "3"), 3)
        self.assertEqual(clean_value(declaration, None), 0)
        self.assertEqual(clean_value(Input("n", "N", "int"), 99), 99)
        with self.assertRaises(ValidationError):
            clean_value(declaration, "drei")
        with self.assertRaises(ValidationError):
            clean_value(declaration, 8)
        # A number that *overflows* rather than failing to parse: `1e400` is
        # ordinary JSON and arrives as `float('inf')`, whose `int()` raises
        # `OverflowError`. No ruleset in tree declares an `int` yet, so this is
        # the only place the gap could be shown — which is why it is shown
        # here rather than left for the section that declares the first one.
        with self.assertRaises(ValidationError):
            clean_value(declaration, 1e400)

    def test_a_flag_and_a_line_of_text(self):
        self.assertIs(clean_value(Input("f", "F", "bool"), "ja"), True)
        self.assertIs(clean_value(Input("f", "F", "bool"), None), False)
        self.assertEqual(clean_value(Input("t", "T", "text"), 12), "12")
        self.assertEqual(clean_value(Input("t", "T", "text"), None), "")

    def test_an_answer_cleared_again(self):
        """Erasing an answer is an answer, and it is not zero.

        A member nobody picked is ``None`` and an empty set is ``[]``, so the
        rules read "nobody" rather than a member id that no longer applies.
        """
        self.assertIsNone(clean_value(Input("m", "M", "member"), None))
        self.assertEqual(clean_value(Input("s", "S", "member_set"), None), [])
        self.assertEqual(clean_value(Input("c", "C", "money"), None), Decimal("0"))

    def test_a_choice_nobody_has_made_yet(self):
        """Empty is an answer to a ``choice`` and reads back as ``""``.

        The same way an unanswered amount reads back as ``0.00``: a form is
        filled in gradually, so "not chosen yet" has to be submittable. Whether
        an answer is *needed* is ``required`` and the ruleset's own checks, not
        this. Neuter it — refuse the empty value here — and a client cannot
        send a half-finished form at all.
        """
        declaration = Input("regime", "Regelwerk", "choice", choices=(Choice("a", "Erstes"),))
        self.assertEqual(clean_value(declaration, None), "")
        self.assertEqual(clean_value(declaration, ""), "")
        self.assertEqual(clean_value(declaration, "a"), "a")
        with self.assertRaises(ValidationError):
            clean_value(declaration, "b")


class FormFieldTestCase(SimpleTestCase):
    """Each type as the control a server-rendered form shows for it.

    Same reason ``clean_value`` is checked without a statement: the admin's
    excursion inline builds its fields from the declarations, and four of the
    seven types have no section in tree that asks for them yet.
    """

    def test_every_type_becomes_a_field_that_says_what_it_wants(self):
        cases = {
            "money": forms.DecimalField,
            "int": forms.IntegerField,
            "bool": forms.BooleanField,
            "text": forms.CharField,
            "choice": forms.ChoiceField,
            "member": forms.TypedChoiceField,
            "member_set": forms.TypedMultipleChoiceField,
        }
        for input_type, expected in cases.items():
            with self.subTest(type=input_type):
                extra = {"choices": (Choice("a", "A"),)} if input_type == "choice" else {}
                field = form_field(Input("k", "Frage", input_type, help="Hilfe", **extra))
                self.assertIsInstance(field, expected)
                self.assertEqual(field.label, "Frage")
                self.assertEqual(field.help_text, "Hilfe")

    def test_a_bound_whole_number_carries_its_bound(self):
        self.assertEqual(form_field(Input("n", "N", "int", max=9)).max_value, 9)

    def test_a_person_may_be_left_unanswered(self):
        field = form_field(Input("m", "M", "member", required=False))
        self.assertIsNone(field.clean(""))
