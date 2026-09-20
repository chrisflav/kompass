"""Admin-parity tests for the expanded finance REST API contract.

These cover the fields added for full Django-admin field parity: the extra
``StatementBrief``/``TransactionBrief``/``TransactionOut``/``BillBrief`` columns,
the ``BillUpdate.refunded`` write path, and the ``/enums`` choices endpoint.

The finance router is mounted centrally at ``/api/finance``. Auth/permission
plumbing is reused from :mod:`finance.api.tests`.
"""

import datetime
import uuid
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from finance.api.tests import AccessToken
from finance.api.tests import Application
from finance.api.tests import grant
from finance.api.tests import make_member_user
from finance.models import Bill
from finance.models import Ledger
from finance.models import Statement
from finance.models import Transaction


class FinanceParityApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client-parity",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("powner")
        self.other_user, self.other = make_member_user("pother")
        self.manager_user, self.manager = make_member_user("pmanager")
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

    # --- statement brief parity -------------------------------------------

    def test_statement_brief_exposes_created_by_and_total(self):
        self.make_statement(self.owner, "mine")
        r = self.client.get("/api/finance/statements", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        row = r.json()[0]
        self.assertEqual(row["created_by"]["id"], self.owner.pk)
        self.assertEqual(row["total"], 0.0)
        self.assertEqual(row["total_pretty"], "0.00€")

    # --- transaction brief / out parity -----------------------------------

    def test_transaction_brief_and_out_expose_new_columns(self):
        stmt = self.make_statement(self.owner)
        ledger = Ledger.objects.create(name="Konto A")
        trans = Transaction.objects.create(
            statement=stmt,
            member=self.owner,
            amount=Decimal("5.00"),
            reference="ref",
            ledger=ledger,
            confirmed=True,
            confirmed_date=timezone.now(),
            confirmed_by=self.manager,
        )

        r = self.client.get("/api/finance/transactions", **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 200)
        row = next(t for t in r.json() if t["id"] == trans.pk)
        self.assertEqual(row["statement_id"], stmt.pk)
        self.assertEqual(row["ledger"]["name"], "Konto A")
        self.assertEqual(row["confirmed_by"]["id"], self.manager.pk)
        self.assertIsNotNone(row["confirmed_date"])

        r = self.client.get(
            "/api/finance/transactions/{}".format(trans.pk), **self.auth(self.manager_user)
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["confirmed_by"]["id"], self.manager.pk)

    # --- bill brief parity -------------------------------------------------

    def test_bill_brief_exposes_statement_explanation_refunded(self):
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(
            statement=stmt,
            short_description="Rope",
            explanation="a rope",
            amount=Decimal("3.00"),
            refunded=True,
        )
        r = self.client.get("/api/finance/bills", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        row = next(b for b in r.json() if b["id"] == bill.pk)
        self.assertEqual(row["statement_id"], stmt.pk)
        self.assertEqual(row["explanation"], "a rope")
        self.assertTrue(row["refunded"])

    # --- bill update: refunded write path ---------------------------------

    def test_update_bill_refunded_on_own_statement(self):
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(statement=stmt, short_description="a", amount=1)
        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"refunded": True},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        bill.refresh_from_db()
        self.assertTrue(bill.refunded)

    def test_update_bill_refunded_other_forbidden(self):
        stmt = self.make_statement(self.other)
        bill = Bill.objects.create(statement=stmt, short_description="a", amount=1)
        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"refunded": True},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        bill.refresh_from_db()
        self.assertFalse(bill.refunded)

    def test_update_bill_invalid_amount_rejected(self):
        stmt = self.make_statement(self.owner)
        bill = Bill.objects.create(statement=stmt, short_description="a", amount=1)
        r = self.client.patch(
            "/api/finance/bills/{}".format(bill.pk),
            data={"amount": "not-a-number"},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 422)

    # --- enums endpoint ----------------------------------------------------

    def test_enums_lists_status_choices(self):
        r = self.client.get("/api/finance/enums", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 200)
        values = {c["value"] for c in r.json()["status"]}
        self.assertEqual(
            values,
            {Statement.UNSUBMITTED, Statement.SUBMITTED, Statement.CONFIRMED},
        )
        for choice in r.json()["status"]:
            self.assertTrue(choice["label"])

    def test_enums_requires_authentication(self):
        self.assertEqual(self.client.get("/api/finance/enums").status_code, 401)
