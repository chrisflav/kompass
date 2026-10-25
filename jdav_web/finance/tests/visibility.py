"""Seeing the statement you have been asked to sign.

Measured on the running Ludwigsburg instance, for a member holding the role
``ressortleitung`` and ``finance.process_statementsubmitted``, against a
submitted statement she had not created::

    finance.view_obj_statement     False
    finance.approve_obj_statement  True

Her signature would have *completed* the approval, and she could not open the
page that would have let her give it. The two rights came from unrelated
places: viewing was an object ACL — creator, the trip's leadership, finance
staff — and signing was the approval engine, which knows who the section's
rules named. Nothing reconciled them. Under Heidelberg it never showed, because
Heidelberg's one signature comes from the finance department, who may see
everything anyway; Ludwigsburg is the first ruleset to name a signer who is not
finance staff.

So being named a signer now confers the sight of that statement, and these are
the tests of what "named" means. Two of them are the whole point and the rest
draw its edges:

* :meth:`SignerVisibilityTestCase.test_the_named_signer_can_fetch_list_and_sign`
  — a member the rules name, who is not finance staff and did not create the
  statement, reaches it three ways and signs it;
* :meth:`SignerVisibilityTestCase.test_a_member_the_rules_did_not_name_cannot_see_it`
  — which is what keeps this from becoming "everybody can see everything".
"""

import datetime
import uuid
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from finance.engine import import_from_directory
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.rules import is_named_signer
from finance.rules import may_approve
from finance.store import ApprovalConstraint
from finance.store import RoleAssignment
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import MALE
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

#: Ludwigsburg's shape, reduced to what this is about: the department head
#: releases her own area's statement, and over a thousand euro the treasurer
#: signs as well. Both groups come from dated roles rather than from the
#: capability, which is exactly why neither of them is finance staff.
#:
#: It asks two questions, which the signature is *about*: the arithmetic of a
#: payout is not the statement, and a section whose rules ask for most of the
#: statement in answers has a signer who has to read them. One is grouped
#: under a step, because that is the grouping ``GET …/form`` serves and the
#: grouping a signer reads them in.
RESSORT_RULES = '''
from kompass.rules import Choice, Constraint, Input, Ruleset, SECTION, PARTICIPANTS, Transfer


class RessortRules(Ruleset):
    """The department head releases; over a thousand euro the treasurer too."""

    name = "ressort"
    permissions = ("finance.process_statementsubmitted",)
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx):
        return [
            Input(
                "naechte",
                "Uebernachtungen",
                "int",
                required=False,
                step="Angaben",
                help="Wie viele Naechte die Gruppe unterwegs war.",
            ),
            Input(
                "regelwerk",
                "Regelwerk",
                "choice",
                required=False,
                step="Angaben",
                choices=(Choice("jdav", "JDAV-Richtlinie"), Choice("dav", "DAV-Satzung")),
            ),
        ]

    def transfers(self, ctx):
        transfers = []
        for bill in ctx.bills:
            if bill.covered and bill.payer is not None:
                transfers.append(
                    Transfer(SECTION, bill.payer, bill.amount, "bill", rule_id="bills")
                )
        return transfers, []

    def approval(self, ctx, transfers):
        total = sum((t.amount for t in transfers), 0)
        return (
            [
                Constraint(
                    name="Freigabe der Leitung",
                    description="Die zustaendige Ressortleitung",
                    applicable=True,
                    required=1,
                    eligible=ctx.role_holders("ressortleitung"),
                ),
                Constraint(
                    name="Schatzmeister",
                    description="Ab 1.000 Euro auch der Schatzmeister",
                    applicable=total > 1000,
                    required=1,
                    eligible=ctx.role_holders("schatzmeister"),
                ),
            ],
            [],
        )


ruleset = RessortRules()
'''


def a_user(name, *, permitted=False):
    """A user with a member record, optionally able to act on statements."""
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


def bearer(user):
    """An ``Authorization`` header for ``user``: the API takes tokens only."""
    application = Application.objects.create(
        name="visibility-{}".format(uuid.uuid4().hex[:8]),
        client_type=Application.CLIENT_CONFIDENTIAL,
        authorization_grant_type=Application.GRANT_PASSWORD,
        client_secret="test-secret",
    )
    token = AccessToken.objects.create(
        user=user,
        application=application,
        token="tok-{}".format(uuid.uuid4().hex),
        expires=timezone.now() + datetime.timedelta(days=1),
        scope="read write",
    )
    return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}


class SignerVisibilityTestCase(TestCase):
    """A section whose signers are department heads rather than finance staff."""

    def setUp(self):
        # The people. Only `leitung` and `schatz` are named by the rules;
        # `kollegin` holds the very same capability and no role, which is the
        # control that says this grants sight of one statement rather than of
        # every statement.
        self.leitung_user, self.leitung = a_user("leitung", permitted=True)
        self.schatz_user, self.schatz = a_user("schatz", permitted=True)
        self.kollegin_user, self.kollegin = a_user("kollegin", permitted=True)
        self.fremde_user, self.fremde = a_user("fremde")
        self.payer_user, self.payer = a_user("zahlerin")
        RoleAssignment.objects.create(role="ressortleitung", member=self.leitung)
        RoleAssignment.objects.create(role="schatzmeister", member=self.schatz)
        self.ledger = Ledger.objects.create(name="Konto")
        # A section's chart of accounts, so "the accounts her statement's
        # bookings sit on" is measurably narrower than "the accounts". Two of
        # these carry her statement's bookings; the rest carry nothing of
        # hers, and she may read none of them.
        self.ledgers = [Ledger.objects.create(name=f"Konto {n:02d}") for n in range(1, 24)]
        self.topf, self.huetten = self.ledgers[2], self.ledgers[16]
        self.directory = TemporaryDirectory()
        package = Path(self.directory.name)
        (package / "__init__.py").write_text(RESSORT_RULES, encoding="utf-8")
        row, problems = import_from_directory(package, name="ressort")
        self.assertEqual(problems, [])
        self.version = row

    def tearDown(self):
        self.directory.cleanup()

    def a_draft(self, amount=Decimal("100.00")):
        """A statement of the payer's, with one covered receipt."""
        statement = Statement.objects.create(
            short_description="Materialkauf", created_by=self.payer
        )
        Bill.objects.create(
            statement=statement,
            short_description="Seil",
            amount=amount,
            costs_covered=True,
            paid_by=self.payer,
        )
        return Statement.objects.get(pk=statement.pk)

    def a_statement(self, amount=Decimal("100.00")):
        """The same, handed in and ready to be released."""
        statement = self.a_draft(amount)
        statement.submit(submitter=self.payer)
        statement.generate_transactions()
        statement.transaction_set.update(ledger=self.ledger)
        return Statement.objects.get(pk=statement.pk)

    def a_statement_on_two_ledgers(self):
        """A handed-in statement whose two bookings sit on two accounts.

        Two receipts rather than one, so the statement has more than one
        booking and the two can be put on *different* accounts — which is
        what makes "she reads the accounts her statement's bookings sit on"
        a claim with an answer that is neither empty nor everything.
        """
        statement = Statement.objects.create(short_description="Hüttenfahrt", created_by=self.payer)
        for description, amount in (("Seil", Decimal("56.00")), ("Hütte", Decimal("44.00"))):
            Bill.objects.create(
                statement=statement,
                short_description=description,
                amount=amount,
                costs_covered=True,
                paid_by=self.payer,
            )
        statement = Statement.objects.get(pk=statement.pk)
        statement.submit(submitter=self.payer)
        statement.generate_transactions()
        bookings = list(statement.transaction_set.order_by("id"))
        self.assertEqual(len(bookings), 2, "two receipts, two bookings to put on two accounts")
        for booking, ledger in zip(bookings, (self.topf, self.huetten)):
            booking.ledger = ledger
            booking.save()
        return Statement.objects.get(pk=statement.pk)

    def listed(self, user):
        """The statement ids the API lists for ``user``."""
        r = self.client.get("/api/finance/statements", **bearer(user))
        self.assertEqual(r.status_code, 200, r.content)
        return {row["id"] for row in r.json()}

    def fetch(self, user, statement):
        """The status code of a detail fetch of ``statement`` by ``user``."""
        r = self.client.get("/api/finance/statements/{}".format(statement.pk), **bearer(user))
        return r.status_code

    def may_view(self, user, statement):
        """``view_obj_statement``, asked of a freshly read user and row."""
        return User.objects.get(pk=user.pk).has_perm(
            "finance.view_obj_statement", Statement.objects.get(pk=statement.pk)
        )

    # --- the two that matter ---------------------------------------------

    def test_the_named_signer_can_fetch_list_and_sign(self):
        """The hole, end to end: she is named, so she can reach it and sign.

        She did not create the statement, she leads no excursion, she holds no
        ``view_global_statement`` — the three ways the object ACL used to let
        anybody in — and the rules name her on the one step they are asking
        for. Before the fix the first two assertions were 403 and an empty
        list while the third one already worked, which is the defect: a right
        to sign that could not be exercised.
        """
        statement = self.a_statement()
        self.assertTrue(self.may_view(self.leitung_user, statement))
        self.assertEqual(self.fetch(self.leitung_user, statement), 200)
        self.assertIn(statement.pk, self.listed(self.leitung_user))
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(statement.pk),
            content_type="application/json",
            data={"note": ""},
            **bearer(self.leitung_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["approved"])
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_a_member_the_rules_did_not_name_cannot_see_it(self):
        """And the other half, which is what stops this widening into nothing.

        ``kollegin`` holds ``process_statementsubmitted`` — the same
        capability the signer holds — and the rules name her on no step, so
        she sees nothing and may sign nothing. ``fremde`` holds neither. The
        creator is asserted alongside, so a run in which *nobody* can see
        anything cannot pass this.
        """
        statement = self.a_statement()
        for user in (self.kollegin_user, self.fremde_user):
            with self.subTest(user=user.username):
                self.assertFalse(self.may_view(user, statement))
                self.assertEqual(self.fetch(user, statement), 403)
                self.assertNotIn(statement.pk, self.listed(user))
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(statement.pk),
            content_type="application/json",
            data={"note": ""},
            **bearer(self.kollegin_user),
        )
        self.assertEqual(r.status_code, 403, r.content)
        self.assertFalse(Statement.objects.get(pk=statement.pk).confirmed)
        # The control: the statement is visible to somebody, so this test
        # cannot pass against a build that refuses everyone.
        self.assertTrue(self.may_view(self.payer_user, statement))
        self.assertIn(statement.pk, self.listed(self.payer_user))

    # --- what she gets to read once she is in -----------------------------

    def test_the_signer_reads_the_accounts_her_own_bookings_sit_on(self):
        """The seam for the account: the booking's own field, nothing wider.

        ``finance.view_ledger`` is the right to read the section's chart of
        accounts, and the signer does not hold it — she is a department head,
        not finance staff. What she needs is narrower by two orders: the
        accounts **her statement's own bookings sit on**, which is where the
        payout she is signing is charged.

        That seam already exists and is the narrowest one available: the
        account rides on the booking (``TransactionOut.ledger``) and the route
        that serves the bookings is authorized by the statement's own
        ``view_obj_statement`` — the very right :func:`is_named_signer` gives
        her. So being named a signer grants **no new permission at all**; it
        grants the statement, and the account comes with the booking.

        Asserted as *which* accounts and not as "it works", because "she can
        read an account" passes against a build that hands her the catalogue.
        Twenty-four accounts exist, two of them carry her bookings, and the
        three facts together are the seam: she reads those two, she reads them
        off the bookings, and the catalogue still refuses her.
        """
        statement = self.a_statement_on_two_ledgers()
        self.assertEqual(Ledger.objects.count(), 24, "a section's chart of accounts")
        r = self.client.get(
            "/api/finance/statements/{}/transactions".format(statement.pk),
            **bearer(self.leitung_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(
            {row["ledger"]["name"] for row in r.json()},
            {self.topf.name, self.huetten.name},
            "the two her bookings sit on, named",
        )
        # And nothing wider: the catalogue is still the capability's, which is
        # what makes the two above a seam rather than a grant.
        self.assertFalse(self.leitung_user.has_perm("finance.view_ledger"))
        self.assertEqual(
            self.client.get("/api/finance/ledgers/", **bearer(self.leitung_user)).status_code,
            403,
        )
        # The control, both halves: the member the rules did not name reads
        # neither the bookings nor the accounts on them.
        self.assertEqual(
            self.client.get(
                "/api/finance/statements/{}/transactions".format(statement.pk),
                **bearer(self.kollegin_user),
            ).status_code,
            403,
        )

    def test_the_signer_reads_the_answers_the_payout_was_computed_from(self):
        """What she is being asked to approve, and not only its arithmetic.

        Under a ruleset that asks for most of the statement in answers, the
        bills and the bookings are the *consequence* of the statement and not
        the statement — so a signer shown only those is being asked to sign
        for facts she has not been shown.

        ``GET …/form`` is where those facts live: the declarations the rules
        ask for, their labels, their grouping into steps and the stored
        answers, in one payload. It is authorized by ``view_obj_statement``,
        so the signer already reaches it and no second vocabulary is needed —
        which is the whole reason the approval surface renders *this* rather
        than a reading of its own.

        Asserted as the questions **and** their answers, because a payload
        carrying the questions with the answers dropped renders a form of
        dashes and reads as a statement nobody filled in.
        """
        statement = self.a_statement_on_two_ledgers()
        statement.inputs = {"naechte": 3, "regelwerk": "jdav"}
        statement.save()
        r = self.client.get(
            "/api/finance/statements/{}/form".format(statement.pk),
            **bearer(self.leitung_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(
            {declaration["key"]: declaration["label"] for declaration in body["inputs"]},
            {"naechte": "Uebernachtungen", "regelwerk": "Regelwerk"},
        )
        self.assertEqual(body["answers"], {"naechte": 3, "regelwerk": "jdav"})
        self.assertEqual(
            [(step["label"], step["keys"]) for step in body["steps"]],
            [("Angaben", ["naechte", "regelwerk"])],
            "the grouping she reads them in is the one the rules declared",
        )
        # And the member the rules did not name is shown none of it.
        self.assertEqual(
            self.client.get(
                "/api/finance/statements/{}/form".format(statement.pk),
                **bearer(self.kollegin_user),
            ).status_code,
            403,
        )

    def test_a_signature_is_still_asked_for_when_a_booking_has_no_account(self):
        """Signing is not paying, and a missing account only stops the paying.

        An account is bookkeeping the treasurer does; a signature is the
        department head's own act. So a booking with no account must not take
        her signature with it — and it did, because the one screen that offers
        the signature was reachable only on ``is_valid``, which a missing
        account makes false.

        The backend already draws the line in the right place, which is why
        the fix is the client's: the signature is **recorded** and the payout
        **refused**, so nothing moves and nothing is lost. Once the account is
        set, the signature already in is the one that releases it.
        """
        statement = self.a_statement()
        statement.transaction_set.update(ledger=None)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertEqual(statement.validity, Statement.MISSING_LEDGER)
        self.assertFalse(statement.is_valid())
        # She may still sign, and the screen reads exactly this field.
        self.assertTrue(statement.may_be_approved_by(self.leitung))
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(statement.pk),
            content_type="application/json",
            data={"note": ""},
            **bearer(self.leitung_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["approved"], "every signature the rules asked for is in")
        statement = Statement.objects.get(pk=statement.pk)
        self.assertFalse(statement.confirmed, "and the money has still not moved")
        # The account is the only thing that was missing, so setting it
        # releases the statement on the signature that was already given.
        statement.transaction_set.update(ledger=self.ledger)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertTrue(statement.confirm(self.leitung))
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    # --- what "named" means ----------------------------------------------

    def test_a_step_the_rules_are_not_asking_for_names_nobody(self):
        """The treasurer's step applies over a thousand euro, and not under it.

        A constraint that does not apply still carries the group the rules
        named for it, so reading every row would have handed the treasurer
        every small statement in the section — a global permission under
        another name. Both statements are asserted, because "he cannot see the
        small one" passes just as well against a build where he can see
        nothing.
        """
        small = self.a_statement(Decimal("100.00"))
        big = self.a_statement(Decimal("1200.00"))
        rows = {row.name: row for row in big.approval_constraint_set.all()}
        self.assertEqual(rows["Schatzmeister"].eligible_member_ids, [self.schatz.pk])
        self.assertFalse(small.approval_constraint_set.get(name="Schatzmeister").applicable)
        self.assertEqual(
            small.approval_constraint_set.get(name="Schatzmeister").eligible_member_ids,
            [self.schatz.pk],
            "the group is on the row either way; only `applicable` differs",
        )
        self.assertFalse(self.may_view(self.schatz_user, small))
        self.assertNotIn(small.pk, self.listed(self.schatz_user))
        self.assertTrue(self.may_view(self.schatz_user, big))
        self.assertIn(big.pk, self.listed(self.schatz_user))

    def test_the_signer_still_sees_the_statement_after_she_has_signed_it(self):
        """A page that vanishes the moment you use it is not a page.

        Over a thousand euro this section asks for two signatures. Once the
        department head has given hers she has nothing left to sign, so the
        *gate* — ``may_be_approved_by`` — says no, and she must still be able
        to read the statement she put her name to. That is the difference
        between ``is_named_signer`` and the approval right, and this is the
        test that tells them apart.
        """
        big = self.a_statement(Decimal("1200.00"))
        self.assertFalse(big.approve(self.leitung), "the treasurer has not signed yet")
        big = Statement.objects.get(pk=big.pk)
        self.assertFalse(big.confirmed)
        self.assertFalse(big.may_be_approved_by(self.leitung), "nothing left for her to sign")
        self.assertTrue(big.names_as_signer(self.leitung))
        self.assertTrue(self.may_view(self.leitung_user, big))
        self.assertIn(big.pk, self.listed(self.leitung_user))

    def test_a_settled_statement_still_shows_its_signers_what_they_signed(self):
        """Visibility survives the payout, because the record does.

        The record of what you put your name to is the thing you are
        accountable for, so it stays readable; and it is read off the frozen
        rows, so a settled statement costs no ruleset resolution to decide.
        """
        big = self.a_statement(Decimal("1200.00"))
        self.assertFalse(big.approve(self.leitung))
        self.assertTrue(Statement.objects.get(pk=big.pk).approve(self.schatz))
        big = Statement.objects.get(pk=big.pk)
        self.assertTrue(big.confirmed)
        self.assertFalse(big.may_be_approved_by(self.leitung), "there is nothing left to sign")
        self.assertTrue(self.may_view(self.leitung_user, big))
        self.assertIn(big.pk, self.listed(self.leitung_user))
        # And the member the rules never named still cannot read it.
        self.assertFalse(self.may_view(self.kollegin_user, big))

    def test_a_statement_that_is_not_handed_in_names_nobody(self):
        """A draft is its author's, and a rejected statement is a draft again.

        The rules have asked for no signature on a statement nobody has handed
        in — and a statement handed *back* keeps its constraint rows, so
        "there are rows naming her" is not the question. Being handed in is.
        """
        draft = self.a_draft()
        self.assertFalse(draft.names_as_signer(self.leitung))
        self.assertFalse(self.may_view(self.leitung_user, draft))
        self.assertNotIn(draft.pk, self.listed(self.leitung_user))
        draft.submit(submitter=self.payer)
        submitted = Statement.objects.get(pk=draft.pk)
        self.assertTrue(self.may_view(self.leitung_user, submitted))
        self.assertIn(submitted.pk, self.listed(self.leitung_user))
        # Rejected back to its author: the rows are still live and still name
        # her, and she is no longer being asked for anything.
        submitted.status = Statement.UNSUBMITTED
        submitted.save()
        rejected = Statement.objects.get(pk=draft.pk)
        self.assertEqual(
            [row.eligible_member_ids for row in rejected.approval_constraint_set.all()],
            [[self.leitung.pk], [self.schatz.pk]],
            "the rows survive the rejection, which is why the status is asked",
        )
        self.assertFalse(self.may_view(self.leitung_user, rejected))
        self.assertNotIn(rejected.pk, self.listed(self.leitung_user))

    def test_the_right_to_sign_carries_the_right_to_look_on_its_own(self):
        """Appointed while the statement was in flight: the gate's own answer.

        The record names who the rules named *at submission*, and the gate
        re-asks eligibility — a treasurer appointed since holds the capability
        and may sign, which is the whole reason the gate re-asks. So the right
        to look is ``view_obj``'s ``may_sign_now`` arm as well as the record's:
        the two rights are the same predicate object, and cannot disagree
        again for any ruleset.

        The list is the bound this design accepts: it is scoped by the record,
        because asking the gate per row means resolving a section's rules once
        per row. She can open and sign it; she finds it in her list once
        anything re-freezes the statement.
        """
        statement = self.a_statement()
        RoleAssignment.objects.all().delete()
        spaet_user, spaet = a_user("spaete", permitted=True)
        RoleAssignment.objects.create(role="ressortleitung", member=spaet)
        statement = Statement.objects.get(pk=statement.pk)
        self.assertEqual(
            statement.approval_constraint_set.get(name="Freigabe der Leitung").eligible_member_ids,
            [self.leitung.pk],
            "the record names who it named",
        )
        self.assertFalse(statement.names_as_signer(spaet), "and that is not her")
        self.assertTrue(statement.may_be_approved_by(spaet), "but the gate asks again")
        self.assertTrue(self.may_view(spaet_user, statement))
        self.assertEqual(self.fetch(spaet_user, statement), 200)
        self.assertNotIn(statement.pk, self.listed(spaet_user), "the documented bound")
        r = self.client.post(
            "/api/finance/statements/{}/approve".format(statement.pk),
            content_type="application/json",
            data={"note": ""},
            **bearer(spaet_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(Statement.objects.get(pk=statement.pk).confirmed)

    def test_every_statement_the_list_returns_is_one_its_reader_may_open(self):
        """The invariant that keeps the list from being a leak of its own.

        The list is a queryset filter and the detail route is a predicate, so
        they are two implementations of one question. This asserts set
        equality over a mixed set — hers to sign, hers to write, somebody
        else's entirely — rather than a count, because a count agrees with
        the wrong rows.
        """
        named = self.a_statement()
        own = Statement.objects.create(short_description="Eigene", created_by=self.leitung)
        alien = self.a_statement()
        # `alien` was resolved while she held the role, so leave its record
        # naming nobody and take the role away, which is what makes the gate
        # refuse her too: this row is in the list for no reason at all.
        alien.approval_constraint_set.update(eligible_member_ids=[])
        RoleAssignment.objects.all().delete()
        expected = {
            statement.pk
            for statement in (named, own, alien)
            if self.may_view(self.leitung_user, statement)
        }
        self.assertEqual(expected, {named.pk, own.pk})
        self.assertEqual(self.listed(self.leitung_user), expected)

    def test_the_list_costs_one_query_whatever_the_number_of_statements(self):
        """The cost: one bulk read of the applicable rows, no rules resolved.

        Asking the gate per row would resolve the section's rules once per
        statement — a context, the permission holders, the dated roles and a
        call into the section's own Python. The rows carry the answer, so the
        scope costs one query that does not grow with the page.
        """
        for _ in range(3):
            self.a_statement()
        header = bearer(self.leitung_user)
        self.client.get("/api/finance/statements", **header)
        with CaptureQueriesContext(connection) as few:
            self.client.get("/api/finance/statements", **header)
        for _ in range(6):
            self.a_statement()
        with CaptureQueriesContext(connection) as many:
            r = self.client.get("/api/finance/statements", **header)
        self.assertEqual(len(r.json()), 9)
        self.assertEqual(
            len(few.captured_queries),
            len(many.captured_queries),
            "the scope must not resolve the rules per row",
        )

    # --- the predicates themselves ---------------------------------------

    def test_the_predicates_answer_for_an_excursion_and_for_nothing(self):
        """What the admin's excursion page and a global check hand them.

        ``is_named_signer`` and ``may_approve`` are asked about a
        :class:`~members.models.Freizeit` by the admin, standing for the
        statement hanging off it — and about ``None`` by a global check. A
        trip without a statement is nobody's to sign.
        """
        trip = Freizeit.objects.create(
            name="Hochtour",
            kilometers_traveled=10,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=2,
        )
        for predicate in (is_named_signer, may_approve):
            with self.subTest(predicate=predicate.name):
                self.assertFalse(predicate(self.leitung_user, trip), "no statement on the trip")
                self.assertFalse(predicate(self.leitung_user, None))
                self.assertFalse(predicate(self.fremde_user, None))
        statement = self.a_draft()
        statement.excursion = Freizeit.objects.get(pk=trip.pk)
        statement.save()
        statement.submit(submitter=self.payer)
        trip = Freizeit.objects.get(pk=trip.pk)
        self.assertTrue(is_named_signer(self.leitung_user, trip))
        self.assertTrue(may_approve(self.leitung_user, trip))

    def test_nobody_is_not_a_signer(self):
        """``None`` is not a member, and is told so rather than crashing.

        Both halves of the question — the statement's own and the scope's —
        are public and both are asked elsewhere with whatever the caller has,
        which for an account with no member record is nothing.
        """
        statement = self.a_statement()
        self.assertFalse(statement.names_as_signer(None))
        self.assertEqual(list(ApprovalConstraint.objects.naming(None)), [])
        self.assertEqual(list(ApprovalConstraint.objects.naming(self.leitung)), [statement.pk])

    def test_the_payload_answers_the_person_who_is_asking(self):
        """``may_approve`` in the payload is *this* asker's answer.

        It is ``Statement.may_be_approved_by(member)``, served under the name
        the client reads, and the one thing a page needs in order to decide
        whether to offer the button. Two askers, one statement, two answers —
        asserted against each other, because a field that is simply constant
        passes every test written about one asker.
        """
        statement = self.a_statement()
        self.assertEqual(
            {
                member.prename: statement.may_be_approved_by(member)
                for member in (self.leitung, self.kollegin, self.payer)
            },
            {"Leitung": True, "Kollegin": False, "Zahlerin": False},
            "the signer is told yes and the two who cannot sign are told no",
        )
        # And that is the field the client reads, under the name it reads it
        # by: `may_approve` in the `/approval` payload.
        for user, expected in ((self.leitung_user, True), (self.payer_user, False)):
            with self.subTest(user=user.username):
                r = self.client.get(
                    "/api/finance/statements/{}/approval".format(statement.pk),
                    **bearer(user),
                )
                self.assertEqual(r.status_code, 200, r.content)
                self.assertEqual(r.json()["may_approve"], expected)
