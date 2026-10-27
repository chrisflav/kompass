"""Who may sign a step off without its signatures.

Measured on an instance before this: a member the rules named only for the
*Freigabe der Leitung* was allowed to override the Schatzmeister step too, and
was refused it under a thousand euro only because that step did not apply
there. Over a thousand — where Ludwigsburg requires the Ressortleitung **and**
the Schatzmeister — the first signer could waive the second, so the rule
requiring two people required one.

Two layers, and these tests hold each of them on its own:

* the limit every section gets — an override reaches only a step the person's
  own signature would have counted towards, or one that named nobody at all,
  which is the vacant office the override exists for;
* the section's own declaration (:attr:`kompass.rules.Ruleset.override`) of
  whether these rules may be overridden at all, and by whom.
"""

import datetime
import pathlib
import uuid
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from django.utils.translation import gettext as _
from finance.api.approval import approval_payload
from finance.api.tests import AccessToken
from finance.api.tests import Application
from finance.engine import import_from_directory
from finance.engine import override_policy
from finance.engine.versions import check_directory
from finance.engine.versions import declared_override
from finance.engine.versions import override_problems
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.rules_api import NO_OVERRIDE
from finance.rules_api import Override
from finance.rules_api import OVERRIDE_BY_SIGNERS
from finance.rulesets.heidelberg import ruleset as heidelberg
from finance.store import RoleAssignment
from finance.store import RuleSet
from finance.tests.approval import a_user

#: Three steps routed by office, as Ludwigsburg routes them: the leadership,
#: the treasurer over a thousand euro, and a youth leadership that is vacant
#: unless somebody holds the role. Whoever the statement pays may not sign.
#: ``__OVERRIDE__`` is replaced with the declaration under test.
BY_OFFICE = """
from kompass.rules import (
    NO_OVERRIDE,
    OVERRIDE_BY_SIGNERS,
    Constraint,
    Forbid,
    Member,
    Override,
    Ruleset,
    SECTION,
    PARTICIPANTS,
    Transfer,
)


class ByOffice(Ruleset):
    name = "by-office"
    balance = (PARTICIPANTS, SECTION, "participant_contribution")
    override = __OVERRIDE__

    def inputs(self, ctx):
        return []

    def transfers(self, ctx):
        transfers = []
        for bill in ctx.bills:
            if bill.covered and bill.payer is not None:
                transfers.append(Transfer(SECTION, bill.payer, bill.amount, "bill", rule_id="bills"))
        return transfers, []

    def approval(self, ctx, transfers):
        paid = {t.destination for t in transfers if isinstance(t.destination, Member)}
        total = sum((t.amount for t in transfers if isinstance(t.destination, Member)), 0)
        return (
            [
                Constraint(
                    name="Leitung",
                    description="",
                    applicable=True,
                    required=1,
                    eligible=tuple(ctx.role_holders("leitung")),
                ),
                Constraint(
                    name="Schatzmeister",
                    description="",
                    applicable=total > 1000,
                    required=1,
                    eligible=tuple(ctx.role_holders("schatzmeister")),
                ),
                Constraint(
                    name="Jugendleitung",
                    description="",
                    applicable=True,
                    required=1,
                    eligible=tuple(ctx.role_holders("jugendleitung")),
                ),
            ],
            [Forbid("Eigene Abrechnung", applies_to=lambda member: member in paid)],
        )


ruleset = ByOffice()
"""


#: The refusals, through the catalogue the code reads them from.
COULD_NOT_SIGN = "You may only override an approval step you could sign yourself."
EXCLUDED = "The section's rules exclude you from this approval step."
CANNOT_SAY = (
    "The section's rules could not say whether they exclude you from this "
    "approval step, so you cannot override it."
)
NOT_ALLOWED = (
    "The section's rules do not allow an approval step to be signed off "
    "without its signatures. Ask somebody who may sign it."
)
ONLY_ROLES = (
    "The section's rules only let the holders of these roles override an approval step: %(roles)s."
)


class OverrideTestCase(TestCase):
    """A statement over the threshold, under rules that route by office."""

    #: The declaration the ruleset is imported with.
    declaration = "OVERRIDE_BY_SIGNERS"

    def setUp(self):
        self.lead_user, self.lead = a_user("leitung", permitted=True)
        self.treasurer_user, self.treasurer = a_user("kasse", permitted=True)
        self.payee_user, self.payee = a_user("zahler", permitted=True)
        RoleAssignment.objects.create(role="leitung", member=self.lead)
        RoleAssignment.objects.create(role="schatzmeister", member=self.treasurer)
        self.directory = TemporaryDirectory()
        package = Path(self.directory.name)
        source = BY_OFFICE.replace("__OVERRIDE__", self.declaration)
        (package / "__init__.py").write_text(source, encoding="utf-8")
        _row, problems = import_from_directory(package, name="by-office")
        self.assertEqual(problems, [])
        self.statement = Statement.objects.create(short_description="Groß")
        Bill.objects.create(
            statement=self.statement,
            short_description="Bus",
            amount=Decimal("1200.00"),
            costs_covered=True,
            paid_by=self.payee,
        )
        self.statement.submit(submitter=self.payee)
        self.statement.generate_transactions()
        self.statement.transaction_set.update(ledger=Ledger.objects.create(name="Konto"))

    def tearDown(self):
        self.directory.cleanup()

    def fresh(self):
        return Statement.objects.get(pk=self.statement.pk)

    def refusal(self, name, member):
        return self.fresh().override_refusal(name, member)

    def overridden(self):
        """The steps that are overridden, read back off the live rows."""
        return sorted(
            row.name for row in self.fresh().approval_constraint_set.all() if row.overridden
        )

    def offered(self, member):
        """The steps the payload offers ``member`` an override on."""
        payload = approval_payload(self.fresh(), member)
        return sorted(item["name"] for item in payload["constraints"] if item["may_override"])


class OnlyAStepYouCouldSignTestCase(OverrideTestCase):
    """The limit every section gets."""

    def test_the_first_signer_cannot_waive_the_second(self):
        """The bypass that was measured: one person, both signatures."""
        self.assertEqual(
            self.refusal("Schatzmeister", self.lead),
            _(COULD_NOT_SIGN),
        )
        self.assertFalse(self.fresh().override_approval("Schatzmeister", self.lead, "Frist"))
        self.assertEqual(self.overridden(), [])
        # And signing her own step leaves the treasurer's open, as it must.
        self.assertFalse(self.fresh().approve(self.lead))
        self.assertFalse(self.fresh().fully_approved)

    def test_a_step_you_could_sign_can_be_overridden(self):
        self.assertIsNone(self.refusal("Leitung", self.lead))
        self.fresh().override_approval("Leitung", self.lead, "Frist")
        self.assertEqual(self.overridden(), ["Leitung"])

    def test_the_treasurer_cannot_waive_the_leadership_either(self):
        """The limit is symmetric: it is about the step, not about seniority."""
        self.assertEqual(
            self.refusal("Leitung", self.treasurer),
            _(COULD_NOT_SIGN),
        )

    def test_a_step_that_named_nobody_can_still_be_overridden(self):
        """A vacant office: nobody can sign, which is what the override is for."""
        state = {s.name: s for s in self.fresh().live_approval_states}["Jugendleitung"]
        self.assertEqual((state.eligible, state.excluded), ((), ()), "the step is vacant")
        self.assertIsNone(self.refusal("Jugendleitung", self.lead))
        self.fresh().override_approval("Jugendleitung", self.lead, "Amt unbesetzt")
        self.assertEqual(self.overridden(), ["Jugendleitung"])

    def test_whoever_is_paid_cannot_waive_a_step_that_named_nobody(self):
        """A step with no group recorded nobody against the forbid, so it is asked."""
        self.assertEqual(
            self.refusal("Jugendleitung", self.payee),
            _(EXCLUDED),
        )
        self.assertFalse(
            self.fresh().override_approval("Jugendleitung", self.payee, "Amt unbesetzt")
        )
        self.assertEqual(self.overridden(), [])

    def test_rules_that_cannot_say_refuse_the_override_of_a_step_that_named_nobody(self):
        with patch("finance.models.forbid_against", side_effect=RuntimeError("the forbid broke")):
            self.assertEqual(
                self.refusal("Jugendleitung", self.lead),
                _(CANNOT_SAY),
            )

    def test_an_account_without_a_member_record_counts_where_its_signature_would(self):
        """Such a signature counts on any step with a group, so its override does.

        :func:`~finance.engine.approval.states` credits it towards a quorum
        wherever the eligible set is not empty, and an override reaches no
        further than a signature — so this is what Kompass did before, and
        Heidelberg's single step keeps it.
        """
        self.assertIsNone(self.refusal("Leitung", None))
        self.assertIsNone(self.refusal("Schatzmeister", None))
        self.assertIsNone(self.refusal("Jugendleitung", None))

    def test_an_account_without_a_member_record_cannot_waive_a_step_all_were_kept_from(self):
        """Named, and every one of them excluded: not vacant, and nobody's to sign.

        Such an account's signature counts only where the group is not empty,
        so a step whose every named person a forbid excluded is one it could
        not have signed — and not the vacant office the exception is for,
        because the rules did name somebody.
        """
        RoleAssignment.objects.create(role="jugendleitung", member=self.payee)
        state = {s.name: s for s in self.fresh().live_approval_states}["Jugendleitung"]
        self.assertEqual(state.eligible, (), "the only holder is the one being paid")
        self.assertTrue(state.excluded, "and the forbid recorded it")
        self.assertEqual(self.refusal("Jugendleitung", None), _(COULD_NOT_SIGN))

    def test_the_payload_offers_exactly_the_steps_that_would_be_taken(self):
        self.assertEqual(self.offered(self.lead), ["Jugendleitung", "Leitung"])
        self.assertEqual(self.offered(self.treasurer), ["Jugendleitung", "Schatzmeister"])
        self.assertEqual(self.offered(self.payee), [])

    def test_the_payload_offers_nothing_once_the_step_is_closed(self):
        self.fresh().override_approval("Leitung", self.lead, "Frist")
        self.assertEqual(self.offered(self.lead), ["Jugendleitung"])

    def test_the_payload_offers_nothing_on_a_settled_statement(self):
        Statement.objects.filter(pk=self.statement.pk).update(status=Statement.CONFIRMED)
        self.assertEqual(self.offered(self.lead), [])


class NoOverrideTestCase(OverrideTestCase):
    """A section that never proceeds without a signature."""

    declaration = "NO_OVERRIDE"

    def test_no_step_can_be_overridden_by_anybody(self):
        message = _(NOT_ALLOWED)
        for name in ("Leitung", "Schatzmeister", "Jugendleitung"):
            for member in (self.lead, self.treasurer, None):
                with self.subTest(step=name, member=member):
                    self.assertEqual(self.refusal(name, member), message)
        self.assertFalse(self.fresh().override_approval("Jugendleitung", self.lead, "unbesetzt"))
        self.assertEqual(self.overridden(), [])

    def test_the_payload_offers_no_override(self):
        self.assertEqual(self.offered(self.lead), [])
        self.assertEqual(self.offered(self.treasurer), [])

    def test_a_vacant_office_is_unstuck_by_filling_it(self):
        """What the section does instead: the step gets a signer."""
        _user, holder = a_user("jugend", permitted=True)
        RoleAssignment.objects.create(role="jugendleitung", member=holder)
        self.assertTrue(self.fresh().may_be_approved_by(holder))


class RestrictedToRolesTestCase(OverrideTestCase):
    """A section that keeps the override for the holders of named roles."""

    declaration = 'Override(roles=("schatzmeister",))'

    def test_only_a_holder_of_the_role_may_override(self):
        message = _(ONLY_ROLES) % {"roles": "schatzmeister"}
        self.assertEqual(self.refusal("Jugendleitung", self.lead), message)
        self.assertEqual(self.refusal("Leitung", self.lead), message)
        self.assertEqual(self.refusal("Jugendleitung", None), message)
        self.assertIsNone(self.refusal("Jugendleitung", self.treasurer))

    def test_holding_the_role_does_not_lift_the_limit(self):
        """The roles narrow the override; they do not widen it past a signature."""
        self.assertEqual(
            self.refusal("Leitung", self.treasurer),
            _(COULD_NOT_SIGN),
        )

    def test_the_role_is_held_on_the_day(self):
        RoleAssignment.objects.filter(member=self.treasurer).update(
            valid_to=timezone.localdate() - datetime.timedelta(days=1)
        )
        RoleAssignment.objects.create(
            role="schatzmeister",
            member=self.lead,
            valid_from=timezone.localdate() - datetime.timedelta(days=10),
        )
        self.assertIsNone(self.refusal("Jugendleitung", self.lead))
        self.assertIsNotNone(self.refusal("Jugendleitung", self.treasurer))


class OverrideEndpointTestCase(OverrideTestCase):
    """The endpoint answers with the same refusal, and 200 only for a waiver given."""

    def post(self, user, name):
        application = Application.objects.create(
            name="override-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        token = AccessToken.objects.create(
            user=user,
            application=application,
            token=f"tok-{uuid.uuid4().hex[:12]}",
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return self.client.post(
            f"/api/finance/statements/{self.statement.pk}/override-approval",
            {"name": name, "reason": "Frist"},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {token.token}",
        )

    def test_the_second_signature_is_refused_with_the_reason(self):
        response = self.post(self.lead_user, "Schatzmeister")
        self.assertEqual(response.status_code, 422)
        self.assertIn(_(COULD_NOT_SIGN), str(response.json()))
        self.assertEqual(self.overridden(), [])

    def test_a_step_she_could_sign_is_waived_and_says_what_is_left(self):
        response = self.post(self.lead_user, "Leitung")
        self.assertEqual(response.status_code, 200)
        offered = {item["name"]: item["may_override"] for item in response.json()["constraints"]}
        self.assertEqual(offered, {"Leitung": False, "Schatzmeister": False, "Jugendleitung": True})


class OverrideDeclarationTestCase(TestCase):
    """What a ruleset may declare, and what happens to one Kompass cannot read."""

    def import_with(self, declaration):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        package = Path(directory.name)
        source = BY_OFFICE.replace("__OVERRIDE__", declaration)
        (package / "__init__.py").write_text(source, encoding="utf-8")
        return import_from_directory(package, name=f"by-office-{uuid.uuid4().hex[:6]}")

    def test_a_declaration_kompass_cannot_read_keeps_the_version_a_draft(self):
        for declaration, expected in (
            ('"off"', "which is not an Override"),
            ('Override(allowed="no")', "has to be Override(allowed=<bool>"),
            ('Override(roles=["kassenwart"])', "has to be Override(allowed=<bool>"),
            ('Override(roles=("kassenwart", ""))', "every role an override names"),
        ):
            with self.subTest(declaration=declaration):
                row, problems = self.import_with(declaration)
                self.assertEqual(row.state, RuleSet.DRAFT)
                self.assertTrue(any(expected in problem for problem in problems), problems)

    def test_a_declaration_that_raises_is_a_problem_with_a_sentence(self):
        """``override`` is read like data and is a section's own Python."""
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        package = Path(directory.name)
        source = BY_OFFICE.replace(
            "    override = __OVERRIDE__\n",
            "    @property\n    def override(self):\n        raise ValueError('nope')\n",
        )
        (package / "__init__.py").write_text(source, encoding="utf-8")
        _loaded, problems = check_directory(package)
        self.assertEqual(problems, ["the ruleset's override could not be read: nope"])

    def test_an_unreadable_declaration_reads_as_no_override(self):
        """The default is the permissive answer, so it is not the fallback."""

        class Unreadable:
            override = "off"

        self.assertEqual(declared_override(Unreadable()), NO_OVERRIDE)
        self.assertEqual(
            override_problems(Unreadable()),
            [
                "the ruleset declares override='off', which is not an Override — "
                "the version cannot be activated with it"
            ],
        )

    def test_rules_whose_declaration_cannot_be_read_refuse_every_override(self):
        statement = Statement.objects.create(short_description="Kaputt")
        with patch("finance.engine.statements.declared_override", side_effect=ValueError):
            self.assertEqual(override_policy(statement), NO_OVERRIDE)

    def test_a_ruleset_that_says_nothing_keeps_the_override(self):
        self.assertEqual(heidelberg.override, OVERRIDE_BY_SIGNERS)
        self.assertEqual(declared_override(heidelberg), Override(allowed=True, roles=()))

    def declared_in(self, section):
        directory = pathlib.Path(settings.BASE_DIR).parent / "deploy" / section / "rules"
        loaded, problems = check_directory(directory)
        self.assertEqual(problems, [])
        return loaded.override

    def test_ludwigsburg_never_proceeds_without_a_signature(self):
        """Its Finanzordnung escalates a stuck case to a person, never past one."""
        self.assertEqual(self.declared_in("ludwigsburg"), NO_OVERRIDE)

    def test_the_template_a_section_copies_keeps_the_default(self):
        self.assertEqual(self.declared_in("config-template"), OVERRIDE_BY_SIGNERS)
