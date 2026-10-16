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
import sys
import threading
from contextlib import nullcontext
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Group as AuthGroup
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.db import connections
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
from finance.engine.evaluation import party_key
from finance.engine.evaluation import party_label
from finance.engine.evaluation import Result as EvaluationResult
from finance.engine.imports import check_source
from finance.engine.imports import check_sources
from finance.engine.loader import FINDER
from finance.engine.loader import package_name
from finance.engine.loader import safe_builtins
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
from finance.rulesets.heidelberg import ruleset as reference
from finance.tests.harness import guard_lifted
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
        rules = active_ruleset()
        ctx = build_context(statement)
        with self.assertNumQueries(0):
            evaluate(rules, ctx)

    def test_the_guard_lifts_again_afterwards(self):
        with no_queries():
            with self.assertRaises(QueryDuringEvaluation):
                Statement.objects.count()
        self.assertEqual(Statement.objects.count(), 0)

    def test_every_route_to_the_database_refuses_and_not_only_the_wrapped_one(self):
        """The first version of this guard wrapped ``execute`` and nothing else.

        ``create_cursor`` is the backend's own factory, ``chunked_cursor``
        hands out a server-side cursor, and ``connection.connection`` is the
        driver's own connection object, which knows nothing about Django at
        all. Each one reaches the database without passing a ``CursorWrapper``,
        so each one was a way past the guard while a rule was running.

        What this does **not** pin is :data:`GUARDED_METHODS`: with a live
        connection the driver object has been taken away, so every route here
        runs into the refusing proxy on its way down and still raises with any
        one method missing from that list. The test below is the one that
        pins it.
        """
        connection = connections["default"]
        connection.ensure_connection()
        with no_queries():
            for route in (
                connection.cursor,
                connection._cursor,
                connection.create_cursor,
                connection.chunked_cursor,
                connection.ensure_connection,
                connection.connect,
            ):
                with self.assertRaises(QueryDuringEvaluation):
                    route()
            with self.assertRaises(QueryDuringEvaluation):
                connection.connection.cursor()
        # And the connection is itself again afterwards, driver object included.
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)
        self.assertIsNotNone(connection.connection.cursor())

    def test_the_routes_refuse_with_no_live_connection_to_take_away(self):
        """The guard's other half, and the one :data:`GUARDED_METHODS` is for.

        Found by the audit in #549: dropping ``create_cursor`` from that list
        left every guard test green, because the test above runs with a live
        connection whose driver object has been swapped for the refusing
        proxy — so the backend's factory refuses on its way down whether or
        not it is on the list. A connection that is not open yet has no driver
        object to take away, which is the ordinary state of a worker that has
        not served a request yet, and then the patch on the connection class
        is the only thing standing there. One route missing from the list is a
        rule with a cursor.
        """
        connection = connections["default"]
        connection.ensure_connection()
        live = connection.connection
        # The same trick the guard itself uses, and put back the same way: the
        # object is never closed, only set aside, so the surrounding test
        # transaction is untouched.
        connection.connection = None
        try:
            with no_queries():
                self.assertIsNone(connection.connection, "nothing was swapped in")
                for route in (
                    connection.cursor,
                    connection._cursor,
                    connection.create_cursor,
                    connection.chunked_cursor,
                    connection.ensure_connection,
                    connection.connect,
                ):
                    with self.assertRaises(QueryDuringEvaluation):
                        route()
        finally:
            connection.connection = live
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_a_cursor_taken_before_the_block_still_refuses_to_execute(self):
        """The execute wrapper stays, as the second net.

        A cursor that predates the block is the one thing the connection-level
        guard cannot take away, so the wrapper that the first version of this
        guard relied on alone is kept for exactly that case.
        """
        connection = connections["default"]
        with connection.cursor() as cursor:
            with no_queries():
                with self.assertRaises(QueryDuringEvaluation):
                    cursor.execute("SELECT 1")
            cursor.execute("SELECT 1")
            self.assertEqual(cursor.fetchone()[0], 1)


class PartyIdentityTestCase(SimpleTestCase):
    """What makes two parties the same party, for netting and for storage.

    :class:`~kompass.rules.Member` is a frozen dataclass, so ``==`` is
    class-exact. A section that subclassed it to carry one more field would
    have had money net against one identity and be stored under another, which
    is the same root as the first review round's finding about ``verify()``
    comparing amounts without comparing recipients.
    """

    def test_a_party_is_the_same_party_whatever_class_it_wears(self):
        class Tagged(Member):
            pass

        plain, tagged = Member(MemberId(7)), Tagged(MemberId(7))
        self.assertNotEqual(plain, tagged, "equality is class-exact, which is the trap")
        self.assertEqual(party_key(plain), party_key(tagged))
        self.assertEqual(party_key(SECTION), ("section", None))
        self.assertEqual(party_key(PARTICIPANTS), ("participants", None))
        self.assertEqual(party_label(plain), "member 7")
        self.assertEqual(party_label(tagged), "member 7")
        self.assertEqual(party_label(SECTION), "the section")
        self.assertEqual(party_label(PARTICIPANTS), "the participants")

    def test_money_nets_against_the_subclass_too(self):
        class Tagged(Member):
            pass

        transfers = [
            Transfer(SECTION, Tagged(MemberId(7)), Decimal("5.00"), "a", rule_id="a"),
            Transfer(Member(MemberId(7)), SECTION, Decimal("2.00"), "b", rule_id="b"),
        ]
        result = Result(
            transfers=tuple(transfers), errors=(), checks=(), declarations=(), balance=None
        )
        self.assertEqual(result.amount_for(Member(MemberId(7))), Decimal("3.00"))

    def test_the_balance_is_checked_after_the_fact_as_well(self):
        """An assertion, with the proof that it fires.

        ``_balance_for`` resolves its amount so that the declared party nets to
        zero, so this cannot fail as the code stands — which is the point of
        checking it rather than asserting it in a docstring: the day somebody
        changes the arithmetic above it, the check is what notices. A check
        nobody has ever seen fail is a check nobody knows works, so the netting
        is forced to disagree with itself here.
        """
        with patch(
            "finance.engine.evaluation._net_out",
            side_effect=[Decimal("10.00"), Decimal("0.01")],
        ):
            result = evaluate(Fixed(), context())
        self.assertIn("out by 0.01", result.errors[0])
        self.assertEqual(result.transfers, ())


class FrameEscapeTestCase(TestCase):
    """The escape no blacklist catches, and the guard that catches it anyway.

    Four lines that mention no banned name reach a caller's frame and read its
    ``f_builtins`` — the interpreter's real builtins, not the restricted
    mapping the loader installs — and from there ``__import__`` and every
    module in the process. The whitelist passing this is not a bug to be fixed
    by adding ``f_builtins`` to a list; it is why the guarantee that matters
    lives at the database connection instead.

    Each ruleset below reaches the database by a route that does **not** go
    through a Django ``CursorWrapper``, because the execute wrapper the first
    version of this guard relied on would have caught the wrapper route — a
    test written that way passes against the guard it was meant to replace.
    """

    PREAMBLE = (
        "from kompass.rules import Ruleset, SECTION, PARTICIPANTS\n"
        "\n"
        "\n"
        "def reach():\n"
        "    try:\n"
        "        raise ValueError()\n"
        "    except ValueError as problem:\n"
        "        real = problem.__traceback__.tb_frame.f_back.f_builtins\n"
        "    return real['__import__']('django.db', {}, {}, ['connections'])\n"
        "\n"
        "\n"
    )

    @classmethod
    def ruleset_source(cls, body):
        """A ruleset whose ``transfers`` runs ``body``, indented into place."""
        lines = "".join(f"        {line}\n" for line in body)
        return (
            cls.PREAMBLE + "class Escaping(Ruleset):\n"
            "    name = 'escaping'\n"
            "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
            "\n"
            "    def inputs(self, ctx):\n"
            "        return []\n"
            "\n"
            "    def transfers(self, ctx):\n" + lines + "        return [], []\n"
            "\n"
            "\n"
            "ruleset = Escaping()\n"
        )

    def test_the_backends_own_cursor_factory_refuses(self):
        """`create_cursor` is the backend's factory; no wrapper is involved.

        Which of the guard's two halves refuses it here is not pinned —
        see ``test_the_routes_refuse_with_no_live_connection_to_take_away``.
        """
        sources = {
            "__init__.py": self.ruleset_source(
                [
                    "db = reach()",
                    "conn = db.connections['default']",
                    "cursor = conn.create_cursor()",
                    "cursor.execute('SELECT 1')",
                ]
            )
        }
        self.assertEqual(check_sources(sources), [], "no name in it is on any list")
        result = evaluate(load(sources), context())
        self.assertIn("must not query the database", result.errors[0])
        self.assertEqual(result.transfers, ())

    def test_the_driver_connection_is_gone_and_hands_nothing_back(self):
        """The proxy used to keep the real connection in a slot called `real`.

        Ordinary attribute lookup finds a slot without ever reaching
        ``__getattr__``, so the fix for a name blacklist had a one-word name
        in it that no list banned.
        """
        sources = {
            "__init__.py": self.ruleset_source(
                [
                    "db = reach()",
                    "conn = db.connections['default']",
                    "cursor = conn.connection.real.cursor()",
                    "cursor.execute('SELECT 1')",
                ]
            )
        }
        result = evaluate(load(sources), context())
        self.assertIn("must not query the database", result.errors[0])
        self.assertIn("connection.connection.real", result.errors[0])

    def test_a_module_body_may_not_query_either(self):
        """The import ran outside the guard, which was two holes at once.

        A ruleset could query while being imported, and keep the cursor it got
        for later use inside `transfers` — where a raw driver cursor goes past
        the execute wrapper. Guarded, there is no moment at which a section's
        own code runs unguarded, so there is nothing to stash.
        """
        source = (
            self.PREAMBLE + "STASH = reach().connections['default'].create_cursor()\n"
            "\n"
            "\n"
            "class Escaping(Ruleset):\n"
            "    name = 'escaping-import'\n"
            "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
            "\n"
            "    def inputs(self, ctx):\n"
            "        return []\n"
            "\n"
            "    def transfers(self, ctx):\n"
            "        STASH.execute('SELECT 1')\n"
            "        return [], []\n"
            "\n"
            "\n"
            "ruleset = Escaping()\n"
        )
        with self.assertRaises(QueryDuringEvaluation):
            load({"__init__.py": source})

    def test_the_exported_ruleset_may_not_query_while_it_is_being_read(self):
        """`as_ruleset` ran one line after the guard lifted.

        Reading `module.ruleset` looks like reading data, and is a call into
        the section's own code whenever the section wants it to be: a module
        may define `__getattr__` (PEP 562). `load` returned *through*
        `as_ruleset` from outside the `with no_queries():` block, so that read
        was the one line of a ruleset that ran unguarded — and a cursor taken
        there is a cursor `transfers` can use later, past the execute wrapper.
        """
        source = (
            self.PREAMBLE + "class Lazy(Ruleset):\n"
            "    name = 'lazy-export'\n"
            "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
            "\n"
            "    def inputs(self, ctx):\n"
            "        return []\n"
            "\n"
            "    def transfers(self, ctx):\n"
            "        return [], []\n"
            "\n"
            "\n"
            "def __getattr__(name):\n"
            "    cursor = reach().connections['default'].create_cursor()\n"
            "    cursor.execute('SELECT 1')\n"
            "    return Lazy()\n"
        )
        sources = {"__init__.py": source}
        self.assertEqual(check_sources(sources), [], "no name in it is on any list")
        with self.assertRaises(QueryDuringEvaluation):
            load(sources)
        # The other direction, which is what says the guard is what refused
        # rather than something about the fixture: with the one line this test
        # exists for lifted, the same read goes through and hands back a
        # ruleset. Neuter the fix, watch it go red — as code.
        with guard_lifted("finance.engine.loader"):
            self.assertEqual(load(sources).name, "lazy-export")

    def test_a_context_version_that_queries_is_refused_as_well(self):
        """The second read `as_ruleset` makes, and a `property` is rule code.

        `exported.context_version` is compared against this Kompass's own, so
        it is read on every load of every version — and a ruleset that
        declares it as a property has the engine call its code to get it.
        """
        source = (
            self.PREAMBLE + "class Nosy(Ruleset):\n"
            "    name = 'nosy-version'\n"
            "    balance = (PARTICIPANTS, SECTION, 'rest')\n"
            "\n"
            "    @property\n"
            "    def context_version(self):\n"
            "        cursor = reach().connections['default'].create_cursor()\n"
            "        cursor.execute('SELECT 1')\n"
            "        return 1\n"
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
        sources = {"__init__.py": source}
        self.assertEqual(check_sources(sources), [])
        with self.assertRaises(QueryDuringEvaluation):
            load(sources)
        with guard_lifted("finance.engine.loader"):
            self.assertEqual(load(sources).context_version, 1)


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
            "now = datetime.now()": "may not read the clock (now())",
            "today = date.today()": "may not read the clock (today())",
            "module = thing.importlib": "may not use importlib",
            # The way out the proposal said was not there.
            "x = thing.__class__": "may not reach through __class__",
            "x = thing.__globals__": "may not reach through __globals__",
            "x = getattr(thing, 'y')": "may not use getattr",
            "x = __builtins__['open']": "may not use __builtins__",
        }
        for source, expected in refused.items():
            with self.subTest(source=source):
                problems = check_source("rules.py", source)
                self.assertEqual(len(problems), 1, problems)
                self.assertIn(expected, problems[0])
                self.assertTrue(problems[0].startswith("rules.py:1:"))

    def test_what_the_check_used_to_let_through(self):
        """The chain that reached a database connection in one line.

        `__loader__.__class__.__init__.__globals__["sys"]` walks out of the
        module the engine executed into the engine's own globals. The textual
        check refuses it here; the loader's restricted `__builtins__` is the
        other half, for the forms of it nobody wrote down.
        """
        escape = 'c = __loader__.__class__.__init__.__globals__["sys"]\n'
        problems = check_source("rules.py", escape)
        self.assertTrue(problems)
        self.assertTrue(all("may not" in problem for problem in problems))

    def test_a_ruleset_is_executed_without_open_or_getattr(self):
        available = safe_builtins()
        for name in ("open", "eval", "exec", "getattr", "globals", "compile", "dir"):
            self.assertNotIn(name, available)
        # And with what a rule actually needs, including the two hooks the
        # interpreter calls for `import` and `class`.
        for name in ("min", "sum", "sorted", "isinstance", "__import__", "__build_class__"):
            self.assertIn(name, available)

    def test_a_compiler_directive_is_not_an_import(self):
        self.assertEqual(check_source("rules.py", "from __future__ import annotations\n"), [])

    def test_a_field_named_now_is_not_the_clock(self):
        self.assertEqual(check_source("rules.py", "x = ctx.statement.now\n"), [])

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

    def test_the_two_dunders_ordinary_python_needs(self):
        """A parameterised base ruleset and a ruleset that labels itself.

        ``super().__init__(…)`` and ``self.__class__.__name__`` are the two
        spellings the dunder list refused and should not have: a section
        writing a base class with parameters hits the first on its second
        ruleset, and neither reaches anything. What they must not open is the
        chain the list exists for, so the attribute *after* a ``__class__`` is
        still what decides.
        """
        allowed = (
            "class Base:\n"
            "    def __init__(self, rate):\n"
            "        self.rate = rate\n"
            "\n"
            "class Derived(Base):\n"
            "    def __init__(self):\n"
            "        super().__init__(2)\n"
            "    def label(self):\n"
            "        return self.__class__.__name__ + self.__class__.__qualname__\n"
        )
        self.assertEqual(check_source("a.py", allowed), [])
        for escape in (
            "x = self.__class__.__init__\n",
            "x = self.__class__.__mro__\n",
            "x = other.__init__\n",
            "x = self.__class__.__bases__\n",
        ):
            self.assertTrue(check_source("a.py", escape), escape)


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


#: A helpers module whose *body* takes long enough to lose the GIL several
#: times over (the switch interval is 5 ms). The package's ``__init__`` is
#: therefore half-executed for a measurable while, which is the window the old
#: loader published a module into.
SLOW_HELPERS_SOURCE = """
from decimal import Decimal

AMOUNT = Decimal("0")
for _tick in range(30000):
    AMOUNT += Decimal("{amount}") / Decimal("30000")
"""


def stored(tag, amount, *, slow=False):
    """A two-file ruleset package, as a version would be stored."""
    helpers = SLOW_HELPERS_SOURCE if slow else HELPERS_SOURCE
    return {
        "__init__.py": RULESET_SOURCE.format(tag=tag),
        "helpers/__init__.py": helpers.format(amount=amount),
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
        self.assertEqual(loaded.name, reference.name)
        self.assertIsNot(loaded, reference)

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
        # Unresolved, not empty: reading a role from the arithmetic's context
        # raises rather than quietly answering "nobody".
        self.assertFalse(ctx.roles.resolved)
        with self.assertRaises(RuleError):
            ctx.roles["kassenwart"]
        with self.assertRaises(RuleError):
            ctx.role_holders("kassenwart")

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
        self.assertEqual(run_cases(reference, REFERENCE / "cases"), {})
        self.assertEqual(len(load_cases(REFERENCE / "cases")), 7)

    def test_a_failing_case_is_reported_by_name(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "wrong.json"
            path.write_text(
                json.dumps({"name": "impossible", "expect": {"transfers": []}}),
                encoding="utf-8",
            )
            failed = run_cases(reference, Path(directory))
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
        failures = run_case(reference, case)
        self.assertEqual(len(failures), 3)
        self.assertTrue(failures[0].startswith("transfers"))
        self.assertTrue(failures[1].startswith("errors"))
        self.assertTrue(failures[2].startswith("checks"))
        self.assertEqual(set(run_cases(reference, REFERENCE / "cases")), set())


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


class ConcurrentLoadTestCase(SimpleTestCase):
    """Two threads loading one version must both get that version.

    The loader used to publish the module into ``sys.modules`` before executing
    it, which bypasses importlib's per-module lock: a second thread arriving
    mid-exec read a module with no ``ruleset`` in it, `as_ruleset` refused it,
    and the caller fell back to the *reference* ruleset and materialised those
    figures. uwsgi runs four threads per process and recycles on RSS, so a cold
    worker taking concurrent requests is routine.

    Two things hold the property now, and they are tested apart because the
    audit in #549 found the first hiding the second: ``_LOAD_LOCK`` serialises
    a whole load, so the test below stays green even against a faithful
    reimplementation of the racy loader, and ``import_module`` publishes
    nothing until the body has run.
    """

    def loaded_by_six_threads(self, sources):
        """Six threads calling ``load`` at once, and what came back."""
        results: list[object] = []
        errors: list[BaseException] = []

        def load_it():
            try:
                results.append(load(sources))
            except BaseException as problem:  # pragma: no cover - the bug
                errors.append(problem)

        threads = [threading.Thread(target=load_it) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(results), 6)
        return results

    def test_six_threads_loading_at_once_all_get_the_same_ruleset(self):
        # `slow=True` is what gives this test teeth: with a package body that
        # executes faster than a thread switch, six threads serialise by luck
        # and the old racy loader passed too.
        sources = stored("concurrent", "7.00", slow=True)
        results = self.loaded_by_six_threads(sources)
        self.assertEqual({type(ruleset).__module__ for ruleset in results}, {package_name(sources)})
        self.assertEqual({ruleset.name for ruleset in results}, {"simple-concurrent"})

    def test_the_import_is_atomic_without_the_lock_around_the_registry(self):
        """And this is the test that pins ``import_module``.

        ``_LOAD_LOCK`` is there for the finder's registry, and it happens to
        serialise the import as well — which is why the test above cannot see
        the difference between `import_module` and the publish-then-exec
        sequence it replaced. With the lock out of the way the import is on
        its own: it holds importlib's per-module lock and publishes nothing
        until the body has run, so a thread arriving mid-exec waits rather
        than reading a module with no ``ruleset`` in it.
        """
        sources = stored("unlocked", "8.00", slow=True)
        with patch("finance.engine.loader._LOAD_LOCK", nullcontext()):
            results = self.loaded_by_six_threads(sources)
        self.assertEqual({type(ruleset).__module__ for ruleset in results}, {package_name(sources)})
        self.assertEqual({ruleset.name for ruleset in results}, {"simple-unlocked"})
