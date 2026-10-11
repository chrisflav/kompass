"""The engine, the typed API and the reference ruleset, each on its own.

The parity suite (:mod:`finance.tests.parity`) checks that the ported rules
produce the old figures. This module checks the machinery around them: that an
undeclared input is an error rather than a zero, that a ruleset cannot query
the database, that an amount of less than a cent is refused, that the books are
closed by the engine and not by the rules, that two versions of a ruleset can
be loaded into one process from their source, and that the import whitelist
says no to what it says no to.
"""

import json
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Group as AuthGroup
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.test import TestCase
from finance.engine import active_ruleset
from finance.engine import build_context
from finance.engine import evaluate
from finance.engine import evaluate_statement
from finance.engine import load
from finance.engine import manifest
from finance.engine import manifest_hash
from finance.engine import no_queries
from finance.engine import parameters
from finance.engine import permission_holders
from finance.engine import QueryDuringEvaluation
from finance.engine import read_sources
from finance.engine import Result
from finance.engine import RulesetInvalid
from finance.engine import RulesetRejected
from finance.engine import source_hash
from finance.engine import sum_amounts
from finance.engine.cases import load_cases
from finance.engine.cases import parse_case
from finance.engine.cases import party
from finance.engine.cases import party_name
from finance.engine.cases import run_case
from finance.engine.cases import run_cases
from finance.engine.context import decimal as to_decimal
from finance.engine.context import member_of
from finance.engine.evaluation import Result as EvaluationResult
from finance.engine.imports import check_source
from finance.engine.imports import check_sources
from finance.engine.loader import FINDER
from finance.engine.loader import package_name
from finance.models import Bill
from finance.models import Statement
from finance.rules_api import Bill as RuleBill
from finance.rules_api import CONTEXT_VERSION
from finance.rules_api import first_of
from finance.rules_api import Input
from finance.rules_api import Inputs
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Params
from finance.rules_api import PARTICIPANTS
from finance.rules_api import pct
from finance.rules_api import quantize
from finance.rules_api import RuleContext
from finance.rules_api import RuleError
from finance.rules_api import Ruleset
from finance.rules_api import SECTION
from finance.rules_api import split
from finance.rules_api import StatementInfo
from finance.rules_api import Transfer
from finance.rulesets.heidelberg import cents
from finance.rulesets.heidelberg import HeidelbergRules
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import MALE
from members.models import Member as MemberModel
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList

#: Where the reference ruleset's own package and cases live.
REFERENCE = Path(__file__).resolve().parent.parent / "rulesets" / "heidelberg"


def context(**overrides):
    """A context with nothing in it but what a test puts there."""
    values = {
        "version": CONTEXT_VERSION,
        "params": Params({"RATE": Decimal("2.50")}),
        "inputs": Inputs({}),
        "bills": (),
        "excursion": None,
        "statement": StatementInfo(id=1, creator=None, submitter=None),
    }
    values.update(overrides)
    return RuleContext(**values)


class Fixed(Ruleset):
    """A ruleset that returns whatever a test hands it."""

    name = "fixed"

    def __init__(self, transfers=(), errors=(), declarations=()):
        self._transfers = list(transfers)
        self._errors = list(errors)
        self._declarations = list(declarations)

    def inputs(self, ctx):
        return list(self._declarations)

    def transfers(self, ctx):
        return list(self._transfers), list(self._errors)


class Broken(Ruleset):
    """A ruleset with a bug in it, which is a section's prerogative."""

    name = "broken"

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        return [Transfer(SECTION, SECTION, Decimal("1.00") / 0, "x", rule_id="boom")], []


class Querying(Ruleset):
    """A ruleset that reaches for the database, which it may not."""

    name = "querying"

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        return [], [f"{Statement.objects.count()} statements"]


# --- the typed API ---------------------------------------------------------


class RulesApiTestCase(SimpleTestCase):
    def test_an_undeclared_input_is_an_error_not_a_zero(self):
        inputs = Inputs({"night_cost": Decimal("1.00")})
        self.assertEqual(inputs.money("night_cost"), Decimal("1.00"))
        with self.assertRaises(RuleError) as caught:
            inputs.raw("nght_cost")
        self.assertIn("night_cost", str(caught.exception))
        with self.assertRaises(RuleError):
            Inputs({}).raw("anything")

    def test_inputs_read_as_attributes_and_list_what_they_hold(self):
        inputs = Inputs({"holiday": True, "flag": "shadowed by the accessor"})
        self.assertIs(inputs.holiday, True)
        self.assertEqual(inputs.declared(), ("holiday", "flag"))
        self.assertIn("holiday", repr(inputs))
        # A key named like an accessor is readable, but not as an attribute.
        self.assertEqual(inputs.raw("flag"), "shadowed by the accessor")
        self.assertTrue(callable(inputs.flag))
        with self.assertRaises(AttributeError):
            inputs._secret

    def test_the_typed_accessors_say_what_they_expected(self):
        inputs = Inputs(
            {
                "money": Decimal("2.00"),
                "number": 3,
                "flag": True,
                "text": "hi",
                "member": Member(MemberId(1)),
                "members": (Member(MemberId(1)),),
                "nobody": None,
                "wrong": "nope",
            }
        )
        self.assertEqual(inputs.money("money"), Decimal("2.00"))
        self.assertEqual(inputs.number("number"), 3)
        self.assertIs(inputs.flag("flag"), True)
        self.assertEqual(inputs.text("text"), "hi")
        self.assertEqual(inputs.member("member"), Member(MemberId(1)))
        self.assertIsNone(inputs.member("nobody"))
        self.assertEqual(inputs.members("members"), (Member(MemberId(1)),))
        wrong = {
            inputs.money: "wrong",
            inputs.number: "wrong",
            inputs.flag: "wrong",
            inputs.text: "number",
            inputs.member: "number",
            inputs.members: "number",
        }
        for accessor, key in wrong.items():
            with self.subTest(accessor=accessor.__name__):
                with self.assertRaises(RuleError):
                    accessor(key)

    def test_parameters_are_decimals_and_unknown_ones_are_an_error(self):
        params = Params({"RATE": Decimal("0.15")})
        self.assertEqual(params.RATE, Decimal("0.15"))
        self.assertEqual(params.get("MISSING", Decimal("1")), Decimal("1"))
        self.assertEqual(params.as_dict(), {"RATE": Decimal("0.15")})
        self.assertIn("RATE", repr(params))
        with self.assertRaises(RuleError) as caught:
            params.RAT
        self.assertIn("RATE", str(caught.exception))
        with self.assertRaises(AttributeError):
            params._hidden
        with self.assertRaises(RuleError):
            Params({}).ANY

    def test_permission_holders_have_to_be_declared(self):
        ctx = context(permissions={"finance.x": (Member(MemberId(2)),)})
        self.assertEqual(ctx.permission_holders("finance.x"), (Member(MemberId(2)),))
        with self.assertRaises(RuleError):
            ctx.permission_holders("finance.y")

    def test_a_ruleset_only_has_to_answer_two_questions(self):
        ruleset = Fixed(declarations=[Input("a", "A", "money")])
        ctx = context()
        self.assertEqual(ruleset.checks(ctx), [])
        self.assertEqual(ruleset.relevant_inputs(ctx), [Input("a", "A", "money")])
        self.assertEqual(ruleset.approval(ctx, []), ([], []))

    def test_split_floors_and_hands_the_remainder_out_from_the_top(self):
        self.assertEqual(
            split(Decimal("0.99"), 5),
            [Decimal("0.20"), Decimal("0.20"), Decimal("0.20"), Decimal("0.20"), Decimal("0.19")],
        )
        self.assertEqual(sum(split(Decimal("10.00"), 3)), Decimal("10.00"))
        self.assertEqual(split(Decimal("10.00"), 1), [Decimal("10.00")])
        self.assertEqual(sum(split(Decimal("-0.99"), 5)), Decimal("-0.99"))
        with self.assertRaises(ValueError):
            split(Decimal("1.00"), 0)

    def test_pct_and_quantize_floor_to_the_cent(self):
        self.assertEqual(pct(Decimal("100.00"), 9000), Decimal("90.00"))
        self.assertEqual(pct(Decimal("1.11"), 1990), Decimal("0.22"))
        self.assertEqual(quantize(Decimal("1.999")), Decimal("1.99"))

    def test_first_of_is_the_fallback_chain(self):
        self.assertEqual(first_of(None, SECTION, PARTICIPANTS), SECTION)
        self.assertIsNone(first_of(None, None))

    def test_the_reference_rounding_is_the_one_kompass_always_used(self):
        self.assertEqual(cents(Decimal("21.675")), Decimal("21.67"))
        self.assertEqual(cents(Decimal("21.676")), Decimal("21.68"))


# --- evaluation ------------------------------------------------------------


class EvaluationTestCase(SimpleTestCase):
    def test_the_engine_closes_the_books_itself(self):
        member = Member(MemberId(1))
        result = evaluate(
            Fixed([Transfer(SECTION, member, Decimal("10.00"), "bill", rule_id="b")]), context()
        )
        self.assertEqual(result.errors, ())
        self.assertTrue(result.ok)
        self.assertEqual(len(result.transfers), 2)
        balance = result.balance
        self.assertEqual((balance.source, balance.destination), (PARTICIPANTS, SECTION))
        self.assertEqual(balance.amount, Decimal("10.00"))
        self.assertEqual(result.net_out(SECTION), Decimal("10.00"))
        self.assertEqual(result.amount_for(member), Decimal("10.00"))
        self.assertEqual(result.members(), (member,))
        self.assertEqual(result.total_of("bill"), Decimal("10.00"))
        self.assertEqual(len(result.of_category("bill")), 1)
        self.assertEqual(result.total_of("nothing"), Decimal("0.00"))

    def test_the_balancing_transfer_turns_round_when_the_section_collects(self):
        member = Member(MemberId(1))
        result = evaluate(
            Fixed([Transfer(member, SECTION, Decimal("5.00"), "fee", rule_id="f")]), context()
        )
        self.assertEqual(
            (result.balance.source, result.balance.destination), (SECTION, PARTICIPANTS)
        )
        self.assertEqual(result.balance.amount, Decimal("5.00"))
        self.assertEqual(result.amount_for(member), Decimal("-5.00"))

    def test_an_amount_finer_than_a_cent_is_refused(self):
        result = evaluate(
            Fixed([Transfer(SECTION, PARTICIPANTS, Decimal("1.005"), "x", rule_id="fine")]),
            context(),
        )
        self.assertEqual(result.rule_transfers, ())
        self.assertIn("whole cents", result.errors[0])

    def test_what_else_a_transfer_may_not_be(self):
        member = Member(MemberId(1))
        refused = [
            ("instead of a Transfer", "not a transfer"),
            ("no source party", Transfer(None, member, Decimal("1.00"), "x", rule_id="a")),
            ("no destination party", Transfer(member, None, Decimal("1.00"), "x", rule_id="b")),
            ("not a Decimal", Transfer(SECTION, member, 1.0, "x", rule_id="c")),
            ("whole cents", Transfer(SECTION, member, Decimal("NaN"), "x", rule_id="d")),
        ]
        for message, candidate in refused:
            with self.subTest(message=message):
                result = evaluate(Fixed([candidate]), context())
                self.assertIn(message, result.errors[0])

    def test_a_transfer_without_a_rule_id_is_still_named_in_the_error(self):
        result = evaluate(
            Fixed([Transfer(SECTION, PARTICIPANTS, Decimal("0.001"), "x", rule_id="")]), context()
        )
        self.assertIn("transfer #0", result.errors[0])

    def test_a_ruleset_that_raises_becomes_an_error_with_a_traceback(self):
        result = evaluate(Broken(), context())
        self.assertEqual(result.transfers, ())
        self.assertIsNone(result.balance)
        self.assertEqual(result.rule_transfers, ())
        self.assertEqual(result.checks, ())
        self.assertIn("the section's rules failed", result.errors[0])
        self.assertIn("transfers", result.errors[0])

    def test_a_balance_declaration_that_names_nothing_is_a_rule_error(self):
        ruleset = Fixed()
        ruleset.balance = (None, SECTION, "x")
        result = evaluate(ruleset, context())
        self.assertIn("balance declaration", result.errors[0])

    def test_an_answer_to_a_question_nobody_asked_is_dropped(self):
        asked = Fixed(declarations=[Input("wanted", "Wanted", "money")])
        ctx = context(inputs=Inputs({"unwanted": "x"}))
        result = evaluate(asked, ctx)
        self.assertEqual([d.key for d in result.declarations], ["wanted"])
        self.assertEqual(result.errors, ())

    def test_a_declared_question_nobody_answered_reads_as_empty(self):
        seen = {}

        class Reader(Fixed):
            def transfers(self, ctx):
                seen["money"] = ctx.inputs.money("money")
                seen["member"] = ctx.inputs.member("member")
                seen["members"] = ctx.inputs.members("members")
                seen["number"] = ctx.inputs.number("number")
                seen["flag"] = ctx.inputs.flag("flag")
                seen["text"] = ctx.inputs.text("text")
                return [], []

        declarations = [
            Input("money", "", "money"),
            Input("member", "", "member"),
            Input("members", "", "member_set"),
            Input("number", "", "int"),
            Input("flag", "", "bool"),
            Input("text", "", "text"),
        ]
        evaluate(Reader(declarations=declarations), context())
        self.assertEqual(
            seen,
            {
                "money": Decimal("0.00"),
                "member": None,
                "members": (),
                "number": 0,
                "flag": False,
                "text": "",
            },
        )

    def test_sum_amounts_is_empty_at_nothing(self):
        self.assertEqual(sum_amounts([]), Decimal("0.00"))
        self.assertIs(Result, EvaluationResult)


class QueryGuardTestCase(TestCase):
    def test_a_rule_that_queries_the_database_is_refused(self):
        result = evaluate(Querying(), context())
        self.assertIn("must not query the database", result.errors[0])

    def test_evaluating_a_statement_makes_no_query_at_all(self):
        statement = Statement.objects.create(short_description="Still", night_cost=0)
        ctx = build_context(statement)
        with self.assertNumQueries(0):
            evaluate(active_ruleset(), ctx)

    def test_the_guard_lifts_again_afterwards(self):
        with no_queries():
            with self.assertRaises(QueryDuringEvaluation):
                Statement.objects.count()
        self.assertEqual(Statement.objects.count(), 0)


# --- the import whitelist --------------------------------------------------


class ImportWhitelistTestCase(SimpleTestCase):
    def test_what_a_ruleset_may_import(self):
        allowed = (
            "import decimal\n"
            "import collections.abc\n"
            "import kompass.rules\n"
            "from decimal import Decimal\n"
            "from kompass.rules import Transfer\n"
            "from . import helpers\n"
            "from .helpers import thing\n"
        )
        self.assertEqual(check_source("rules.py", allowed), [])

    def test_what_it_may_not(self):
        refused = {
            "import os": "may not import os",
            "import django.db": "may not import django.db",
            "from django.conf import settings": "may not import from django.conf",
            "from finance.models import Statement": "may not import from finance.models",
            "value = open('/etc/passwd')": "may not use open",
            "value = __import__('os')": "may not use __import__",
            "now = datetime.now()": "may not read the clock (now)",
            "today = date.today()": "may not read the clock (today)",
            "module = thing.importlib": "may not use importlib",
        }
        for source, expected in refused.items():
            with self.subTest(source=source):
                problems = check_source("rules.py", source)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(expected, problems[0])
                self.assertTrue(problems[0].startswith("rules.py:1:"))

    def test_a_file_that_does_not_parse_is_one_problem(self):
        problems = check_source("rules.py", "def broken(:\n")
        self.assertEqual(len(problems), 1)
        self.assertIn("cannot be parsed", problems[0])

    def test_a_whole_ruleset_is_checked_file_by_file(self):
        problems = check_sources({"b.py": "import os", "a.py": "import sys"})
        self.assertEqual(len(problems), 2)
        self.assertTrue(problems[0].startswith("a.py:"))

    def test_the_reference_ruleset_passes_its_own_check(self):
        self.assertEqual(check_sources(read_sources(REFERENCE)), [])


# --- the loader ------------------------------------------------------------


RULESET_SOURCE = """
from decimal import Decimal

from kompass.rules import Ruleset, SECTION, PARTICIPANTS, Transfer

from .helpers import AMOUNT
from .rates import SHARE


class Simple(Ruleset):
    name = "simple-{tag}"
    balance = (PARTICIPANTS, SECTION, "rest")

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        return [Transfer(SECTION, PARTICIPANTS, AMOUNT * SHARE, "flat", rule_id="flat")], []


ruleset = Simple()
"""

HELPERS_SOURCE = """
from decimal import Decimal

AMOUNT = Decimal("{amount}")
"""

RATES_SOURCE = """
from decimal import Decimal

SHARE = Decimal("1")
"""


def stored(tag, amount):
    """A two-file ruleset package, as a version would be stored."""
    return {
        "__init__.py": RULESET_SOURCE.format(tag=tag),
        "helpers/__init__.py": HELPERS_SOURCE.format(amount=amount),
        "rates.py": RATES_SOURCE,
    }


class LoaderTestCase(SimpleTestCase):
    def test_the_manifest_names_every_file_and_the_hash_covers_the_manifest(self):
        sources = stored("a", "1.00")
        entries = manifest(sources)
        self.assertEqual(sorted(entries), ["__init__.py", "helpers/__init__.py", "rates.py"])
        self.assertEqual(manifest_hash(entries), source_hash(sources))
        self.assertNotEqual(source_hash(sources), source_hash(stored("a", "2.00")))
        renamed = dict(sources)
        renamed["other.py"] = renamed.pop("rates.py")
        self.assertNotEqual(source_hash(sources), source_hash(renamed))

    def test_two_versions_of_a_ruleset_live_in_one_process(self):
        first = load(stored("one", "1.00"))
        second = load(stored("two", "2.00"))
        self.assertNotEqual(type(first).__module__, type(second).__module__)
        self.assertEqual(first.name, "simple-one")
        self.assertEqual(second.name, "simple-two")
        self.assertEqual(
            evaluate(first, context()).balance.amount - Decimal("1.00"),
            Decimal("0.00"),
        )
        self.assertEqual(evaluate(second, context()).balance.amount, Decimal("2.00"))

    def test_loading_the_same_version_twice_returns_the_loaded_one(self):
        sources = stored("again", "3.00")
        self.assertIs(load(sources), load(sources))
        self.assertTrue(package_name(sources).startswith("kompass_rules_"))
        self.assertIsNone(FINDER.find_spec("not_a_ruleset_package"))

    def test_the_reference_ruleset_loads_from_its_own_source(self):
        loaded = load(read_sources(REFERENCE))
        self.assertEqual(loaded.name, active_ruleset().name)
        self.assertIsNot(loaded, active_ruleset())

    def test_a_ruleset_that_is_not_one(self):
        with self.assertRaises(RulesetInvalid):
            load({"helpers.py": "x = 1"})
        with self.assertRaises(RulesetInvalid):
            load({"__init__.py": "ruleset = 1"})

    def test_a_ruleset_written_against_a_newer_context(self):
        source = (
            "from kompass.rules import Ruleset, SECTION, PARTICIPANTS\n"
            "class Future(Ruleset):\n"
            f"    context_version = {CONTEXT_VERSION + 1}\n"
            "    def inputs(self, ctx):\n        return []\n"
            "    def transfers(self, ctx):\n        return [], []\n"
            "ruleset = Future()\n"
        )
        with self.assertRaises(RulesetInvalid) as caught:
            load({"__init__.py": source})
        self.assertIn("context version", str(caught.exception))

    def test_a_ruleset_the_whitelist_refuses_is_never_executed(self):
        with self.assertRaises(RulesetRejected) as caught:
            load({"__init__.py": "import os\nruleset = None\n"})
        self.assertEqual(len(caught.exception.problems), 1)

    def test_a_ruleset_that_fails_while_it_is_imported_leaves_nothing_behind(self):
        import sys

        sources = {"__init__.py": "raise ValueError('nope')\n"}
        with self.assertRaises(ValueError):
            load(sources)
        self.assertNotIn(package_name(sources), sys.modules)

    def test_reading_a_package_from_disk_keeps_posix_paths(self):
        sources = read_sources(REFERENCE)
        self.assertIn("__init__.py", sources)
        self.assertTrue(all("\\" not in path for path in sources))


# --- the context -----------------------------------------------------------


class ContextTestCase(TestCase):
    def setUp(self):
        self.member = MemberModel.objects.create(
            prename="Kontext", lastname="Test", birth_date=None, email="k@localhost", gender=MALE
        )
        self.statement = Statement.objects.create(short_description="Kontext", night_cost="12.50")

    def test_money_arrives_as_a_decimal_of_the_text_not_of_the_float(self):
        self.assertEqual(to_decimal(0.15), Decimal("0.15"))
        self.assertEqual(to_decimal("3"), Decimal("3"))
        self.assertIsNone(member_of(None))
        self.assertEqual(member_of(4), Member(MemberId(4)))

    def test_a_submitted_statement_reads_its_own_snapshot(self):
        live = parameters(self.statement)
        self.assertEqual(live["ALLOWANCE_PER_DAY"], Decimal("22"))
        self.statement.submit(submitter=self.member)
        self.statement.settings_snapshot["ALLOWANCE_PER_DAY"] = 30.0
        del self.statement.settings_snapshot["MAX_NIGHT_COST"]
        snapshot = parameters(self.statement)
        self.assertEqual(snapshot["ALLOWANCE_PER_DAY"], Decimal("30.0"))
        self.assertEqual(snapshot["MAX_NIGHT_COST"], Decimal("11"))

    def test_a_statement_without_a_trip_has_no_excursion_in_its_context(self):
        Bill.objects.create(
            statement=self.statement,
            short_description="Essen",
            amount=Decimal("5.00"),
            costs_covered=True,
            paid_by=self.member,
        )
        ctx = build_context(self.statement)
        self.assertIsNone(ctx.excursion)
        self.assertEqual(ctx.version, CONTEXT_VERSION)
        self.assertEqual(
            ctx.bills,
            (
                RuleBill(
                    id=self.statement.bill_set.get().pk,
                    amount=Decimal("5.00"),
                    covered=True,
                    payer=Member(MemberId(self.member.pk)),
                    has_proof=False,
                    description="Essen",
                ),
            ),
        )
        self.assertEqual(ctx.inputs.money("night_cost"), Decimal("12.50"))
        self.assertEqual(ctx.roles, {})

    def test_the_trip_is_copied_out_with_both_ages(self):
        excursion = Freizeit.objects.create(
            name="Kontextfahrt",
            kilometers_traveled=12,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        excursion.jugendleiter.add(self.member)
        NewMemberOnList.objects.create(member=self.member, memberlist=excursion)
        self.statement.excursion = excursion
        self.statement.save()
        ctx = build_context(self.statement)
        self.assertEqual(ctx.excursion.approach, "muscle")
        self.assertEqual(ctx.excursion.kilometers, 12)
        self.assertEqual(ctx.excursion.leaders, (Member(MemberId(self.member.pk)),))
        self.assertIsNone(ctx.excursion.ljp)
        participant = ctx.excursion.participants[0]
        self.assertTrue(participant.is_leader)
        # The member has no birth date, so neither age is known — and the
        # organisation fee then counts them as not older than 27 rather than
        # falling over, which is what the old property did.
        self.assertIsNone(participant.age)
        self.assertIsNone(participant.age_at_start)

    def test_answers_can_be_handed_in_for_a_dry_run(self):
        ctx = build_context(self.statement, inputs={"night_cost": Decimal("1.00")})
        self.assertEqual(ctx.inputs.money("night_cost"), Decimal("1.00"))

    def test_who_holds_a_permission_is_resolved_against_the_real_system(self):
        codename = "process_statementsubmitted"
        permission = Permission.objects.get(codename=codename)
        direct = User.objects.create_user("direct")
        direct.user_permissions.add(permission)
        MemberModel.objects.create(
            prename="Direkt", lastname="T", email="d@localhost", gender=MALE, user=direct
        )
        group = AuthGroup.objects.create(name="Kasse")
        group.permissions.add(permission)
        grouped = User.objects.create_user("grouped")
        grouped.groups.add(group)
        MemberModel.objects.create(
            prename="Gruppe", lastname="T", email="g@localhost", gender=MALE, user=grouped
        )
        root = User.objects.create_superuser("root", "root@localhost", "x")
        MemberModel.objects.create(
            prename="Root", lastname="T", email="r@localhost", gender=MALE, user=root
        )
        holders = permission_holders([f"finance.{codename}"])[f"finance.{codename}"]
        self.assertEqual(len(holders), 3)
        # Without an app label every permission of that codename counts.
        self.assertEqual(len(permission_holders([codename])[codename]), 3)
        self.assertEqual(permission_holders([]), {})

    def test_a_statement_offers_its_transfers_as_a_property(self):
        self.assertEqual(self.statement.transfers, self.statement.rule_result.transfers)
        self.assertEqual(self.statement.transfers[-1].rule_id, "balance")

    def test_a_category_this_app_has_no_wording_for_keeps_the_rules_label(self):
        other = Transfer(SECTION, PARTICIPANTS, Decimal("1.00"), "jahresbeitrag", rule_id="x")
        self.assertEqual(self.statement._transfer_reference(other), "jahresbeitrag")
        labelled = Transfer(
            SECTION, PARTICIPANTS, Decimal("1.00"), "jahresbeitrag", rule_id="x", label="Beitrag"
        )
        self.assertEqual(self.statement._transfer_reference(labelled), "Beitrag")

    def test_the_payout_payload_names_every_party(self):
        payload = self.statement.transfer_payload()
        self.assertEqual(payload[-1]["source"], {"kind": "participants", "member": None})
        self.assertEqual(payload[-1]["destination"], {"kind": "section", "member": None})
        self.assertIsNone(self.statement.org_fee_payant)

    def test_the_reference_ruleset_asks_for_the_approver_permission(self):
        result = evaluate_statement(self.statement)
        self.assertEqual(result.errors, ())
        constraints, forbids = active_ruleset().approval(
            build_context(self.statement, permissions=active_ruleset().permissions),
            list(result.transfers),
        )
        self.assertEqual(forbids, [])
        self.assertEqual(constraints[0].required, 1)
        self.assertTrue(constraints[0].applicable)
        self.assertEqual(constraints[0].eligible, ())


# --- cases -----------------------------------------------------------------


class CasesTestCase(SimpleTestCase):
    def test_the_reference_rulesets_cases_all_pass(self):
        self.assertEqual(run_cases(active_ruleset(), REFERENCE / "cases"), {})
        self.assertEqual(len(load_cases(REFERENCE / "cases")), 6)

    def test_a_failing_case_is_reported_by_name(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.json"
            path.write_text(
                json.dumps({"name": "impossible", "expect": {"transfers": []}}),
                encoding="utf-8",
            )
            failed = run_cases(active_ruleset(), Path(directory))
        self.assertEqual(list(failed), ["impossible"])

    def test_a_case_names_its_parties_the_way_a_person_would(self):
        self.assertEqual(party("SECTION"), SECTION)
        self.assertEqual(party("PARTICIPANTS"), PARTICIPANTS)
        self.assertEqual(party(7), Member(MemberId(7)))
        self.assertEqual(party_name(SECTION), "SECTION")
        self.assertEqual(party_name(PARTICIPANTS), "PARTICIPANTS")
        self.assertEqual(party_name(Member(MemberId(7))), "7")

    def test_a_case_with_nothing_in_it_is_a_statement_with_nothing_in_it(self):
        case = parse_case({}, name="empty")
        self.assertEqual(case.name, "empty")
        self.assertIsNone(case.context.excursion)
        self.assertIsNone(case.checks)
        # Even an empty statement has the engine's balancing transfer, and a
        # case that does not say so fails — which is the point of saying so.
        failures = run_case(Fixed(), case)
        self.assertEqual(len(failures), 1)
        self.assertIn("balance", failures[0])

    def test_a_case_reports_every_way_it_can_go_wrong(self):
        case = parse_case(
            {
                "name": "wrong",
                "params": {"RATE": "1.00"},
                "inputs": {"night_cost": "2.00", "extra": 1},
                "bills": [{"amount": "3.00", "covered": True, "payer": 1}],
                "excursion": {
                    "duration": "1.0",
                    "leaders": [1],
                    "participants": [{"member": 1, "age": 30, "is_leader": True}],
                    "ljp": {"goal": "participation", "theoretic_participant_count": 9},
                },
                "permissions": {"finance.x": [1]},
                "expect": {
                    "transfers": [["SECTION", "1", "9.99", "bill"]],
                    "errors": ["nope"],
                    "checks": [False],
                },
            },
            name="file",
        )
        self.assertEqual(case.context.inputs.raw("extra"), 1)
        self.assertEqual(case.context.excursion.ljp.goal, "participation")
        self.assertEqual(case.context.permission_holders("finance.x"), (Member(MemberId(1)),))
        failures = run_case(active_ruleset(), case)
        self.assertEqual(len(failures), 3)
        self.assertTrue(failures[0].startswith("transfers"))
        self.assertTrue(failures[1].startswith("errors"))
        self.assertTrue(failures[2].startswith("checks"))
        self.assertEqual(set(run_cases(active_ruleset(), REFERENCE / "cases")), set())


# --- the reference ruleset's own edges -------------------------------------


class ReferenceRulesetTestCase(SimpleTestCase):
    def test_it_declares_the_four_answers_it_needs(self):
        declarations = HeidelbergRules().inputs(context())
        self.assertEqual(
            [declaration.key for declaration in declarations],
            ["night_cost", "allowance_to", "subsidy_to", "ljp_to"],
        )
        self.assertEqual(declarations[1].options, ())
        self.assertEqual(declarations[1].max, 0)

    def test_the_ljp_check_asks_for_a_picture_of_every_bill(self):
        ctx = context(
            inputs=Inputs({"ljp_to": Member(MemberId(1))}),
            bills=(
                RuleBill(
                    id=1,
                    amount=Decimal("1.00"),
                    covered=True,
                    payer=Member(MemberId(1)),
                    has_proof=False,
                    description="Beleg",
                ),
            ),
        )
        checks = HeidelbergRules().checks(ctx)
        self.assertFalse(checks[0].ok)
        self.assertIn("Bild", checks[0].message)
