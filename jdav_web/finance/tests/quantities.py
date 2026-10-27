"""A quantity that is not money: the ``decimal`` input type.

Ludwigsburg declared the days a trip lasted as ``money``, because a trip can
last half a day and the vocabulary offered only ``int`` and ``money`` — so the
form and the signer read „5,00 €“ for five days. The fix is a type for what
the figure *is*, and the half of it that matters most is what it does **not**
inherit from money: the cent. ``0.125`` is an answer here and a refusal
there, and nothing on the way rounds it.
"""

import json
import pathlib
from decimal import Decimal
from random import Random

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase
from finance.engine.answers import EMPTY
from finance.engine.answers import typed_inputs
from finance.engine.answers import within
from finance.engine.fuzz import random_answer
from finance.engine.fuzz import random_context
from finance.engine.versions import check_directory
from finance.inputs import clean_value
from finance.inputs import DECIMAL_MAX
from finance.inputs import form_field
from finance.inputs import stored
from finance.rules_api import CELL_TYPES
from finance.rules_api import Field
from finance.rules_api import Input
from finance.rules_api import Inputs
from finance.rules_api import RuleError

DAYS = Input("duration", "Dauer in Tagen", "decimal")
AMOUNT = Input("night_cost", "Übernachtung", "money")


class DecimalAnswerTestCase(SimpleTestCase):
    """What a person may give as a ``decimal``, and what they get back."""

    def test_an_answer_keeps_every_place_it_was_given(self):
        for given, expected in (
            ("0.5", Decimal("0.5")),
            ("0.125", Decimal("0.125")),
            ("0.1255", Decimal("0.1255")),
            ("3", Decimal("3")),
            (2, Decimal("2")),
            (None, Decimal("0")),
        ):
            with self.subTest(given=given):
                cleaned = clean_value(DAYS, given)
                self.assertEqual(cleaned, expected)
                self.assertEqual(str(cleaned), str(expected), "and nothing rounded it")

    def test_the_cent_is_money_s_rule_and_not_this_one_s(self):
        """The same three answers, the opposite verdicts, which is the type's point."""
        self.assertEqual(clean_value(DAYS, "0.125"), Decimal("0.125"))
        self.assertEqual(clean_value(DAYS, "-1.5"), Decimal("-1.5"))
        with self.assertRaises(ValidationError):
            clean_value(AMOUNT, "0.125")
        with self.assertRaises(ValidationError):
            clean_value(AMOUNT, "-1.5")

    def test_a_value_that_is_not_a_number_is_refused_as_not_a_number(self):
        for given in ("viel", "NaN", "Infinity", "-inf"):
            with self.subTest(given=given), self.assertRaises(ValidationError) as refused:
                clean_value(DAYS, given)
            self.assertIn("Dauer in Tagen", refused.exception.messages[0])

    def test_a_value_past_its_resolution_or_its_ceiling_is_refused(self):
        for given in ("0.12345", str(DECIMAL_MAX + 1), str(-DECIMAL_MAX - 1), "1E+1000000"):
            with self.subTest(given=given), self.assertRaises(ValidationError):
                clean_value(DAYS, given)
        self.assertEqual(clean_value(DAYS, str(DECIMAL_MAX)), DECIMAL_MAX)
        self.assertEqual(clean_value(DAYS, str(-DECIMAL_MAX)), -DECIMAL_MAX)

    def test_it_is_stored_as_text_like_money(self):
        kept = stored({"duration": clean_value(DAYS, "0.125")})
        self.assertEqual(kept, {"duration": "0.125"})
        self.assertEqual(json.loads(json.dumps(kept)), kept)

    def test_a_cell_may_be_one(self):
        self.assertIn("decimal", CELL_TYPES)
        table = Input("reisen", "Fahrten", "rows", fields=(Field("km", "Kilometer", "decimal"),))
        self.assertEqual(clean_value(table, [{"km": "12.75"}]), [{"km": Decimal("12.75")}])

    def test_the_admin_widget_refuses_what_the_declaration_does(self):
        field = form_field(DAYS)
        self.assertIsInstance(field, forms.DecimalField)
        self.assertEqual(field.clean("-0.25"), Decimal("-0.25"), "no floor below zero")
        self.assertEqual(field.clean("0.1255"), Decimal("0.1255"))
        with self.assertRaises(ValidationError):
            field.clean("0.12345")


class DecimalReadingTestCase(SimpleTestCase):
    """What a rule reads, from a stored answer or none."""

    def test_a_stored_answer_reads_as_the_decimal_it_was(self):
        self.assertEqual(typed_inputs([DAYS], {"duration": "0.125"})["duration"], Decimal("0.125"))
        self.assertEqual(typed_inputs([DAYS], {"duration": 0.1})["duration"], Decimal("0.1"))

    def test_no_answer_reads_as_zero_and_not_as_a_cent(self):
        """Compared as text, because ``Decimal("0") == Decimal("0.00")``.

        Equal as numbers, which is exactly what made a cent here invisible to
        an assertion of equality: the two are different statements about the
        figure, and the string is the one that differs.
        """
        self.assertEqual(str(typed_inputs([DAYS], {})["duration"]), "0")
        # And the empty value the evaluation reads a dropped answer as.
        self.assertEqual(str(EMPTY["decimal"]), "0")
        self.assertEqual(str(EMPTY["money"]), "0.00")

    def test_its_own_accessor_reads_it_and_no_other(self):
        inputs = Inputs({"duration": Decimal("0.5"), "nights": 2})
        self.assertEqual(inputs.decimal("duration"), Decimal("0.5"))
        with self.assertRaises(RuleError):
            inputs.decimal("nights")

    def test_it_has_no_domain_to_fall_out_of(self):
        self.assertTrue(within(DAYS, Decimal("-3.1415")))

    def test_the_fuzzer_reaches_past_the_cent_and_below_zero(self):
        """Inside the domain, which includes both — so a rule meets them there."""
        rng = Random(11)
        drawn = [random_answer(rng, DAYS) for _ in range(200)]
        self.assertTrue(all(isinstance(value, Decimal) for value in drawn))
        self.assertTrue(all(clean_value(DAYS, value) == value for value in drawn))
        self.assertTrue(any(-value.as_tuple().exponent > 2 for value in drawn if value))
        self.assertTrue(any(value < 0 for value in drawn))


class LudwigsburgDurationTestCase(SimpleTestCase):
    """The declaration this was measured on."""

    def test_the_days_a_trip_lasted_are_a_decimal(self):
        directory = pathlib.Path(settings.BASE_DIR).parent / "deploy" / "ludwigsburg" / "rules"
        loaded, problems = check_directory(directory)
        self.assertEqual(problems, [])
        declared = {
            declaration.key: declaration.type
            for declaration in loaded.inputs(random_context(Random(1), {}))
        }
        self.assertEqual(declared["duration"], "decimal")
        self.assertNotIn("money", declared.values(), "nothing else there is an amount either")
