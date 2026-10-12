"""Who signs a statement off: the arithmetic, the record, and the routing.

The proposal's §7 is the specification, and these are its four rules:

* a **forbid** is subtracted from every eligible set before anything is
  counted, and no amount of permitting puts somebody back,
* **one signature counts against every constraint it satisfies**,
* **applicable** and **satisfied** are separate recorded states, and an
  **override** is a third — recorded with who and why, never a constraint that
  quietly vanished,
* the eligible set the rules name is **re-checked against the real permission
  system**, so a configuration repository cannot hand anybody a right.

And the ordering constraint §7 insists on: routing runs on the *resolved
transfers*, after rule expansion, which is what lets a rule say "nobody who
receives money from this statement".
"""

from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils.translation import gettext as _
from finance.engine import import_from_directory
from finance.engine.approval import Exclusion
from finance.engine.approval import fully_approved
from finance.engine.approval import may_sign
from finance.engine.approval import resolve_eligibility
from finance.engine.approval import states
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.rules_api import Constraint
from finance.rules_api import Forbid
from finance.rules_api import Member as RuleMember
from finance.rules_api import MemberId
from finance.store import Approval
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import MALE
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE

#: A ruleset that asks for two signatures and excludes whoever is paid.
TWO_SIGNATURES = '''
from kompass.rules import Constraint, Forbid, Member, Ruleset, SECTION, PARTICIPANTS, Transfer


class TwoSignatures(Ruleset):
    """Two signatures, and nobody who receives money may give one."""

    name = "two-signatures"
    permissions = ("finance.process_statementsubmitted",)
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

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
        signers = ctx.permission_holders("finance.process_statementsubmitted")
        paid = {t.destination for t in transfers if isinstance(t.destination, Member)}
        return (
            [
                Constraint(
                    name="Kasse",
                    description="Eine Unterschrift aus der Kasse",
                    applicable=True,
                    required=1,
                    eligible=signers,
                ),
                Constraint(
                    name="Vorstand",
                    description="Zwei Unterschriften ab 1.000 Euro",
                    applicable=sum((t.amount for t in transfers), 0) >= 1000,
                    required=2,
                    eligible=signers,
                ),
            ],
            [Forbid("Befangenheit", applies_to=lambda m: m in paid)],
        )


ruleset = TwoSignatures()
'''


def row(**overrides):
    """One stored constraint, as a mapping, for the pure tests."""
    values = {
        "name": "Freigabe",
        "description": "Eine Unterschrift",
        "applicable": True,
        "required": 1,
        "eligible": [1, 2],
        "excluded": [],
        "overridden": False,
        "overridden_by": None,
        "override_reason": "",
    }
    values.update(overrides)
    return values


class ApprovalArithmeticTestCase(SimpleTestCase):
    def test_a_forbid_is_subtracted_before_anything_is_counted(self):
        anna, bernd = RuleMember(MemberId(1)), RuleMember(MemberId(2))
        constraint = Constraint(
            name="Freigabe", description="", applicable=True, required=1, eligible=(anna, bernd)
        )
        forbids = [Forbid("Befangenheit", applies_to=lambda member: member == anna)]
        resolved = resolve_eligibility(constraint, forbids, permitted=[1, 2])
        self.assertEqual(resolved.eligible, (2,))
        self.assertEqual(resolved.excluded, (Exclusion(member=1, forbid="Befangenheit"),))

    def test_the_rules_cannot_name_somebody_who_may_not_act(self):
        constraint = Constraint(
            name="Freigabe",
            description="",
            applicable=True,
            required=1,
            eligible=(RuleMember(MemberId(1)), RuleMember(MemberId(2))),
        )
        resolved = resolve_eligibility(constraint, [], permitted=[2])
        self.assertEqual(resolved.eligible, (2,))
        self.assertEqual(resolved.excluded, (Exclusion(member=1, forbid="permission"),))
        # Without a permitted set nothing is re-checked, which is the dry run.
        self.assertEqual(resolve_eligibility(constraint, []).eligible, (1, 2))

    def test_a_forbid_that_raises_excludes_nobody(self):
        def angry(member):
            raise ValueError("nope")

        constraint = Constraint(
            name="Freigabe",
            description="",
            applicable=True,
            required=1,
            eligible=(RuleMember(MemberId(1)),),
        )
        resolved = resolve_eligibility(constraint, [Forbid("kaputt", applies_to=angry)])
        self.assertEqual(resolved.eligible, (1,))

    def test_one_signature_counts_against_every_constraint_it_satisfies(self):
        resolved = states(
            [row(name="Kasse", eligible=[1, 2]), row(name="Vorstand", eligible=[2, 3])],
            signatures=[2],
        )
        self.assertTrue(all(state.satisfied for state in resolved))
        self.assertTrue(fully_approved(resolved))

    def test_a_quorum_of_two_needs_two_people(self):
        rows = [row(required=2, eligible=[1, 2, 3])]
        one = states(rows, signatures=[1])
        self.assertFalse(one[0].satisfied)
        self.assertEqual(one[0].missing, 1)
        self.assertTrue(one[0].open)
        self.assertFalse(fully_approved(one))
        two = states(rows, signatures=[1, 3])
        self.assertTrue(two[0].satisfied)
        self.assertEqual(two[0].missing, 0)
        self.assertFalse(two[0].open)
        self.assertTrue(fully_approved(two))

    def test_a_signature_from_somebody_not_named_does_not_count(self):
        resolved = states([row(eligible=[1])], signatures=[9])
        self.assertEqual(resolved[0].signed_by, ())
        self.assertFalse(resolved[0].satisfied)

    def test_a_constraint_that_names_nobody_falls_back_to_the_capability(self):
        """The state Kompass was in before there were constraints at all."""
        resolved = states([row(eligible=[])], signatures=[9])
        self.assertEqual(resolved[0].signed_by, (9,))
        self.assertTrue(resolved[0].satisfied)

    def test_a_signature_nobody_can_be_named_for_still_counts(self):
        resolved = states([row(eligible=[1])], signatures=[], uncredited=1)
        self.assertTrue(resolved[0].satisfied)

    def test_a_constraint_that_does_not_apply_is_reported_not_hidden(self):
        resolved = states([row(applicable=False, required=2)], signatures=[])
        self.assertFalse(resolved[0].applicable)
        self.assertFalse(resolved[0].open)
        self.assertEqual(resolved[0].missing, 0)
        self.assertTrue(fully_approved(resolved))

    def test_an_override_is_a_state_with_who_and_why(self):
        resolved = states(
            [
                row(
                    required=2,
                    overridden=True,
                    overridden_by=7,
                    override_reason="Fristende",
                    excluded=[{"member": 3, "forbid": "Befangenheit"}],
                )
            ],
            signatures=[],
        )
        state = resolved[0]
        self.assertTrue(state.overridden)
        self.assertEqual(state.overridden_by, 7)
        self.assertEqual(state.override_reason, "Fristende")
        self.assertFalse(state.open)
        self.assertEqual(state.excluded, (Exclusion(member=3, forbid="Befangenheit"),))
        self.assertTrue(fully_approved(resolved))

    def test_who_still_has_something_to_sign(self):
        rows = [row(name="Kasse", eligible=[1]), row(name="Vorstand", eligible=[2], required=1)]
        resolved = states(rows, signatures=[1])
        self.assertFalse(may_sign(resolved, 1), "Kasse is signed and Anna is not on Vorstand")
        self.assertTrue(may_sign(resolved, 2))
        self.assertTrue(may_sign(states([row(eligible=[])], signatures=[]), 99))
        self.assertFalse(may_sign(states([], signatures=[]), 1))

    def test_no_constraints_at_all_is_approved(self):
        self.assertTrue(fully_approved([]))


def a_user(name, *, permitted=False):
    user = User.objects.create_user(name, password="secret")
    if permitted:
        user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="finance", codename="process_statementsubmitted"
            )
        )
    member = Member.objects.create(
        prename=name.title(), lastname="Test", email=f"{name}@localhost", gender=MALE, user=user
    )
    return User.objects.get(pk=user.pk), member


class HeidelbergApprovalTestCase(TestCase):
    """Heidelberg asks for one signature from the finance department.

    Which is what Kompass did before any of this existed, so these are the
    tests that say the behaviour did not move.
    """

    def setUp(self):
        self.user, self.treasurer = a_user("kasse", permitted=True)
        self.other_user, self.other = a_user("andere")
        self.statement = Statement.objects.create(short_description="Freigabe", night_cost=0)
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.other,
        )
        self.statement.submit(submitter=self.other)
        self.statement.generate_transactions()
        # A payout needs somewhere to book it: a statement without ledgers is
        # not ready to be paid, whatever anybody signs.
        self.statement.transaction_set.update(ledger=Ledger.objects.create(name="Konto"))

    def test_submission_freezes_one_constraint_over_the_permission_holders(self):
        constraint = self.statement.approval_constraint_set.get()
        self.assertEqual(constraint.name, "Freigabe")
        self.assertEqual(constraint.required, 1)
        self.assertEqual(constraint.eligible_member_ids, [self.treasurer.pk])
        self.assertFalse(constraint.satisfied)
        self.assertFalse(constraint.overridden)
        self.assertEqual(str(constraint.state_display), _("Open"))

    def test_one_signature_from_the_finance_department_pays_it_out(self):
        self.assertFalse(self.statement.fully_approved)
        self.assertTrue(self.statement.may_be_approved_by(self.treasurer))
        self.assertFalse(self.statement.may_be_approved_by(self.other))
        self.assertTrue(self.statement.approve(self.treasurer))
        self.statement.refresh_from_db()
        self.assertTrue(self.statement.confirmed)
        self.assertEqual(self.statement.confirmed_by, self.treasurer)
        self.assertTrue(self.statement.approval_constraint_set.get().satisfied)
        signature = self.statement.approval_set.get()
        self.assertEqual(signature.member, self.treasurer)
        # The signature reads as who signed and the day they did.
        self.assertIn(str(self.treasurer), str(signature))
        self.assertIn(signature.at.strftime("%Y-%m-%d"), str(signature))
        self.assertTrue(all(t.confirmed for t in self.statement.transaction_set.all()))

    def test_confirm_is_the_same_thing_under_its_old_name(self):
        self.assertTrue(self.statement.confirm(self.treasurer))
        self.statement.refresh_from_db()
        self.assertTrue(self.statement.confirmed)

    def test_somebody_the_rules_did_not_name_signs_nothing(self):
        self.assertFalse(self.statement.approve(self.other))
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.confirmed)
        # The signature is recorded even so: it happened.
        self.assertEqual(self.statement.approval_set.get().member, self.other)
        self.assertFalse(self.statement.approval_constraint_set.get().satisfied)

    def test_a_statement_that_is_not_submitted_cannot_be_signed(self):
        draft = Statement.objects.create(short_description="Entwurf", night_cost=0)
        self.assertFalse(draft.approve(self.treasurer))
        self.assertFalse(draft.may_be_approved_by(self.treasurer))
        self.assertFalse(draft.override_approval("Freigabe", self.treasurer, "weil"))

    def test_a_paid_statement_is_not_signed_twice(self):
        self.statement.approve(self.treasurer)
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.approve(self.treasurer))
        self.assertFalse(self.statement.may_be_approved_by(self.treasurer))

    def test_an_override_pays_out_and_says_who_and_why(self):
        self.assertTrue(self.statement.override_approval("Freigabe", self.treasurer, "Fristende"))
        self.statement.refresh_from_db()
        self.assertTrue(self.statement.confirmed)
        constraint = self.statement.approval_constraint_set.get()
        self.assertTrue(constraint.overridden)
        self.assertEqual(constraint.overridden_by, self.treasurer)
        self.assertEqual(constraint.override_reason, "Fristende")
        self.assertEqual(str(constraint.state_display), _("Overridden"))

    def test_overriding_a_step_nobody_asked_for_does_nothing(self):
        self.assertFalse(self.statement.override_approval("Nope", self.treasurer, "weil"))
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.confirmed)

    def test_the_object_permission_asks_the_capability_and_the_rules(self):
        self.assertTrue(self.user.has_perm("finance.approve_obj_statement", self.statement))
        self.assertFalse(self.other_user.has_perm("finance.approve_obj_statement", self.statement))
        # Signed off: there is nothing left for anybody to sign.
        self.statement.approve(self.treasurer)
        self.assertFalse(
            User.objects.get(pk=self.user.pk).has_perm(
                "finance.approve_obj_statement", Statement.objects.get(pk=self.statement.pk)
            )
        )

    def test_the_permission_answers_for_an_excursion_as_well(self):
        """The object the permission is asked about is not always a statement.

        An excursion page asks the same question with the trip in hand, which
        is why ``not_submitted`` and ``leads_excursion`` both accept one. This
        answers through the trip's statement, and no when the trip has none —
        there is nothing to sign before somebody has handed anything in.
        """
        excursion = Freizeit.objects.create(
            name="Bergtour",
            kilometers_traveled=10,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.assertFalse(self.user.has_perm("finance.approve_obj_statement", excursion))
        self.statement.excursion = excursion
        self.statement.save()
        self.assertTrue(
            User.objects.get(pk=self.user.pk).has_perm(
                "finance.approve_obj_statement", Freizeit.objects.get(pk=excursion.pk)
            )
        )

    def test_an_unpayable_statement_is_not_paid_out_by_a_signature(self):
        self.statement.transaction_set.all().delete()
        self.assertFalse(self.statement.approve(self.treasurer))
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.confirmed)


class SectionWithTwoSignaturesTestCase(TestCase):
    """A section whose rules ask for more, end to end from its own package.

    Two constraints, one of them only over a thousand euro, and a forbid that
    excludes whoever the payout pays — which is the ordering §7 insists on,
    because that set is derived from the transfers rather than from the
    statement's fields.
    """

    def setUp(self):
        self.anna_user, self.anna = a_user("anna", permitted=True)
        self.bernd_user, self.bernd = a_user("bernd", permitted=True)
        self.clara_user, self.clara = a_user("clara", permitted=True)
        self.ledger = Ledger.objects.create(name="Konto")
        self.directory = TemporaryDirectory()
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(TWO_SIGNATURES, encoding="utf-8")
        row, problems = import_from_directory(package, name="two-signatures")
        self.assertEqual(problems, [])
        self.version = row

    def tearDown(self):
        self.directory.cleanup()

    def statement_for(self, amount, payer):
        statement = Statement.objects.create(short_description="Gross", night_cost=0)
        Bill.objects.create(
            statement=statement,
            short_description="Bus",
            amount=amount,
            costs_covered=True,
            paid_by=payer,
        )
        statement.submit(submitter=payer)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def test_the_second_constraint_only_applies_over_a_thousand(self):
        small = self.statement_for(Decimal("100.00"), self.clara)
        states_by_name = {state.name: state for state in small.approval_states}
        self.assertTrue(states_by_name["Kasse"].applicable)
        self.assertFalse(states_by_name["Vorstand"].applicable)
        # And the frozen row says so in words, rather than reading as unsigned.
        rows = {row.name: row for row in small.approval_constraint_set.all()}
        self.assertEqual(str(rows["Vorstand"].state_display), _("Does not apply"))
        self.assertTrue(small.approve(self.anna))
        self.assertTrue(Statement.objects.get(pk=small.pk).confirmed)

    def test_whoever_is_paid_may_not_sign_their_own_payout(self):
        big = self.statement_for(Decimal("1200.00"), self.anna)
        states_by_name = {state.name: state for state in big.approval_states}
        kasse = states_by_name["Kasse"]
        self.assertNotIn(self.anna.pk, kasse.eligible)
        self.assertIn(Exclusion(member=self.anna.pk, forbid="Befangenheit"), kasse.excluded)
        self.assertIn(self.bernd.pk, kasse.eligible)
        # And a signature from the excluded person advances nothing.
        self.assertFalse(big.approve(self.anna))
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed)

    def test_two_signatures_are_two_people(self):
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.approve(self.anna))
        big = Statement.objects.get(pk=big.pk)
        states_by_name = {state.name: state for state in big.approval_states}
        self.assertTrue(states_by_name["Kasse"].satisfied, "one signature is enough for Kasse")
        self.assertFalse(states_by_name["Vorstand"].satisfied)
        self.assertEqual(states_by_name["Vorstand"].missing, 1)
        # The same person signing again adds nothing.
        Approval.objects.create(statement=big, member=self.anna)
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.fully_approved)
        self.assertTrue(big.approve(self.bernd))
        self.assertTrue(Statement.objects.get(pk=big.pk).confirmed)

    def test_an_override_of_one_step_leaves_the_other_standing(self):
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.override_approval("Vorstand", self.anna, "Fristende"))
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.confirmed)
        self.assertTrue(big.approve(self.bernd))
        self.assertTrue(Statement.objects.get(pk=big.pk).confirmed)
