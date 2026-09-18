"""End-to-end tests for the finance REST API.

These exercise the real authentication path (OAuth2 bearer tokens) and the
object/global permission model, mirroring the guarantees enforced by the admin
(``finance/admin.py``) and the rules predicates (``finance/rules.py``) but
through the HTTP API.

The finance router is mounted centrally at ``/api/finance``.
"""

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from finance.models import Bill
from finance.models import Statement
from finance.models import Transaction
from members.models import DIVERSE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()


def make_member_user(username):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=username.title(),
        lastname="Test",
        birth_date=timezone.now().date(),
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    return user, member


def grant(user, *codenames):
    for codename in codenames:
        user.user_permissions.add(
            Permission.objects.get(content_type__app_label="finance", codename=codename)
        )
    # Return a fresh instance so the permission cache is clear.
    return User.objects.get(pk=user.pk)


class FinanceApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            # A short secret; the default 128-char one exceeds bcrypt's 72-byte
            # limit configured via PASSWORD_HASHERS.
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("owner")
        self.other_user, self.other = make_member_user("other")
        self.manager_user, self.manager = make_member_user("manager")
        self.manager_user = grant(
            self.manager_user,
            "add_global_statement",
            "list_global_statement",
            "view_global_statement",
            "change_global_statement",
            "delete_global_statement",
            "process_statementsubmitted",
            "may_manage_confirmed_statements",
            "view_transaction",
        )

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def make_statement(self, created_by, short_description="A statement"):
        return Statement.objects.create(
            short_description=short_description,
            explanation="",
            night_cost=0,
            created_by=created_by,
        )

    def make_excursion(self, name, *leaders):
        excursion = Freizeit.objects.create(
            name=name,
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        for leader in leaders:
            excursion.jugendleiter.add(leader)
        return excursion

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        self.assertEqual(self.client.get("/api/finance/statements").status_code, 401)

    def test_invalid_token_rejected(self):
        r = self.client.get("/api/finance/statements", HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- statement list scoping -------------------------------------------

    def test_list_scoped_to_creator(self):
        mine = self.make_statement(self.owner, "mine")
        self.make_statement(self.other, "theirs")

        r = self.client.get("/api/finance/statements", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({s["id"] for s in r.json()}, {mine.pk})

    def test_list_all_with_global_permission(self):
        mine = self.make_statement(self.owner, "mine")
        theirs = self.make_statement(self.other, "theirs")

        r = self.client.get("/api/finance/statements", **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({s["id"] for s in r.json()}, {mine.pk, theirs.pk})

    # --- statement retrieval ----------------------------------------------

    def test_retrieve_own_allowed(self):
        stmt = self.make_statement(self.owner)
        r = self.client.get(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["id"], stmt.pk)
        self.assertEqual(body["total"], 0.0)
        self.assertFalse(body["submitted"])
        # The submitted-statement review modal reads these off the detail payload.
        self.assertEqual(body["transaction_issues"], [])
        self.assertEqual(body["validity_display"], str(stmt.validity_display))

    def test_retrieve_other_forbidden(self):
        stmt = self.make_statement(self.other)
        r = self.client.get(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_retrieve_any_with_global_permission(self):
        stmt = self.make_statement(self.owner)
        r = self.client.get(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200)

    # --- statement create -------------------------------------------------

    def test_create_requires_global_add_permission(self):
        r = self.client.post(
            "/api/finance/statements",
            data={"short_description": "New"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_create_with_permission_sets_creator(self):
        r = self.client.post(
            "/api/finance/statements",
            data={"short_description": "New", "explanation": "note"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt = Statement.objects.get(pk=r.json()["id"])
        self.assertEqual(stmt.created_by, self.manager)
        self.assertEqual(stmt.status, Statement.UNSUBMITTED)

    # --- statement update / delete ----------------------------------------

    def test_update_own_draft_allowed(self):
        stmt = self.make_statement(self.owner)
        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"explanation": "changed"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200)
        stmt.refresh_from_db()
        self.assertEqual(stmt.explanation, "changed")

    def test_update_other_forbidden(self):
        stmt = self.make_statement(self.other)
        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"explanation": "changed"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_delete_own_draft_allowed(self):
        stmt = self.make_statement(self.owner)
        r = self.client.delete(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Statement.objects.filter(pk=stmt.pk).exists())

    def test_delete_submitted_forbidden(self):
        stmt = self.make_statement(self.owner)
        stmt.submit(self.owner)
        r = self.client.delete(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Statement.objects.filter(pk=stmt.pk).exists())

    # --- submit action ----------------------------------------------------

    def test_submit_own_draft(self):
        stmt = self.make_statement(self.owner)
        r = self.client.post(
            "/api/finance/statements/{}/submit".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.status, Statement.SUBMITTED)
        self.assertEqual(stmt.submitted_by, self.owner)

    def test_submit_other_forbidden(self):
        stmt = self.make_statement(self.other)
        r = self.client.post(
            "/api/finance/statements/{}/submit".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- submitted-stage actions ------------------------------------------

    def test_generate_reduce_confirm_flow(self):
        auth = self.auth(self.manager_user)
        # Manager creates and submits (creator => change_obj holds).
        stmt = self.make_statement(self.manager)
        stmt.submit(self.manager)

        r = self.client.post(
            "/api/finance/statements/{}/generate-transactions".format(stmt.pk), **auth
        )
        self.assertEqual(r.status_code, 200, r.content)

        r = self.client.post(
            "/api/finance/statements/{}/reduce-transactions".format(stmt.pk), **auth
        )
        self.assertEqual(r.status_code, 200, r.content)

        r = self.client.post("/api/finance/statements/{}/confirm".format(stmt.pk), **auth)
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.status, Statement.CONFIRMED)
        self.assertEqual(stmt.confirmed_by, self.manager)

    def test_generate_requires_process_permission(self):
        stmt = self.make_statement(self.owner)
        stmt.submit(self.owner)
        r = self.client.post(
            "/api/finance/statements/{}/generate-transactions".format(stmt.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_confirm_requires_process_permission(self):
        stmt = self.make_statement(self.owner)
        stmt.submit(self.owner)
        r = self.client.post(
            "/api/finance/statements/{}/confirm".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    def test_reject_returns_to_draft(self):
        stmt = self.make_statement(self.manager)
        stmt.submit(self.manager)
        r = self.client.post(
            "/api/finance/statements/{}/reject".format(stmt.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.status, Statement.UNSUBMITTED)

    def test_unconfirm_reverts_to_submitted(self):
        stmt = self.make_statement(self.manager)
        stmt.submit(self.manager)
        self.assertTrue(stmt.confirm(self.manager))
        r = self.client.post(
            "/api/finance/statements/{}/unconfirm".format(stmt.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.status, Statement.SUBMITTED)
        self.assertIsNone(stmt.confirmed_date)

    def test_unconfirm_requires_permission(self):
        stmt = self.make_statement(self.owner)
        stmt.submit(self.owner)
        self.assertTrue(stmt.confirm(self.owner))
        r = self.client.post(
            "/api/finance/statements/{}/unconfirm".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)

    # --- bills ------------------------------------------------------------

    def test_create_bill_on_own_statement(self):
        stmt = self.make_statement(self.owner)
        proof = SimpleUploadedFile("proof.pdf", b"%PDF-1.4 test", content_type="application/pdf")
        r = self.client.post(
            "/api/finance/bills",
            data={
                "statement_id": stmt.pk,
                "short_description": "Rope",
                "amount": "12.50",
                "proof": proof,
            },
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        bill = Bill.objects.get(pk=r.json()["id"])
        self.assertEqual(bill.statement, stmt)
        self.assertEqual(bill.amount, Decimal("12.50"))
        self.assertTrue(bill.proof)

    def test_create_bill_on_other_statement_forbidden(self):
        stmt = self.make_statement(self.other)
        r = self.client.post(
            "/api/finance/bills",
            data={"statement_id": stmt.pk, "short_description": "Rope", "amount": "5"},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_create_bill_rejects_bad_filetype(self):
        stmt = self.make_statement(self.owner)
        bad = SimpleUploadedFile("x.exe", b"MZ", content_type="application/x-msdownload")
        r = self.client.post(
            "/api/finance/bills",
            data={"statement_id": stmt.pk, "short_description": "x", "amount": "1", "proof": bad},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_list_bills_scoped_to_creator(self):
        mine = self.make_statement(self.owner)
        my_bill = Bill.objects.create(statement=mine, short_description="a", amount=1)
        theirs = self.make_statement(self.other)
        Bill.objects.create(statement=theirs, short_description="b", amount=1)

        r = self.client.get("/api/finance/bills", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({b["id"] for b in r.json()}, {my_bill.pk})

    # --- transactions (read-only) -----------------------------------------

    def test_transactions_read_only(self):
        stmt = self.make_statement(self.owner)
        trans = Transaction.objects.create(
            statement=stmt, member=self.owner, amount=Decimal("5.00"), reference="ref"
        )

        r = self.client.get("/api/finance/transactions", **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 200)
        self.assertEqual({t["id"] for t in r.json()}, {trans.pk})

        r = self.client.get(
            "/api/finance/transactions/{}".format(trans.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["reference"], "ref")
        # No creation endpoint is exposed for transactions.
        r = self.client.post("/api/finance/transactions", **self.auth(self.manager_user))
        self.assertIn(r.status_code, (404, 405))

    # --- the excursion stays editable while a draft ------------------------

    def test_update_sets_the_excursion_on_a_draft(self):
        """The submission flow asks what a statement is for on its first step, so
        picking the wrong trip has to be a correction, not a delete-and-restart."""
        stmt = self.make_statement(self.owner)
        excursion = self.make_excursion("Skifreizeit", self.owner)
        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"excursion_id": excursion.pk},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.excursion, excursion)

    def test_update_clears_recipients_when_the_excursion_changes(self):
        old_trip = self.make_excursion("Old", self.owner)
        stmt = self.make_statement(self.owner)
        stmt.excursion = old_trip
        stmt.subsidy_to = self.owner
        stmt.save()
        stmt.allowance_to.add(self.owner)

        new_trip = self.make_excursion("New", self.other)
        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"excursion_id": new_trip.pk},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        # The old recipients don't lead the new trip, so they cannot stay.
        self.assertIsNone(stmt.subsidy_to)
        self.assertEqual(list(stmt.allowance_to.all()), [])

    def test_update_validates_recipients_against_the_incoming_excursion(self):
        """A combined change must not check the recipients against the outgoing
        trip, which would admit someone who doesn't lead the new one."""
        stmt = self.make_statement(self.owner)
        stmt.excursion = self.make_excursion("Old", self.owner)
        stmt.save()
        new_trip = self.make_excursion("New", self.other)

        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"excursion_id": new_trip.pk, "subsidy_to_id": self.owner.pk},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        stmt.refresh_from_db()
        self.assertIsNone(stmt.subsidy_to)

    def test_update_accepts_a_recipient_of_the_incoming_excursion(self):
        stmt = self.make_statement(self.owner)
        stmt.excursion = self.make_excursion("Old", self.owner)
        stmt.save()
        new_trip = self.make_excursion("New", self.other)

        r = self.client.patch(
            "/api/finance/statements/{}".format(stmt.pk),
            data={"excursion_id": new_trip.pk, "subsidy_to_id": self.other.pk},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        stmt.refresh_from_db()
        self.assertEqual(stmt.excursion, new_trip)
        self.assertEqual(stmt.subsidy_to, self.other)

    # --- who may decide that a bill is covered -----------------------------

    def test_finance_officer_covers_a_bill_on_a_submitted_statement(self):
        """``costs_covered`` exists for the finance officer, who sets it during
        review — after the statement has been submitted and frozen for its
        author. The statement's own change rule would deny that."""
        officer_user, _officer = make_member_user("officer")
        officer_user = grant(
            officer_user,
            "change_global_billonstatementproxy",
            "process_statementsubmitted",
        )
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(statement=stmt, short_description="Rope", amount=Decimal("10"))
        stmt.submit(self.owner)

        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"costs_covered": True},
            content_type="application/json",
            **self.auth(officer_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        bill.refresh_from_db()
        self.assertTrue(bill.costs_covered)

    def test_author_may_not_edit_a_bill_once_submitted(self):
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(statement=stmt, short_description="Rope", amount=Decimal("10"))
        stmt.submit(self.owner)

        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"amount": "99"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_stranger_may_not_edit_a_bill(self):
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(statement=stmt, short_description="Rope", amount=Decimal("10"))

        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"costs_covered": True},
            content_type="application/json",
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_statement_bills_carry_their_proof(self):
        """The flow flags receipts without a scan and the review screen shows the
        evidence, both from the statement's own payload."""
        stmt = self.make_statement(self.owner)
        Bill.objects.create(
            statement=stmt,
            short_description="Scanned",
            amount=Decimal("10"),
            proof=SimpleUploadedFile("p.pdf", b"%PDF-1.4", content_type="application/pdf"),
        )
        Bill.objects.create(statement=stmt, short_description="Bare", amount=Decimal("5"))

        r = self.client.get(
            "/api/finance/statements/{}".format(stmt.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        bills = {b["short_description"]: b for b in r.json()["bills"]}
        self.assertTrue(bills["Scanned"]["has_proof"])
        self.assertIn(".pdf", bills["Scanned"]["proof_url"])
        self.assertFalse(bills["Bare"]["has_proof"])
        self.assertIsNone(bills["Bare"]["proof_url"])

    def test_transaction_carries_the_iban_and_epc_payload(self):
        """The payout screen lists each transfer's account and renders ``code``
        as an EPC-QR, so both must survive the serializer."""
        self.owner.iban = "DE02120300000000202051"
        self.owner.save()
        stmt = self.make_statement(self.owner)
        trans = Transaction.objects.create(
            statement=stmt, member=self.owner, amount=Decimal("42.50"), reference="Fahrtkosten"
        )

        r = self.client.get(
            "/api/finance/transactions/{}".format(trans.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["iban"], "DE02120300000000202051")
        self.assertTrue(body["iban_valid"])
        self.assertTrue(body["code"].startswith("BCD"))
        self.assertIn("DE02120300000000202051", body["code"])

    def test_transaction_without_a_valid_iban_has_no_epc_payload(self):
        """An unpayable transfer must say so rather than render a QR that would
        send money nowhere."""
        self.owner.iban = "not-an-iban"
        self.owner.save()
        stmt = self.make_statement(self.owner)
        trans = Transaction.objects.create(
            statement=stmt, member=self.owner, amount=Decimal("42.50"), reference="Fahrtkosten"
        )

        r = self.client.get(
            "/api/finance/transactions/{}".format(trans.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["iban_valid"])
        self.assertEqual(r.json()["code"], "")

    def test_transactions_require_view_permission(self):
        r = self.client.get("/api/finance/transactions", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    # --- the remaining statement and bill paths ---------------------------

    def test_create_statement_refuses_a_second_one_for_the_same_excursion(self):
        # `Statement.excursion` is unique, so without the guard this surfaces as
        # a raw IntegrityError rather than something the client can act on.
        excursion = self.make_excursion("Hochtour", self.manager)
        first = self.client.post(
            "/api/finance/statements",
            data={
                "short_description": "Erste",
                "explanation": "",
                "night_cost": 0,
                "excursion_id": excursion.pk,
            },
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(first.status_code, 200, first.content)

        second = self.client.post(
            "/api/finance/statements",
            data={
                "short_description": "Zweite",
                "explanation": "",
                "night_cost": 0,
                "excursion_id": excursion.pk,
            },
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(second.status_code, 422, second.content)
        self.assertEqual(Statement.objects.filter(excursion=excursion).count(), 1)

    def test_update_a_submitted_statement_is_refused(self):
        # The author is already stopped by the object rule; this is about the
        # endpoint's own guard, which only someone still holding change
        # permission on a submitted statement can reach.
        statement = self.make_statement(self.manager)
        statement.submit(self.manager)
        r = self.client.patch(
            "/api/finance/statements/{}".format(statement.pk),
            data={"short_description": "Doch anders"},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        statement.refresh_from_db()
        self.assertEqual(statement.short_description, "A statement")

    def test_update_refuses_more_allowance_recipients_than_approved(self):
        # An excursion with no participants approves no youth leaders, so even a
        # single recipient is one too many.
        excursion = self.make_excursion("Tagestour", self.owner, self.other)
        statement = self.make_statement(self.owner)
        statement.excursion = excursion
        statement.save()
        r = self.client.patch(
            "/api/finance/statements/{}".format(statement.pk),
            data={"allowance_to_ids": [self.owner.pk, self.other.pk]},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        self.assertEqual(list(statement.allowance_to.all()), [])

    def test_submit_an_already_submitted_statement_is_refused(self):
        statement = self.make_statement(self.manager)
        statement.submit(self.manager)
        r = self.client.post(
            "/api/finance/statements/{}/submit".format(statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_submit_refuses_an_excursion_with_invalid_allowance_recipients(self):
        excursion = self.make_excursion("Tagestour", self.owner)
        statement = self.make_statement(self.owner)
        statement.excursion = excursion
        statement.save()
        statement.allowance_to.set([self.owner])
        r = self.client.post(
            "/api/finance/statements/{}/submit".format(statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        # The refusal is shown to the submitter, so it arrives translated.
        self.assertIn(
            str(
                _(
                    "The configured recipients of the allowance don't match the "
                    "regulations. Please correct this and try again."
                )
            ).strip(),
            " ".join(r.json()["detail"]),
        )
        statement.refresh_from_db()
        self.assertFalse(statement.submitted)

    def test_finance_overview_needs_an_excursion(self):
        statement = self.make_statement(self.owner)
        r = self.client.get(
            "/api/finance/statements/{}/overview".format(statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 404, r.content)

    def test_finance_overview_of_an_excursion_statement(self):
        excursion = self.make_excursion("Hochtour", self.owner)
        statement = self.make_statement(self.owner)
        statement.excursion = excursion
        statement.subsidy_to = self.owner
        statement.save()
        r = self.client.get(
            "/api/finance/statements/{}/overview".format(statement.pk),
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["subsidy_to"]["name"], self.owner.name)
        self.assertIsNone(body["ljp_to"])

    def test_generate_transactions_refuses_a_draft(self):
        statement = self.make_statement(self.manager)
        r = self.client.post(
            "/api/finance/statements/{}/generate-transactions".format(statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_generate_transactions_refuses_to_run_twice(self):
        statement = self.make_statement(self.manager)
        # Only a covered bill produces a transaction, and without one the second
        # call would find nothing to complain about.
        Bill.objects.create(
            statement=statement,
            short_description="Hütte",
            amount=10,
            paid_by=self.manager,
            costs_covered=True,
        )
        statement.submit(self.manager)
        first = self.client.post(
            "/api/finance/statements/{}/generate-transactions".format(statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(first.status_code, 200, first.content)

        second = self.client.post(
            "/api/finance/statements/{}/generate-transactions".format(statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(second.status_code, 422, second.content)

    def test_upload_and_replace_a_bill_proof(self):
        statement = self.make_statement(self.owner)
        bill = Bill.objects.create(
            statement=statement, short_description="Hütte", amount=10, paid_by=self.owner
        )
        pdf = SimpleUploadedFile("beleg.pdf", b"fakepdf", content_type="application/pdf")
        r = self.client.post(
            "/api/finance/bills/{}/proof".format(bill.pk),
            data={"proof": pdf},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        bill.refresh_from_db()
        self.assertTrue(bill.proof)

    def test_upload_a_bill_proof_rejects_wrong_content_type(self):
        statement = self.make_statement(self.owner)
        bill = Bill.objects.create(
            statement=statement, short_description="Hütte", amount=10, paid_by=self.owner
        )
        bad = SimpleUploadedFile("beleg.txt", b"text", content_type="text/plain")
        r = self.client.post(
            "/api/finance/bills/{}/proof".format(bill.pk),
            data={"proof": bad},
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422, r.content)
        bill.refresh_from_db()
        self.assertFalse(bill.proof)

    def test_retrieve_and_delete_a_bill(self):
        statement = self.make_statement(self.owner)
        bill = Bill.objects.create(
            statement=statement, short_description="Hütte", amount=10, paid_by=self.owner
        )
        fetched = self.client.get(
            "/api/finance/bills/{}".format(bill.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(fetched.status_code, 200, fetched.content)
        self.assertEqual(fetched.json()["short_description"], "Hütte")

        r = self.client.delete(
            "/api/finance/bills/{}".format(bill.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 204, r.content)
        self.assertFalse(Bill.objects.filter(pk=bill.pk).exists())

    def test_delete_a_stranger_s_bill_forbidden(self):
        statement = self.make_statement(self.other)
        bill = Bill.objects.create(
            statement=statement, short_description="Hütte", amount=10, paid_by=self.other
        )
        r = self.client.delete(
            "/api/finance/bills/{}".format(bill.pk), **self.auth(self.owner_user)
        )
        self.assertEqual(r.status_code, 403)
        self.assertTrue(Bill.objects.filter(pk=bill.pk).exists())
