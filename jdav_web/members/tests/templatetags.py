from datetime import date
from datetime import datetime

from django.test import TestCase
from members.templatetags.overview_extras import blToColor
from members.templatetags.overview_extras import render_bool
from members.templatetags.tex_extras import add
from members.templatetags.tex_extras import date_short
from members.templatetags.tex_extras import date_vs
from members.templatetags.tex_extras import datetime_short
from members.templatetags.tex_extras import index
from members.templatetags.tex_extras import plus
from members.templatetags.tex_extras import time_short


class TexExtrasTestCase(TestCase):
    def setUp(self):
        self.test_date = date(2024, 3, 15)
        self.test_datetime = datetime(2024, 3, 15, 14, 30)
        self.test_list = ["a", "b", "c"]

    def test_index_valid_position(self):
        result = index(self.test_list, 1)
        self.assertEqual(result, "b")

    def test_index_invalid_position(self):
        result = index(self.test_list, 5)
        self.assertEqual(result, "")

    def test_index_type_error(self):
        result = index(123, 1)
        self.assertEqual(result, "")

    def test_datetime_short(self):
        result = datetime_short(self.test_datetime)
        self.assertEqual(result, "15.03.2024 14:30")

    def test_date_short(self):
        result = date_short(self.test_date)
        self.assertEqual(result, "15.03.24")

    def test_date_vs(self):
        result = date_vs(self.test_date)
        self.assertEqual(result, "15.03.")

    def test_time_short(self):
        result = time_short(self.test_datetime)
        self.assertEqual(result, "14:30")

    def test_add_with_days(self):
        result = add(self.test_date, 5)
        self.assertEqual(result, date(2024, 3, 20))

    def test_add_without_days(self):
        result = add(self.test_date, None)
        self.assertEqual(result, self.test_date)

    def test_plus_with_second_number(self):
        result = plus(10, 5)
        self.assertEqual(result, 15)

    def test_plus_without_second_number(self):
        result = plus(10, None)
        self.assertEqual(result, 10)


class OverviewExtrasTestCase(TestCase):
    def test_blToColor_truthy_value(self):
        result = blToColor(True)
        self.assertEqual(result, "green")

    def test_blToColor_falsy_value(self):
        result = blToColor(False)
        self.assertEqual(result, "red")

    def test_render_bool_non_boolean_value(self):
        with self.assertRaises(ValueError):
            render_bool("not_a_boolean")

    def test_render_bool_true(self):
        result = render_bool(True)
        self.assertIn("#bcd386", result)
        self.assertIn("icon-tick", result)

    def test_render_bool_false(self):
        result = render_bool(False)
        self.assertIn("#dba4a4", result)
        self.assertIn("icon-cross", result)
