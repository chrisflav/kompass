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

import os
from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import IntegrityError
from django.db import transaction
from django.test import SimpleTestCase
from django.test import TestCase
from django.utils.translation import gettext as _
from finance.api.approval import approval_payload
from finance.api.approval import state_display
from finance.engine import import_from_directory
from finance.engine import reference_directory
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
from finance.rules_api import RuleError
from finance.store import Approval
from finance.store import ApprovalConstraint
from finance.store import RoleAssignment
from finance.store import RuleSet
from finance.tests.harness import gate_of
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

#: The same section, with a bug in its exclusion rule.
ANGRY_FORBID = '''
from kompass.rules import Constraint, Forbid, Ruleset, SECTION, PARTICIPANTS, Transfer


def kaputt(member):
    raise ValueError("der Vorstand ist unbekannt")


class AngryForbid(Ruleset):
    """A forbid whose predicate raises on everybody it is asked about."""

    name = "angry-forbid"
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
                    description="Zwei Unterschriften aus dem Vorstand",
                    applicable=True,
                    required=2,
                    eligible=signers,
                ),
            ],
            [Forbid("kaputt", applies_to=kaputt)],
        )


ruleset = AngryForbid()
'''


#: A section whose approval group is empty for an innocent reason — the role
#: it reads is vacant — with the same conflict-of-interest forbid.
VACANT_GROUP = '''
from kompass.rules import Constraint, Forbid, Member, Ruleset, SECTION, PARTICIPANTS, Transfer


class VacantGroup(Ruleset):
    """The treasurer's post is unfilled, so the group comes out empty."""

    name = "vacant-group"
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
        paid = {t.destination for t in transfers if isinstance(t.destination, Member)}
        return (
            [
                Constraint(
                    name="Kasse",
                    description="Wer auch immer die Kasse führt",
                    applicable=True,
                    required=1,
                    eligible=(),
                    anyone_permitted=ANYONE_PERMITTED,
                )
            ],
            [Forbid("Befangenheit", applies_to=lambda m: m in paid)],
        )


ruleset = VacantGroup()
'''


#: A section that routes its two signatures by **role**, which makes the two
#: groups disjoint and — unlike a group derived from who holds the capability —
#: stable when somebody loses it. Both are needed to see what the ``satisfied``
#: column records: with one shared group, the second signature re-satisfies the
#: step the first signer's lost capability had emptied, and a column rewritten
#: in between is invisible.
TWO_ROLES = '''
from kompass.rules import Constraint, Ruleset, SECTION, PARTICIPANTS, Transfer


class TwoRoles(Ruleset):
    """One signature from whoever keeps the cash, one from the board."""

    name = "two-roles"
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
        return (
            [
                Constraint(
                    name="Kasse",
                    description="Die Kassenwartin",
                    applicable=True,
                    required=1,
                    eligible=ctx.role_holders("kassenwart"),
                ),
                Constraint(
                    name="Vorstand",
                    description="Der Vorstand",
                    applicable=True,
                    required=1,
                    eligible=ctx.role_holders("vorstand"),
                ),
            ],
            [],
        )


ruleset = TwoRoles()
'''


#: A section that narrows the reference ruleset: the step keeps the name the
#: reference gives it — ``Freigabe`` — and the group is the treasurer rather
#: than everybody who may process statements. Which is what a section that
#: starts from the shipped rules and tightens them looks like, and why the
#: identity :func:`~finance.engine.statements.loaded_ruleset` reports has to
#: be the identity of what *loaded*: the same step name is what lets a
#: fallback hand the signature to the reference ruleset's group.
NARROW_FREIGABE = '''
from kompass.rules import Constraint, Ruleset, SECTION, PARTICIPANTS, Transfer


class NarrowFreigabe(Ruleset):
    """One signature, from whoever keeps the cash."""

    name = "narrow-freigabe"
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
        return (
            [
                Constraint(
                    name="Freigabe",
                    description="Die Kassenwartin",
                    applicable=True,
                    required=1,
                    eligible=ctx.role_holders("kassenwart"),
                )
            ],
            [],
        )


ruleset = NarrowFreigabe()
'''


#: One approval step called "Kasse", over whichever group ``ELIGIBLE`` names.
#: Two sections that ask for the same-named signature from different groups,
#: which is what the version bound in `_rows_from_the_same_rules` is for: the
#: frozen rows being the spine does not help when the rows and the resolution
#: agree on the name and disagree on the group.
ONE_STEP = '''
from kompass.rules import Constraint, Ruleset, SECTION, PARTICIPANTS, Transfer


class OneStep(Ruleset):
    """One signature, from the group this version names."""

    name = "NAME"
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
        return (
            [
                Constraint(
                    name="Kasse",
                    description="Eine Unterschrift aus der Kasse",
                    applicable=True,
                    required=1,
                    eligible=ELIGIBLE,
                )
            ],
            [],
        )


ruleset = OneStep()
'''


def one_step(name, eligible):
    """:data:`ONE_STEP` as a version called ``name`` over ``eligible``."""
    return ONE_STEP.replace("NAME", name).replace("ELIGIBLE", eligible)


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
        "error": "",
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

    def test_a_forbid_that_raises_is_a_rule_error_and_excludes_everybody(self):
        """Failing open on a *forbid* is failing in the one forbidden direction.

        A predicate that raises used to be shrugged off, which decided — on
        the section's behalf and against its intent — that its most
        restrictive instruction did not apply. It is an error now, and the
        caller writes a constraint nobody can satisfy.
        """

        def angry(member):
            raise ValueError("nope")

        constraint = Constraint(
            name="Freigabe",
            description="",
            applicable=True,
            required=1,
            eligible=(RuleMember(MemberId(1)),),
        )
        with self.assertRaises(RuleError) as caught:
            resolve_eligibility(constraint, [Forbid("kaputt", applies_to=angry)])
        self.assertIn("kaputt", str(caught.exception))

    def test_an_unresolvable_constraint_is_satisfied_by_nobody(self):
        resolved = states([row(error="ValueError: nope", eligible=[], required=1)], signatures=[1])
        self.assertTrue(resolved[0].unsatisfiable)
        self.assertFalse(resolved[0].satisfied)
        self.assertTrue(resolved[0].open)
        self.assertFalse(fully_approved(resolved))
        self.assertFalse(may_sign(resolved, 1))
        # Not even an unattributable signature from the permission holder.
        self.assertFalse(
            states([row(error="boom", eligible=[])], signatures=[], uncredited=[("user", 1)])[
                0
            ].satisfied
        )

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

    def test_a_group_that_came_out_empty_is_nobody_whatever_emptied_it(self):
        """The fourth hole of the same shape, and the end of inferring intent.

        "Nobody was excluded" was read as "the rules named nobody on purpose",
        which is a proxy for intent: a role nobody holds, or a filter that
        matched nobody, records `eligible=[]` and `excluded=[]` and used to
        open the constraint to anybody — including the payee a forbid was
        written for, whom the forbids never even saw, because there was nobody
        to iterate.
        """
        resolved = states([row(eligible=[])], signatures=[9])
        self.assertEqual(resolved[0].signed_by, ())
        self.assertFalse(resolved[0].satisfied)
        self.assertTrue(resolved[0].unsatisfiable)
        self.assertTrue(resolved[0].open)
        self.assertFalse(may_sign(resolved, 9))

    def test_a_section_that_wants_the_capability_to_decide_says_so(self):
        """And then the engine fills the group in, so the forbids still bite.

        Which is the difference between an opt-in and an inference: the
        constraint that means "whoever may act on statements" names nobody
        *and says that is what it means*, and what it gets is the permission
        holders — minus whoever this statement pays.
        """
        constraint = Constraint(
            name="Freigabe",
            description="",
            applicable=True,
            required=1,
            eligible=(),
            anyone_permitted=True,
        )
        resolved = resolve_eligibility(constraint, [], permitted=[2, 1])
        self.assertEqual(resolved.eligible, (1, 2))
        forbidden = resolve_eligibility(
            constraint,
            [Forbid("Befangenheit", applies_to=lambda m: m.id == 1)],
            permitted=[2, 1],
        )
        self.assertEqual(forbidden.eligible, (2,))
        self.assertEqual(forbidden.excluded, (Exclusion(member=1, forbid="Befangenheit"),))
        # Without a permitted set there is nothing to fill in with: a dry run
        # shows the constraint as the rules wrote it.
        self.assertEqual(resolve_eligibility(constraint, []).eligible, ())
        # And nobody holding the capability still means nobody.
        self.assertEqual(resolve_eligibility(constraint, [], permitted=[]).eligible, ())

    def test_an_eligible_set_emptied_by_a_forbid_means_nobody_not_anybody(self):
        """One bug that produces three, and the one the exclusions tell apart.

        "Nobody is left" read as "anybody will do" meant: a forbid that
        excluded everyone disabled itself, so the person it was written for
        could sign their own payout; a permission re-check that rejected
        everyone handed the right to every permission holder instead, which
        inverts the rule it implements; and both of those were reported as
        *satisfied*. The discriminator is already on the row: a constraint
        that named nobody has no exclusions, and one whose people were all
        removed has the list of who and why.
        """
        emptied = row(eligible=[], excluded=[{"member": 1, "forbid": "Befangenheit"}])
        resolved = states([emptied], signatures=[1, 9], uncredited=[("user", 7)])
        self.assertTrue(resolved[0].unsatisfiable)
        self.assertEqual(resolved[0].signed_by, ())
        self.assertFalse(resolved[0].satisfied)
        self.assertTrue(resolved[0].open)
        self.assertFalse(fully_approved(resolved))
        self.assertFalse(may_sign(resolved, 1), "the excluded person least of all")
        self.assertFalse(may_sign(resolved, 9))

    def test_a_signature_nobody_can_be_named_for_counts_once(self):
        """An unlinked account is one signer, however many times it clicks.

        Counting unattributable signatures rather than *naming* them let one
        administrator with no member record satisfy a quorum of two on their
        own, which is the whole of what a four-eyes rule is for.
        """
        one = states([row(eligible=[1])], signatures=[], uncredited=[("user", 3)])
        self.assertTrue(one[0].satisfied)
        twice = states(
            [row(required=2, eligible=[1])], signatures=[], uncredited=[("user", 3), ("user", 3)]
        )
        self.assertFalse(twice[0].satisfied)
        self.assertEqual(twice[0].missing, 2)
        two_accounts = states(
            [row(required=2, eligible=[1])], signatures=[], uncredited=[("user", 3), ("user", 4)]
        )
        self.assertTrue(two_accounts[0].satisfied)
        # And signatures nobody can attribute at all are one bucket, not many.
        anonymous = states(
            [row(required=2, eligible=[1])],
            signatures=[],
            uncredited=[("unattributable",), ("unattributable",)],
        )
        self.assertFalse(anonymous[0].satisfied)

    def test_the_record_is_read_and_the_gate_is_counted(self):
        """``recorded`` is an argument, not a key the row happens to carry.

        The two callers ask different questions of the same rows, so the
        answer cannot be inferred from what is in them: a row builder that
        included ``satisfied: False`` without meaning anything by it would
        have frozen the gate at *unsatisfied*, and nothing could ever be
        signed again.
        """
        signed = row(eligible=[1], satisfied=True)
        self.assertTrue(states([signed], signatures=[], recorded=True)[0].satisfied)
        self.assertFalse(states([signed], signatures=[])[0].satisfied, "counted, not read")
        self.assertTrue(states([signed], signatures=[1])[0].satisfied)
        # And the other way round: the record says what it says, whoever has
        # signed since — a row recorded unsatisfied is unsatisfied even when
        # the person who signed is in the frozen group.
        unsigned = row(eligible=[1], satisfied=False)
        self.assertFalse(states([unsigned], signatures=[1], recorded=True)[0].satisfied)
        self.assertTrue(states([unsigned], signatures=[1])[0].satisfied)
        # A row without the column at all — which is what `resolve_constraints`
        # produces — reads as unsatisfied rather than raising.
        self.assertFalse(states([row(eligible=[1])], signatures=[], recorded=True)[0].satisfied)

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
        self.assertFalse(may_sign(states([row(eligible=[])], signatures=[]), 99))
        self.assertFalse(may_sign(states([], signatures=[]), 1))

    def test_the_state_says_which_kind_of_open_it_is(self):
        """Six states a person has to tell apart, in words.

        "Open" and "nobody may sign" are the same boolean and completely
        different situations: one waits for a signature, the other waits for
        somebody to fix a rule or change who holds a role.

        Read off the resolved state rather than off the frozen row, which is
        what the row answering it cost (#551): every other field of the
        rendering comes from the state, so the row's answer was the one that
        could contradict the rest of its own line.
        """

        def display(signatures=(), **overrides):
            return state_display(states([row(**overrides)], signatures=signatures)[0])

        self.assertEqual(display(eligible=[1]), _("Open"))
        self.assertEqual(display(eligible=[1], signatures=[1]), _("Signed"))
        self.assertEqual(display(applicable=False), _("Does not apply"))
        self.assertEqual(display(overridden=True), _("Overridden"))
        self.assertEqual(
            display(eligible=[], excluded=[{"member": 1, "forbid": "Befangenheit"}]),
            _("Nobody may sign"),
        )
        self.assertEqual(display(eligible=[], error="boom"), _("Could not be resolved"))
        # An empty group reads the same way whatever emptied it, which is the
        # point: "the rules named nobody" is not a licence any more.
        self.assertEqual(display(eligible=[]), _("Nobody may sign"))

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
        self.statement = Statement.objects.create(short_description="Freigabe")
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
        self.assertEqual(state_display(self.statement.approval_states[0]), _("Open"))

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
        self.assertEqual(signature.signer, ("member", self.treasurer.pk))
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

    def test_a_draft_has_nothing_to_approve_and_is_not_approved(self):
        draft = Statement.objects.create(short_description="Entwurf")
        self.assertFalse(draft.fully_approved)
        self.assertFalse(draft.may_be_approved_by(self.treasurer))
        self.assertFalse(draft.approve(self.treasurer))

    def test_a_statement_whose_rules_report_a_problem_is_not_paid_out(self):
        """The one bill Heidelberg refuses: covered, and nobody paid it.

        Such a statement is submitted but never frozen — freezing a payout
        that is known to be wrong would make the record say something false —
        so there is nothing to pay out, whoever signs.
        """
        statement = Statement.objects.create(short_description="Ohne")
        Bill.objects.create(
            statement=statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=None,
        )
        statement.submit(submitter=self.other)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(statement.rule_result.errors)
        self.assertFalse(statement.obligation_set.exists(), "nothing was frozen")
        self.assertFalse(statement.approve(self.treasurer))
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_statement_that_is_not_submitted_cannot_be_signed(self):
        draft = Statement.objects.create(short_description="Entwurf")
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
        self.assertEqual(state_display(self.statement.approval_states[0]), _("Overridden"))

    def test_overriding_a_step_nobody_asked_for_does_nothing(self):
        self.assertFalse(self.statement.override_approval("Nope", self.treasurer, "weil"))
        self.statement.refresh_from_db()
        self.assertFalse(self.statement.confirmed)
        # And a step nobody asked for excludes nobody, rather than raising.
        self.assertFalse(self.statement.forbids_approval_by("Nope", self.treasurer))

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

    def test_a_treasurer_appointed_after_submission_can_still_sign(self):
        """What may not be frozen: who is *allowed* to act.

        Heidelberg's one constraint names whoever holds
        ``process_statementsubmitted``, resolved when the statement was handed
        in. Appointing a treasurer while statements are in flight is ordinary,
        and before the store they could confirm those statements at once; with
        the eligible set frozen they passed the capability check and were
        refused by the rules. The rows stay the record of who was named — an
        audit asks what the rules said then — and the *gate* asks the rules
        again.
        """
        frozen = self.statement.approval_constraint_set.get()
        self.assertEqual(frozen.eligible_member_ids, [self.treasurer.pk])
        self.assertFalse(self.statement.may_be_approved_by(self.other))
        self.other_user.user_permissions.add(
            Permission.objects.get(
                content_type__app_label="finance", codename="process_statementsubmitted"
            )
        )
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(statement.may_be_approved_by(self.other))
        self.assertTrue(statement.approve(self.other))
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(statement.confirmed)
        self.assertEqual(statement.confirmed_by, self.other)
        # And the frozen row still names who the rules named at submission.
        self.assertEqual(
            statement.approval_constraint_set.get().eligible_member_ids, [self.treasurer.pk]
        )
        self.assertEqual(
            [state.eligible for state in statement.approval_states],
            [(self.treasurer.pk,)],
            "the record, not the gate",
        )

    def test_one_account_without_a_member_record_is_one_signature(self):
        """An administrator who is not a member signs — and is named as one.

        Heidelberg asks for a single signature, so this pays the statement
        out, which is what Kompass did before there were constraints at all.
        What such a signature may no longer do is *add up*: the account is
        recorded, so two clicks are one signer rather than a quorum of two.
        """
        admin = User.objects.create_user("admin", password="secret")
        self.assertTrue(self.statement.approve(None, user=admin))
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(statement.confirmed)
        signature = statement.approval_set.get()
        self.assertEqual(signature.user, admin)
        self.assertIsNone(signature.member)
        self.assertEqual(signature.signer, ("user", admin.pk))
        self.assertIn(str(admin), str(signature))

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

    def test_a_statement_whose_rules_break_after_submission_is_not_approved(self):
        """ "No constraints" means *approved*, so the rows may not simply go.

        A statement whose rules report a problem persists nothing: its rows
        are retired, and with no rows at all ``fully_approved`` answers yes to
        an empty list and the payload reads ``approved: true`` for a statement
        nobody has signed. The payout was refused either way — ``_pay_out``
        checks the problem itself, and ``confirm`` checks the validity — so
        this is what a person is *told*, which is the half the record is for.

        Since #555 the superseded rows are still there, so the gate can
        answer with what the record last asked for.
        """
        bill = self.statement.bill_set.first()
        bill.paid_by = None
        bill.save()
        statement = Statement.objects.get(pk=self.statement.pk)
        self.assertTrue(statement.rule_result.errors, "the rules report a problem")
        self.assertEqual(statement.approval_constraint_set.count(), 0, "nothing live")
        self.assertEqual(
            [row.name for row in ApprovalConstraint.all_objects.filter(statement=statement)],
            ["Freigabe"],
            "and the record of what was asked for is kept",
        )
        self.assertEqual([state.name for state in gate_of(statement)], ["Freigabe"])
        self.assertFalse(statement.fully_approved)
        self.assertFalse(approval_payload(statement, self.treasurer)["approved"])
        # And the money does not move, by either door.
        self.assertFalse(statement.approve(self.treasurer))
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirm(confirmer=self.treasurer))
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

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
        statement = Statement.objects.create(short_description="Gross")
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
        # And it says so in words, rather than reading as unsigned.
        self.assertEqual(state_display(states_by_name["Vorstand"]), _("Does not apply"))
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
        # The same person signing again adds nothing, and the database says so
        # rather than leaving it to the arithmetic.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Approval.objects.create(statement=big, member=self.anna)
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.approve(self.anna), "signing twice is signing once")
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.fully_approved)
        self.assertEqual(big.approval_set.count(), 1)
        self.assertTrue(big.approve(self.bernd))
        self.assertTrue(Statement.objects.get(pk=big.pk).confirmed)

    def test_a_forbid_cannot_be_overridden_by_the_person_it_excluded(self):
        """Recording an override is a mitigation; refusing it is the control.

        The forbid says nobody this statement pays may approve it. An override
        that ignored it would make that rule a formality for anybody holding
        the permission — and the person it names is exactly the person with a
        reason to use it.
        """
        big = self.statement_for(Decimal("1200.00"), self.anna)
        self.assertTrue(
            big.approval_constraint_set.filter(name="Kasse").exists(),
            "there is a Kasse row to override, which is what makes this a test",
        )
        self.assertFalse(big.override_approval("Kasse", self.anna, "Fristende"))
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.approval_constraint_set.get(name="Kasse").overridden)
        self.assertFalse(big.confirmed)
        # Somebody the forbid did not name may still override it (the payout
        # waits for the second constraint, which is why this returns False).
        self.assertFalse(big.override_approval("Kasse", self.bernd, "Fristende"))
        self.assertTrue(
            Statement.objects.get(pk=big.pk).approval_constraint_set.get(name="Kasse").overridden
        )

    def test_a_broken_forbid_stops_the_payout_instead_of_disabling_itself(self):
        """A section's predicate that raises leaves the statement stuck.

        Which is the safe direction: the alternatives are to persist no
        constraints at all — a statement payable without a signature — or to
        resolve them as if the rule had said nothing.
        """
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(ANGRY_FORBID, encoding="utf-8")
        row, problems = import_from_directory(package, name="angry-forbid")
        self.assertEqual(problems, [])
        big = self.statement_for(Decimal("1200.00"), self.anna)
        rows = {row.name: row for row in big.approval_constraint_set.all()}
        resolved = {state.name: state for state in big.approval_states}
        # One failure, two constraints: collapsing them into a single
        # unresolved row turned a board's two signatures into one row that one
        # override could clear.
        self.assertEqual(sorted(rows), ["Kasse", "Vorstand"])
        self.assertEqual(rows["Vorstand"].required, 2)
        for constraint in rows.values():
            self.assertIn("kaputt", constraint.error)
            self.assertEqual(constraint.eligible_member_ids, [])
            self.assertEqual(state_display(resolved[constraint.name]), _("Could not be resolved"))
        self.assertFalse(big.fully_approved)
        self.assertFalse(big.may_be_approved_by(self.anna))
        self.assertFalse(big.approve(self.anna))
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed)

    def test_a_broken_forbid_may_not_be_overridden_either(self):
        """ "Stuck" has to mean unpayable, and an override is a way to pay.

        A broken forbid is a rule that failed to say who is excluded, so there
        is no answer to "may this person sign it off" — and the person with
        the most reason to ask is the payee the forbid was written for. She
        cleared her own constraint and the statement paid out.
        """
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(ANGRY_FORBID, encoding="utf-8")
        row, problems = import_from_directory(package, name="angry-forbid")
        self.assertEqual(problems, [])
        big = self.statement_for(Decimal("1200.00"), self.anna)
        self.assertTrue(
            big.approval_constraint_set.filter(name="Kasse").exists(),
            "there is a Kasse row to override, which is what makes this a test",
        )
        self.assertFalse(big.override_approval("Kasse", self.anna, "Fristende"))
        self.assertFalse(big.override_approval("Kasse", self.bernd, "Fristende"))
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.approval_constraint_set.get(name="Kasse").overridden)
        self.assertFalse(big.confirmed)

    def test_a_signature_as_an_account_and_then_as_a_member(self):
        """Signing twice is signing once, even across the two identities.

        An administrator signs before their member record exists and again
        after it does. The lookup used to be the whole row — member *and*
        account — so the second signature missed it, violated the account's
        own uniqueness constraint and raised a bare `IntegrityError`: a 500
        where the answer was "you have already signed".
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.approve(None, user=self.anna_user))
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.approve(self.anna, user=self.anna_user))
        self.assertEqual(big.approval_set.count(), 1)
        # And the other way round, on a second statement.
        other = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(other.approve(self.anna, user=self.anna_user))
        other = Statement.objects.get(pk=other.pk)
        self.assertFalse(other.approve(None, user=self.anna_user))
        self.assertEqual(other.approval_set.count(), 1)

    def test_a_fallback_to_other_rules_does_not_drop_a_frozen_forbid(self):
        """The hole the mid-flight fix opened, and what bounds it now.

        Re-resolution took today's constraints wholesale. `ruleset_for` falls
        back to the active version, and then to the reference ruleset, on
        nothing worse than a statement created before the first import or an
        upgrade that makes an old snapshot unloadable — and the reference
        ruleset has no forbids. So the section's conflict of interest
        evaporated, the excluded payee signed her own 1.200 € payout, and the
        record was left reading "Kasse: not signed" while the money moved.

        Now a re-resolution is only accepted from the version the rows were
        frozen under, and the frozen rows are the spine in any case. What this
        test pins is the spine: the reference ruleset names a differently
        *named* step, so the version bound never comes into it, which is why
        it has a test of its own below
        (``test_only_the_version_the_rows_were_frozen_under_may_widen_the_group``).
        """
        big = self.statement_for(Decimal("1200.00"), self.anna)
        kasse = big.approval_constraint_set.get(name="Kasse")
        self.assertNotIn(self.anna.pk, kasse.eligible_member_ids)
        # The statement loses its own closure — which is exactly the state of
        # every statement created before the first import — and the section's
        # rules are replaced as the active version.
        import_from_directory(reference_directory(), name="heidelberg-later")
        Statement.objects.filter(pk=big.pk).update(ruleset_snapshot={})
        big = Statement.objects.get(pk=big.pk)
        names = [state.name for state in big.live_approval_states]
        self.assertEqual(names, ["Kasse", "Vorstand"], "not the reference ruleset's own step")
        self.assertFalse(big.may_be_approved_by(self.anna))
        self.assertFalse(big.approve(self.anna))
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed)
        self.assertFalse(big.fully_approved)

    def vacant_group_version(self, *, anyone_permitted):
        """Import the vacant-group ruleset, with the opt-in on or off."""
        package = Path(self.directory.name)
        source = VACANT_GROUP.replace(
            "anyone_permitted=ANYONE_PERMITTED", f"anyone_permitted={anyone_permitted}"
        )
        (package / "__init__.py").write_text(source, encoding="utf-8")
        row, problems = import_from_directory(package, name=f"vacant-{anyone_permitted}")
        self.assertEqual(problems, [])
        return row

    def test_a_vacant_group_leaves_the_statement_waiting_for_a_person(self):
        """End to end: the role is unfilled, so nobody may sign — least of all
        the person being paid, whom the forbids never even saw, because there
        was nobody in the group to iterate over.
        """
        self.vacant_group_version(anyone_permitted=False)
        big = self.statement_for(Decimal("1200.00"), self.anna)
        constraint = big.approval_constraint_set.get()
        self.assertEqual(constraint.eligible_member_ids, [])
        self.assertEqual(constraint.excluded, [])
        self.assertEqual(state_display(big.approval_states[0]), _("Nobody may sign"))
        self.assertFalse(big.fully_approved)
        for signer in (self.anna, self.bernd, self.clara):
            self.assertFalse(big.may_be_approved_by(signer))
            self.assertFalse(big.approve(signer))
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed)

    def test_the_same_section_saying_it_means_whoever_may_act(self):
        """With the opt-in, the engine fills the group in — forbids and all."""
        self.vacant_group_version(anyone_permitted=True)
        big = self.statement_for(Decimal("1200.00"), self.anna)
        constraint = big.approval_constraint_set.get()
        self.assertEqual(
            sorted(constraint.eligible_member_ids), sorted([self.bernd.pk, self.clara.pk])
        )
        self.assertIn({"member": self.anna.pk, "forbid": "Befangenheit"}, constraint.excluded)
        self.assertFalse(big.approve(self.anna), "the payee is still the payee")
        big = Statement.objects.get(pk=big.pk)
        self.assertTrue(big.approve(self.bernd))
        self.assertTrue(Statement.objects.get(pk=big.pk).confirmed)

    def test_a_frozen_exclusion_survives_a_resolution_that_forgets_it(self):
        """A forbid is sticky; eligibility is not.

        The appointed-treasurer fix needs today's answer to who may act, and
        the audit needs yesterday's answer to who may not. Both, by taking the
        frozen rows as the spine and subtracting anybody a *forbid* removed
        from whatever today's resolution produced — the permission exclusions
        being the one kind that is re-asked, because the capability is a
        question about now.
        """
        big = self.statement_for(Decimal("1200.00"), self.anna)
        generous = [
            {
                "name": "Kasse",
                "description": "",
                "applicable": True,
                "required": 1,
                "eligible": [self.anna.pk, self.bernd.pk],
                "excluded": [],
                "error": "",
            },
            {
                "name": "Vorstand",
                "description": "",
                "applicable": True,
                "required": 2,
                "eligible": [self.anna.pk, self.bernd.pk],
                "excluded": [],
                "error": "",
            },
        ]
        with patch("finance.engine.statements.resolve_constraints", return_value=generous):
            states_by_name = {state.name: state for state in big.live_approval_states}
        self.assertEqual(sorted(states_by_name), ["Kasse", "Vorstand"])
        kasse = states_by_name["Kasse"]
        self.assertNotIn(self.anna.pk, kasse.eligible, "the payee stays excluded")
        self.assertIn(self.bernd.pk, kasse.eligible)
        self.assertIn(Exclusion(member=self.anna.pk, forbid="Befangenheit"), kasse.excluded)
        # And a resolution that forgets a whole constraint cannot drop it: the
        # frozen rows are the spine, so a requirement can only be added by
        # re-asking, never removed. (Unreachable while the rules and the
        # transfers are both frozen, which is exactly why it is asserted.)
        # A *fresh* instance: `live_approval_states` caches per instance, so
        # re-reading `big` here would assert the answer from the block above.
        again = Statement.objects.get(pk=big.pk)
        with patch("finance.engine.statements.resolve_constraints", return_value=generous[:1]):
            names = {state.name: state for state in again.live_approval_states}
        self.assertEqual(sorted(names), ["Kasse", "Vorstand"])
        self.assertEqual(names["Vorstand"].required, 2)
        self.assertNotIn(self.anna.pk, names["Vorstand"].eligible)

    def test_the_gate_does_not_read_the_answer_the_record_wrote_down(self):
        """The record carries ``satisfied``; the gate may not read it.

        The two resolutions are supposed to disagree, and this is the
        direction that makes the difference worth having: a signature that
        counted when it was given stays on the record, while the gate asks who
        may sign *now* — so a signer who has since lost the capability stops
        advancing the step they signed. The gate is handed the same frozen
        rows, `satisfied` column and all, and asks `states` without
        `recorded=True`: answering from the row instead would let the record
        decide what the gate is for.
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.approve(self.anna), "Kasse is in, Vorstand wants two")
        self.assertTrue(big.approval_constraint_set.get(name="Kasse").satisfied)
        # Anna leaves the finance department.
        self.anna_user.user_permissions.clear()
        record = {state.name: state for state in Statement.objects.get(pk=big.pk).approval_states}
        self.assertTrue(record["Kasse"].satisfied, "she signed it, and that is the record")
        gate = {state.name: state for state in gate_of(big)}
        self.assertNotIn(self.anna.pk, gate["Kasse"].eligible)
        self.assertFalse(gate["Kasse"].satisfied, "and she may not sign it any more")
        self.assertTrue(gate["Kasse"].open)
        self.assertFalse(Statement.objects.get(pk=big.pk).fully_approved)

    def test_the_rendering_does_not_contradict_itself_in_its_own_line(self):
        """#551: the words came from the row, every other field from the state.

        The same situation as the test above, read through the payload the
        ``/approval`` endpoint and the admin page are both built from. The row
        is right about what it records — Anna's signature satisfied Kasse
        when she gave it, and #552 keeps that — and wrong as a rendering of
        the gate, which has just stopped counting her. Measured before the
        fix: ``satisfied: false``, ``open: true``, ``missing: 1``, ``signed_by:
        []`` and, in the same dict, ``state_display: "Signed"``.
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.approve(self.anna), "Kasse is in, Vorstand wants two")
        self.assertTrue(big.approval_constraint_set.get(name="Kasse").satisfied)
        self.anna_user.user_permissions.clear()
        payload = approval_payload(Statement.objects.get(pk=big.pk))
        kasse = next(row for row in payload["constraints"] if row["name"] == "Kasse")
        self.assertFalse(kasse["satisfied"])
        self.assertTrue(kasse["open"])
        self.assertEqual(kasse["missing"], 1)
        self.assertEqual(kasse["signed_by"], [])
        self.assertEqual(kasse["state_display"], _("Open"), "and the words agree with all of it")
        # The record of a settled statement reads the row, and says the other
        # thing on purpose: `approval_states` is resolved *from* the frozen
        # row, so the same function renders "signed" for the audit trail.
        record = {state.name: state for state in Statement.objects.get(pk=big.pk).approval_states}
        self.assertEqual(state_display(record["Kasse"]), _("Signed"))

    def test_a_recorded_signature_is_not_rewritten_by_the_next_one(self):
        """#552: the column was a cache of the gate rather than a record.

        Anna, the treasurer, signs "Kasse" and the column records it. She
        loses the capability, so the gate stops counting her signature —
        correctly, that is what the gate is for — and Bernd then signs the
        *other* step. Re-syncing every row to the gate's answer on the way
        past wrote that verdict over the record of hers: Kasse's column came
        back ``False`` while her ``Approval`` row still stood. No money ever
        moved on it — the signatures are the trail and the column is read for
        display — but a record that is edited is the one thing §6's appeal to
        the GoBD's *Unveränderbarkeit* cannot have.

        Two roles rather than two groups of signers, because that is what
        makes the rewrite observable at all; see :data:`TWO_ROLES`.
        """
        RoleAssignment.objects.create(role="kassenwart", member=self.anna)
        RoleAssignment.objects.create(role="vorstand", member=self.bernd)
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(TWO_ROLES, encoding="utf-8")
        version, problems = import_from_directory(package, name="two-roles")
        self.assertEqual(problems, [])
        big = self.statement_for(Decimal("1200.00"), self.clara)
        rows = {row.name: row for row in big.approval_constraint_set.all()}
        self.assertEqual(rows["Kasse"].eligible_member_ids, [self.anna.pk])
        self.assertEqual(rows["Vorstand"].eligible_member_ids, [self.bernd.pk])
        self.assertFalse(big.approve(self.anna), "the board has not signed yet")
        self.assertTrue(big.approval_constraint_set.get(name="Kasse").satisfied)
        # Anna leaves the finance department, which empties Kasse's group: the
        # statement is stuck, and that much is the gate working.
        self.anna_user.user_permissions.clear()
        self.assertFalse(Statement.objects.get(pk=big.pk).approve(self.bernd))
        after = {row.name: row for row in big.approval_constraint_set.all()}
        self.assertTrue(after["Kasse"].satisfied, "she signed it, and that is the record")
        self.assertTrue(after["Vorstand"].satisfied, "and the step just signed is recorded too")
        self.assertTrue(big.approval_set.filter(member=self.anna).exists())
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed)
        # The gate still disagrees, which is the point of having two answers.
        gate = {state.name: state for state in gate_of(big)}
        self.assertFalse(gate["Kasse"].satisfied)
        self.assertEqual(gate["Kasse"].eligible, ())

    def test_a_step_that_can_no_longer_be_resolved_says_so_rather_than_open(self):
        """#551 again, and the residue of #546: an unresolvable step read "Open".

        A step the rules can no longer resolve names nobody and carries the
        reason, and the payload said "Open" beside an empty ``eligible`` — the
        row having been resolved while the rules still worked.

        The re-resolution is patched, which is the seam its sibling above uses
        too: under an unchanged version the same rules only start failing on
        data they did not see at submission — a forbid that raises on the
        treasurer appointed since — and what is under test here is the
        rendering of that state, not how it arises.
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        unresolvable = [
            {
                "name": name,
                "description": "",
                "applicable": True,
                "required": 1,
                "eligible": [],
                "excluded": [],
                "error": "RuleError: the forbid 'Befangenheit' failed",
            }
            for name in ("Kasse", "Vorstand")
        ]
        with patch("finance.engine.statements.resolve_constraints", return_value=unresolvable):
            payload = approval_payload(Statement.objects.get(pk=big.pk))
        kasse = next(row for row in payload["constraints"] if row["name"] == "Kasse")
        self.assertEqual(kasse["eligible"], [])
        self.assertEqual(kasse["state_display"], _("Could not be resolved"))

    def test_only_the_version_the_rows_were_frozen_under_may_widen_the_group(self):
        """The bound that the frozen spine does not provide, found by #549's audit.

        Its sibling above — "a fallback to other rules does not drop a frozen
        forbid" — stayed green with the version check removed, because the
        ruleset it falls back to names a *differently* named step, so the
        spine kept the section's rows untouched and the check never mattered.
        Two sections that ask for the same-named signature from different
        groups are the case it was written for: the frozen row and today's
        resolution agree on the name, the merge takes today's eligible set,
        and a forbid cannot bar somebody the section's own rules never named.
        So an unrelated version would hand the signature to whoever *it*
        names, on nothing worse than a statement that lost its own closure.
        """
        package = Path(self.directory.name)
        narrow = one_step("narrow", "tuple(sorted(signers, key=lambda m: int(m.id))[:1])")
        (package / "__init__.py").write_text(narrow, encoding="utf-8")
        row, problems = import_from_directory(package, name="narrow")
        self.assertEqual(problems, [])
        statement = self.statement_for(Decimal("100.00"), self.clara)
        named = min(member.pk for member in (self.anna, self.bernd, self.clara))
        outsider = next(
            member for member in (self.anna, self.bernd, self.clara) if member.pk != named
        )
        self.assertEqual(statement.approval_constraint_set.get().eligible_member_ids, [named])
        # Another section's version takes over, naming everybody for the step
        # this one named one person for, and the statement loses its own
        # closure — which is the state of every statement created before the
        # first import, and of every one whose snapshot stops loading.
        (package / "__init__.py").write_text(one_step("wide", "tuple(signers)"), encoding="utf-8")
        wide, problems = import_from_directory(package, name="wide")
        self.assertEqual(problems, [])
        self.assertNotEqual(wide.hash, row.hash)
        Statement.objects.filter(pk=statement.pk).update(ruleset_snapshot={})
        gate = {state.name: state for state in gate_of(statement)}
        self.assertEqual(gate["Kasse"].eligible, (named,), "the other version's group is not read")
        again = Statement.objects.get(pk=statement.pk)
        self.assertFalse(again.may_be_approved_by(outsider))
        self.assertFalse(again.approve(outsider))
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_snapshot_that_will_not_load_does_not_widen_the_group(self):
        """The other half of #553: degrading may not substitute other rules.

        Falling back is safe only while the fallback cannot *answer* for the
        section. ``loaded_ruleset`` reported the active row's hash even when
        that row was the row that would not load and the **reference** ruleset
        had answered — so for the ordinary case, a statement frozen under the
        version that has just stopped loading, the hash matched itself, the
        bound in :func:`_rows_from_the_same_rules` passed, and eligibility was
        re-resolved under rules the section never wrote.

        It bites because the step name survives: this section narrowed the
        reference ruleset's ``Freigabe`` to the treasurer, so the reference
        ruleset's own ``Freigabe`` — whoever holds the capability — lands on
        the same row in the merge. The quorum and the frozen forbids stay; who
        may sign widens from one person to everybody. Reported as ``""``, the
        bound fails and the frozen rows stand.
        """
        RoleAssignment.objects.create(role="kassenwart", member=self.anna)
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(NARROW_FREIGABE, encoding="utf-8")
        version, problems = import_from_directory(package, name="narrow-freigabe")
        self.assertEqual(problems, [])
        statement = self.statement_for(Decimal("100.00"), self.clara)
        row = statement.approval_constraint_set.get()
        self.assertEqual(row.name, "Freigabe", "the name the reference ruleset uses as well")
        self.assertEqual(row.eligible_member_ids, [self.anna.pk])
        # The upgrade this is written for: `kompass.rules` renamed something
        # the section's rules import, so neither the statement's snapshot nor
        # the version in force loads any more — while the row stays ACTIVE,
        # because nothing re-imports it. `update()` because a stored version is
        # immutable through `save`, which is the hole `verify` watches.
        gone = {"__init__.py": "from kompass.rules import Gone\n"}
        RuleSet.objects.filter(pk=version.pk).update(sources=gone)
        Statement.objects.filter(pk=statement.pk).update(
            ruleset_snapshot={**statement.ruleset_snapshot, "sources": gone}
        )
        gate = {state.name: state for state in gate_of(statement)}
        self.assertEqual(gate["Freigabe"].eligible, (self.anna.pk,), "nobody is added")
        waiting = Statement.objects.get(pk=statement.pk)
        self.assertFalse(waiting.may_be_approved_by(self.bernd))
        self.assertFalse(waiting.approve(self.bernd), "and a signature from him advances nothing")
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)
        # The treasurer the section did name can still sign, which is what
        # says the statement degraded rather than seized up.
        self.assertTrue(Statement.objects.get(pk=statement.pk).approve(self.anna))

    def test_an_override_of_one_step_leaves_the_other_standing(self):
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.override_approval("Vorstand", self.anna, "Fristende"))
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.confirmed)
        self.assertTrue(big.approve(self.bernd))
        self.assertTrue(Statement.objects.get(pk=big.pk).confirmed)

    def cover_another_receipt(self, statement, payer, amount=Decimal("30.00")):
        """The one edit a submitted statement stays open for.

        The finance officer covering a receipt after submission —
        ``BillOnStatementProxy``'s whole reason to exist — resolves the
        statement again through ``Bill.save`` → ``_refresh_statement`` →
        ``freeze_obligations``, and the transactions are re-booked against the
        new total as they would be in the admin.

        ``payer`` is explicit, and that is the point: this section's forbid
        excludes whoever the payout pays, so *who* fronted the receipt decides
        whether the eligible set changes between the two freezes. Covering a
        receipt for somebody who was already being paid leaves the sets
        identical and exercises none of the merge — which is the case #546 was
        filed for, and the one a first version of these tests missed.
        """
        Bill.objects.create(
            statement=statement,
            short_description="Essen",
            amount=amount,
            costs_covered=True,
            paid_by=payer,
        )
        statement = Statement.objects.get(pk=statement.pk)
        statement.transaction_set.all().delete()
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def test_a_re_freeze_keeps_who_overrode_a_step_and_why(self):
        """#555, and the record the whole versioning argument is about.

        An override is "we went ahead anyway", and its entire value is the
        record of who decided that and what reason they gave. Re-freezing
        *deleted* the constraint rows and wrote fresh ones, so a finance
        officer covering an unrelated receipt — an ordinary action, and the
        one edit a submitted statement stays open for — turned
        ``(overridden_by=bernd, override_reason="Fristende")`` into
        ``(None, "")``. Both halves were wrong: the authorisation was gone
        from the record, and the payout was back in front of the board that
        had already waived it.

        The rows are superseded now, the way ``Obligation`` rows have been
        since ``0019``, and the decision taken about a step is carried onto
        the row that takes over.
        """
        _dana_user, dana = a_user("dana", permitted=True)
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.override_approval("Vorstand", self.bernd, "Fristende"))
        self.assertFalse(Statement.objects.get(pk=big.pk).confirmed, "Kasse is still open")
        before = big.approval_constraint_set.get(name="Vorstand")
        self.assertIn(dana.pk, before.eligible_member_ids)

        # Dana fronted the receipt, so the second resolution pays her and the
        # section's forbid excludes her: the eligible set is genuinely
        # different across the two freezes, which is what makes this a test of
        # the merge rather than of two identical answers.
        statement = self.cover_another_receipt(big, payer=dana)

        self.assertEqual(
            [row.name for row in statement.approval_constraint_set.all()],
            ["Kasse", "Vorstand"],
            "one live row per step, and a superseded row is not one of them",
        )
        board_now = statement.approval_constraint_set.get(name="Vorstand")
        self.assertNotIn(dana.pk, board_now.eligible_member_ids, "the group moved")
        self.assertIn(
            dana.pk, [int(item["member"]) for item in board_now.excluded], "under Befangenheit"
        )
        waived = statement.approval_constraint_set.get(name="Vorstand")
        self.assertEqual(waived.overridden_by, self.bernd)
        self.assertEqual(waived.override_reason, "Fristende")
        self.assertIsNotNone(waived.overridden_at)
        # The row that was replaced is kept, saying what it said.
        superseded = [
            row
            for row in ApprovalConstraint.all_objects.filter(statement=statement)
            if not row.live
        ]
        self.assertEqual(
            [row.name for row in superseded], ["Kasse", "Vorstand"], "kept, not deleted"
        )
        before = next(row for row in superseded if row.name == "Vorstand")
        self.assertEqual(before.overridden_by, self.bernd)
        self.assertEqual(before.override_reason, "Fristende")
        self.assertIn("superseded", str(before))
        # The gate does not ask the board again, and nothing counts twice.
        gate = gate_of(statement)
        self.assertEqual([state.name for state in gate], ["Kasse", "Vorstand"])
        board = next(state for state in gate if state.name == "Vorstand")
        self.assertTrue(board.overridden)
        self.assertFalse(board.open)
        # And what a treasurer reads still names the person and the reason.
        payload = approval_payload(statement, self.anna)
        shown = next(item for item in payload["constraints"] if item["name"] == "Vorstand")
        self.assertEqual(shown["overridden_by"].name, self.bernd.name)
        self.assertEqual(shown["override_reason"], "Fristende")
        self.assertEqual(shown["state_display"], _("Overridden"))
        # The one signature that was still outstanding pays it out: the
        # waiver survived the edit, so the board is not in the way.
        self.assertTrue(statement.approve(self.anna))
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_waiver_does_not_carry_onto_a_row_that_excludes_its_author(self):
        """The control #555's fix must not defeat, measured end to end.

        An override is refused from somebody a forbid excludes, because
        "recording that they did it is a mitigation rather than a control".
        Carrying an earlier copy of exactly that override is the same hole
        with a timestamp on it: ``ConstraintState.open`` reads ``overridden``
        on every call, the gate's included, so the waiver would go on closing
        the step for the person who may no longer give it.

        The sequence: Bernd waives the board's two signatures legitimately,
        the finance officer then covers a receipt **Bernd** fronted, and the
        new resolution excludes him under *Befangenheit*. The waiver stays on
        the row it was given on — that is #555 — and the row that takes over
        says why it did not come with it.
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.override_approval("Vorstand", self.bernd, "Fristende"))

        statement = self.cover_another_receipt(big, payer=self.bernd)

        board = statement.approval_constraint_set.get(name="Vorstand")
        self.assertFalse(board.overridden, "the waiver did not carry")
        self.assertIsNone(board.overridden_by)
        self.assertEqual(board.override_reason, "")
        self.assertIn("Befangenheit", board.override_withdrawn)
        self.assertIn(self.bernd.name, board.override_withdrawn)
        self.assertIn("Fristende", board.override_withdrawn, "and what it said")
        # It is not destroyed, which is the whole of #555: it is on the row
        # that was live when it was given.
        kept = [
            row
            for row in ApprovalConstraint.all_objects.filter(statement=statement, name="Vorstand")
            if not row.live
        ]
        self.assertEqual(len(kept), 1)
        self.assertEqual(kept[0].overridden_by, self.bernd)
        self.assertEqual(kept[0].override_reason, "Fristende")
        # The gate asks the board again, and the live path refuses the very
        # override the carried copy would have honoured.
        gate = {state.name: state for state in gate_of(statement)}
        self.assertFalse(gate["Vorstand"].overridden)
        self.assertTrue(gate["Vorstand"].open)
        self.assertFalse(statement.override_approval("Vorstand", self.bernd, "Fristende"))
        # So no payout: Anna's signature satisfies Kasse and nothing else.
        self.assertFalse(statement.approve(self.anna))
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_waiver_nobody_can_be_named_for_carries(self):
        """The other end of the forbid re-check: there is nobody to re-ask about.

        ``override_approval`` skips the forbid check when there is no member to
        check — an administrator with no member record, whom the capability
        layer let in — because a forbid matches member ids and matches nothing
        here. So the carry has nothing to re-ask either, and the waiver stands
        even though this resolution excludes somebody else entirely. The row
        goes on saying that it was given and that nobody can be named for it,
        which is what ``Approval.signer`` says about the same case one model
        over.
        """
        big = self.statement_for(Decimal("1200.00"), self.clara)
        self.assertFalse(big.override_approval("Vorstand", None, "Vorstandsbeschluss"))

        statement = self.cover_another_receipt(big, payer=self.bernd)

        board = statement.approval_constraint_set.get(name="Vorstand")
        self.assertTrue(board.overridden, "a waiver with no author still carries")
        self.assertIsNone(board.overridden_by)
        self.assertEqual(board.override_reason, "Vorstandsbeschluss")
        self.assertEqual(board.override_withdrawn, "", "there was nothing to withdraw")
        # Bernd is excluded by the forbid now, which is what makes this the
        # same shape as the test above with the author taken out of it.
        self.assertIn(self.bernd.pk, [int(item["member"]) for item in board.excluded])
        self.assertTrue(statement.approve(self.anna))
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_superseded_constraint_row_is_never_written_again(self):
        """The other half of #555's measurement: the ``satisfied`` column.

        A signed step read ``satisfied: True``; the officer covered a receipt
        and both columns read ``False`` again. No money moved, because the
        gate counts signatures — but the column is the *record* of what was
        true when the statement was signed (#552), and an unrelated edit
        rewriting it is what §6's *Unveränderbarkeit* cannot live with.

        So the answer is carried onto the live row, and the superseded row
        keeps its own: a later signature writes the live rows and never
        reaches back. The statement is unpayable here for an unrelated
        reason, which is what lets a signature be recorded without the
        statement confirming and the rows freezing for good.
        """
        _dana_user, dana = a_user("dana", permitted=True)
        big = self.statement_for(Decimal("1200.00"), self.clara)
        big.transaction_set.all().delete()
        self.assertFalse(big.approve(self.anna), "Vorstand still wants two")
        signed = Statement.objects.get(pk=big.pk).approval_constraint_set.get(name="Kasse")
        self.assertTrue(signed.satisfied)
        self.assertIn(dana.pk, signed.eligible_member_ids)

        # Again the receipt is Dana's, so the eligible set changes with it.
        statement = self.cover_another_receipt(big, payer=dana)
        self.assertNotIn(
            dana.pk,
            statement.approval_constraint_set.get(name="Kasse").eligible_member_ids,
            "the group moved between the two freezes",
        )

        rows = {row.name: row for row in statement.approval_constraint_set.all()}
        self.assertTrue(rows["Kasse"].satisfied, "the step stays signed across the re-freeze")
        self.assertFalse(rows["Vorstand"].satisfied)
        kept = ApprovalConstraint.all_objects.filter(
            statement=statement, superseded_at__isnull=False
        )
        self.assertEqual(
            {row.name: row.satisfied for row in kept}, {"Kasse": True, "Vorstand": False}
        )
        # The second signature completes the board's quorum. It writes the
        # live row and may not touch the row that was replaced.
        self.assertTrue(statement.approve(self.bernd))
        live = statement.approval_constraint_set.get(name="Vorstand")
        self.assertTrue(live.satisfied)
        self.assertEqual(
            {row.name: row.satisfied for row in kept.all()},
            {"Kasse": True, "Vorstand": False},
            "a superseded row is history and is never written again",
        )


class BootstrapAccountTestCase(TestCase):
    """A brand new instance can approve a payout through the ordinary path.

    This is the test that would have caught the one real cost of making an
    empty eligible group mean *nobody*: ``permission_holders`` names members,
    the documented bootstrap account had no member row, so on a fresh
    deployment the frozen group came out empty, ``confirm()`` refused, and the
    only way to pay anybody was the override — the mechanism reserved for "we
    went ahead anyway", which would have recorded every legitimate payout as
    *overridden by nobody* rather than *signed*.
    """

    def setUp(self):
        with patch.dict(
            os.environ,
            {
                "DJANGO_SUPERUSER_USERNAME": "kompass",
                "DJANGO_SUPERUSER_PASSWORD": "secret",
                "DJANGO_SUPERUSER_EMAIL": "admin@localhost",
            },
        ):
            call_command("ensuresuperuser", stdout=StringIO())
        self.user = User.objects.get(username="kompass")
        self.member = Member.objects.get(user=self.user)
        self.ledger = Ledger.objects.create(name="Konto")

    def test_the_only_account_there_is_can_sign_a_payout_off(self):
        payee = Member.objects.create(
            prename="Anna", lastname="Test", email="a@localhost", gender=MALE
        )
        statement = Statement.objects.create(short_description="Erste")
        Bill.objects.create(
            statement=statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=payee,
        )
        statement.submit(submitter=payee)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        statement = Statement.objects.get(pk=statement.pk)
        # The rules can name the bootstrap account, so the group is not empty.
        self.assertEqual(
            statement.approval_constraint_set.get().eligible_member_ids, [self.member.pk]
        )
        self.assertTrue(self.user.has_perm("finance.approve_obj_statement", statement))
        self.assertTrue(statement.confirm(self.member, user=self.user))
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(statement.confirmed)
        self.assertEqual(statement.confirmed_by, self.member)
        # Signed, not overridden: the override's signal is intact.
        constraint = statement.approval_constraint_set.get()
        self.assertTrue(constraint.satisfied)
        self.assertFalse(constraint.overridden)
        self.assertEqual(statement.approval_set.get().member, self.member)
