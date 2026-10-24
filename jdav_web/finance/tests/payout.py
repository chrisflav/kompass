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

import pathlib
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core import mail
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from finance.engine import check_directory
from finance.engine import import_from_directory
from finance.engine import reference_directory
from finance.engine.versions import active_version
from finance.engine.versions import declared_payout
from finance.engine.versions import payout_problems
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.models import Transaction
from finance.rules_api import OFFICE_PAYMENT
from finance.rules_api import SELF_PAYMENT
from finance.rulesets.heidelberg import HeidelbergRules
from finance.store import ImmutableRuleSet
from finance.store import RuleSet
from finance.tests.approval import a_user
from finance.tests.approval import bearer
from finance.tests.store import querying_field
from mailer.mailutils import NOT_SENT
from mailer.mailutils import SENT
from members.models import MALE
from members.models import Member

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


# --- the rulesets in this repository ---------------------------------------


class DeployedRulesetsTestCase(SimpleTestCase):
    """What the two rulesets in this repository's ``deploy/`` actually declare.

    Nothing else pins them. ``manage.py checkruleset`` passes under either
    mode — the declaration is valid, not wrong — so a declaration dropped in a
    rebase would take Ludwigsburg's whole handoff with it and no gate would
    say a word. The sections' own configuration lives in this repository, so
    the assertion does too; ``contrib.tests`` reaches outside ``jdav_web`` for
    ``frontend/openapi.json`` for the same reason.
    """

    def declared_in(self, section):
        directory = pathlib.Path(settings.BASE_DIR).parent / "deploy" / section / "rules"
        self.assertTrue(directory.is_dir(), f"{directory} is not in this checkout")
        loaded, problems = check_directory(directory)
        self.assertEqual(problems, [])
        return loaded.payout

    def test_ludwigsburgs_geschaeftsstelle_makes_the_transfers(self):
        self.assertEqual(self.declared_in("ludwigsburg"), OFFICE_PAYMENT)

    def test_the_template_a_section_copies_pays_from_the_review_screen(self):
        """The default, so that copying the template changes nothing.

        A template that declared a handoff would hand every new section the
        arrangement of exactly one of them, and the one Kompass cannot observe.
        """
        self.assertEqual(self.declared_in("config-template"), SELF_PAYMENT)


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


# --- the handoff -----------------------------------------------------------


class HandoffTestCase(TestCase):
    """Releasing a statement where the Geschäftsstelle makes the transfers."""

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        self.clara_user, self.clara = a_user("clara", permitted=True)
        self.ledger = Ledger.objects.create(name="Konto")
        row, problems = imported(HANDOFF, "handoff")
        self.assertEqual(problems, [])
        self.version = row

    def a_statement(self, amount=Decimal("100.00")):
        """A statement that is ready to be released, and nothing more."""
        statement = Statement.objects.create(short_description="Übergabe")
        Bill.objects.create(
            statement=statement,
            short_description="Bus",
            amount=amount,
            costs_covered=True,
            paid_by=self.clara,
        )
        statement.submit(submitter=self.clara)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def test_the_release_mails_the_office_and_then_moves_the_status(self):
        statement = self.a_statement()
        mail.outbox = []
        self.assertTrue(statement.approve(self.anna))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [settings.SEKTION_FINANCE_MAIL])
        self.assertEqual(mail.outbox[0].cc, [self.anna.email])
        statement.refresh_from_db()
        self.assertTrue(statement.confirmed)

    def test_a_mail_that_did_not_go_leaves_the_statement_where_it_was(self):
        """The decision, and the reason it is the right way round.

        In this mode "Completed" asserts that somebody else now holds the
        instruction. Asserting it over a mail the server refused is exactly
        the defect — a status claiming an act that did not happen — so the
        send comes first and the status waits for it.

        What the failure costs is a click. The signature is a fact and stays
        on the record; the statement is submitted, fully approved and not
        released, and pressing the button again retries the handoff without
        recording a second signature. That is why "leave it where it was" is
        affordable here: there is no half-released state to get stuck in.
        """
        statement = self.a_statement()
        mail.outbox = []
        with patch("finance.models.send_mail", return_value=NOT_SENT) as refused:
            self.assertFalse(statement.approve(self.anna))
        self.assertEqual(refused.call_count, 1)
        statement.refresh_from_db()
        self.assertFalse(statement.confirmed)
        self.assertTrue(statement.submitted)
        self.assertTrue(statement.fully_approved, "the signature is a fact and stays")
        self.assertEqual(statement.approval_set.count(), 1)
        self.assertEqual(mail.outbox, [])

        # And the retry goes through, on the signature that is already in.
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(statement.approve(self.anna))
        self.assertEqual(statement.approval_set.count(), 1, "signing twice is signing once")
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_the_handoff_happens_on_a_waiver_as_well(self):
        """Every release goes through one funnel, which is why it is there.

        ``_pay_out`` is reached from the signature that completes the quorum
        **and** from a step somebody waived. An endpoint that sent the mail
        instead would leave the second route able to mark a statement handed
        over with nothing handed over.
        """
        statement = self.a_statement()
        mail.outbox = []
        self.assertTrue(statement.override_approval("Freigabe", self.anna, "Frist"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_nothing_is_sent_for_a_statement_that_cannot_be_released(self):
        """The mail is the last thing before the status, not the first thing.

        A statement whose bookings do not reconcile is refused before the
        send, so an unreleasable statement does not reach the office at all.
        """
        statement = self.a_statement()
        statement.transaction_set.all().delete()
        mail.outbox = []
        self.assertFalse(statement.approve(self.anna))
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

    def test_send_summary_says_whether_it_went(self):
        """Which is the value the status of a handed-over statement hangs on.

        ``mailer.mailutils.send`` catches its own exceptions and answers with a
        status, so "the mail did not go" is a value rather than a traceback —
        and the only honest reading of "the handoff happened" that Kompass can
        get at.
        """
        statement = self.a_statement()
        self.assertEqual(statement.send_summary(), SENT)
        with patch("finance.models.send_mail", return_value=NOT_SENT):
            self.assertEqual(statement.send_summary(), NOT_SENT)
            self.assertFalse(statement.hand_over(self.anna))

    def test_a_handoff_nobody_can_be_copied_in_on_still_goes(self):
        """A release with no member behind it copies nobody, and still sends.

        ``confirm`` takes a member where there is one and ``None`` where the
        account has no member record — which is a signer the approval engine
        counts by account. The courtesy copy is the only thing that is then
        missing, and it is not the handoff.
        """
        statement = self.a_statement()
        mail.outbox = []
        self.assertTrue(statement.hand_over())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].cc, [])


class SelfPaymentIsUntouchedTestCase(TestCase):
    """The shipped behaviour, asserted as behaviour rather than assumed.

    Heidelberg's release is a payout the reviewer has already made, so the
    mail is a courtesy that the ``send`` flag asks for. Nothing about the mode
    may start sending one by itself: neuter the ``payout_handoff`` test in
    ``_pay_out`` and this goes red.
    """

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        import_from_directory(reference_directory())

    def test_releasing_a_statement_mails_nothing_by_itself(self):
        statement = Statement.objects.create(short_description="Auszahlung")
        statement.submit(submitter=self.anna)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertEqual(statement.payout_mode, SELF_PAYMENT)
        mail.outbox = []
        self.assertTrue(statement.confirm(self.anna))
        self.assertEqual(mail.outbox, [], "the summary is sent when somebody asks for it")
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)


# --- the paper -------------------------------------------------------------


class PaymentOrdersTestCase(TestCase):
    """What the Geschäftsstelle has to be able to read off the Beleg.

    Per recipient: the amount, the account, the reference — and, where two
    amounts to one person must not be combined, that fact and why. The
    document carried the covered bills and the payout lines and not one
    account number, so in handoff mode the per-transfer instruction never
    reached the person making the transfers at all.
    """

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        self.anna.iban = "DE89370400440532013000"
        self.anna.save()
        self.ledger = Ledger.objects.create(name="Konto")
        imported(HANDOFF, "handoff")
        self.statement = Statement.objects.create(short_description="Übergabe")

    def booking(self, amount, reference, group="", member=None):
        return Transaction.objects.create(
            statement=self.statement,
            member=member or self.anna,
            amount=amount,
            reference=reference,
            settlement_group=group,
            ledger=self.ledger,
        )

    def test_one_order_per_booking_with_everything_needed_to_make_it(self):
        self.booking(Decimal("24.00"), "Fahrtkosten")
        orders = self.statement.payment_orders()
        self.assertEqual(len(orders), 1)
        self.assertEqual(
            {
                "recipient": orders[0]["recipient"],
                "iban": orders[0]["iban"],
                "reference": orders[0]["reference"],
                "amount": orders[0]["amount"],
                "ledger": orders[0]["ledger"],
            },
            {
                "recipient": self.anna.name,
                "iban": "DE89370400440532013000",
                "reference": "Fahrtkosten",
                "amount": Decimal("24.00"),
                "ledger": "Konto",
            },
        )

    def test_two_amounts_that_may_not_be_combined_say_so_and_say_why(self):
        """And the two that may are *not* marked, which is the real assertion.

        A test that counted marks would pass against code that marked every
        row, so this pins which rows carry the note: the pair in two different
        groups does, the pair in one group does not.
        """
        self.booking(Decimal("24.00"), "Fahrtkosten")
        self.booking(Decimal("56.00"), "Tourenleitervergütung", group="steuerrelevant")
        apart = {
            (order["reference"], order["separate"], order["settlement_group"])
            for order in self.statement.payment_orders()
        }
        self.assertEqual(
            apart,
            {
                ("Fahrtkosten", True, ""),
                ("Tourenleitervergütung", True, "steuerrelevant"),
            },
        )

        together = Statement.objects.create(short_description="Zusammen")
        for reference in ("Fahrtkosten", "Tagegeld"):
            Transaction.objects.create(
                statement=together,
                member=self.anna,
                amount=Decimal("10.00"),
                reference=reference,
                settlement_group="",
                ledger=self.ledger,
            )
        self.assertEqual(
            {order["separate"] for order in together.payment_orders()},
            {False},
            "two amounts in one group are one transfer, and the paper says nothing",
        )

    def test_an_order_whose_booking_has_no_ledger_still_says_what_to_transfer(self):
        """The ledger is the section's bookkeeping, not the recipient's.

        A booking with no account assigned holds up the release — so this is a
        statement nobody has handed over — but the order is still rendered,
        because the admin reads the same list while fixing it, and a crash
        there would be the only thing between somebody and the fix.
        """
        Transaction.objects.create(
            statement=self.statement,
            member=self.anna,
            amount=Decimal("24.00"),
            reference="Fahrtkosten",
        )
        orders = self.statement.payment_orders()
        self.assertEqual([order["ledger"] for order in orders], [""])
        self.assertEqual([order["amount"] for order in orders], [Decimal("24.00")])

    def test_an_order_nobody_can_execute_says_the_account_is_missing(self):
        """Which matters more here than on the review screen.

        The person making the transfer cannot ask: they have the paper and
        nothing else. An IBAN that is absent and one that does not validate
        are the same fact to them — there is nothing to type in — so both
        come through as no account at all.
        """
        bernd_user, bernd = a_user("bernd")
        self.booking(Decimal("10.00"), "Hütte", member=bernd)
        bernd.iban = "DE00"
        bernd.save()
        self.booking(Decimal("12.00"), "Bus", member=bernd)
        orders = {
            order["reference"]: order["iban"]
            for order in self.statement.payment_orders()
            if order["recipient"] == bernd.name
        }
        self.assertEqual(orders, {"Hütte": "", "Bus": ""})

    def test_the_document_prints_the_orders_in_the_handoff_mode(self):
        self.booking(Decimal("24.00"), "Fahrtkosten")
        self.booking(Decimal("56.00"), "Tourenleitervergütung", group="steuerrelevant")
        document = render_to_string(
            "finance/statement_summary.tex",
            {"statement": self.statement.template_context(), "excursion": None},
        )
        self.assertIn("Überweisungsaufträge", document)
        self.assertIn("DE89370400440532013000", document)
        self.assertIn("Tourenleitervergütung", document)
        self.assertIn("getrennt zu überweisen", document)
        self.assertIn("Abrechnungsgruppe steuerrelevant", document)
        # German formatting, because this is the paper somebody reads.
        self.assertIn("24,00", document)
        self.assertIn("56,00", document)
        self.assertIn("80,00", document, "and the sum of what is to be transferred")

    def test_a_statement_with_no_bookings_says_there_is_nothing_to_transfer(self):
        document = render_to_string(
            "finance/statement_summary.tex",
            {"statement": self.statement.template_context(), "excursion": None},
        )
        self.assertIn("Überweisungsaufträge", document)
        self.assertIn("keine Überweisungen auszuführen", document)


class SelfPaymentPaperIsUntouchedTestCase(TestCase):
    """Heidelberg's Beleg is the one it always was.

    The document goes to the office as a *record* there: the transfers were
    made from the review screen, by the person who was looking at the accounts
    and the QR codes. Printing payment orders on it would be an instruction to
    make transfers that have already been made.
    """

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        self.anna.iban = "DE89370400440532013000"
        self.anna.save()
        self.ledger = Ledger.objects.create(name="Konto")
        import_from_directory(reference_directory())
        self.statement = Statement.objects.create(short_description="Auszahlung")
        Transaction.objects.create(
            statement=self.statement,
            member=self.anna,
            amount=Decimal("24.00"),
            reference="Fahrtkosten",
            ledger=self.ledger,
        )

    def test_the_paper_carries_no_payment_orders(self):
        context = self.statement.template_context()
        self.assertFalse(context["handoff"])
        self.assertEqual(context["orders"], [])
        document = render_to_string(
            "finance/statement_summary.tex",
            {"statement": context, "excursion": None},
        )
        self.assertNotIn("Überweisungsaufträge", document)
        self.assertNotIn("DE89370400440532013000", document)


# --- the endpoint ----------------------------------------------------------


class ReleaseEndpointTestCase(TestCase):
    """``POST /confirm`` under each mode, from outside.

    The server decides what releasing means, not the client: a client that
    forgot the ``send`` flag must not be able to mark a statement handed over
    with nothing handed over, and one that passes it must not cause two mails
    for one act.
    """

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        self.bernd_user, self.bernd = a_user("bernd", permitted=True)
        self.anna_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="finance", codename="view_global_statement"
            )
        )
        self.anna_user = User.objects.get(pk=self.anna_user.pk)
        self.ledger = Ledger.objects.create(name="Konto")

    def a_statement(self, source=HANDOFF, name="handoff"):
        row, problems = imported(source, name)
        self.assertEqual(problems, [])
        statement = Statement.objects.create(short_description="Übergabe")
        Bill.objects.create(
            statement=statement,
            short_description="Bus",
            amount=Decimal("100.00"),
            costs_covered=True,
            paid_by=self.bernd,
        )
        statement.submit(submitter=self.bernd)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def release(self, statement, query=""):
        return self.client.post(
            "/api/finance/statements/{}/confirm{}".format(statement.pk, query),
            **bearer(self.anna_user),
        )

    def test_the_payload_says_who_makes_the_transfers(self):
        """Per statement, because a statement is bound to its own version.

        The screen has to know before it can describe its own last button, and
        it cannot ask the instance: two statements open at once may have been
        created under different arrangements.
        """
        handoff = self.a_statement()
        r = self.client.get(
            "/api/finance/statements/{}".format(handoff.pk), **bearer(self.anna_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["payout_mode"], OFFICE_PAYMENT)

        imported(with_mode(HANDOFF, "'self'"), "handoff")
        own = Statement.objects.create(short_description="Selbst")
        r = self.client.get("/api/finance/statements/{}".format(own.pk), **bearer(self.anna_user))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["payout_mode"], SELF_PAYMENT)
        # And the one created before the change still answers the old mode,
        # from the same endpoint, in the same process.
        r = self.client.get(
            "/api/finance/statements/{}".format(handoff.pk), **bearer(self.anna_user)
        )
        self.assertEqual(r.json()["payout_mode"], OFFICE_PAYMENT)

    def test_the_handoff_is_sent_once_whatever_the_client_asks_for(self):
        """Without the flag, because the mail is the act and not an extra."""
        statement = self.a_statement()
        mail.outbox = []
        r = self.release(statement)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1)
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_asking_for_the_summary_as_well_does_not_send_it_twice(self):
        statement = self.a_statement()
        mail.outbox = []
        r = self.release(statement, "?send=true")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(len(mail.outbox), 1, "one act, one mail")

    def test_a_mail_that_did_not_go_is_a_refusal_that_says_so(self):
        """And it says which refusal it is, which is the whole point.

        Everything else about the statement is in — the signatures, the
        bookings, the rules — so "not ready to be confirmed" would send
        somebody looking for a problem that is not there. The one thing that
        failed is the only thing left to name.
        """
        statement = self.a_statement()
        mail.outbox = []
        with patch("finance.models.send_mail", return_value=NOT_SENT):
            r = self.release(statement)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(
            r.json()["detail"],
            [
                _(
                    "The summary could not be sent to the office, so the statement "
                    "was not handed over. Nothing was changed — try again."
                )
            ],
        )
        self.assertEqual(mail.outbox, [])
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

    def test_short_of_a_quorum_the_refusal_is_worded_for_the_mode(self):
        """Neither sentence is true in the other section.

        "Cannot be paid out yet" is false where nobody on this screen pays
        anything, so the handoff gets its own refusal — and the reference
        ruleset's refusal is the one it always had, which the parity suite in
        ``finance.tests.approval`` holds down from the other side.
        """
        statement = self.a_statement(
            HANDOFF.replace(TWO_OF_THEM, "    required=2,"), name="handoff-twice"
        )
        mail.outbox = []
        r = self.release(statement)
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(
            r.json()["detail"],
            [_("The statement is still handed in for approvals and cannot be handed over yet.")],
        )
        statement = Statement.objects.get(pk=statement.pk)
        self.assertEqual([a.member for a in statement.approval_set.all()], [self.anna])
        self.assertFalse(statement.confirmed)
        self.assertEqual(mail.outbox, [], "nothing reaches the office short of a quorum")

    def test_a_released_statement_is_told_it_is_not_ready_like_any_other(self):
        """The third refusal, which the mode does not change.

        A statement that has been handed over is not waiting for approvals and
        its mail did not fail, so the general wording is the right one — which
        is why the branch is asked rather than the message swapped.
        """
        statement = self.a_statement()
        self.assertEqual(self.release(statement).status_code, 200)
        r = self.release(Statement.objects.get(pk=statement.pk))
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(r.json()["detail"], [_("Statement is not ready to be confirmed.")])


class LegacyAdminReleaseTestCase(TestCase):
    """The admin's confirm page, which is a second door onto the same act.

    It calls ``Statement.confirm`` directly and then offers to mail the
    summary, which is right where the reviewer makes the transfers: the mail
    is a receipt they ask for. In a handoff the mail has already gone —
    ``_pay_out`` sent it, and refused to move the status until it had — so
    sending it again here would put a second copy of one handoff in the
    office's inbox. Putting the handoff in the model rather than in the
    endpoint is what makes this a *duplicate* to suppress rather than a hole
    to plug.
    """

    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "chef", "chef@localhost", "secret", is_staff=True
        )
        Member.objects.create(
            prename="Chef",
            lastname="Test",
            email="chef@localhost",
            gender=MALE,
            user=self.superuser,
        )
        self.bernd_user, self.bernd = a_user("bernd", permitted=True)
        self.ledger = Ledger.objects.create(name="Konto")

    def a_statement(self, source):
        row, problems = imported(source, "admin-handoff")
        self.assertEqual(problems, [])
        statement = Statement.objects.create(short_description="Übergabe")
        Bill.objects.create(
            statement=statement,
            short_description="Bus",
            amount=Decimal("100.00"),
            costs_covered=True,
            paid_by=self.bernd,
        )
        statement.submit(submitter=self.bernd)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def confirm_and_send(self, statement):
        self.client.force_login(self.superuser)
        url = reverse("admin:finance_statement_overview", args=(statement.pk,))
        return self.client.post(url, data={"transaction_execution_confirm_and_send": ""})

    def test_a_handoff_is_not_mailed_twice_from_the_admin(self):
        statement = self.a_statement(HANDOFF)
        mail.outbox = []
        response = self.confirm_and_send(statement)
        self.assertEqual(response.status_code, 302, response.content[:300])
        self.assertEqual(len(mail.outbox), 1, "one act, one mail")
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_payout_the_reviewer_made_is_still_mailed_on_request(self):
        statement = self.a_statement(with_mode(HANDOFF, "'self'"))
        mail.outbox = []
        response = self.confirm_and_send(statement)
        self.assertEqual(response.status_code, 302, response.content[:300])
        self.assertEqual(len(mail.outbox), 1, "the receipt somebody asked for")
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)
