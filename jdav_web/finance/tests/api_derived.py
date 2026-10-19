"""A form a ruleset shapes: derived answers, named choices, steps, option sources.

The four things a ruleset gained, exercised through the endpoint a client
actually uses, because every one of them is a claim about what a *request* can
and cannot do:

* a question the engine answers from the trip is served with its value and its
  answer is **refused** on the way in (:class:`DerivedInputApiTestCase`),
* a ``choice`` carries its own alternatives and nothing else is accepted
  (:class:`ChoiceInputApiTestCase`),
* a party-valued question can name where its people come from, so a statement
  with no excursion can still pay somebody
  (:class:`OptionSourceApiTestCase`),
* and the declarations come back grouped (:class:`FormStepApiTestCase`).

Read :mod:`finance.tests.harness` before adding to this module. Every test
here names the line whose absence it detects, because most of what is being
claimed is a *refusal*, and a test that only asserts the happy path passes
against a version that accepts anything. The derived figure is the sharpest
case: asserting that ``kilometers`` comes back as 100 passes just as well
against a form that lets a client ``PATCH`` it to 9999.
"""

import datetime
import uuid
from contextlib import contextmanager
from contextlib import ExitStack
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from finance.api.tests import AccessToken
from finance.api.tests import Application
from finance.api.tests import make_member_user
from finance.engine import evaluate_statement
from finance.models import Bill
from finance.models import Statement
from finance.rules_api import Choice
from finance.rules_api import Input
from finance.rules_api import Member as RuleMember
from finance.rules_api import PARTICIPANTS
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset
from finance.rules_api import SECTION
from finance.rules_api import Transfer
from finance.testing import answer
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import NewMemberOnList

#: The two rates the regime question picks between, per kilometre.
RATES = {"ehrenamt": Decimal("0.20"), "tourenleitung": Decimal("0.30")}


class TravelRules(Ruleset):
    """Ludwigsburg in miniature: two rulebooks, one form, trip or no trip.

    The shape that motivated all of this. The section has two parallel travel
    rulebooks whose rates differ, so which one applies is a question — a
    ``choice``, which is why #573 had to be fixed first. The kilometres come off
    the excursion when there is one and are asked for when there is not, which
    is what ``source`` is for: the rule below reads
    ``ctx.inputs.number("kilometers")`` once and never asks where the figure
    came from. And a statement with no trip still has to be able to pay
    somebody, which is what ``options_source`` is for — there are no youth
    leaders to offer, but there is whoever paid the receipt.
    """

    name = "travel"
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [
            Input(
                "regime",
                "Regelwerk",
                "choice",
                step="Grundlagen",
                choices=(
                    Choice("ehrenamt", "Ehrenamtspauschale"),
                    Choice("tourenleitung", "Tourenleitung"),
                ),
            ),
            Input(
                "kilometers",
                "Gefahrene Kilometer",
                "int",
                required=False,
                step="Fahrt",
                source="excursion.kilometers",
            ),
            Input(
                "paid_to",
                "Auslagen an",
                "member",
                required=False,
                step="Fahrt",
                options_source="bills.payers",
            ),
        ]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        recipient = ctx.inputs.member("paid_to")
        # One accessor, one code path, trip or no trip. That is the whole point
        # of a derived input: without it this rule would need a branch on
        # `ctx.excursion is None` and would read the figure from two places.
        kilometers = ctx.inputs.number("kilometers")
        rate = RATES.get(ctx.inputs.text("regime"), Decimal("0.00"))
        amount = (kilometers * rate).quantize(Decimal("0.01"))
        if recipient is None or not amount:
            return [], []
        return [Transfer(SECTION, recipient, amount, "travel", rule_id="travel")], []


class DerivedFormTestCase(TestCase):
    """The fixture every class here shares: a trip, a statement, a token."""

    kilometers = 100

    def setUp(self):
        self.application = Application.objects.create(
            name="test-client-derived",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("downer")
        self.leader_user, self.leader = make_member_user("dleader")
        self.excursion = Freizeit.objects.create(
            name="Fahrt mit Kilometern",
            kilometers_traveled=self.kilometers,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=FAHRGEMEINSCHAFT_ANREISE,
            difficulty=1,
        )
        self.excursion.jugendleiter.add(self.leader)
        NewMemberOnList.objects.create(member=self.leader, memberlist=self.excursion)
        self.statement = Statement.objects.create(
            short_description="Mit Fahrt", excursion=self.excursion, created_by=self.owner
        )
        self.loose = Statement.objects.create(short_description="Ohne Fahrt", created_by=self.owner)
        self.rules = TravelRules()

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    @contextmanager
    def serving(self):
        """Serve ``self.rules`` to the form, the ``PATCH`` and the evaluation.

        Two entry points resolve a statement's ruleset, and a test that patched
        only one would compare a form derived from one ruleset with money
        resolved by another. ``finance.inputs`` is what ``/form`` and ``clean``
        go through; ``finance.engine.statements`` is what the materialisation on
        save and ``Statement.rule_result`` go through.
        """
        with ExitStack() as stack:
            for where in ("finance.inputs", "finance.engine.statements"):
                stack.enter_context(patch(f"{where}.ruleset_for", return_value=self.rules))
            yield

    def form(self, statement):
        """``GET …/form``'s body for ``statement``, under ``TravelRules``."""
        with self.serving():
            response = self.client.get(
                "/api/finance/statements/{}/form".format(statement.pk),
                **self.auth(self.owner_user),
            )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def answer_through_the_api(self, statement, answers):
        """``PATCH``'s response for ``answers``, under ``TravelRules``."""
        with self.serving():
            return self.client.patch(
                "/api/finance/statements/{}".format(statement.pk),
                data={"inputs": answers},
                content_type="application/json",
                **self.auth(self.owner_user),
            )

    def declaration(self, body, key):
        """One declaration out of a ``/form`` body, by key."""
        return next(entry for entry in body["inputs"] if entry["key"] == key)

    def paid(self, statement):
        """What ``TravelRules`` pays out as travel money on ``statement``."""
        result = evaluate_statement(Statement.objects.get(pk=statement.pk), ruleset=self.rules)
        self.assertEqual(result.errors, (), result.errors)
        return result.total_of("travel")


class DerivedInputApiTestCase(DerivedFormTestCase):
    """A question the engine answers from the statement's own data."""

    def test_a_derived_question_is_served_with_the_value_it_derives(self):
        body = self.form(self.statement)
        kilometers = self.declaration(body, "kilometers")
        self.assertTrue(kilometers["derived"], "the form has to say it is not a question")
        self.assertEqual(body["answers"]["kilometers"], self.kilometers)

    def test_a_derived_answer_is_refused_and_not_quietly_dropped(self):
        """The guarding test for the whole feature's fail-closed half.

        A derived figure is never stored, so a value submitted for one would go
        where nothing reads it — and nothing would tell the sender. Refusing is
        what makes that impossible rather than merely pointless: a hand-crafted
        ``PATCH``, or a client that echoed back the form it was served, cannot
        put a figure of its own where the excursion's kilometres belong.

        Neuter it — drop the ``if declaration.derived: raise`` in
        :func:`finance.inputs.clean` — and this goes red twice over: the request
        answers 200, and the bogus figure lands in ``Statement.inputs``, where
        the next person to read the column sees 9999 beside a trip that drove
        100. A test asserting only that the derived value is *correct* would
        notice neither, because the payout is right either way — the engine
        shadows the stored figure — and that is exactly why the refusal needs a
        test of its own.
        """
        response = self.answer_through_the_api(self.statement, {"kilometers": 9999})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("kilometers", response.json()["errors"])
        self.statement.refresh_from_db()
        self.assertNotIn("kilometers", self.statement.inputs)

    def test_a_value_written_behind_the_form_is_shadowed_rather_than_read(self):
        """Not stored, so a stored one does not count — belt as well as braces.

        ``clean`` refuses the key, and a fixture (or an admin editing the JSON
        column, or a row that predates the question being derived) can still
        put a value there. The engine resolves the source again on every
        context build, so the figure a rule reads is the trip's.

        What this detects is the resolution in
        :func:`finance.engine.answers.typed_inputs`: prefer ``answers`` over the
        engine's own value and the form reports 9999 and the payout doubles.
        The *other* resolution, in ``_answered``, is a different claim on a
        different route — see
        ``test_a_dry_run_cannot_put_its_own_figure_in_a_derived_answer``.
        """
        answer(self.statement, kilometers=9999, regime="ehrenamt")
        with self.serving():
            self.assertEqual(self.form(self.statement)["answers"]["kilometers"], self.kilometers)
        self._a_bill_paid_by(self.leader)
        self.assertEqual(
            self.answer_through_the_api(self.statement, {"paid_to": self.leader.pk}).status_code,
            200,
        )
        self.assertEqual(self.paid(self.statement), Decimal("20.00"))

    def test_without_a_trip_the_same_question_is_asked_and_answered(self):
        """The other half: one declaration, two provenances, one accessor.

        A statement with no excursion has no kilometres to read, so the
        declaration is an ordinary question — not derived, answerable,
        stored — and the rule reads it exactly as it reads the derived one.
        Neuter the ``if value is not None`` in
        :func:`finance.engine.declared.supplied` and the question is marked
        derived with nothing behind it, so this statement can never say how far
        it drove.
        """
        body = self.form(self.loose)
        self.assertFalse(self.declaration(body, "kilometers")["derived"])
        self._a_bill_paid_by(self.leader, statement=self.loose)
        response = self.answer_through_the_api(
            self.loose,
            {"kilometers": 250, "regime": "tourenleitung", "paid_to": self.leader.pk},
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.loose.refresh_from_db()
        self.assertEqual(self.loose.inputs["kilometers"], 250)
        self.assertEqual(self.paid(self.loose), Decimal("75.00"))

    def test_a_dry_run_cannot_put_its_own_figure_in_a_derived_answer(self):
        """``_answered`` resolves the source again, and that is the last word.

        A dry run hands ``evaluate_statement`` the answers to try, and
        ``build_context`` returns early for an override rather than typing the
        stored ones — so on *this* route nothing but ``_answered`` would resolve
        a derived question at all. The same is true of a case file and of the
        fuzzer: they build their own context and never go through
        ``build_context``.

        So the two resolutions are not one belt and one brace. They cover
        different routes, and this is the one that covers the routes the form
        does not. Neuter it — drop the ``engine_supplied`` branch of
        ``_answered`` — and the 9999 below is paid at 0.20 a kilometre: a dry
        run, a case or a fuzz round could each assert a figure production will
        never produce.
        """
        result = evaluate_statement(
            self.statement,
            ruleset=self.rules,
            inputs={
                "kilometers": 9999,
                "regime": "ehrenamt",
                "paid_to": RuleMember(self.leader.pk),
            },
        )
        self.assertEqual(result.errors, (), result.errors)
        self.assertEqual(result.total_of("travel"), Decimal("20.00"))

    def test_a_derived_answer_is_there_when_relevant_inputs_branches_on_it(self):
        """Why ``build_context`` resolves a derived answer as well as ``_answered``.

        ``relevant_inputs`` is given the context ``build_context`` built, and a
        ruleset may branch on an answer there — that is what the method is for.
        A derived answer has to be in that context, or a ruleset would see the
        figure the engine supplies everywhere except in the one method whose
        job is to decide what to ask about it.

        The ruleset below asks how many people shared the car only when the
        trip recorded any kilometres, and the statement carries a stored ``0``
        behind the form to make the two readings differ. Neuter
        :func:`finance.engine.answers.typed_inputs` so that the stored answer
        wins — or drop ``supplied`` from ``build_context`` altogether — and the
        question disappears from a form that should be asking it.
        """
        answer(self.statement, kilometers=0)
        self.rules = _AsksAboutTheJourney()
        keys = [entry["key"] for entry in self.form(self.statement)["inputs"]]
        self.assertIn("car_share", keys, "the trip drove 100 km, so the question applies")
        # And on a statement with no trip the stored answer is the figure, so
        # the same branch reads it and takes the question off the form.
        answer(self.loose, kilometers=0)
        self.assertNotIn("car_share", [entry["key"] for entry in self.form(self.loose)["inputs"]])

    def test_the_admin_is_not_offered_a_field_it_would_have_to_refuse(self):
        """A server-rendered form writes every field it renders.

        So :func:`finance.inputs.answerable` hands it the questions it can
        honour. Neuter it — return the declarations unfiltered — and the
        admin's excursion inline renders an editable kilometre field whose
        value it would then write to a key nothing reads.
        """
        from finance.inputs import answerable
        from finance.inputs import declarations

        with self.serving():
            self.assertEqual(
                [entry.key for entry in answerable(self.statement)],
                ["regime", "paid_to"],
            )
            self.assertIn("kilometers", [entry.key for entry in declarations(self.statement)])

    def _a_bill_paid_by(self, member, statement=None):
        return Bill.objects.create(
            statement=statement or self.statement,
            short_description="Tankfüllung",
            amount=Decimal("40.00"),
            costs_covered=False,
            paid_by=member,
        )


class ChoiceInputApiTestCase(DerivedFormTestCase):
    """``choice``, which was in the vocabulary and unusable (taxis #573)."""

    def test_a_choice_arrives_with_the_alternatives_it_declared(self):
        regime = self.declaration(self.form(self.statement), "regime")
        self.assertEqual(
            regime["choices"],
            [
                {"value": "ehrenamt", "label": "Ehrenamtspauschale"},
                {"value": "tourenleitung", "label": "Tourenleitung"},
            ],
        )

    def test_an_answer_outside_the_alternatives_is_refused(self):
        """What a ``choice`` was for, and what it did not do.

        ``Input.options`` could only carry members, so a ``choice`` reached the
        form with nothing to choose from and ``clean_value`` fell through to
        "anything else is text" — it accepted any string at all. Neuter it
        (drop the ``choice`` arm of :func:`finance.inputs.clean_value`) and
        ``"hausregel"`` is stored as the regime, and the rule that reads it
        pays at a rate of zero without anybody being told.
        """
        refused = self.answer_through_the_api(self.statement, {"regime": "hausregel"})
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertIn("regime", refused.json()["errors"])
        accepted = self.answer_through_the_api(self.statement, {"regime": "tourenleitung"})
        self.assertEqual(accepted.status_code, 200, accepted.content)
        self.statement.refresh_from_db()
        self.assertEqual(self.statement.inputs["regime"], "tourenleitung")

    def test_the_regime_decides_the_rate(self):
        """The reason the widget had to work: it picks between two rulebooks."""
        Bill.objects.create(
            statement=self.statement,
            short_description="Tankfüllung",
            amount=Decimal("40.00"),
            paid_by=self.leader,
        )
        for regime, expected in (("ehrenamt", "20.00"), ("tourenleitung", "30.00")):
            with self.subTest(regime=regime):
                response = self.answer_through_the_api(
                    self.statement, {"regime": regime, "paid_to": self.leader.pk}
                )
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(self.paid(self.statement), Decimal(expected))

    def test_a_choice_nobody_has_answered_yet_is_readable(self):
        """A half-finished form resolves, with nothing owed and no error.

        The *statement* route to an unanswered choice goes through
        ``coerce_input``, which makes an absent answer ``""`` on its way into
        the context — so the ``_EMPTY["choice"]`` that taxis #573 is about is
        not what this exercises, and neutering it leaves this green. The guard
        for that is
        ``finance.tests.engine.EvaluationTestCase``'s
        ``test_a_declared_question_nobody_answered_reads_as_empty``, where the
        context never mentions the key — which is the shape a case file and the
        fuzzer have. This is the end-to-end half: the form asks, nothing is
        owed, and nothing is wrong.
        """
        self.assertEqual(self.paid(self.statement), Decimal("0.00"))
        body = self.form(self.statement)
        self.assertIsNone(body["answers"]["regime"])


class OptionSourceApiTestCase(DerivedFormTestCase):
    """Where a party-valued question's people come from, said by the ruleset."""

    def test_a_statement_without_a_trip_can_still_pay_whoever_paid(self):
        """The gap: no excursion, so no leaders, so nobody to pay.

        ``options_source="bills.payers"`` is the ruleset saying where to look
        instead, and the engine serving it. Neuter
        :func:`finance.engine.declared.options_from` — return ``()`` — and the
        option list is empty and the ``PATCH`` below is refused, which is the
        state this exists to end.
        """
        self._a_receipt_paid_by(self.leader)
        body = self.form(self.loose)
        self.assertEqual(
            self.declaration(body, "paid_to")["options"],
            [{"id": self.leader.pk, "name": self.leader.name}],
        )
        response = self.answer_through_the_api(
            self.loose, {"paid_to": self.leader.pk, "kilometers": 10, "regime": "ehrenamt"}
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.paid(self.loose), Decimal("2.00"))

    def test_somebody_the_statement_mentions_otherwise_is_still_refused(self):
        """It is *this* source's set, not everybody the statement touches.

        The owner created this statement, so ``statement.creator`` would offer
        them — but the question asked for ``bills.payers`` and they paid
        nothing. Neuter ``options_from`` by resolving the wrong arm of its
        vocabulary (hand ``bills.payers`` the creator) and this 422 becomes a
        200: a question that says who paid, answered with somebody who did not.

        That the bound is a *vocabulary* and not a path is what makes the whole
        set of answers to this question enumerable; the fifth name in it is the
        widest, and it is still one person the statement names itself.
        """
        self._a_receipt_paid_by(self.leader)
        response = self.answer_through_the_api(self.loose, {"paid_to": self.owner.pk})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("paid_to", response.json()["errors"])
        self.assertEqual(self.loose.created_by, self.owner, "the statement does mention them")

    def _a_receipt_paid_by(self, member):
        return Bill.objects.create(
            statement=self.loose,
            short_description="Seil",
            amount=Decimal("90.00"),
            paid_by=member,
        )


class FormStepApiTestCase(DerivedFormTestCase):
    """The declarations, grouped the way the ruleset said they group."""

    def test_the_form_says_which_questions_belong_together_and_in_what_order(self):
        """A flat list is a long form, and nothing more can be made of it.

        Neuter :func:`finance.inputs.steps` — return ``[]`` — and a client is
        back to one list with no way to know that the regime question comes
        before the two about the journey.
        """
        body = self.form(self.statement)
        self.assertEqual(
            body["steps"],
            [
                {"label": "Grundlagen", "keys": ["regime"]},
                {"label": "Fahrt", "keys": ["kilometers", "paid_to"]},
            ],
        )
        # Every declaration carries its own label too, so a client that walks
        # `inputs` rather than `steps` is not told less.
        self.assertEqual(self.declaration(body, "kilometers")["step"], "Fahrt")

    def test_a_ruleset_that_named_no_steps_comes_back_as_one(self):
        """So a client renders ``steps`` unconditionally.

        Heidelberg names none, and the grouping is therefore the whole form
        under the empty label rather than nothing at all.
        """
        response = self.client.get(
            "/api/finance/statements/{}/form".format(self.statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            body["steps"],
            [{"label": "", "keys": [entry["key"] for entry in body["inputs"]]}],
        )


class NarrowedRules(TravelRules):
    """A ruleset that stops asking the regime once the journey is free.

    The shape taxis #579 is about, and the one the regime question makes real:
    ``relevant_inputs`` takes a question off the form while ``inputs`` goes on
    naming it. The question is whether the answer still reaches the rules.
    """

    def relevant_inputs(self, ctx: RuleContext) -> list[Input]:
        return [entry for entry in self.inputs(ctx) if entry.key != "regime"]


class NarrowedFormApiTestCase(DerivedFormTestCase):
    """taxis #579: the form and the rules ask one question, not two."""

    def setUp(self):
        super().setUp()
        self.rules = NarrowedRules()

    def test_a_question_off_the_form_reads_as_one_nobody_answered(self):
        """The stranded answer, and why it no longer moves money.

        Before, a ruleset narrowing only ``relevant_inputs`` reached a state
        with no way out through the API: the question was off the form, so
        nobody could change the answer; ``clean`` refused the key, so nobody
        could clear it; and ``build_context`` still asked ``inputs``, so the
        **stored answer still reached the rules** and still paid out. Now the
        rules read a question the form is not asking as unanswered — the regime
        below reads ``""``, the rate falls to nothing, and the payout is zero.

        Neuter it — ``_answered`` resolving every declaration in the vocabulary
        rather than only the ones being asked — and the ``20.00`` the narrowed
        regime would have paid comes back, from a value this API offers no way
        to see or to change.

        Note what is deliberately *not* asserted: an error. Reading a narrowed
        key is not a ruleset bug, so it does not collapse the evaluation — a
        traceback about a question nobody can see is the mistake
        ``_EMPTY["choice"]`` used to make.
        """
        answer(self.statement, regime="ehrenamt")
        Bill.objects.create(
            statement=self.statement,
            short_description="Tankfüllung",
            amount=Decimal("40.00"),
            paid_by=self.leader,
        )
        body = self.form(self.statement)
        self.assertNotIn("regime", [entry["key"] for entry in body["inputs"]])
        self.assertNotIn("regime", body["answers"])
        self.assertEqual(
            self.answer_through_the_api(self.statement, {"paid_to": self.leader.pk}).status_code,
            200,
        )
        self.assertEqual(
            self.paid(self.statement),
            Decimal("0.00"),
            "an answer nobody can see or change still moved money",
        )

    def test_a_narrowed_question_is_still_readable_and_not_an_error(self):
        """Declared is readable; asked is answered. Two different questions.

        The ruleset above goes on reading ``regime`` in ``transfers``, which it
        is entitled to do — it declared it. Neuter it the other way — have
        ``_answered`` range over the *asked* declarations alone — and reading it
        raises ``RuleError`` inside ``transfers``, which comes back as one
        error with a traceback instead of a statement that simply owes nothing.
        """
        answer(self.statement, regime="ehrenamt")
        result = evaluate_statement(Statement.objects.get(pk=self.statement.pk), ruleset=self.rules)
        self.assertEqual(result.errors, (), result.errors)
        self.assertEqual(result.total_of("travel"), Decimal("0.00"))

    def test_the_wider_question_is_still_the_right_one_for_pruning(self):
        """``party_keys`` asks ``inputs``, deliberately, and still should.

        What has to be cleaned of a deleted member is every key an answer can
        be *stored* under, which is the wider set: a key the rules are not
        currently reading can still hold an id, and
        ``Obligation.destination_member_id`` has a real foreign key behind it.
        The ruleset here narrows ``paid_to`` — the only party-valued question —
        off the form, so neutering :func:`finance.inputs.party_keys` to ask
        ``relevant_inputs`` makes this an empty set, and a deleted member's id
        would survive in a draft that still names them.
        """
        from finance.inputs import party_keys

        self.rules = _NoJourney()
        with self.serving():
            self.assertEqual(
                [entry["key"] for entry in self.form(self.statement)["inputs"]],
                ["regime"],
                "the form asks no party-valued question at all, which is the point",
            )
            self.assertEqual(party_keys(self.statement), {"paid_to"})

    def test_a_derived_question_narrowed_away_is_not_resolved_either(self):
        """Narrowing is narrowing, whoever answers the question.

        A derived declaration the ruleset stopped asking for is not resolved
        and not read, exactly like a stored one — otherwise ``relevant_inputs``
        would be authoritative for some answers and not others.
        """
        self.rules = _NoJourney()
        body = self.form(self.statement)
        self.assertEqual([entry["key"] for entry in body["inputs"]], ["regime"])
        self.assertNotIn("kilometers", body["answers"])
        result = evaluate_statement(Statement.objects.get(pk=self.statement.pk), ruleset=self.rules)
        self.assertEqual([entry.key for entry in result.declarations], ["regime"])


class _NoJourney(TravelRules):
    """Only the regime question survives, derived kilometres included."""

    def relevant_inputs(self, ctx: RuleContext) -> list[Input]:
        return [entry for entry in self.inputs(ctx) if entry.key == "regime"]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        return [], []


class DerivedMemberApiTestCase(DerivedFormTestCase):
    """A derived answer that is a *person*, and one that is money.

    Three of the shapes a context field can hold have to survive the trip out
    to a client as JSON: a person becomes an id, a set of people a list of ids,
    an amount a string. Nothing in tree exercises them otherwise, and a client
    reads a derived answer with the same code it reads a stored one — so if one
    came back as ``Member(id=3)`` the SPA would render it as nothing at all.
    """

    def setUp(self):
        super().setUp()
        self.rules = _DerivedShapes()

    def test_every_shape_a_derived_answer_can_have_comes_back_as_json(self):
        body = self.form(self.statement)
        answers = body["answers"]
        self.assertEqual(answers["creator"], self.owner.pk)
        self.assertEqual(answers["crew"], [self.leader.pk])
        self.assertEqual(answers["days"], str(Decimal(str(self.excursion.duration))))
        self.assertEqual(answers["how"], "car")

    def test_a_source_naming_a_structure_is_text_rather_than_a_crash(self):
        """A ruleset's mistake, on the one endpoint that could report it.

        ``source`` names a context *field*, and the engine does not police
        which fields hold a figure — ``excursion.participants`` holds a whole
        dataclass each. Serialising what is left as text keeps ``/form``
        answering, which is the only place a rule author would ever see what
        went wrong; a 500 there would take away the page that says so. Neuter
        :func:`finance.inputs._as_json` — drop its last line and hand the value
        back untouched — and this endpoint answers 500 instead.
        """
        self.rules = _DerivedStructure()
        NewMemberOnList.objects.create(member=self.owner, memberlist=self.excursion)
        served = self.form(self.statement)["answers"]["people"]
        self.assertTrue(served, "there are participants, so there is something to serialise")
        self.assertTrue(all(isinstance(entry, str) for entry in served), served)


class _AsksAboutTheJourney(TravelRules):
    """A ruleset whose ``relevant_inputs`` branches on a *derived* answer.

    The question about sharing the car is only worth asking if the trip drove
    anywhere, and how far it drove is the engine's answer rather than
    anybody's. So this reads a derived value in the one method that decides
    what to ask.
    """

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [
            *super().inputs(ctx),
            Input("car_share", "Wie viele im Auto?", "int", required=False, step="Fahrt"),
        ]

    def relevant_inputs(self, ctx: RuleContext) -> list[Input]:
        if ctx.inputs.number("kilometers") > 0:
            return self.inputs(ctx)
        return [entry for entry in self.inputs(ctx) if entry.key != "car_share"]


class _DerivedShapes(TravelRules):
    """Derived declarations of every shape a context field hands back."""

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [
            Input("creator", "Erstellt von", "member", required=False, source="statement.creator"),
            Input(
                "crew", "Jugendleitung", "member_set", required=False, source="excursion.leaders"
            ),
            Input("days", "Tage", "money", required=False, source="excursion.duration"),
            Input("how", "Anreise", "text", required=False, source="excursion.approach"),
        ]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        # Read through the accessors, so a shape that did not survive the
        # coercion is a `RuleError` here rather than a silent zero.
        self.read = (
            ctx.inputs.member("creator"),
            ctx.inputs.members("crew"),
            ctx.inputs.money("days"),
            ctx.inputs.text("how"),
        )
        return [], []


class _DerivedStructure(TravelRules):
    """A source that names a nested structure, which is a ruleset's mistake."""

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [
            Input("people", "Teilnehmende", "text", required=False, source="excursion.participants")
        ]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        return [], []


class DerivedMemberReadTestCase(DerivedFormTestCase):
    """What a rule gets for a derived person, as opposed to what a client gets."""

    def test_a_derived_person_reaches_the_rules_as_a_member(self):
        """``coerce_input`` is given a value that is already typed.

        A stored person is an id and becomes a :class:`kompass.rules.Member`; a
        derived one is already one, and has to stay one — otherwise a rule that
        reads it with :meth:`kompass.rules.Inputs.member` raises and the whole
        statement comes back as an error.
        """
        rules = _DerivedShapes()
        result = evaluate_statement(self.statement, ruleset=rules)
        self.assertEqual(result.errors, (), result.errors)
        self.assertEqual(
            rules.read,
            (
                RuleMember(self.owner.pk),
                (RuleMember(self.leader.pk),),
                Decimal(str(self.excursion.duration)),
                "car",
            ),
        )
