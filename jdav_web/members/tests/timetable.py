import datetime
from types import SimpleNamespace

from django.test import TestCase
from members.timetable import _wrap_text
from members.timetable import build_svg_data


def _make_group(name, weekday, start_h, start_m, end_h, end_m, pk=1):
    return SimpleNamespace(
        name=name,
        weekday=weekday,
        start_time=datetime.time(start_h, start_m),
        end_time=datetime.time(end_h, end_m),
        pk=pk,
    )


class WrapTextTestCase(TestCase):
    def test_wraps_long_line(self):
        # covers: first word (if not current), word fits (elif), word doesn't fit (else)
        self.assertEqual(_wrap_text("hello world extra", 12), ["hello world", "extra"])

    def test_empty_string(self):
        # covers: return lines or [""]
        self.assertEqual(_wrap_text("", 10), [""])


class BuildSvgDataTestCase(TestCase):
    def test_empty_returns_none(self):
        self.assertIsNone(build_svg_data([]))

    def test_with_groups(self):
        groups = [
            # Two overlapping Monday groups → second opens a new lane (placed=False branch)
            _make_group("Jugend", 0, 17, 0, 19, 0, pk=1),
            _make_group("Bambinis", 0, 17, 30, 18, 30, pk=2),
            # Non-overlapping with Bambinis → fits back in an existing lane (placed=True branch)
            _make_group("Teens", 0, 19, 0, 20, 0, pk=3),
            # Very short group → max(24, ...) branch
            _make_group("Kurz", 1, 10, 0, 10, 15, pk=4),
            # Early start → min_time < 9:00
            _make_group("Early", 2, 7, 0, 8, 30, pk=5),
            # Late end → max_time > 21:00
            _make_group("Late", 3, 21, 0, 22, 0, pk=6),
            # Saturday → weekend day included in visible_days
            _make_group("Samstag", 5, 10, 0, 12, 0, pk=7),
            # Long name in narrow two-lane column → _wrap_text wrapping branch
            _make_group("A Very Long Group Name Here", 0, 20, 0, 21, 0, pk=8),
        ]

        data = build_svg_data(groups)

        self.assertIsNotNone(data)
        # Mon–Fri always shown plus Sat (has groups); Sun absent
        self.assertEqual(len(data["days"]), 6)
        # min_time extended to 7:00 → first tick y == header_h + time_padding
        self.assertEqual(data["time_ticks"][0]["y"], 40 + 10)
        # max_time extended to 22:00 → height larger than default 9–21 range
        default_height = 40 + 10 + (21 - 9) * 60 + 10
        self.assertGreater(data["height"], default_height)
