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
from finance.models import Bill
from finance.models import Statement
from finance.models import Transaction
from members.models import DIVERSE
from members.models import Member
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

    def test_transactions_require_view_permission(self):
        r = self.client.get("/api/finance/transactions", **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)
