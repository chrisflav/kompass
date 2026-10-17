"""The store: versions, bindings, materialised rows, and what verifies them.

What these pin, in the order the refactor's proposal argues for them:

* a stored version is **immutable** — the fields that say what the rules are
  cannot change, and a correction is a new row,
* a statement is bound to a version **when it is created**, which is the second
  of the two bugs §1 of the proposal named, and the numbers it was created
  under follow it through a settings change and through submission,
* the resolved transfers are **rows**, written on every draft save, frozen when
  the statement is handed in, and never written at all while the rules report a
  problem,
* and ``verify`` notices when any of that stops being true.
"""

import os
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from random import Random
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.test import override_settings
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils import timezone
from django.utils.translation import gettext as _
from finance.engine import active_ruleset
from finance.engine import cents_of
from finance.engine import check_directory
from finance.engine import configured_directory
from finance.engine import engine_version
from finance.engine import import_from_directory
from finance.engine import materialise
from finance.engine import read_sources
from finance.engine import reference_directory
from finance.engine import result_from_rows
from finance.engine import ruleset_directory
from finance.engine import ruleset_for
from finance.engine import statement_context
from finance.engine import statement_params
from finance.engine import verify
from finance.engine.fuzz import check_and_fuzz
from finance.engine.fuzz import fuzz
from finance.engine.fuzz import random_answer
from finance.engine.fuzz import random_context
from finance.engine.statements import bind
from finance.engine.statements import UNRESOLVED
from finance.engine.versions import activate
from finance.engine.versions import active_version
from finance.engine.versions import decimal_params
from finance.engine.versions import declared_valid_from
from finance.engine.versions import parameters_from_settings
from finance.engine.versions import params_fingerprint
from finance.engine.versions import version_hash
from finance.models import Bill
from finance.models import Statement
from finance.models import Transaction
from finance.rules_api import Input
from finance.rules_api import Member as RuleMember
from finance.rules_api import MemberId
from finance.rules_api import PARTICIPANTS
from finance.rules_api import RuleError
from finance.rules_api import SECTION
from finance.rules_api import Transfer
from finance.rulesets.heidelberg import HeidelbergRules
from finance.store import ApprovalConstraint
from finance.store import ImmutableRuleSet
from finance.store import Obligation
from finance.store import RoleAssignment
from finance.store import RuleSet
from finance.tests.harness import guard_lifted
from members.models import MALE
from members.models import Member

#: A ruleset that is stored but cannot be loaded, for the fallbacks.
BROKEN_SOURCES = {"__init__.py": "ruleset = 'not a ruleset at all'\n"}

#: A stored closure that is not *refused* but simply will not run: a section's
#: own exception in the module body, which is ordinary Python and may be
#: anything. Nothing about it is refusable — the whitelist passes it, and it
#: never gets far enough to be asked for a ``ruleset``.
ANGRY_SOURCES = {"__init__.py": "raise ValueError('kaputt')\n"}

#: The realistic way the same thing happens: an old snapshot meeting a
#: ``kompass.rules`` that has moved on, which is the case
#: :func:`~finance.engine.statements.active_ruleset` names — "a Kompass
#: upgrade that makes an old snapshot unloadable".
RENAMED_API_SOURCES = {"__init__.py": "from kompass.rules import Gone\n"}

#: A ruleset that queries from a field the **import** reads rather than from a
#: rule the engine calls. ``name`` and ``valid_from`` are attribute lookups on
#: the loaded object, which is why they were written as data; a ``property``
#: makes reading one a call into the section's own code. It reaches the
#: database through a caller's frame and the backend's own cursor factory, so
#: that no name in it is on the import whitelist and no ``CursorWrapper`` is
#: involved. ``FIELD`` is the field to declare that way and ``VALUE`` what it
#: answers once it is allowed to.
QUERYING_FIELD = (
    "from kompass.rules import Ruleset, SECTION, PARTICIPANTS\n"
    "\n"
    "\n"
    "class Nosy(Ruleset):\n"
    "    name = 'nosy'\n"
    "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
    "\n"
    "    @property\n"
    "    def FIELD(self):\n"
    "        try:\n"
    "            raise ValueError()\n"
    "        except ValueError as problem:\n"
    "            real = problem.__traceback__.tb_frame.f_back.f_builtins\n"
    "        db = real['__import__']('django.db', {}, {}, ['connections'])\n"
    "        cursor = db.connections['default'].create_cursor()\n"
    "        cursor.execute('SELECT 1')\n"
    "        return VALUE\n"
    "\n"
    "    def inputs(self, ctx):\n"
    "        return []\n"
    "\n"
    "    def transfers(self, ctx):\n"
    "        return [], []\n"
    "\n"
    "\n"
    "ruleset = Nosy()\n"
)


def querying_field(field, value):
    """:data:`QUERYING_FIELD` with its field and its answer filled in."""
    return QUERYING_FIELD.replace("FIELD", field).replace("VALUE", repr(value))


#: A ruleset that says when its rules were in force from, which is the
#: declaration a section backdates or stages a change with — and the only
#: authority for either, because it is reviewed and committed in the
#: configuration repository rather than typed at a command line.
DATED = """
from kompass.rules import Ruleset, SECTION, PARTICIPANTS


class Dated(Ruleset):
    name = "NAME"
    valid_from = "WHEN"
    balance = (PARTICIPANTS, SECTION, "rest")

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        return [], []


ruleset = Dated()
"""


def dated(name, when):
    """:data:`DATED` as a version called ``name``, valid from ``when``."""
    return DATED.replace("NAME", name).replace("WHEN", when)


def a_member(name="Rolle"):
    return Member.objects.create(prename=name, lastname="Test", email="r@localhost", gender=MALE)


def a_version(**overrides):
    """A stored version, by hand, for the cases an import cannot produce."""
    values = {
        "name": "fixture",
        "hash": "f" * 64,
        "manifest": {},
        "sources": BROKEN_SOURCES,
        "params": {"ALLOWANCE_PER_DAY": "22"},
        "state": RuleSet.ACTIVE,
        "valid_from": timezone.now(),
        "activated_at": timezone.now(),
        "context_version": 1,
    }
    values.update(overrides)
    return RuleSet.objects.create(**values)


class RuleSetModelTestCase(TestCase):
    def test_a_stored_version_cannot_be_changed(self):
        row = a_version()
        row.params = {"ALLOWANCE_PER_DAY": "99"}
        with self.assertRaises(ImmutableRuleSet) as caught:
            row.save()
        self.assertIn("params", str(caught.exception))
        # The lifecycle is not the rules, and does move.
        row.refresh_from_db()
        row.retire()
        row.refresh_from_db()
        self.assertEqual(row.state, RuleSet.RETIRED)
        self.assertIsNotNone(row.valid_to)

    def test_what_is_in_force_now(self):
        RuleSet.objects.all().delete()
        self.assertIsNone(RuleSet.objects.active())
        yesterday = timezone.now() - timezone.timedelta(days=1)
        old = a_version(hash="a" * 64, valid_from=yesterday, valid_to=timezone.now())
        self.assertIsNone(RuleSet.objects.active())
        current = a_version(hash="b" * 64, valid_from=yesterday)
        self.assertEqual(RuleSet.objects.active(), current)
        tomorrow = timezone.now() + timezone.timedelta(days=1)
        a_version(hash="c" * 64, valid_from=tomorrow)
        self.assertEqual(RuleSet.objects.active(), current, "a staged version is not in force yet")
        self.assertEqual(
            RuleSet.objects.active(when=tomorrow + timezone.timedelta(hours=1)).hash, "c" * 64
        )
        self.assertEqual(old.state, RuleSet.ACTIVE)
        self.assertEqual(str(current), f"fixture@{'b' * 12}")

    def test_a_version_carries_everything_a_statement_needs(self):
        row = a_version()
        snapshot = row.snapshot()
        self.assertEqual(snapshot["hash"], row.hash)
        self.assertEqual(snapshot["sources"], BROKEN_SOURCES)
        self.assertEqual(snapshot["params"], {"ALLOWANCE_PER_DAY": "22"})
        self.assertEqual(snapshot["context_version"], 1)


class RoleAssignmentTestCase(TestCase):
    def test_who_held_a_role_when(self):
        member = a_member()
        other = a_member("Zweite")
        today = timezone.localdate()
        RoleAssignment.objects.create(role="kassenwart", member=member, valid_from=today)
        past = RoleAssignment.objects.create(
            role="kassenwart",
            member=other,
            valid_from=today - timezone.timedelta(days=30),
            valid_to=today - timezone.timedelta(days=1),
        )
        self.assertEqual(RoleAssignment.roles_at(), {"kassenwart": (member.pk,)})
        self.assertEqual(
            RoleAssignment.roles_at(when=today - timezone.timedelta(days=2)),
            {"kassenwart": (other.pk,)},
        )
        self.assertEqual(str(past), f"kassenwart: {other}")

    def test_the_rules_see_the_roles_in_force(self):
        member = a_member()
        RoleAssignment.objects.create(role="kassenwart", member=member)
        statement = Statement.objects.create(short_description="Rollen")
        # Who may act is resolved for the approval step, not for the
        # arithmetic — see `statement_context`.
        context = statement_context(statement, active_ruleset(), actors=True)
        self.assertEqual(context.roles["kassenwart"], (RuleMember(MemberId(member.pk)),))
        self.assertEqual(context.role_holders("kassenwart"), (RuleMember(MemberId(member.pk)),))
        self.assertEqual(context.role_holders("vorstand"), ())
        self.assertEqual(len(context.roles), 1)
        self.assertEqual(list(context.roles), ["kassenwart"])
        self.assertIn("kassenwart", repr(context.roles))
        unresolved = statement_context(statement, active_ruleset()).roles
        self.assertFalse(unresolved.resolved)
        self.assertIn("unresolved", repr(unresolved))
        with self.assertRaises(RuleError):
            unresolved.get("kassenwart")


class ObligationModelTestCase(TestCase):
    def test_a_row_reads_as_money_and_names_its_parties(self):
        member = a_member()
        statement = Statement.objects.create(short_description="Zeilen")
        row = Obligation.objects.create(
            statement=statement,
            source_kind="section",
            destination_kind="member",
            destination_member=member,
            destination_name=member.name,
            amount_cents=1234,
            category="bill",
        )
        self.assertEqual(row.amount, Decimal("12.34"))
        self.assertEqual(row.source_display, str(_("Section")))
        self.assertEqual(row.destination_display, member.name)
        self.assertEqual(str(row), "bill: 12.34€")
        # A member who is gone leaves the name that was copied beside them.
        row.destination_member = None
        self.assertEqual(row.destination_display, member.name)
        participants = Obligation.objects.create(
            statement=statement, source_kind="participants", destination_kind="section"
        )
        self.assertEqual(participants.source_display, str(_("Participants")))

    def test_a_constraint_names_who_may_sign(self):
        member = a_member()
        statement = Statement.objects.create(short_description="Freigabe")
        constraint = ApprovalConstraint.objects.create(
            statement=statement, name="Freigabe", required=1, eligible_member_ids=[member.pk]
        )
        self.assertEqual(list(constraint.eligible), [member])
        self.assertEqual(str(constraint), "Freigabe (1)")

    def test_cents_are_whole(self):
        self.assertEqual(cents_of(Decimal("12.34")), 1234)
        self.assertEqual(cents_of(Decimal("-0.01")), -1)
        self.assertEqual(cents_of(Decimal("0.00")), 0)


class VersionIdentityTestCase(SimpleTestCase):
    def test_a_version_is_its_sources_and_its_numbers(self):
        sources = {"__init__.py": "x = 1\n"}
        first = version_hash(sources, {"A": "1"})
        self.assertEqual(first, version_hash(sources, {"A": "1"}))
        self.assertNotEqual(first, version_hash(sources, {"A": "2"}))
        self.assertNotEqual(first, version_hash({"__init__.py": "x = 2\n"}, {"A": "1"}))
        self.assertEqual(params_fingerprint({"B": "2", "A": "1"}), "A=1\nB=2")

    def test_the_image_digest_joins_the_record_once_there_is_one(self):
        with patch.dict(os.environ, {"KOMPASS_IMAGE_DIGEST": "sha256:abc"}):
            self.assertIn("sha256:abc", engine_version())

    def test_a_parameter_that_is_not_a_number_is_dropped(self):
        self.assertEqual(
            decimal_params({"ALLOWANCE_PER_DAY": "22", "NONSENSE": "zwölf"}),
            {"ALLOWANCE_PER_DAY": Decimal("22")},
        )

    def test_the_numbers_are_text_not_floats(self):
        with override_settings(AID_PER_KM_TRAIN=0.155):
            params = parameters_from_settings()
        self.assertEqual(params["AID_PER_KM_TRAIN"], "0.155")

    def test_what_a_version_was_imported_into(self):
        self.assertIn("CPython", engine_version())
        self.assertTrue(engine_version().startswith("kompass "))

    def test_when_a_version_applies_from(self):
        """A declared date is honoured, **including one in the past**.

        That is a decision rather than drift (R3 on taxis #495). A past date
        was refused on the grounds that honouring it would rewrite settled
        statements, which it does not: a statement copies its closure when it
        is created and nothing imported later moves it. What the refusal did
        was pin valid time to transaction time, so the one correction a
        section actually needs — rates resolved in March, Kompass told in May
        — could not be expressed at all, and the record could not say that
        Kompass had applied one version while another had been in force.

        Unset, and unreadable, both mean "from now": an import that silently
        backdated a typo to the epoch would be worse than one that does not
        backdate.
        """
        rules = HeidelbergRules()
        now = timezone.now()
        self.assertGreaterEqual(declared_valid_from(rules), now)
        rules.valid_from = "not a date"
        self.assertGreaterEqual(declared_valid_from(rules), now)
        rules.valid_from = "2020-01-01"
        self.assertEqual(declared_valid_from(rules).date().isoformat(), "2020-01-01")
        future = (now + timezone.timedelta(days=30)).replace(microsecond=0)
        rules.valid_from = future.isoformat()
        self.assertEqual(declared_valid_from(rules), future)
        rules.valid_from = future.replace(tzinfo=None).isoformat()
        self.assertEqual(declared_valid_from(rules).date(), future.date())

    def test_where_the_rules_are_read_from(self):
        self.assertIsNone(ruleset_directory())
        self.assertEqual(configured_directory(), reference_directory())
        with override_settings(FINANCE_RULESET="rules", CONFIG_DIR_PATH="/app/config"):
            self.assertEqual(ruleset_directory(), Path("/app/config/rules"))
            self.assertEqual(configured_directory(), Path("/app/config/rules"))


class CheckDirectoryTestCase(SimpleTestCase):
    def test_the_reference_ruleset_passes(self):
        loaded, problems = check_directory(reference_directory())
        self.assertEqual(problems, [])
        self.assertEqual(loaded.name, "heidelberg")

    def test_a_directory_with_no_python_in_it(self):
        with TemporaryDirectory() as directory:
            loaded, problems = check_directory(Path(directory))
        self.assertIsNone(loaded)
        self.assertIn("holds no Python files", problems[0])

    def test_a_ruleset_that_imports_what_it_may_not(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text("import os\n", encoding="utf-8")
            loaded, problems = check_directory(Path(directory))
        self.assertIsNone(loaded)
        self.assertIn("may not import os", problems[0])

    def test_a_ruleset_that_exports_nothing_usable(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text("ruleset = 1\n", encoding="utf-8")
            loaded, problems = check_directory(Path(directory))
        self.assertIsNone(loaded)
        self.assertIn("does not export", problems[0])

    def test_a_ruleset_that_breaks_while_it_is_imported(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text(
                "raise ValueError('nope')\n", encoding="utf-8"
            )
            loaded, problems = check_directory(Path(directory))
        self.assertIsNone(loaded)
        self.assertIn("could not be loaded", problems[0])

    def test_a_ruleset_with_no_cases_at_all_still_passes(self):
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text(
                "from kompass.rules import Ruleset\n"
                "class Nothing(Ruleset):\n"
                "    name = 'nothing'\n"
                "    def inputs(self, ctx):\n        return []\n"
                "    def transfers(self, ctx):\n        return [], []\n"
                "ruleset = Nothing()\n",
                encoding="utf-8",
            )
            loaded, problems = check_directory(Path(directory))
        self.assertEqual(problems, [], "a ruleset without cases is not a ruleset with failures")
        self.assertEqual(loaded.name, "nothing")

    def test_a_ruleset_whose_cases_do_not_pass(self):
        with TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "__init__.py").write_text(
                "from kompass.rules import Ruleset, SECTION, PARTICIPANTS\n"
                "class Nothing(Ruleset):\n"
                "    name = 'nothing'\n"
                "    def inputs(self, ctx):\n        return []\n"
                "    def transfers(self, ctx):\n        return [], []\n"
                "ruleset = Nothing()\n",
                encoding="utf-8",
            )
            cases = package / "cases"
            cases.mkdir()
            (cases / "one.json").write_text(
                '{"name": "impossible", "expect": {"transfers": []}}', encoding="utf-8"
            )
            loaded, problems = check_directory(package)
        self.assertIsNotNone(loaded)
        self.assertIn("case “impossible”", problems[0])


class ImportTestCase(TestCase):
    def test_importing_the_reference_ruleset_activates_it(self):
        RuleSet.objects.all().delete()
        row, problems = import_from_directory(reference_directory(), revision="abc123")
        self.assertEqual(problems, [])
        self.assertEqual(row.state, RuleSet.ACTIVE)
        self.assertEqual(row.name, "heidelberg")
        self.assertEqual(row.revision, "abc123")
        self.assertIsNotNone(row.cases_passed_at)
        self.assertEqual(active_version(), row)
        # Importing the same package again is the same version.
        again, problems = import_from_directory(reference_directory())
        self.assertEqual(problems, [])
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(RuleSet.objects.count(), 1)

    def test_changing_a_number_is_a_new_version_that_supersedes_the_old_one(self):
        first, _problems = import_from_directory(reference_directory())
        with override_settings(ALLOWANCE_PER_DAY=23):
            second, problems = import_from_directory(reference_directory())
        self.assertEqual(problems, [])
        self.assertNotEqual(second.pk, first.pk)
        self.assertEqual(second.supersedes, first)
        first.refresh_from_db()
        self.assertEqual(first.state, RuleSet.RETIRED)
        self.assertEqual(first.valid_to, second.valid_from)
        self.assertEqual(active_version(), second)
        self.assertEqual(second.params["ALLOWANCE_PER_DAY"], "23")

    def test_a_ruleset_that_fails_is_stored_as_a_draft_and_changes_nothing(self):
        active = active_version()
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text("import socket\n", encoding="utf-8")
            row, problems = import_from_directory(Path(directory), name="kaputt")
        self.assertTrue(problems)
        self.assertEqual(row.state, RuleSet.DRAFT)
        self.assertEqual(row.name, "kaputt")
        self.assertEqual(row.context_version, 0)
        self.assertIsNone(row.cases_passed_at)
        self.assertEqual(active_version(), active, "the previous version stays in force")
        # Importing the same broken package again returns the same draft.
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text("import socket\n", encoding="utf-8")
            again, problems = import_from_directory(Path(directory))
        self.assertEqual(again.pk, row.pk)
        self.assertTrue(problems)

    def imported(self, source, **options):
        """Import ``source`` as a ruleset of its own, and return the outcome."""
        with TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "__init__.py").write_text(source, encoding="utf-8")
            return import_from_directory(package, **options)

    def days_ago(self, days):
        """A date that many days back, as a ruleset declares one."""
        return (timezone.localdate() - timezone.timedelta(days=days)).isoformat()

    def test_a_correction_may_say_its_rules_were_valid_before_the_import(self):
        """R3: the gap between what was in force and what Kompass was told.

        A section resolves new rates in March and gets round to telling
        Kompass in May. Both instants are on the record afterwards: the
        correction's own ``valid_from`` is in March and its ``imported_at`` is
        now, and the version it replaced says its rules ended in March
        (``valid_to``) while Kompass went on applying them until now
        (``retired_at``). That second pair is what a single column could not
        say, and unrecorded history cannot be retrofitted.
        """
        RuleSet.objects.all().delete()
        january, problems = self.imported(dated("januar", self.days_ago(120)), name="januar")
        self.assertEqual(problems, [])
        self.assertEqual(active_version(), january)

        march, problems = self.imported(dated("maerz", self.days_ago(60)), name="maerz")
        self.assertEqual(problems, [])
        self.assertLess(march.valid_from, march.imported_at, "valid time before transaction time")
        january.refresh_from_db()
        self.assertEqual(january.valid_to, march.valid_from, "its rules ended in March")
        self.assertLess(january.valid_to, january.retired_at, "and Kompass applied them until now")
        # Nothing was in force after March, so the correction is in force now.
        self.assertEqual(active_version(), march)
        # And the valid-time question has an answer for a past moment.
        in_february = timezone.now() - timezone.timedelta(days=90)
        self.assertEqual(RuleSet.objects.active(when=in_february), january)

    def test_a_correction_does_not_displace_a_version_imported_after_it(self):
        """A backdated row fills its gap and withdraws nothing.

        The section resolved March's rates in March, imported an April change
        on time, and only then got round to March. Valid time now reads
        January → March → April, the April version is still what applies
        today, and the correction answers for the month it was resolved for.
        Without the cap, "what applies now" would have come out as the March
        rules and an April change nobody withdrew would have been reverted.
        """
        RuleSet.objects.all().delete()
        january, _problems = self.imported(dated("januar", self.days_ago(120)), name="januar")
        april, _problems = self.imported(dated("april", self.days_ago(30)), name="april")
        self.assertEqual(active_version(), april)

        march, problems = self.imported(dated("maerz", self.days_ago(60)), name="maerz")
        self.assertEqual(problems, [])
        april.refresh_from_db()
        january.refresh_from_db()
        self.assertEqual(march.valid_to, april.valid_from, "the correction ends where April began")
        self.assertEqual(january.valid_to, march.valid_from)
        self.assertIsNone(april.valid_to, "April is untouched")
        self.assertEqual(active_version(), april, "and still in force")
        when = timezone.now() - timezone.timedelta(days=45)
        self.assertEqual(RuleSet.objects.active(when=when), march)

    def test_a_statement_already_bound_is_not_re_settled_by_a_correction(self):
        """The constraint that is not negotiable, and why backdating is safe.

        Binding happens at creation (§7), so what a statement settles under is
        decided once. A correction imported afterwards — with a date before
        the statement was even created — leaves its version, its hash, its
        closure and its numbers exactly as they were. Re-settling it under the
        corrected rules would be a separate, deliberate act, and this code
        does not offer one.
        """
        RuleSet.objects.all().delete()
        with override_settings(ALLOWANCE_PER_DAY=22):
            january, _problems = self.imported(dated("januar", self.days_ago(120)), name="januar")
            statement = Statement.objects.create(short_description="Februar", night_cost=0)
        self.assertEqual(statement.ruleset_id, january.pk)

        with override_settings(ALLOWANCE_PER_DAY=99):
            march, problems = self.imported(dated("maerz", self.days_ago(60)), name="maerz")
        self.assertEqual(problems, [])
        bound = Statement.objects.get(pk=statement.pk)
        self.assertEqual(bound.ruleset_id, january.pk)
        self.assertEqual(bound.ruleset_hash, january.hash)
        self.assertEqual(statement_params(bound)["ALLOWANCE_PER_DAY"], Decimal("22"))
        self.assertEqual(ruleset_for(bound).name, "januar")
        # A statement created now is settled under what is in force now.
        with override_settings(ALLOWANCE_PER_DAY=99):
            later = Statement.objects.create(short_description="Juni", night_cost=0)
        self.assertEqual(later.ruleset_id, march.pk)
        self.assertEqual(statement_params(later)["ALLOWANCE_PER_DAY"], Decimal("99"))

    def test_a_staged_version_leaves_the_current_one_in_force(self):
        """Staging a change may not leave nothing in force in the meantime.

        Activating a staged version closes its predecessor's validity at the
        future date and marks it ``RETIRED`` there and then, and
        ``RuleSet.objects.active`` used to require ``state=ACTIVE`` — so
        between the import and the date it takes effect, **nothing was in
        force**. A statement created in that window bound to no version at
        all and was settled against the reference ruleset and the live
        settings rather than the section's own rules. The state column says
        how an import ended; the dates say what applies when.
        """
        RuleSet.objects.all().delete()
        current, _problems = self.imported(dated("jetzt", self.days_ago(30)), name="jetzt")
        when = (timezone.localdate() + timezone.timedelta(days=10)).isoformat()
        staged, problems = self.imported(dated("naechster-monat", when), name="naechster-monat")
        self.assertEqual(problems, [])
        self.assertEqual(active_version(), current, "the staged change is not in force yet")
        statement = Statement.objects.create(short_description="Heute", night_cost=0)
        self.assertEqual(statement.ruleset_id, current.pk, "and a new statement is bound to it")
        later = staged.valid_from + timezone.timedelta(days=1)
        self.assertEqual(RuleSet.objects.active(when=later), staged)

    def test_a_name_that_queries_is_a_draft_rather_than_a_free_cursor(self):
        """The import read two fields off the loaded object, past the guard.

        ``loaded.name`` is an attribute lookup, which is why it was written as
        data, and a section can declare it as a ``property`` — at which point
        reading it is a call into the section's own code, one line after the
        load's guard lifted and on the way into ``RuleSet.objects.create``.
        The refusal is *reported*, like every other way a ruleset can be bad:
        the row is a draft and the version in force does not move.
        """
        active = active_version()
        row, problems = self.imported(querying_field("name", "nosy-name"))
        self.assertEqual(row.state, RuleSet.DRAFT)
        self.assertTrue(any("must not query the database" in problem for problem in problems))
        self.assertEqual(active_version(), active, "the previous version stays in force")
        # The other direction, which is what says the guard refused rather
        # than the fixture failing some other way: with `no_queries` lifted
        # where the import opens it, the same read goes through and the name
        # it answers is the name on the row. (A different answer, so that this
        # is a different version rather than the stored draft read back.)
        with guard_lifted("finance.engine.versions"):
            lifted, problems = self.imported(querying_field("name", "nosy-anyway"))
        self.assertEqual(problems, [])
        self.assertEqual(lifted.name, "nosy-anyway")
        self.assertEqual(active_version(), lifted)

    def test_a_name_given_by_the_importer_is_not_read_off_the_ruleset(self):
        """The short-circuit `declared_fields` keeps, and what it costs.

        ``name or loaded.name`` is the behaviour this replaced, and it is
        preserved deliberately: an explicit name is the importer's, not the
        ruleset's, so ``importruleset --name`` must not depend on what the
        ruleset says about itself. The cost is that the querying property is
        never read, and so never refused: such a version activates with no
        problem recorded. That is harmless — nothing else reads
        ``loaded.name``, and the row's own name is what the admin shows — but
        it is the kind of thing to pin rather than discover.
        """
        row, problems = self.imported(querying_field("name", "nosy-explicit"), name="von-hand")
        self.assertEqual(problems, [], "the property was never read, so it never refused")
        self.assertEqual(row.name, "von-hand")
        self.assertEqual(row.state, RuleSet.ACTIVE)
        self.assertEqual(active_version(), row)

    def test_a_valid_from_that_queries_is_a_draft_too(self):
        """The second field, read through ``declared_valid_from``.

        A section stages a change by naming a future date, so this one is read
        on the way into the row as well — and ``getattr(ruleset,
        "valid_from")`` runs whatever the section put behind that name.
        """
        active = active_version()
        row, problems = self.imported(querying_field("valid_from", "2099-01-01"))
        self.assertEqual(row.state, RuleSet.DRAFT)
        self.assertTrue(any("must not query the database" in problem for problem in problems))
        self.assertEqual(active_version(), active)
        with guard_lifted("finance.engine.versions"):
            lifted, problems = self.imported(querying_field("valid_from", "2099-01-02"))
        self.assertEqual(problems, [])
        self.assertEqual(lifted.valid_from.date().isoformat(), "2099-01-02")

    def test_a_stored_draft_without_problems_is_activated_on_the_next_import(self):
        row, _problems = import_from_directory(reference_directory())
        RuleSet.objects.filter(pk=row.pk).update(state=RuleSet.DRAFT, problems=[])
        again, problems = import_from_directory(reference_directory())
        self.assertEqual(problems, [])
        self.assertEqual(again.pk, row.pk)
        self.assertEqual(RuleSet.objects.get(pk=row.pk).state, RuleSet.ACTIVE)


class BindingTestCase(TestCase):
    def test_a_statement_is_bound_when_it_is_created(self):
        version = active_version()
        self.assertIsNotNone(version, "the migration imported one")
        statement = Statement.objects.create(short_description="Gebunden")
        self.assertEqual(statement.ruleset, version)
        self.assertEqual(statement.ruleset_hash, version.hash)
        self.assertEqual(statement.ruleset_snapshot["params"], version.params)
        self.assertEqual(ruleset_for(statement).name, "heidelberg")

    def test_a_new_version_does_not_reach_a_statement_that_exists(self):
        statement = Statement.objects.create(short_description="Alt")
        before = statement.ruleset_hash
        with override_settings(ALLOWANCE_PER_DAY=99):
            import_from_directory(reference_directory())
        statement.refresh_from_db()
        self.assertEqual(statement.ruleset_hash, before)
        self.assertEqual(statement_params(statement)["ALLOWANCE_PER_DAY"], Decimal("22"))
        # A statement created now gets the new version.
        self.assertEqual(
            statement_params(Statement.objects.create(short_description="Neu"))[
                "ALLOWANCE_PER_DAY"
            ],
            Decimal("99"),
        )

    def test_without_a_version_nothing_is_bound(self):
        RuleSet.objects.all().delete()
        statement = Statement(short_description="Ungebunden")
        self.assertFalse(bind(statement))
        statement.save()
        self.assertIsNone(statement.ruleset_id)
        self.assertEqual(ruleset_for(statement).name, "heidelberg")
        self.assertEqual(active_ruleset().name, "heidelberg")

    def test_a_stored_version_that_cannot_be_loaded_falls_back_loudly(self):
        RuleSet.objects.all().delete()
        a_version()
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            self.assertEqual(active_ruleset().name, "heidelberg")
        statement = Statement.objects.create(short_description="Kaputt")
        self.assertEqual(statement.ruleset_snapshot["sources"], BROKEN_SOURCES)
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            self.assertEqual(ruleset_for(statement).name, "heidelberg")

    def assert_a_statement_bound_to(self, sources):
        """A statement bound to ``sources`` works on the paths that 500ed.

        The draft save that materialises it and the reads a page makes, which
        is what "must not take its finance pages down" means in code.
        """
        RuleSet.objects.all().delete()
        a_version(sources=sources)
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            statement = Statement.objects.create(short_description="Weg")
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            self.assertEqual(ruleset_for(statement).name, "heidelberg")
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            statement.save()
        with self.assertLogs("finance.engine.statements", level="WARNING"):
            self.assertEqual(Statement.objects.get(pk=statement.pk).rule_result.errors, ())
        statement.submit(submitter=None)
        settled = Statement.objects.get(pk=statement.pk)
        self.assertTrue(settled.approval_constraint_set.exists(), "and it can be handed in")
        self.assertEqual([state.name for state in settled.live_approval_states], ["Freigabe"])

    def test_a_snapshot_whose_own_code_raises_falls_back_as_well(self):
        """#553: the fallback caught a refusal and nothing else.

        A module body is a section's own Python and may raise anything at all.
        Caught narrowly, a ``ValueError`` in one came out of
        ``loaded_ruleset`` on every path a statement has — the draft save, the
        form, the printout — rather than reaching the fallback written for
        exactly this.
        """
        self.assert_a_statement_bound_to(ANGRY_SOURCES)

    def test_a_snapshot_the_api_has_moved_on_from_falls_back_as_well(self):
        """The same hole, through the door ``active_ruleset`` names.

        "A Kompass upgrade that makes an old snapshot unloadable" is its
        docstring's own example, and the way that happens is an
        ``ImportError``: rename anything in ``kompass.rules`` and every
        statement bound to a version that mentions the old name stopped
        rendering and stopped saving — one deployment, every open draft of
        every section whose rules use it.
        """
        self.assert_a_statement_bound_to(RENAMED_API_SOURCES)


class MaterialisationTestCase(TestCase):
    def setUp(self):
        self.member = a_member()
        self.statement = Statement.objects.create(short_description="Zeilen")
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("12.34"),
            costs_covered=True,
            paid_by=self.member,
        )

    def test_a_draft_is_written_down_on_every_save(self):
        rows = list(self.statement.obligation_set.all())
        self.assertEqual([row.category for row in rows], ["bill", "participant_contribution"])
        self.assertEqual(rows[0].amount_cents, 1234)
        self.assertEqual(rows[0].destination_member, self.member)
        self.assertEqual(rows[0].destination_name, self.member.name)
        self.assertEqual(rows[0].rule_version, self.statement.ruleset_hash)
        self.assertIsNone(rows[0].frozen_at)
        self.assertEqual(rows[1].source_kind, "participants")

    def test_submission_freezes_the_rows_and_a_draft_edit_does_not(self):
        self.statement.submit(submitter=self.member)
        rows = list(self.statement.obligation_set.all())
        self.assertTrue(all(row.frozen_at is not None for row in rows))
        frozen = rows[0].frozen_at
        # Saving a submitted statement leaves the record alone.
        self.statement.save()
        self.assertEqual(self.statement.obligation_set.first().frozen_at, frozen)
        self.assertEqual(materialise(self.statement)[0].frozen_at, frozen)

    def test_a_submitted_statement_reads_its_rows_once(self):
        self.statement.submit(submitter=self.member)
        statement = Statement.objects.get(pk=self.statement.pk)
        with self.assertNumQueries(2):
            # One for `exists`, one for the rows; the second read is cached.
            self.assertEqual(statement.total, Decimal("12.34"))
            self.assertEqual(statement.total, Decimal("12.34"))
        self.assertEqual(statement.rule_result.balance.amount, Decimal("12.34"))

    def test_a_settled_row_is_superseded_rather_than_overwritten(self):
        """What the GoBD's Unveränderbarkeit asks of the one editable field.

        Covering a bill after submission resolves the payout again. The rows
        that were frozen at submission are kept and marked; only the current
        ones are read.
        """
        self.statement.submit(submitter=self.member)
        before = list(self.statement.obligation_set.all())
        self.assertTrue(all(row.live for row in before))
        bill = self.statement.bill_set.first()
        bill.amount = Decimal("20.00")
        bill.save()
        statement = Statement.objects.get(pk=self.statement.pk)
        rows = list(statement.obligation_set.all())
        superseded = [row for row in rows if not row.live]
        live = [row for row in rows if row.live]
        self.assertEqual(len(superseded), len(before), "the old record is kept")
        self.assertEqual({row.amount_cents for row in superseded}, {1234})
        self.assertEqual(statement.total, Decimal("20.00"))
        self.assertEqual(len(live), 2)
        self.assertIn("superseded", str(superseded[0]))
        # A draft's rows are a working copy and are simply replaced.
        draft = Statement.objects.create(short_description="Entwurf")
        Bill.objects.create(
            statement=draft,
            short_description="Seil",
            amount=Decimal("1.00"),
            costs_covered=True,
            paid_by=self.member,
        )
        draft.save()
        self.assertTrue(all(row.live for row in draft.obligation_set.all()))
        self.assertEqual(draft.obligation_set.count(), 2)

    def test_the_finance_officer_covering_a_bill_refreezes_the_payout(self):
        bill = Bill.objects.create(
            statement=self.statement,
            short_description="Essen",
            amount=Decimal("5.00"),
            costs_covered=False,
            paid_by=self.member,
        )
        self.statement.submit(submitter=self.member)
        self.assertEqual(Statement.objects.get(pk=self.statement.pk).total, Decimal("12.34"))
        bill.costs_covered = True
        bill.save()
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertEqual(statement.total, Decimal("17.34"))
        self.assertTrue(all(row.frozen_at for row in statement.obligation_set.all()))
        bill.delete()
        self.assertEqual(Statement.objects.get(pk=self.statement.pk).total, Decimal("12.34"))

    def test_a_paid_statement_is_not_touched_by_a_bill_at_all(self):
        self.statement.submit(submitter=self.member)
        self.statement.status = Statement.CONFIRMED
        self.statement.save()
        bill = self.statement.bill_set.first()
        bill.amount = Decimal("99.00")
        bill.save()
        self.assertEqual(
            Statement.objects.get(pk=self.statement.pk).total, Decimal("12.34"), "frozen for good"
        )

    def test_nothing_is_written_while_the_rules_report_a_problem(self):
        self.statement.bill_set.update(paid_by=None)
        self.statement.save()
        self.assertEqual(self.statement.obligation_set.count(), 0)
        self.assertEqual(self.statement.approval_constraint_set.count(), 0)
        # And a submitted statement in that state still shows the problem.
        self.statement.submit(submitter=self.member)
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(statement.rule_result.errors)
        self.assertFalse(statement.generate_transactions())

    def test_the_signatures_the_rules_asked_for_are_written_down_too(self):
        self.statement.submit(submitter=self.member)
        constraint = self.statement.approval_constraint_set.get()
        self.assertEqual(constraint.name, "Freigabe")
        self.assertEqual(constraint.required, 1)
        self.assertIsNotNone(constraint.frozen_at)

    def test_an_unsaved_statement_has_nothing_to_write(self):
        self.assertEqual(materialise(Statement(short_description="Neu")), ())

    def test_the_rows_read_back_as_the_transfers_they_came_from(self):
        self.statement.submit(submitter=self.member)
        result = result_from_rows(self.statement)
        self.assertEqual(len(result.transfers), 2)
        self.assertEqual(result.transfers[0].destination, RuleMember(MemberId(self.member.pk)))
        self.assertEqual(result.balance.rule_id, "balance")
        self.assertEqual(result.net_out(result.balance.destination), Decimal("12.34"))
        # A record without a balancing row reads as one without a balance.
        self.statement.obligation_set.filter(rule_id="balance").delete()
        self.assertIsNone(result_from_rows(self.statement).balance)


class VerifyTestCase(TestCase):
    def setUp(self):
        self.member = a_member()
        self.statement = Statement.objects.create(short_description="Prüfung")
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.member,
        )
        self.statement.submit(submitter=self.member)
        self.statement.status = Statement.CONFIRMED
        self.statement.save()

    def test_what_is_stored_verifies(self):
        self.assertEqual(verify(Statement.objects.all()), [])

    def test_a_tampered_version_is_noticed(self):
        row = active_version()
        RuleSet.objects.filter(pk=row.pk).update(sources={"__init__.py": "x = 1\n"})
        problems = verify(Statement.objects.all())
        self.assertTrue(any("do not match the stored manifest" in p for p in problems))
        self.assertTrue(any("does not hash to the stored hash" in p for p in problems))

    def test_a_statement_bound_to_a_version_nobody_imported(self):
        Statement.objects.filter(pk=self.statement.pk).update(ruleset_hash="d" * 64)
        problems = verify(Statement.objects.all())
        self.assertTrue(any("which is not imported" in p for p in problems))

    def test_a_statement_whose_payout_no_longer_reproduces(self):
        self.statement.obligation_set.filter(rule_id="bills").update(amount_cents=999)
        problems = verify(Statement.objects.all())
        self.assertTrue(any("does not reproduce" in p for p in problems))

    def test_a_statement_whose_snapshot_cannot_be_loaded(self):
        snapshot = dict(self.statement.ruleset_snapshot, sources=BROKEN_SOURCES)
        Statement.objects.filter(pk=self.statement.pk).update(ruleset_snapshot=snapshot)
        problems = verify(Statement.objects.all())
        self.assertTrue(any("does not export" in p for p in problems))

    def test_a_snapshot_that_will_not_load_at_all_is_a_finding_too(self):
        """However it fails to load: a finding, never an exception.

        The replay is the audit, and an audit that stops at the first thing it
        cannot read has audited nothing after it. See the command and the beat
        task in ``finance.tests.commands`` for what that cost.
        """
        snapshot = dict(self.statement.ruleset_snapshot, sources=RENAMED_API_SOURCES)
        Statement.objects.filter(pk=self.statement.pk).update(ruleset_snapshot=snapshot)
        problems = verify(Statement.objects.all())
        self.assertTrue(any("ImportError" in p and "Gone" in p for p in problems))

    def test_rows_back_filled_from_transactions_are_not_replayed(self):
        self.statement.obligation_set.all().update(rule_id="legacy")
        self.assertEqual(verify(Statement.objects.all()), [])

    def test_the_sample_bounds_how_much_is_replayed(self):
        self.statement.obligation_set.filter(rule_id="bills").update(amount_cents=999)
        self.assertEqual(verify(Statement.objects.all(), sample=0), [])

    def test_a_draft_is_not_replayed(self):
        draft = Statement.objects.create(short_description="Entwurf")
        Transaction.objects.create(
            reference="x", amount=Decimal("1.00"), member=self.member, statement=draft
        )
        self.assertEqual(verify(Statement.objects.filter(pk=draft.pk)), [])


class MigrationAgreementTestCase(SimpleTestCase):
    def test_the_migration_hashes_a_version_the_way_the_engine_does(self):
        """The copy in ``0016`` has to agree with the engine.

        If it did not, the first import after a deployment would store the
        reference ruleset a second time under a different hash, and every
        statement the migration had just bound would be bound to a version
        nothing else uses. The copy is deliberate — a migration has to keep
        meaning the same thing in five years — so this is the test that keeps
        the two honest.
        """
        migration = import_module("finance.migrations.0016_import_reference_ruleset")
        sources = migration._sources(reference_directory())
        params = migration._parameters(settings)
        self.assertEqual(sources, read_sources(reference_directory()))
        self.assertEqual(params, parameters_from_settings())
        self.assertEqual(
            migration._hash(migration._manifest(sources), params),
            version_hash(sources, params),
        )


class FuzzTestCase(SimpleTestCase):
    """The fuzzer: random statements the rules have to survive."""

    def test_the_reference_ruleset_survives_two_hundred_random_statements(self):
        self.assertEqual(fuzz(HeidelbergRules(), 200, seed=1), [])

    def test_a_random_statement_is_a_statement_somebody_could_have_handed_in(self):
        context = random_context(Random(7), {"ALLOWANCE_PER_DAY": Decimal("22")})
        self.assertIsNotNone(context.excursion)
        self.assertTrue(all(bill.payer is not None for bill in context.bills))
        self.assertEqual(context.params.ALLOWANCE_PER_DAY, Decimal("22"))

    def test_an_answer_stays_inside_the_domain_the_rules_declared(self):
        rng = Random(3)
        options = (RuleMember(MemberId(1)), RuleMember(MemberId(2)))
        self.assertIsInstance(random_answer(rng, Input("a", "A", "money")), Decimal)
        self.assertIsInstance(random_answer(rng, Input("b", "B", "int", max=3)), int)
        self.assertIsInstance(random_answer(rng, Input("c", "C", "bool")), bool)
        self.assertIsInstance(random_answer(rng, Input("d", "D", "text")), str)
        self.assertIsNone(random_answer(rng, Input("e", "E", "member")))
        self.assertIn(
            random_answer(rng, Input("f", "F", "member", options=options)), options + (None,)
        )
        picked = random_answer(rng, Input("g", "G", "member_set", options=options, max=1))
        self.assertLessEqual(len(picked), 1)
        self.assertEqual(random_answer(rng, Input("h", "H", "member_set")), ())
        self.assertIsNone(random_answer(rng, Input("i", "I", "choice")))
        self.assertIsInstance(random_answer(rng, Input("j", "J", "int")), int)

    def test_a_balance_declared_the_wrong_way_round_is_refused(self):
        """The error the proposal's own sketch would have produced.

        ``balance`` is resolved so that its *destination* comes out at zero, so
        ``(SECTION, PARTICIPANTS, …)`` — the order §3 and §4.3 of the proposal
        are written in — closes nothing: the participants were already square
        and the section is not. It used to yield a ``0.00`` balancing row and
        books that did not add up, with no error; now it says so.
        """

        class Leaky(HeidelbergRules):
            balance = (SECTION, PARTICIPANTS, "participant_contribution")

        problems = fuzz(Leaky(), 20, seed=2)
        self.assertTrue(problems)
        self.assertIn("the other way round", problems[0])

    def test_a_balance_that_closes_the_wrong_books(self):
        """Closing the participants' books does not close the section's.

        The engine guarantees that the party a declaration names as its
        *destination* comes out at zero. It does not guarantee that the
        section does — so a ruleset that balances the other way round, with
        something else keeping the participants off zero so the direction
        guard does not fire, leaves every row two-ended and the section ten
        euro short. That is what the fuzzer's second assertion is for.
        """

        class Sideways(HeidelbergRules):
            balance = (SECTION, PARTICIPANTS, "rest")

            def transfers(self, ctx):
                return [
                    Transfer(
                        source=SECTION,
                        destination=PARTICIPANTS,
                        amount=Decimal("10.00"),
                        category="rest",
                        rule_id="pot",
                    ),
                    Transfer(
                        source=SECTION,
                        destination=RuleMember(MemberId(1)),
                        amount=Decimal("10.00"),
                        category="rest",
                        rule_id="gift",
                    ),
                ], []

        problems = fuzz(Sideways(), 3, seed=5)
        self.assertEqual(len(problems), 3)
        self.assertIn("the section is out by 10.00", problems[0])

    def test_a_person_may_not_be_the_party_the_books_are_balanced_against(self):
        """The residue sink has to be a ledger, and a member is not one.

        ``(PARTICIPANTS, Member(1), …)`` resolves, writes a transfer and adds
        up — and hands that member whatever the rules did not account for,
        which is a bill nobody wrote. §3 of the proposal claims the engine
        makes sum-to-zero unfalsifiable; what it can promise is that the
        declared party comes out at zero and that no transfer invents money,
        and this is the declaration that satisfies both while being nonsense.
        """

        class Personal(HeidelbergRules):
            balance = (PARTICIPANTS, RuleMember(MemberId(1)), "rest")

        problems = fuzz(Personal(), 2, seed=5)
        self.assertEqual(len(problems), 2)
        self.assertIn("a payee and not a ledger", problems[0])
        self.assertIn("member 1", problems[0])

    def test_a_ruleset_whose_rules_raise_is_reported(self):
        class Angry(HeidelbergRules):
            def transfers(self, ctx):
                raise ValueError("nope")

        problems = fuzz(Angry(), 3, seed=0)
        self.assertEqual(len(problems), 3)
        self.assertIn("the section's rules failed", problems[0])

    def test_check_and_fuzz_is_the_whole_check_in_one_call(self):
        self.assertEqual(check_and_fuzz(reference_directory(), 5, seed=4), [])
        self.assertEqual(check_and_fuzz(reference_directory(), 0), [])
        with TemporaryDirectory() as directory:
            (Path(directory) / "__init__.py").write_text("import os\n", encoding="utf-8")
            self.assertTrue(check_and_fuzz(Path(directory), 5))


class GuardedCallsTestCase(TestCase):
    """Every call into a section's rules runs inside the query guard.

    ``transfers`` and ``checks`` always did. ``approval`` and ``inputs`` did
    not, and ``approval`` is reached from ``materialise`` on every draft save —
    so a rule resolving its eligible set with a query would have frozen today's
    membership into rows that replay differently in two years, with nothing to
    notice it.

    Both tests here drive the **real** path: the previous versions called the
    rule inside a guard the test itself opened, which passes whether or not the
    production code opens one, and asserted that the reference ruleset does not
    query, which it never did.
    """

    #: A ruleset that reaches the database through a caller's frame, so that no
    #: name on the import whitelist appears in it, and by the *backend's own*
    #: cursor factory, so that no Django ``CursorWrapper`` is involved and the
    #: execute wrapper this guard used to rely on would not have seen it. The
    #: whitelist cannot stop this; the guard can, and that is the point of
    #: asking from inside ``approval``, which is where nothing was guarding.
    QUERYING_APPROVAL = (
        "from kompass.rules import Constraint, Ruleset, SECTION, PARTICIPANTS\n"
        "\n"
        "\n"
        "class Nosy(Ruleset):\n"
        "    name = 'nosy'\n"
        "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
        "\n"
        "    def inputs(self, ctx):\n"
        "        return []\n"
        "\n"
        "    def transfers(self, ctx):\n"
        "        return [], []\n"
        "\n"
        "    def approval(self, ctx, transfers):\n"
        "        try:\n"
        "            raise ValueError()\n"
        "        except ValueError as problem:\n"
        "            real = problem.__traceback__.tb_frame.f_back.f_builtins\n"
        "        db = real['__import__']('django.db', {}, {}, ['connections'])\n"
        "        cursor = db.connections['default'].create_cursor()\n"
        "        cursor.execute('SELECT 1')\n"
        "        return [], []\n"
        "\n"
        "\n"
        "ruleset = Nosy()\n"
    )

    def test_a_rule_that_queries_from_approval_leaves_a_statement_unpayable(self):
        with TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "__init__.py").write_text(self.QUERYING_APPROVAL, encoding="utf-8")
            row, problems = import_from_directory(package, name="nosy")
            self.assertEqual(problems, [], "no banned name appears in it")
            self.assertEqual(active_version(), row)
            statement = Statement.objects.create(short_description="Wach")
        constraint = statement.approval_constraint_set.get()
        self.assertIn("must not query the database", constraint.error)
        self.assertEqual(constraint.eligible_member_ids, [])
        statement.submit(submitter=None)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertFalse(statement.fully_approved, "a broken rule is not signed away")
        self.assertFalse(statement.approve(None))

    #: The same escape, from the ``permissions`` declaration: a class
    #: attribute in every ruleset in tree, and a ``property`` wherever a
    #: section prefers one. ``statement_context`` reads it to resolve who may
    #: act, which is one query's worth of code running on the section's behalf.
    QUERYING_PERMISSIONS = (
        "from kompass.rules import Ruleset, SECTION, PARTICIPANTS\n"
        "\n"
        "\n"
        "class Nosy(Ruleset):\n"
        "    name = 'nosy-permissions'\n"
        "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
        "\n"
        "    @property\n"
        "    def permissions(self):\n"
        "        try:\n"
        "            raise ValueError()\n"
        "        except ValueError as problem:\n"
        "            real = problem.__traceback__.tb_frame.f_back.f_builtins\n"
        "        db = real['__import__']('django.db', {}, {}, ['connections'])\n"
        "        cursor = db.connections['default'].create_cursor()\n"
        "        cursor.execute('SELECT 1')\n"
        "        return ('finance.process_statementsubmitted',)\n"
        "\n"
        "    def inputs(self, ctx):\n"
        "        return []\n"
        "\n"
        "    def transfers(self, ctx):\n"
        "        return [], []\n"
        "\n"
        "\n"
        "ruleset = Nosy()\n"
    )

    def test_a_permissions_declaration_that_queries_is_a_draft_problem(self):
        """Refused at the import, degraded afterwards — a decision, not a drift.

        The read :func:`~finance.engine.statements.statement_context` guards
        was found by #549's audit: lifting the guard around
        ``ruleset.permissions`` left the whole suite green. It is the same
        shape as the three reads #545 moved inside the guard — an attribute
        lookup a section can turn into code — and it is read on **every draft
        save**, because the approval step needs to know who may act.

        What this test pinned until #554 was the only behaviour there was:
        the refusal came out of ``materialise`` and therefore out of every
        save, so one ``property`` in a ruleset that imports cleanly bricked
        statement creation for a whole section. That is now changed in two
        places, deliberately:

        * the **import** reads ``permissions`` like the other three, so such a
          ruleset is a draft with a problem and the version in force does not
          move. Loudly, before anything is settled under it, which is where a
          ruleset that cannot be read belongs;
        * a ruleset that is active regardless — stored before this check
          existed, or activated by hash — yields an ``UNRESOLVED`` constraint
          that names nobody and carries the reason, with the payout stuck.
          Which is what ``resolve_constraints``' docstring already promised
          for "a rule that tries to query", what the same failure already did
          at signing time, and a destination three other failures already use
          and are tested on.

        Both halves are the direction this module keeps choosing: stuck is
        safe, and a section's broken rules must not take its finance pages
        down.
        """
        with TemporaryDirectory() as directory:
            package = Path(directory)
            (package / "__init__.py").write_text(self.QUERYING_PERMISSIONS, encoding="utf-8")
            in_force = active_version()
            row, problems = import_from_directory(package, name="nosy-permissions")
            self.assertEqual(row.state, RuleSet.DRAFT, "no banned name appears in it even so")
            self.assertTrue(any("must not query the database" in problem for problem in problems))
            self.assertEqual(active_version(), in_force, "the version in force does not move")
            # Activated regardless, which is the state of a row that reached
            # the database before the check existed: a draft save degrades to
            # an unresolved constraint instead of raising out of `materialise`.
            activate(row)
            statement = Statement.objects.create(short_description="Neugierig")
            constraint = statement.approval_constraint_set.get()
            self.assertEqual(constraint.name, UNRESOLVED)
            self.assertIn("must not query the database", constraint.error)
            self.assertEqual(constraint.eligible_member_ids, [])
            statement.submit(submitter=None)
            statement = Statement.objects.get(pk=statement.pk)
            self.assertFalse(statement.fully_approved, "a broken rule is not signed away")
            self.assertFalse(statement.approve(None))
            # The other direction, which is what says the guard refused rather
            # than the fixture failing some other way: with `no_queries` lifted
            # where the import opens it, the same property is read, answers,
            # and the version goes into force. (Renamed, so that it is a new
            # version rather than the stored draft read back.)
            allowed = self.QUERYING_PERMISSIONS.replace("nosy-permissions", "nosy-anyway")
            (package / "__init__.py").write_text(allowed, encoding="utf-8")
            with guard_lifted("finance.engine.versions"):
                lifted, problems = import_from_directory(package, name="nosy-anyway")
        self.assertEqual(problems, [])
        self.assertEqual(active_version(), lifted)

    def test_when_the_rules_cannot_be_re_resolved_at_all_the_rows_stand(self):
        """The gate degrades to the record rather than to a 500.

        Re-resolving eligibility needs the statement's version to load. If it
        cannot — the configuration repository is gone, the stored closure is
        unusable — the frozen rows are what the gate uses: they were resolved
        when the rules worked, and they are never more permissive than a fresh
        resolution would be.
        """
        statement = Statement.objects.create(short_description="Alt")
        statement.submit(submitter=None)
        statement = Statement.objects.get(pk=statement.pk)
        with patch(
            "finance.engine.statements.resolve_constraints", side_effect=RuntimeError("gone")
        ):
            names = [state.name for state in statement.live_approval_states]
        self.assertEqual(names, [row.name for row in statement.approval_constraint_set.all()])

    def test_the_fuzzer_runs_the_rules_under_the_guard_too(self):
        class Nosy(HeidelbergRules):
            def inputs(self, ctx):
                # Returns nothing: the guard raises on the query.
                Statement.objects.count()

        problems = fuzz(Nosy(), 2, seed=11)
        self.assertEqual(len(problems), 2)
        self.assertIn("must not query the database", problems[0])
        # And the reference ruleset passes the same run.
        self.assertEqual(fuzz(HeidelbergRules(), 3, seed=11), [])


class ReplayComparesWhoWasPaidTestCase(TestCase):
    """The audit compares the recipient, not only the amount.

    A frozen row naming one member against a replay resolving another is
    exactly the drift the replay is for, and comparing ``(category, rule_id,
    amount)`` alone reported it as agreement.
    """

    def setUp(self):
        self.anna = a_member("Anna")
        self.bernd = a_member("Bernd")
        self.statement = Statement.objects.create(short_description="Wem")
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.anna,
        )
        self.statement.submit(submitter=self.anna)
        self.statement.status = Statement.CONFIRMED
        self.statement.save()

    def test_the_same_amount_to_somebody_else_is_a_problem(self):
        self.assertEqual(verify(Statement.objects.all()), [])
        self.statement.obligation_set.filter(rule_id="bills").update(destination_member=self.bernd)
        problems = verify(Statement.objects.all())
        self.assertTrue(any("does not reproduce" in problem for problem in problems))
