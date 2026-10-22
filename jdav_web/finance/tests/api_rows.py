"""A repeating-row input: the declaration, the cells, the seed, the error keys.

One statement settles a trip several people went on, and they travelled
differently. ``rows`` is the declaration that can say so, and everything in this
module is a claim about one of its four halves:

* the **declaration** refuses what the engine cannot serve
  (:class:`RowDeclarationTestCase`),
* a **cell** is validated by its own type, by the same code the question of that
  type goes through (:class:`RowCellTestCase`, :class:`RowPatchTestCase`),
* a **seed** prefills one row, once, and the person's edit survives
  (:class:`RowSeedTestCase`),
* and a refusal about a cell lands **on that cell**
  (:class:`RowErrorKeyTestCase`).

Read :mod:`finance.tests.harness` before adding to this module, and keep its
recipe: every test below names the line whose absence it detects. The seed is
the sharpest case and the reason the recipe matters here. A test asserting only
that a seeded row *appears* passes just as well against a version that re-seeds
on every context build — which would silently throw away every edit the person
makes. So the tests that matter assert the **edit**, not the row.

The admin's inline is tested here too rather than beside the rest of
``members.admin``, because what it exercises is this feature's own contract: the
one client that has nowhere to put a per-cell error, and what
:func:`finance.inputs.flat_messages` does about it.
"""

import datetime
import json
import uuid
from contextlib import contextmanager
from contextlib import ExitStack
from dataclasses import replace
from decimal import Decimal
from random import Random
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils import timezone
from finance.api.tests import AccessToken
from finance.api.tests import Application
from finance.api.tests import grant
from finance.api.tests import make_member_user
from finance.engine import evaluate
from finance.engine import evaluate_statement
from finance.engine import seeds
from finance.engine import typed_inputs
from finance.engine.cases import parse_case
from finance.engine.cases import run_case
from finance.engine.fuzz import fuzz
from finance.engine.fuzz import random_answer
from finance.engine.fuzz import random_context
from finance.inputs import cell_key
from finance.inputs import clean_value
from finance.inputs import flat_messages
from finance.inputs import form_field
from finance.inputs import party_answers
from finance.inputs import row_key
from finance.models import Bill
from finance.models import Statement
from finance.rules_api import Bill as RuleBill
from finance.rules_api import CELL_TYPES
from finance.rules_api import Choice
from finance.rules_api import Excursion
from finance.rules_api import Field
from finance.rules_api import Input
from finance.rules_api import Inputs
from finance.rules_api import Member as RuleMember
from finance.rules_api import MemberId
from finance.rules_api import Params
from finance.rules_api import PARTICIPANTS
from finance.rules_api import Roles
from finance.rules_api import Row
from finance.rules_api import RuleContext
from finance.rules_api import RuleError
from finance.rules_api import Ruleset
from finance.rules_api import SECTION
from finance.rules_api import StatementInfo
from finance.rules_api import Transfer
from finance.signals import forget_member
from finance.testing import answer
from members.admin import statement_answer_form
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList

#: How a journey was made, in the section's own vocabulary rather than Kompass's.
#:
#: Deliberately *not* the three words :data:`~kompass.rules.TourApproach` uses,
#: except for ``car``: a section names its own alternatives, and a seed off
#: ``excursion.approach`` is therefore a suggestion that may not fit — which is
#: a state ``test_a_seeded_value_the_cell_does_not_offer_is_left_empty`` is
#: about.
APPROACHES = (
    Choice("car", "Privatauto"),
    Choice("public", "Bahn oder ÖPNV"),
    Choice("bike", "Fahrrad"),
)

#: What a kilometre in a private car is worth, and what each passenger adds.
RATE = Decimal("0.30")
PER_PASSENGER = Decimal("0.02")


def travel_rows() -> Input:
    """The declaration this whole module is about, as a section would write it."""
    return Input(
        "reisen",
        "Fahrten",
        "rows",
        required=False,
        step="Fahrt",
        max=3,
        options_source="bills.payers",
        fields=(
            Field("member", "Person", "member"),
            Field(
                "approach",
                "Verkehrsmittel",
                "choice",
                choices=APPROACHES,
                seed="excursion.approach",
            ),
            Field("kilometers", "Kilometer", "int", max=2000, seed="excursion.kilometers"),
            Field("passengers", "Mitfahrende", "int", required=False, max=4),
        ),
    )


class JourneyRules(Ruleset):
    """Ludwigsburg's ordinary case: one statement, several people, three ways there.

    Which is the whole argument for a row rather than a map from person to
    number: whether somebody is owed anything per kilometre depends on *their*
    mode of travel — a private car yes, the train no, because there the receipt
    is the claim — so the mode and the distance decide each other and belong to
    the same traveller in the same place.
    """

    name = "journeys"
    context_version = 1
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [travel_rows()]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        transfers: list[Transfer] = []
        for journey in ctx.inputs.rows("reisen"):
            driver = journey.member("member")
            if driver is None or journey.text("approach") != "car":
                continue
            rate = RATE + PER_PASSENGER * journey.number("passengers")
            amount = (journey.number("kilometers") * rate).quantize(Decimal("0.01"))
            if not amount:
                continue
            transfers.append(
                Transfer(SECTION, driver, amount, "travel", rule_id="travel", label="Fahrtkosten")
            )
        return transfers, []


def offering(*ids: int) -> Input:
    """:func:`travel_rows` with its people already resolved, as the engine serves it.

    ``options_source`` is a *request*, and the engine's answer is ``options``
    (:func:`finance.engine.declared._served`), so a declaration handed straight
    to :func:`~finance.inputs.clean_value` offers nobody. The classes that go
    through the API get the resolved one for free; the ones that call the
    validation directly resolve it here.
    """
    return replace(
        travel_rows(),
        options=tuple(RuleMember(MemberId(pk)) for pk in ids),
        options_source="",
    )


def trip(**changed: object) -> Excursion:
    """A trip of 120 km by car, with whatever one test wants different."""
    fields: dict[str, object] = {
        "duration": Decimal("1.0"),
        "nights": 0,
        "kilometers": 120,
        "approach": "car",
        "leaders": (),
        "staff_count": 0,
        "approved_staff_count": 0,
        "participants": (),
        "ljp": None,
    }
    fields.update(changed)
    return Excursion(**fields)  # type: ignore[arg-type]


def context(
    excursion: Excursion | None = None, payers: tuple[int, ...] = (), **answers: object
) -> RuleContext:
    """A context with ``answers`` typed by :func:`travel_rows`'s declaration.

    ``payers`` are the receipts, which is how the table comes to offer anybody:
    its ``options_source`` is ``bills.payers``. A context with none offers
    nobody, which is a state worth having on purpose — but a test about
    something *other* than the domain has to hand over a receipt, or the domain
    check answers first and the test passes for the wrong reason.
    """
    bills = tuple(
        RuleBill(
            id=index + 1,
            amount=Decimal("40.00"),
            covered=False,
            payer=RuleMember(MemberId(pk)),
            has_proof=True,
            description="Tankfüllung",
        )
        for index, pk in enumerate(payers)
    )
    return RuleContext(
        version=1,
        params=Params({}),
        inputs=Inputs(typed_inputs([travel_rows()], answers)),
        bills=bills,
        excursion=excursion,
        statement=StatementInfo(id=1, creator=None, submitter=None),
        roles=Roles({}),
        permissions={},
    )


class RowDeclarationTestCase(SimpleTestCase):
    """What a ``rows`` declaration may and may not say.

    Every refusal here is refused *where it is written*, which is the point: a
    declaration the engine cannot serve should fail the section's own CI rather
    than reach somebody's form as a question with nothing behind it.
    """

    def test_a_table_with_no_fields_is_refused(self):
        """Neuter it — drop the ``not self.fields`` arm — and the question
        reaches the form as a table with no columns, which stores an empty
        object per row and reads every cell as a ``RuleError``."""
        with self.assertRaises(RuleError) as refusal:
            Input("reisen", "Fahrten", "rows")
        self.assertIn("declares no fields", str(refusal.exception))

    def test_fields_on_anything_but_a_table_are_refused(self):
        with self.assertRaises(RuleError) as refusal:
            Input("km", "Kilometer", "int", fields=(Field("a", "A", "int"),))
        self.assertIn("so it has no rows", str(refusal.exception))

    def test_there_is_no_table_inside_a_table(self):
        with self.assertRaises(RuleError) as refusal:
            Field("inner", "Innen", "rows")
        self.assertIn("no table inside a table", str(refusal.exception))
        self.assertNotIn("rows", CELL_TYPES)

    def test_one_field_key_per_row(self):
        """A row keeps one value per field, so a repeat would shadow the first."""
        with self.assertRaises(RuleError) as refusal:
            Input(
                "reisen",
                "Fahrten",
                "rows",
                fields=(Field("km", "Kilometer", "int"), Field("km", "Nochmal", "int")),
            )
        self.assertIn("twice", str(refusal.exception))

    def test_a_table_is_not_derived_from_a_source(self):
        """The refusal that keeps ``seed`` and ``source`` from being one word.

        A table is not one figure, so there is nothing for a ``source`` to
        supply — and a supplied answer is refused on the form, which is the
        opposite of what a prefilled row is for.
        """
        with self.assertRaises(RuleError) as refusal:
            Input(
                "reisen",
                "Fahrten",
                "rows",
                source="excursion.kilometers",
                fields=(Field("km", "Kilometer", "int"),),
            )
        self.assertIn("`seed`", str(refusal.exception))

    def test_a_table_with_a_person_in_it_may_name_an_option_source(self):
        """And one without a person in it may not, with the message it deserves.

        Neuter it — put the old ``self.type not in _PARTY_INPUT_TYPES`` back —
        and the first half is refused: a table of journeys could not say where
        the people who made them come from, which is the whole declaration.
        """
        self.assertEqual(travel_rows().options_source, "bills.payers")
        self.assertTrue(travel_rows().names_people())
        with self.assertRaises(RuleError) as refusal:
            Input(
                "zeiten",
                "Zeiten",
                "rows",
                options_source="bills.payers",
                fields=(Field("stunden", "Stunden", "int"),),
            )
        self.assertIn("names no people", str(refusal.exception))

    def test_a_cell_is_refused_for_what_a_question_of_its_type_is_refused_for(self):
        """One validation path, asked of a cell: ``Field`` builds the ``Input``.

        Neuter it — drop the ``self.as_input()`` from
        :meth:`~kompass.rules.Field.__post_init__` — and a ``choice`` column
        with nothing to choose from reaches the form, where it validates
        nothing and accepts any string at all. Which is taxis #573 again, one
        level in.
        """
        with self.assertRaises(RuleError) as refusal:
            Field("approach", "Verkehrsmittel", "choice")
        self.assertIn("offers no choices", str(refusal.exception))

    def test_a_seed_names_a_field_the_context_really_has(self):
        with self.assertRaises(RuleError) as refusal:
            Field("km", "Kilometer", "int", seed="excursion.gefahrene_kilometer")
        self.assertIn("excursion has no field", str(refusal.exception))


class RowCellTestCase(SimpleTestCase):
    """Reading a table, and what happens to a cell that no longer fits."""

    def test_a_rule_reads_rows_as_typed_cells(self):
        rows = Inputs(
            typed_inputs(
                [travel_rows()],
                {
                    "reisen": [
                        {"member": 7, "approach": "car", "kilometers": 120, "passengers": 2},
                        {"member": 8, "approach": "public", "kilometers": 120},
                    ]
                },
            )
        ).rows("reisen")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].member("member"), RuleMember(MemberId(7)))
        self.assertEqual(rows[0].text("approach"), "car")
        self.assertEqual(rows[0].number("kilometers"), 120)
        self.assertEqual(rows[0].number("passengers"), 2)
        self.assertEqual(rows[1].text("approach"), "public")
        self.assertIn("reisen", repr(rows[1]))

    def test_a_cell_nobody_filled_in_reads_as_its_type_s_empty_value(self):
        """Every declared field is in the row whether the row answered it or not.

        Neuter it — build the row from ``row`` rather than from the
        declaration's fields in :func:`finance.engine.answers._fitted_row` — and
        a rule reading ``passengers`` on a row that left it out gets a
        ``RuleError`` instead of ``0``, which collapses the whole evaluation
        over a column somebody simply did not need.
        """
        rows = Inputs(typed_inputs([travel_rows()], {"reisen": [{"member": 7}]})).rows("reisen")
        self.assertEqual(rows[0].number("passengers"), 0)
        self.assertEqual(rows[0].text("approach"), "")
        self.assertEqual(rows[0].number("kilometers"), 0)

    def test_an_undeclared_cell_raises_and_says_which_fields_there_are(self):
        rows = Inputs(typed_inputs([travel_rows()], {"reisen": [{"member": 7}]})).rows("reisen")
        with self.assertRaises(RuleError) as refusal:
            rows[0].raw("fahrzeug")
        self.assertIn("undeclared field 'fahrzeug'", str(refusal.exception))
        self.assertIn("kilometers", str(refusal.exception))

    def test_an_empty_table_and_an_unanswered_one_read_the_same(self):
        """Both ``()``, which is the whole of what an empty table means."""
        for stored in ([], None):
            with self.subTest(stored=stored):
                self.assertEqual(
                    Inputs(typed_inputs([travel_rows()], {"reisen": stored})).rows("reisen"), ()
                )
        self.assertEqual(Inputs(typed_inputs([travel_rows()], {})).rows("reisen"), ())

    def test_max_bounds_the_number_of_rows_and_not_what_is_in_one(self):
        """The qualification :attr:`~kompass.rules.Input.max` needed twice.

        Three rows is the question's bound; 2000 kilometres is the cell's. A
        version that read the question's ``max`` as a cell ceiling would refuse
        a 120 km journey in a table of at most three, and one that read the
        cell's as a row count would allow five journeys.
        """
        declaration = offering(7)
        self.assertEqual(declaration.max, 3)
        kilometers = next(cell for cell in declaration.fields if cell.key == "kilometers")
        self.assertEqual(kilometers.max, 2000)
        three = [{"member": 7, "kilometers": 1999}] * 3
        self.assertEqual(len(clean_value(declaration, three)), 3)
        with self.assertRaises(ValidationError) as refusal:
            clean_value(declaration, three + [{"member": 7}])
        self.assertEqual(list(refusal.exception.message_dict), ["reisen"])
        with self.assertRaises(ValidationError) as refusal:
            clean_value(declaration, [{"member": 7, "kilometers": 2001}])
        self.assertEqual(list(refusal.exception.message_dict), ["reisen[0].kilometers"])

    def test_a_table_whose_cell_falls_out_of_its_domain_is_dropped_whole(self):
        """And reported, which is the half that cannot be left out.

        The shape every dropped answer has to have: nothing paid **and**
        somebody told. Here the domain shrinks without anybody editing the
        statement — the receipt whose payer the table offered is cleared — so
        the stored row names a person the rules no longer offer. Neuter it —
        drop the ``rows`` arm of :func:`finance.engine.answers.within` — and the
        statement pays the journey to somebody the declaration does not offer,
        which is the one mistake in this area that costs money.
        """
        rules = JourneyRules()
        # Nobody paid a receipt, so `bills.payers` offers nobody at all.
        result = evaluate(rules, context(trip(), reisen=[{"member": 7, "kilometers": 100}]))
        self.assertFalse(result.ok)
        self.assertTrue(any("reisen" in error for error in result.errors), result.errors)
        self.assertEqual(result.total_of("travel"), Decimal("0.00"))

    def test_a_stored_table_over_a_bound_the_section_has_since_lowered_is_dropped(self):
        """``max`` is re-checked on the way **out**, not only on the way in.

        A bound shrinks without anybody editing the statement: the section
        lowers how many journeys one abrechnung may carry, and a table stored
        under the old bound is then over it. Neuter it — drop the ``max`` arm of
        :func:`finance.engine.answers.within`'s ``rows`` branch — and the
        statement goes on paying four journeys against a rule that allows three,
        which is a figure no page explains.
        """
        four = [{"member": 7, "approach": "car", "kilometers": 10}] * 4
        # Member 7 paid a receipt, so the *domain* is satisfied and the only
        # thing left to drop the table is the bound — without which this passes
        # for the wrong reason, which is how it first did.
        result = evaluate(JourneyRules(), context(trip(), payers=(7,), reisen=four))
        self.assertFalse(result.ok)
        self.assertTrue(any("reisen" in error for error in result.errors), result.errors)
        self.assertEqual(result.total_of("travel"), Decimal("0.00"))

    def test_a_table_whose_type_no_longer_fits_stays_loud(self):
        """A section retyped the key; the rule's own accessor says so.

        Not read as empty: that is the retyped-key reading, and it is
        deliberately the opposite of the withdrawn-option one. Neuter it —
        return ``()`` from :func:`finance.engine.answers._fitted` for a value
        that is not a list — and a statement whose stored answer is a leftover
        text reads as "no journeys" with no error, which is a zero nobody can
        account for.
        """
        result = evaluate(JourneyRules(), context(trip(), reisen="120 km"))
        self.assertFalse(result.ok)
        self.assertIn("not a table of rows", result.errors[0])

    def test_a_row_that_is_not_a_set_of_answers_is_handed_through_untouched(self):
        self.assertEqual(typed_inputs([travel_rows()], {"reisen": ["nope"]})["reisen"], ["nope"])

    def test_money_in_a_cell_is_a_decimal_both_ways(self):
        """A cent in a cell behaves like a cent in an answer: text in storage.

        Neuter it — make :func:`finance.inputs.stored` stringify only the top
        level — and the ``Decimal`` reaches ``json.dumps``, which raises on
        every save of a table with a money column.
        """
        from finance.inputs import stored

        declaration = Input(
            "belege",
            "Belege",
            "rows",
            fields=(Field("betrag", "Betrag", "money"),),
        )
        cleaned = clean_value(declaration, [{"betrag": "12.30"}])
        self.assertEqual(cleaned, [{"betrag": Decimal("12.30")}])
        kept = stored({"belege": cleaned})
        self.assertEqual(kept, {"belege": [{"betrag": "12.30"}]})
        self.assertEqual(json.loads(json.dumps(kept)), kept)
        rows = Inputs(typed_inputs([declaration], kept)).rows("belege")
        self.assertEqual(rows[0].money("betrag"), Decimal("12.30"))

    def test_a_duplicate_member_across_rows_is_accepted(self):
        """Decided, not overlooked — see :func:`finance.inputs._clean_rows`.

        The engine cannot tell a there-and-back entered in two halves from the
        same journey typed twice, and nothing in the declaration says which
        field identifies a row. So both rows stand and both are paid, and a
        section that means one row per person says so in a ``Check``, where the
        sentence is its own. This test exists so that the behaviour is a
        decision with a reason rather than something a later change can quietly
        flip either way.
        """
        rows = clean_value(
            offering(7),
            [
                {"member": 7, "approach": "car", "kilometers": 60},
                {"member": 7, "approach": "car", "kilometers": 60},
            ],
        )
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["member"] for row in rows], [7, 7])

    def test_a_required_cell_left_empty_is_stored_rather_than_refused(self):
        """``required`` is advisory on a cell, exactly as it is on a question.

        A form is filled in gradually. What refuses to hand the statement in is
        the section's own ``checks``, where "Für jede Fahrt braucht es ein
        Verkehrsmittel" is in the section's words.
        """
        self.assertTrue(
            next(cell for cell in travel_rows().fields if cell.key == "approach").required
        )
        rows = clean_value(offering(7), [{"member": 7, "kilometers": 60}])
        self.assertEqual(rows, [{"member": 7, "approach": "", "kilometers": 60, "passengers": 0}])

    def test_a_rows_answer_that_is_not_a_list_is_refused_by_the_question(self):
        with self.assertRaises(ValidationError) as refusal:
            clean_value(offering(7), "eine Fahrt")
        self.assertEqual(list(refusal.exception.message_dict), ["reisen"])
        self.assertEqual(clean_value(offering(7), None), [])

    def test_a_row_that_is_not_an_object_is_keyed_to_that_row(self):
        with self.assertRaises(ValidationError) as refusal:
            clean_value(offering(7), [{"member": 7}, "nope"])
        self.assertEqual(list(refusal.exception.message_dict), ["reisen[1]"])


class RowSeedResolutionTestCase(SimpleTestCase):
    """:func:`finance.engine.declared.seeds` — what one trip prefills."""

    def test_a_trip_seeds_exactly_one_row(self):
        self.assertEqual(
            seeds([travel_rows()], context(trip())),
            {"reisen": ({"approach": "car", "kilometers": 120},)},
        )

    def test_no_trip_seeds_no_row_at_all(self):
        """Not a row of blank cells, which is a row nobody asked for.

        Neuter it — return ``(row,)`` unconditionally — and a statement that
        settles a purchase opens with an empty journey in its table that
        somebody then has to delete.
        """
        self.assertEqual(seeds([travel_rows()], context(None)), {"reisen": ()})

    def test_a_seeded_value_the_cell_does_not_offer_is_left_empty(self):
        """``excursion.approach`` is Kompass's word; the ``choice`` is the section's.

        Neuter it — drop the ``within`` check in
        :func:`finance.engine.declared.seeds` — and ``"muscle"`` is written into
        a column that offers ``car``, ``public`` and ``bike``. Which the rules
        then drop and report, so the statement a person has just created does
        not resolve and the only way out is to notice and re-answer a question
        nobody touched.
        """
        self.assertEqual(
            seeds([travel_rows()], context(trip(approach="muscle"))),
            {"reisen": ({"kilometers": 120},)},
        )

    def test_a_trip_at_the_model_s_default_of_zero_kilometres_is_seeded_with_zero(self):
        """``Excursion.kilometers`` cannot say "not recorded", so neither can this.

        The column is a non-nullable ``IntegerField(default=0)``: "nobody
        recorded it" and "nobody drove" are the same value there. A ``source``
        has to serve that zero and then refuse a correction; a seed hands over
        the zero *and the pencil*, so the person fixes it in the row. Which is
        why seeding what the trip records is right here for the reason supplying
        it is awkward there.
        """
        self.assertEqual(
            seeds([travel_rows()], context(trip(kilometers=0))),
            {"reisen": ({"approach": "car", "kilometers": 0},)},
        )

    def test_a_table_with_no_seeded_field_is_not_seeded(self):
        """So changing the excursion leaves it alone rather than emptying it."""
        unseeded = Input("zeiten", "Zeiten", "rows", fields=(Field("stunden", "Stunden", "int"),))
        self.assertEqual(seeds([unseeded], context(trip())), {})
        self.assertEqual(seeds([Input("km", "Kilometer", "int")], context(trip())), {})


class RowCaseAndFuzzTestCase(SimpleTestCase):
    """A worked case and a random statement, both of which have to reach a table.

    Worked cases gate activation — a version whose cases fail is stored as a
    draft and never applied — so a type a case cannot express is a type a
    section cannot ship. That is why this is a test and not a remark.
    """

    def test_a_case_file_can_answer_a_table(self):
        case = parse_case(
            {
                "name": "three people, three ways there",
                "inputs": {
                    "reisen": [
                        {"member": 7, "approach": "car", "kilometers": 100, "passengers": 2},
                        {"member": 8, "approach": "public", "kilometers": 100},
                    ]
                },
                "bills": [{"amount": "31.40", "payer": 7}, {"amount": "9.90", "payer": 8}],
                "expect": {
                    "transfers": [
                        ["SECTION", "7", "34.00", "travel"],
                        ["PARTICIPANTS", "SECTION", "34.00", "participant_contribution"],
                    ]
                },
            },
            name="rows",
        )
        self.assertEqual(run_case(JourneyRules(), case), [])

    def test_a_case_whose_table_names_somebody_the_rules_do_not_offer_fails(self):
        """The option source is resolved for a case too, so the case can be wrong.

        Member 9 paid no receipt, so ``bills.payers`` does not offer them and
        the table is dropped and reported — which is a *failing* case rather
        than a quiet zero, and therefore a version that is never activated.
        """
        case = parse_case(
            {
                "name": "a driver who paid nothing",
                "inputs": {"reisen": [{"member": 9, "approach": "car", "kilometers": 100}]},
                "bills": [{"amount": "31.40", "payer": 7}],
                "expect": {"transfers": []},
            },
            name="rows",
        )
        self.assertNotEqual(run_case(JourneyRules(), case), [])

    def test_the_fuzzer_answers_a_table_inside_its_own_domains(self):
        """Both halves: rows do get built, and every cell is inside its domain.

        The second half alone is vacuous — a fuzzer that answered every table
        with ``()`` would satisfy every assertion in the loop and exercise
        nothing, which is what it did when this test was first written. So the
        counts are asserted too: some round fills a table, some round leaves it
        empty, and no round goes over the bound.
        """
        rng = Random(5)
        declaration = offering(1, 2)
        sizes = set()
        for _round in range(20):
            rows = random_answer(rng, declaration)
            sizes.add(len(rows))
            self.assertLessEqual(len(rows), 3)
            for row in rows:
                self.assertIsInstance(row, Row)
                self.assertIn(row.raw("member"), (*declaration.options, None))
                self.assertIn(row.text("approach"), ("", "car", "public", "bike"))
                self.assertLessEqual(row.number("kilometers"), 2000)
                self.assertLessEqual(row.number("passengers"), 4)
        self.assertTrue(sizes - {0}, "no round ever filled a row")
        self.assertIn(0, sizes, "no round ever left the table empty")

    def test_a_random_statement_sometimes_settles_no_trip_at_all(self):
        """The arm nothing random ever reached, which a ``rows`` input needs.

        A table seeded off the excursion arrives *empty* on a statement with no
        trip, so the rules' behaviour on an empty table is the behaviour a real
        purchase statement gets. Neuter it — make ``random_context`` always
        build an excursion again — and this goes red, and with it every round
        that would have exercised a ruleset's "and when there is no trip" arm.
        """
        built = [random_context(Random(seed), {}) for seed in range(40)]
        with_trip = [ctx for ctx in built if ctx.excursion is not None]
        without = [ctx for ctx in built if ctx.excursion is None]
        self.assertTrue(with_trip, "no round built a trip")
        self.assertTrue(without, "no round left the trip out")
        for ctx in built:
            self.assertTrue(all(bill.payer is not None for bill in ctx.bills))
            self.assertIsNotNone(ctx.statement.creator)

    def test_a_ruleset_with_a_table_survives_two_hundred_random_statements(self):
        self.assertEqual(fuzz(JourneyRules(), 200, seed=1), [])


class RowFormTestCase(TestCase):
    """The fixture the API classes share: a trip, a receipt, a statement, a token."""

    def setUp(self):
        self.application = Application.objects.create(
            name="test-client-rows",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("rowner")
        self.owner_user = grant(
            self.owner_user,
            "add_global_statement",
            "view_global_statement",
            "change_global_statement",
        )
        self.driver_user, self.driver = make_member_user("rdriver")
        self.rider_user, self.rider = make_member_user("rrider")
        self.excursion = Freizeit.objects.create(
            name="Fahrt zu dreien",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=FAHRGEMEINSCHAFT_ANREISE,
            difficulty=1,
        )
        for member in (self.driver, self.rider):
            self.excursion.jugendleiter.add(member)
            NewMemberOnList.objects.create(member=member, memberlist=self.excursion)
        self.other = Freizeit.objects.create(
            name="Andere Fahrt",
            kilometers_traveled=40,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.other.jugendleiter.add(self.driver)
        NewMemberOnList.objects.create(member=self.driver, memberlist=self.other)
        self.rules = JourneyRules()

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
        """Serve ``self.rules`` everywhere a statement's ruleset is resolved."""
        with ExitStack() as stack:
            for where in ("finance.inputs", "finance.engine.statements"):
                stack.enter_context(patch(f"{where}.ruleset_for", return_value=self.rules))
            yield

    def a_statement(self, excursion=None, with_a_receipt=True):
        """A draft created through the API, so that a seed applies if one does."""
        with self.serving():
            response = self.client.post(
                "/api/finance/statements",
                data={
                    "short_description": "Fahrtkosten",
                    "excursion_id": None if excursion is None else excursion.pk,
                },
                content_type="application/json",
                **self.auth(self.owner_user),
            )
        self.assertEqual(response.status_code, 200, response.content)
        statement = Statement.objects.get(pk=response.json()["id"])
        if with_a_receipt:
            for member in (self.driver, self.rider):
                Bill.objects.create(
                    statement=statement,
                    short_description="Tankfüllung",
                    amount=Decimal("40.00"),
                    costs_covered=False,
                    paid_by=member,
                )
        return statement

    def form(self, statement):
        with self.serving():
            response = self.client.get(
                "/api/finance/statements/{}/form".format(statement.pk),
                **self.auth(self.owner_user),
            )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def patch(self, statement, **payload):
        with self.serving():
            return self.client.patch(
                "/api/finance/statements/{}".format(statement.pk),
                data=payload,
                content_type="application/json",
                **self.auth(self.owner_user),
            )

    def declaration(self, body, key="reisen"):
        return next(entry for entry in body["inputs"] if entry["key"] == key)

    def rows_of(self, statement):
        statement.refresh_from_db()
        return statement.answers.get("reisen")

    def paid(self, statement):
        result = evaluate_statement(Statement.objects.get(pk=statement.pk), ruleset=self.rules)
        self.assertEqual(result.errors, (), result.errors)
        return result.total_of("travel")


class RowPatchTestCase(RowFormTestCase):
    """What ``GET …/form`` serves for a table and what ``PATCH`` accepts."""

    def test_the_form_serves_the_columns_and_the_table_s_own_people(self):
        """``fields`` is the grid; ``options`` is stated once for the table.

        Neuter it — drop ``fields`` from :func:`finance.inputs._declaration` —
        and a client is served a question of a type it has never heard of with
        nothing to render, which is the state before this change.
        """
        declaration = self.declaration(self.form(self.a_statement(self.excursion)))
        self.assertEqual(declaration["type"], "rows")
        self.assertEqual(declaration["max"], 3)
        self.assertEqual(
            [(cell["key"], cell["type"]) for cell in declaration["fields"]],
            [
                ("member", "member"),
                ("approach", "choice"),
                ("kilometers", "int"),
                ("passengers", "int"),
            ],
        )
        approach = next(cell for cell in declaration["fields"] if cell["key"] == "approach")
        self.assertEqual(
            [choice["value"] for choice in approach["choices"]], ["car", "public", "bike"]
        )
        kilometers = next(cell for cell in declaration["fields"] if cell["key"] == "kilometers")
        self.assertEqual(kilometers["max"], 2000)
        # The people are the question's, once, out of `bills.payers`.
        self.assertEqual(
            sorted(option["id"] for option in declaration["options"]),
            sorted([self.driver.pk, self.rider.pk]),
        )
        self.assertEqual([cell.get("options") for cell in declaration["fields"]], [None] * 4)

    def test_a_table_round_trips_and_moves_money_per_row(self):
        statement = self.a_statement(self.excursion)
        response = self.patch(
            statement,
            inputs={
                "reisen": [
                    {
                        "member": self.driver.pk,
                        "approach": "car",
                        "kilometers": 120,
                        "passengers": 1,
                    },
                    {"member": self.rider.pk, "approach": "public", "kilometers": 120},
                ]
            },
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.rows_of(statement),
            [
                {"member": self.driver.pk, "approach": "car", "kilometers": 120, "passengers": 1},
                {"member": self.rider.pk, "approach": "public", "kilometers": 120, "passengers": 0},
            ],
        )
        # 120 km at 0.30 plus 0.02 for the one passenger: the car only.
        self.assertEqual(self.paid(statement), Decimal("38.40"))
        self.assertEqual(self.form(statement)["answers"]["reisen"], self.rows_of(statement))

    def test_a_journey_of_no_kilometres_is_no_line_in_the_books(self):
        """A person can always type a zero, and a zero is worth no transfer.

        Not merely worth ``0.00``: a transfer of nothing is a row in the books
        and a line on every readout that explains where the money went, about a
        journey that moved none. Neuter it — drop the ``if not amount`` in
        :class:`JourneyRules` — and the assertion on the categories goes red
        while a total of ``0.00`` would not have noticed.
        """
        statement = self.a_statement(self.excursion)
        response = self.patch(
            statement,
            inputs={"reisen": [{"member": self.driver.pk, "approach": "car", "kilometers": 0}]},
        )
        self.assertEqual(response.status_code, 200, response.content)
        result = evaluate_statement(Statement.objects.get(pk=statement.pk), ruleset=self.rules)
        self.assertEqual(result.errors, ())
        self.assertEqual(
            [transfer.category for transfer in result.transfers], ["participant_contribution"]
        )

    def test_an_empty_table_is_an_answer_and_not_a_refusal(self):
        """Including the delete that empties it, which is what makes a seed safe.

        Neuter the ``if value is None: return []`` or add a "a table needs a
        row" refusal to :func:`finance.inputs._clean_rows`, and a person who
        drove nowhere cannot save their statement at all.
        """
        statement = self.a_statement(self.excursion)
        self.assertEqual(self.patch(statement, inputs={"reisen": []}).status_code, 200)
        self.assertEqual(self.rows_of(statement), [])
        self.assertEqual(self.paid(statement), Decimal("0.00"))

    def test_a_person_the_table_does_not_offer_is_refused(self):
        """The domain is the question's, and it bounds every row.

        Neuter it — hand ``()`` instead of ``declaration.options`` to the cells
        in :func:`finance.inputs._clean_rows` — and this still refuses, which is
        why the assertion is the other way round as well: the *driver*, who did
        pay a receipt, has to be accepted.
        """
        statement = self.a_statement(self.excursion)
        stranger = self.patch(
            statement, inputs={"reisen": [{"member": self.owner.pk, "kilometers": 10}]}
        )
        self.assertEqual(stranger.status_code, 422, stranger.content)
        self.assertEqual(list(stranger.json()["errors"]), [cell_key("reisen", 0, "member")])
        # Nothing written: the seeded row the statement opened with is still
        # the only thing in the column.
        self.assertEqual(self.rows_of(statement), [{"approach": "car", "kilometers": 120}])
        offered = self.patch(
            statement, inputs={"reisen": [{"member": self.driver.pk, "kilometers": 10}]}
        )
        self.assertEqual(offered.status_code, 200, offered.content)

    def test_nothing_is_written_when_one_cell_is_refused(self):
        """Everything is checked before anything is written, tables included."""
        statement = self.a_statement(self.excursion)
        answer(statement, reisen=[{"member": self.driver.pk, "kilometers": 5}])
        response = self.patch(
            statement,
            inputs={
                "reisen": [
                    {"member": self.driver.pk, "kilometers": 99},
                    {"member": self.driver.pk, "kilometers": 9999},
                ]
            },
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(self.rows_of(statement), [{"member": self.driver.pk, "kilometers": 5}])


class RowErrorKeyTestCase(RowFormTestCase):
    """The error contract: where a refusal about one cell lands.

    This is the part of the feature that is hard to change later, because an
    error key is what a client renders against. The grammar is
    :func:`finance.inputs.row_key`'s, and these are the tests that pin it.
    """

    def test_a_refusal_about_a_cell_is_keyed_to_that_cell(self):
        """Neuter it — re-key a table's refusal by the question in
        :func:`finance.inputs.clean`, as every other type's is — and the message
        about one person's kilometres arrives under the whole table, which tells
        somebody with three journeys in front of them only that one of them is
        wrong. The payload is a 422 either way, which is exactly why this needs
        a test of its own."""
        statement = self.a_statement(self.excursion)
        response = self.patch(
            statement,
            inputs={
                "reisen": [
                    {"member": self.driver.pk, "approach": "car", "kilometers": 120},
                    {"member": self.rider.pk, "approach": "car", "kilometers": "weit"},
                ]
            },
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(list(response.json()["errors"]), ["reisen[1].kilometers"])
        self.assertEqual(cell_key("reisen", 1, "kilometers"), "reisen[1].kilometers")

    def test_every_cell_a_table_got_wrong_is_reported_at_once(self):
        """A table is one answer, so correcting it should take one round trip.

        Neuter it — raise inside the loop in
        :func:`finance.inputs._clean_rows` rather than collecting — and a person
        with three wrong cells needs three requests to find out.
        """
        statement = self.a_statement(self.excursion)
        response = self.patch(
            statement,
            inputs={
                "reisen": [
                    {"member": self.driver.pk, "approach": "flugzeug", "kilometers": "weit"},
                    {"member": self.owner.pk, "approach": "car", "kilometers": 10},
                ]
            },
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            sorted(response.json()["errors"]),
            ["reisen[0].approach", "reisen[0].kilometers", "reisen[1].member"],
        )

    def test_a_refusal_about_the_table_itself_is_keyed_to_the_table(self):
        statement = self.a_statement(self.excursion)
        response = self.patch(statement, inputs={"reisen": [{"member": self.driver.pk}] * 4})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(list(response.json()["errors"]), ["reisen"])
        self.assertEqual(row_key("reisen", 0), "reisen[0]")

    def test_a_row_answering_a_column_that_does_not_exist_is_keyed_to_the_row(self):
        statement = self.a_statement(self.excursion)
        response = self.patch(
            statement, inputs={"reisen": [{"member": self.driver.pk, "fahrzeug": "Bus"}]}
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(list(response.json()["errors"]), ["reisen[0]"])
        self.assertIn("fahrzeug", response.json()["errors"]["reisen[0]"][0])

    def test_a_question_that_is_not_a_table_still_keys_by_its_own_key(self):
        """Nothing that reads ``errors`` today has to change to keep working."""
        statement = self.a_statement(self.excursion)
        response = self.patch(statement, inputs={"nonsense": 1})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(list(response.json()["errors"]), ["__all__"])


class RowSeedTestCase(RowFormTestCase):
    """The seed: once, when the excursion is set, and the person's from then on.

    Every test in this class exists because the obvious implementations are
    wrong in ways a happy-path test cannot see. "Re-seed on every build" serves
    a correct-looking first row and discards every edit; "seed when the table is
    empty" brings back a row somebody deliberately deleted. So what is asserted
    here is the **edit** and the **deletion**, not the row.
    """

    def test_a_statement_created_on_a_trip_starts_with_one_row(self):
        statement = self.a_statement(self.excursion)
        self.assertEqual(self.rows_of(statement), [{"approach": "car", "kilometers": 120}])
        self.assertEqual(self.form(statement)["answers"]["reisen"], self.rows_of(statement))

    def test_a_statement_created_without_a_trip_starts_with_an_empty_table(self):
        statement = self.a_statement(None)
        self.assertEqual(self.rows_of(statement), [])

    def test_an_edited_seed_row_survives_every_later_read(self):
        """**The** test for this feature, and the one the brief asks for by name.

        A test that asserted only that a seeded row appears would pass against a
        version that re-seeds on every context build — and that version silently
        throws away the split the person just entered, which is the worst
        outcome available here. So this edits the row, reads the statement back
        three ways, and asserts the *edit*.

        Neuter it — call :func:`finance.inputs.seeded` from
        :func:`finance.inputs.form` (or from
        :func:`finance.engine.context.build_context`), so the table is re-seeded
        whenever anything looks at it — and this goes red on the first
        assertion: the two rows the person entered are back to one, at the
        trip's own 120 km, and nothing anywhere says so.
        """
        statement = self.a_statement(self.excursion)
        split = [
            {"member": self.driver.pk, "approach": "car", "kilometers": 240, "passengers": 1},
            {"member": self.rider.pk, "approach": "public", "kilometers": 120, "passengers": 0},
        ]
        self.assertEqual(self.patch(statement, inputs={"reisen": split}).status_code, 200)
        self.assertEqual(self.rows_of(statement), split)
        self.assertEqual(self.form(statement)["answers"]["reisen"], split)
        # And an unrelated edit does not bring the seed back either.
        self.assertEqual(self.patch(statement, explanation="Nachtrag").status_code, 200)
        self.assertEqual(self.rows_of(statement), split)
        self.assertEqual(self.paid(statement), Decimal("76.80"))

    def test_a_deleted_row_stays_deleted(self):
        """Not "seed whenever the table is empty", which is the other wrong fix.

        Nobody drove, so the person clears the table. Neuter it — seed when the
        stored table is empty rather than when the excursion is set — and the
        row comes back on the next read, with no way for the person to say no.
        """
        statement = self.a_statement(self.excursion)
        self.assertEqual(self.patch(statement, inputs={"reisen": []}).status_code, 200)
        self.assertEqual(self.rows_of(statement), [])
        self.assertEqual(self.form(statement)["answers"]["reisen"], [])
        self.assertEqual(self.patch(statement, explanation="Nichts gefahren").status_code, 200)
        self.assertEqual(self.rows_of(statement), [])

    def test_changing_the_excursion_re_seeds_the_table(self):
        """The old row described a different trip — its distance, its mode.

        The same reasoning an excursion swap already drops every answer naming a
        person by: those people led the *other* trip. Neuter it — drop the
        ``seeded_rows`` call from the ``excursion_changed`` arm of
        ``update_statement`` — and a statement moved from a 120 km car trip to a
        40 km walk keeps claiming 120 km by car.
        """
        statement = self.a_statement(self.excursion)
        self.assertEqual(self.rows_of(statement), [{"approach": "car", "kilometers": 120}])
        response = self.patch(statement, excursion_id=self.other.pk)
        self.assertEqual(response.status_code, 200, response.content)
        # The other trip is on muscle power, which this section's `choice` does
        # not offer — so that cell seeds empty and the distance is the new one.
        self.assertEqual(self.rows_of(statement), [{"kilometers": 40}])

    def test_clearing_the_excursion_empties_the_table(self):
        statement = self.a_statement(self.excursion)
        self.assertEqual(self.patch(statement, excursion_id=None).status_code, 200)
        self.assertEqual(self.rows_of(statement), [])

    def test_a_table_restated_in_the_same_request_wins_over_the_re_seed(self):
        """So correcting the excursion and the journeys together is one call.

        Neuter it — apply the seed *after* the cleaned answers in
        ``update_statement`` — and a client that sends both gets its table
        overwritten by the seed and no indication that it happened.
        """
        statement = self.a_statement(self.excursion)
        mine = [{"member": self.driver.pk, "approach": "bike", "kilometers": 15}]
        response = self.patch(statement, excursion_id=self.other.pk, inputs={"reisen": mine})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            self.rows_of(statement),
            [{"member": self.driver.pk, "approach": "bike", "kilometers": 15, "passengers": 0}],
        )

    def test_the_seed_is_resolved_against_the_incoming_trip_and_not_the_outgoing_one(self):
        """``update_statement`` assigns the excursion before anything else runs.

        Which it already did for the declarations' sake; this pins that the seed
        is on the same side of that line. Neuter it — move the assignment after
        the re-seed — and the table is prefilled from the trip the statement is
        leaving.
        """
        statement = self.a_statement(self.other)
        self.assertEqual(self.rows_of(statement), [{"kilometers": 40}])
        self.assertEqual(self.patch(statement, excursion_id=self.excursion.pk).status_code, 200)
        self.assertEqual(self.rows_of(statement), [{"approach": "car", "kilometers": 120}])


class RowDeletedMemberTestCase(RowFormTestCase):
    """A deleted member, out of the cell that named them.

    The four columns did this for free — ``SET_NULL`` and a cascading m2m — and
    JSON does not. One level further in, an id inside a row is exactly the
    dangling ``destination_member_id`` :mod:`finance.signals` exists to prevent.
    """

    def test_the_fields_that_name_people_are_reported_with_the_key(self):
        statement = self.a_statement(self.excursion)
        with self.serving():
            self.assertEqual(party_answers(statement), {"reisen": frozenset({"member"})})

    def test_a_deleted_member_is_cleared_from_the_cell_and_the_row_stays(self):
        """Neuter it — report only the key from
        :func:`finance.inputs.party_answers`, as the old ``party_keys`` did, or
        drop the ``if cells`` arm of :func:`finance.signals.forget_member` — and
        the id stays in the row. On MariaDB the next ``Bill.save()`` and the next
        ``POST …/submit`` are then both 500s, because that foreign key has a
        real constraint behind it.

        The row is **kept** with the cell empty rather than dropped: dropping
        would throw away a journey somebody entered, in a draft, with nothing to
        put it back.
        """
        statement = self.a_statement(self.excursion)
        self.assertEqual(
            self.patch(
                statement,
                inputs={
                    "reisen": [
                        {"member": self.driver.pk, "approach": "car", "kilometers": 120},
                        {"member": self.rider.pk, "approach": "bike", "kilometers": 12},
                    ]
                },
            ).status_code,
            200,
        )
        gone = self.driver.pk
        with self.serving():
            self.driver.delete()
        self.assertEqual(
            self.rows_of(statement),
            [
                {"member": None, "approach": "car", "kilometers": 120, "passengers": 0},
                {
                    "member": self.rider.pk,
                    "approach": "bike",
                    "kilometers": 12,
                    "passengers": 0,
                },
            ],
        )
        self.assertNotIn(gone, [row["member"] for row in self.rows_of(statement)])

    def test_a_cell_that_merely_equals_an_id_is_left_alone(self):
        """Only the fields that name people, never every cell.

        A count of kilometres can equal a member's id, and clearing it would be
        the pruner inventing a figure. Neuter it — prune every cell of a row
        rather than the party-valued ones — and this goes red on the distance.
        """
        statement = self.a_statement(self.excursion)
        answer(
            statement,
            reisen=[{"member": self.rider.pk, "approach": "car", "kilometers": self.driver.pk}],
        )
        # Nothing changed, so nothing was written: the only cell that names
        # people holds somebody else.
        with self.serving():
            self.assertEqual(forget_member(self.driver.pk), [])
        self.assertEqual(
            self.rows_of(statement),
            [{"member": self.rider.pk, "approach": "car", "kilometers": self.driver.pk}],
        )

    def test_a_statement_that_mentions_nobody_inside_a_row_is_not_touched(self):
        statement = self.a_statement(self.excursion)
        answer(statement, reisen=[{"member": self.rider.pk, "kilometers": 1}])
        with self.serving():
            self.assertEqual(forget_member(self.owner.pk), [])


class RowPrunerShapeTestCase(TestCase):
    """The pruner, asked about a stored table that is not the shape it expects.

    :func:`finance.signals.forget_member` runs inside a member deletion's own
    transaction, so anything it raises rolls that deletion back and makes the
    member undeletable. A stored answer it cannot read is therefore handed back
    untouched rather than reasoned about: the id is left in a *draft*, which the
    readouts drop and nothing has frozen, and that is the harmless half.
    """

    def setUp(self):
        self.ghost_user, self.ghost = make_member_user("pruneghost")
        self.rules = _PrunerRules()

    @contextmanager
    def serving(self):
        with patch("finance.inputs.ruleset_for", return_value=self.rules):
            yield

    def stored(self, value):
        statement = Statement.objects.create(short_description="Zu putzen")
        answer(statement, reisen=value)
        return statement

    def test_a_table_stored_as_something_else_is_handed_back_untouched(self):
        statement = self.stored(self.ghost.pk)
        with self.serving():
            self.assertEqual(forget_member(self.ghost.pk), [])
        statement.refresh_from_db()
        self.assertEqual(statement.inputs["reisen"], self.ghost.pk)

    def test_a_row_stored_as_something_else_is_handed_back_untouched(self):
        statement = self.stored([self.ghost.pk, {"member": self.ghost.pk}])
        with self.serving():
            self.assertEqual(forget_member(self.ghost.pk), [statement.pk])
        statement.refresh_from_db()
        self.assertEqual(statement.inputs["reisen"], [self.ghost.pk, {"member": None}])

    def test_a_set_of_people_in_a_cell_loses_the_one_that_is_gone(self):
        """A ``member_set`` cell: the same filter, one level further in.

        Neuter it — treat every cell as a single id — and the deleted member
        stays inside the list, which is the dangling id this exists to remove.
        """
        statement = self.stored([{"mitfahrende": [self.ghost.pk, 999], "member": 999}])
        with self.serving():
            self.assertEqual(forget_member(self.ghost.pk), [statement.pk])
        statement.refresh_from_db()
        self.assertEqual(statement.inputs["reisen"], [{"mitfahrende": [999], "member": 999}])


class _PrunerRules(JourneyRules):
    """A table with both kinds of party-valued cell, for the pruner's sake.

    Only the declaration is ever asked for: :func:`finance.signals.forget_member`
    reads :func:`finance.inputs.party_answers`, and nothing evaluates this. So it
    inherits its ``transfers`` rather than stating a stub of its own, which was a
    statement no test could reach.
    """

    name = "pruner"

    def inputs(self, ctx: RuleContext) -> list[Input]:
        return [
            Input(
                "reisen",
                "Fahrten",
                "rows",
                required=False,
                fields=(
                    Field("member", "Person", "member"),
                    Field("mitfahrende", "Mitfahrende", "member_set"),
                ),
            )
        ]


class RowAdminFormTestCase(TestCase):
    """The admin's excursion inline, which has one field per question.

    Tested here rather than beside the rest of ``members.admin`` because what it
    exercises is this feature's own contract: the one client with nowhere to put
    a per-cell error, and what :func:`finance.inputs.flat_messages` does about
    it.
    """

    def setUp(self):
        self.owner_user, self.owner = make_member_user("aowner")
        self.driver_user, self.driver = make_member_user("adriver")
        self.excursion = Freizeit.objects.create(
            name="Fahrt im Admin",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=FAHRGEMEINSCHAFT_ANREISE,
            difficulty=1,
        )
        self.excursion.jugendleiter.add(self.driver)
        NewMemberOnList.objects.create(member=self.driver, memberlist=self.excursion)
        self.rules = JourneyRules()

    @contextmanager
    def serving(self):
        with patch("finance.inputs.ruleset_for", return_value=self.rules):
            yield

    def a_statement(self):
        """A saved statement with a receipt, so ``bills.payers`` offers the driver."""
        statement = Statement.objects.create(short_description="Im Admin", excursion=self.excursion)
        Bill.objects.create(
            statement=statement,
            short_description="Tankfüllung",
            amount=Decimal("40.00"),
            costs_covered=False,
            paid_by=self.driver,
        )
        return statement

    def form(self, statement, **kwargs):
        with self.serving():
            return statement_answer_form(statement)(
                parent_obj=self.excursion, instance=statement, **kwargs
            )

    def test_a_table_is_a_json_field_and_not_a_text_input(self):
        """Neuter it — let ``rows`` fall through to ``forms.CharField`` in
        :func:`finance.inputs.form_field` — and the admin stores the table as
        the string ``"[{'member': 3}]"``, which ``clean_value`` then refuses on
        every save of that excursion."""
        from django import forms

        self.assertIsInstance(form_field(travel_rows()), forms.JSONField)

    def test_opening_a_statement_on_a_trip_seeds_the_table_in_the_admin(self):
        """The same moment as through the API: the excursion being assigned.

        Neuter it — drop the ``seeded_rows`` call from
        ``StatementOnListForm.__init__`` — and the admin's inline opens a
        statement on a trip with an empty table while the API's opens one with a
        row, which is two answers to one question.
        """
        # The inline's own ``extra = 1`` form: an unsaved statement with no
        # excursion yet, and the trip as ``parent_obj``. The formset assigns the
        # excursion on save; the form needs it now, to know whom the rules offer
        # — and that assignment is the moment a seed applies.
        with self.serving():
            form = statement_answer_form(Statement(excursion=self.excursion))(
                parent_obj=self.excursion, instance=Statement()
            )
        self.assertEqual(form.initial["reisen"], [{"approach": "car", "kilometers": 120}])

    def test_a_cell_refusal_reaches_the_one_field_with_its_path_in_the_message(self):
        """Less than the SPA gets, and stated as less — but not dropped.

        ``add_error`` refuses a keyed ``ValidationError`` against a named field
        outright, so without :func:`finance.inputs.flat_messages` this is a
        ``ValueError`` out of the admin rather than a form error. Neuter it —
        pass the ``ValidationError`` straight through — and saving the inline
        with a bad cell is a 500.
        """
        statement = self.a_statement()
        form = self.form(
            statement,
            data={"reisen": json.dumps([{"member": self.driver.pk, "kilometers": 9999}])},
        )
        self.assertFalse(form.is_valid())
        self.assertIn("reisen[0].kilometers", " ".join(form.errors["reisen"]))

    def test_a_table_the_admin_accepts_is_stored_like_any_other_answer(self):
        statement = self.a_statement()
        form = self.form(
            statement,
            data={
                "reisen": json.dumps(
                    [{"member": self.driver.pk, "approach": "car", "kilometers": 120}]
                )
            },
        )
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        statement.refresh_from_db()
        self.assertEqual(
            statement.inputs["reisen"],
            [{"member": self.driver.pk, "approach": "car", "kilometers": 120, "passengers": 0}],
        )

    def test_flat_messages_leaves_an_unkeyed_refusal_alone(self):
        self.assertEqual(flat_messages(ValidationError("Nur ein Satz.")), ["Nur ein Satz."])
        self.assertEqual(
            flat_messages(ValidationError({"reisen[0].kilometers": ["Keine Zahl."]})),
            ["reisen[0].kilometers: Keine Zahl."],
        )
