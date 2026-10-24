"""Who makes the transfers, and what the terminal act of a review then is.

Two arrangements exist among JDAV sections and Kompass only ever implemented
one. Heidelberg's finance department makes the bank transfers itself, off the
review screen, and a released statement is *ausgezahlt*. Ludwigsburg's
Geschäftsstelle makes them afterwards, from the Beleg it receives, and a
released statement is *zur Auszahlung übergeben* — Kompass never learns that
the money moved. No wording is true in both, so the mode is a declaration of
the section's rules (:attr:`kompass.rules.Ruleset.payout`) and the last step
genuinely branches on it.

What this module pins:

* the **declaration**: what each ruleset says, what the stored version
  records, and that a mode Kompass cannot read keeps the version out of force
  rather than falling back to one of the two false sentences;
* the **binding**: a statement keeps the arrangement it was created under, so
  a released statement's terminal act cannot change meaning later;
* the **handoff**: in office mode the mail *is* the release, it goes from the
  one funnel every release passes through, and the status does not move until
  it has gone;
* the **paper**: the summary carries one payment order per booking — the
  recipient, the account, the reference, the amount, and the fact that two
  amounts to one person may not be combined — because in that mode the
  document is the only thing the person making the transfers ever sees;
* and that **none of it touches a section that pays from the review screen**,
  which is the shipped behaviour and the reference ruleset.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase
from django.test import TestCase
from finance.engine import check_directory
from finance.engine import import_from_directory
from finance.engine import reference_directory
from finance.engine.versions import active_version
from finance.engine.versions import declared_payout
from finance.engine.versions import payout_problems
from finance.models import Statement
from finance.rules_api import OFFICE_PAYMENT
from finance.rules_api import SELF_PAYMENT
from finance.rulesets.heidelberg import HeidelbergRules
from finance.store import ImmutableRuleSet
from finance.store import RuleSet
from finance.tests.store import querying_field

#: ``HANDOFF`` with a quorum of two, for the refusal short of one.
#:
#: The wording of that refusal is the mode's as well — "cannot be paid out
#: yet" is false where nobody on this screen pays anything — and a section
#: with one signature can never produce it.
TWO_OF_THEM = "    required=1,"

#: A ruleset whose section's office makes the transfers.
#:
#: Deliberately the smallest thing that is still a ruleset: one covered bill
#: paid back to whoever paid it, one signature from whoever holds the
#: capability. What is under test is the declaration on the second line, and
#: everything else is scaffolding for a statement that can actually be
#: released.
HANDOFF = '''
from kompass.rules import Constraint, OFFICE_PAYMENT, Ruleset, SECTION, PARTICIPANTS, Transfer


class Handoff(Ruleset):
    """A section whose Geschäftsstelle makes the transfers."""

    name = "handoff"
    permissions = ("finance.process_statementsubmitted",)
    balance = (PARTICIPANTS, SECTION, "participant_contribution")
    payout = OFFICE_PAYMENT

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        transfers = []
        for bill in ctx.bills:
            if bill.covered and bill.payer is not None:
                transfers.append(
                    Transfer(SECTION, bill.payer, bill.amount, "bill", rule_id="bills")
                )
        return transfers, []

    def approval(self, ctx, transfers):
        return (
            [
                Constraint(
                    name="Freigabe",
                    description="Eine Unterschrift",
                    applicable=True,
                    required=1,
                    eligible=ctx.permission_holders("finance.process_statementsubmitted"),
                )
            ],
            [],
        )


ruleset = Handoff()
'''


def with_mode(source, mode):
    """``HANDOFF`` with its declaration replaced by ``mode``, verbatim."""
    return source.replace("payout = OFFICE_PAYMENT", f"payout = {mode}")


def imported(source, name):
    """Import ``source`` as a ruleset package of its own."""
    with TemporaryDirectory() as directory:
        package = Path(directory)
        (package / "__init__.py").write_text(source, encoding="utf-8")
        return import_from_directory(package, name=name)


def checked(source):
    """Run ``source`` past everything :func:`check_directory` checks."""
    with TemporaryDirectory() as directory:
        package = Path(directory)
        (package / "__init__.py").write_text(source, encoding="utf-8")
        return check_directory(package)


# --- the declaration -------------------------------------------------------


class DeclaredPayoutModeTestCase(SimpleTestCase):
    """What a ruleset says about who pays, read off the ruleset object."""

    def test_a_ruleset_that_says_nothing_pays_from_the_review_screen(self):
        """The default, and the reason every existing section is untouched.

        It is also what the reference ruleset *says*, explicitly, although it
        would get the same answer by saying nothing: the point of the
        declaration is that a section states its arrangement, and a reader of
        Heidelberg's rules should not have to know Kompass's fallback.
        """

        class Silent:
            pass

        self.assertEqual(declared_payout(Silent()), SELF_PAYMENT)
        self.assertEqual(HeidelbergRules().payout, SELF_PAYMENT)
        self.assertEqual(declared_payout(HeidelbergRules()), SELF_PAYMENT)
        self.assertEqual(payout_problems(HeidelbergRules()), [])

    def test_a_mode_kompass_does_not_know_is_a_problem_and_not_a_fallback(self):
        """Both halves, and they are different halves.

        ``declared_payout`` has to answer *something* storable, because the
        row it fills in is a draft with a column that has choices. What
        decides whether the version applies is ``payout_problems``, and it
        refuses — because the fallback would otherwise put one of two false
        sentences in front of whoever releases a payout, and there is no third
        wording to retreat to.
        """
        rules = HeidelbergRules()
        rules.payout = "Geschäftsstelle"
        self.assertEqual(declared_payout(rules), SELF_PAYMENT)
        problems = payout_problems(rules)
        self.assertEqual(len(problems), 1)
        self.assertIn("Geschäftsstelle", problems[0])
        self.assertIn("'self'", problems[0])
        self.assertIn("'office'", problems[0])


class CheckedPayoutModeTestCase(SimpleTestCase):
    def test_a_section_that_declares_the_office_passes_every_check(self):
        loaded, problems = checked(HANDOFF)
        self.assertEqual(problems, [])
        self.assertEqual(loaded.payout, OFFICE_PAYMENT)

    def test_a_mode_nobody_can_read_is_reported_where_it_is_written(self):
        loaded, problems = checked(with_mode(HANDOFF, "'offices'"))
        self.assertIsNotNone(loaded, "the ruleset loads; it is the declaration that is wrong")
        self.assertEqual(len(problems), 1)
        self.assertIn("'offices'", problems[0])

    def test_a_payout_mode_that_queries_the_database_is_refused(self):
        """``payout`` is a section's own Python, like the four fields beside it.

        It is read like data — an attribute lookup — and a section can write
        it as a ``property``, so it is read inside the query guard and a
        version whose mode goes to the database is a draft with a sentence
        rather than a version that got a cursor for free (#554).
        """
        loaded, problems = checked(querying_field("payout", OFFICE_PAYMENT))
        self.assertIsNotNone(loaded)
        self.assertEqual(len(problems), 1)
        self.assertIn("payout mode could not be read", problems[0])


class StoredPayoutModeTestCase(TestCase):
    """The column, and that it is part of what a version says."""

    def test_an_imported_version_records_the_mode_it_declared(self):
        row, problems = imported(HANDOFF, "handoff")
        self.assertEqual(problems, [])
        self.assertEqual(row.state, RuleSet.ACTIVE)
        self.assertEqual(row.payout, OFFICE_PAYMENT)
        self.assertEqual(row.snapshot()["payout"], OFFICE_PAYMENT)

    def test_the_reference_version_records_that_it_pays_from_the_screen(self):
        RuleSet.objects.all().delete()
        row, problems = import_from_directory(reference_directory())
        self.assertEqual(problems, [])
        self.assertEqual(row.payout, SELF_PAYMENT)
        self.assertEqual(row.snapshot()["payout"], SELF_PAYMENT)

    def test_changing_how_a_section_pays_is_a_new_version(self):
        """Which is the whole argument for the declaration living in the rules.

        The mode is part of the sources, the sources are hashed into the
        version, so a section that changes how it pays gets a new row with its
        own validity and its own hash. The change is on the record instead of
        being a line somebody edited in a configuration file one afternoon.
        """
        first, problems = imported(with_mode(HANDOFF, "'self'"), "turning")
        self.assertEqual(problems, [])
        second, problems = imported(HANDOFF, "turning")
        self.assertEqual(problems, [])
        self.assertNotEqual(second.pk, first.pk)
        self.assertNotEqual(second.hash, first.hash)
        self.assertEqual(second.supersedes, first)
        self.assertEqual(first.payout, SELF_PAYMENT)
        self.assertEqual(second.payout, OFFICE_PAYMENT)
        self.assertEqual(active_version(), second)

    def test_a_stored_version_cannot_change_how_it_pays(self):
        row, _problems = imported(HANDOFF, "handoff")
        row.payout = SELF_PAYMENT
        with self.assertRaises(ImmutableRuleSet) as caught:
            row.save()
        self.assertIn("payout", str(caught.exception))

    def test_a_broken_version_is_stored_without_claiming_a_mode(self):
        """A draft needs something storable, and it must not be a claim.

        It never applies — the previous version stays in force — so what the
        column holds is the default rather than a guess about a package that
        does not load.
        """
        row, problems = imported("import socket\n", "kaputt")
        self.assertTrue(problems)
        self.assertEqual(row.state, RuleSet.DRAFT)
        self.assertEqual(row.payout, SELF_PAYMENT)


# --- the binding -----------------------------------------------------------


class StatementPayoutModeTestCase(TestCase):
    def test_a_statement_keeps_the_arrangement_it_was_created_under(self):
        """Bound, not current — and this is the test that says which.

        A section that takes its transfers back in house imports a new
        version. The statements released under the old one stay *zur
        Auszahlung übergeben*: reading whatever version is in force at the
        moment somebody looks would make a settled statement's terminal act
        change meaning afterwards, which is the record saying something that
        did not happen.
        """
        imported(HANDOFF, "handoff")
        handed_over = Statement.objects.create(short_description="Übergabe")
        self.assertEqual(handed_over.payout_mode, OFFICE_PAYMENT)
        self.assertTrue(handed_over.payout_handoff)

        imported(with_mode(HANDOFF, "'self'"), "handoff")
        afterwards = Statement.objects.create(short_description="Selbst")
        self.assertEqual(afterwards.payout_mode, SELF_PAYMENT)
        self.assertFalse(afterwards.payout_handoff)

        handed_over.refresh_from_db()
        self.assertEqual(
            handed_over.payout_mode,
            OFFICE_PAYMENT,
            "the statement keeps the arrangement it was created under",
        )

    def test_a_statement_bound_to_nothing_pays_from_the_review_screen(self):
        """And so does one whose snapshot holds a mode nobody can read.

        An instance that has imported no version binds nothing, and a snapshot
        written before the column existed has no ``payout`` key. Both read as
        the default, because the default is what Kompass did.
        """
        RuleSet.objects.all().delete()
        unbound = Statement.objects.create(short_description="Ohne Regelwerk")
        self.assertEqual(unbound.ruleset_snapshot, {})
        self.assertEqual(unbound.payout_mode, SELF_PAYMENT)

        unbound.ruleset_snapshot = {"payout": "irgendwas"}
        self.assertEqual(unbound.payout_mode, SELF_PAYMENT)
        self.assertFalse(unbound.payout_handoff)
