"""End-to-end tests for the finance transaction-inline REST API.

The standalone ``TransactionAdmin`` is fully read-only; transactions are only
edited through ``TransactionOnSubmittedStatementInline`` on a *submitted*
statement, reachable from the ``StatementSubmitted`` change view (gated on the
global ``finance.process_statementsubmitted`` permission, offered only while the
statement is submitted-and-not-confirmed). These tests exercise the real OAuth2
bearer authentication path and assert that ``PATCH /api/finance/transactions/{id}``
and ``GET /api/finance/statements/{id}/transactions`` reproduce exactly that
surface (authorized 200 / unauthorized 403 / validation 422).

The inline router is mounted centrally at ``/api/finance``.
"""

import datetime
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from finance.models import Ledger
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


class FinanceTransactionInlineApiTestCase(TestCase):
    def setUp(self):
        self.application = Application.objects.create(
            name="test-client",
            client_type=Application.CLIENT_CONFIDENTIAL,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="test-secret",
        )
        self.owner_user, self.owner = make_member_user("owner")
        self.other_user, self.other = make_member_user("other")
        self.manager_user, self.manager = make_member_user("manager")
        self.manager_user = grant(
            self.manager_user,
            "process_statementsubmitted",
            "view_global_statement",
        )
        self.ledger = Ledger.objects.create(name="Bank")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def make_statement(self, status=Statement.SUBMITTED):
        statement = Statement.objects.create(
            short_description="A statement",
            explanation="",
            night_cost=0,
            created_by=self.owner,
            status=status,
        )
        if status in (Statement.SUBMITTED, Statement.CONFIRMED):
            statement.submitted_date = timezone.now()
            statement.save()
        return statement

    def make_transaction(self, statement, member=None):
        return Transaction.objects.create(
            reference="Payout",
            amount=Decimal("10.00"),
            member=member or self.owner,
            ledger=self.ledger,
            statement=statement,
        )

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"amount": 5},
            content_type="application/json",
        )
        self.assertEqual(r.status_code, 401)

    # --- list-by-statement ------------------------------------------------

    def test_list_transactions_requires_statement_view(self):
        statement = self.make_statement()
        self.make_transaction(statement)
        r = self.client.get(
            "/api/finance/statements/{}/transactions".format(statement.pk),
            **self.auth(self.other_user),
        )
        self.assertEqual(r.status_code, 403)

    def test_list_transactions_with_permission(self):
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        r = self.client.get(
            "/api/finance/statements/{}/transactions".format(statement.pk),
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual({t["id"] for t in r.json()}, {transaction.pk})

    # --- edit -------------------------------------------------------------

    def test_update_requires_process_permission(self):
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"amount": 5},
            content_type="application/json",
            **self.auth(self.owner_user),
        )
        self.assertEqual(r.status_code, 403)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal("10.00"))

    def test_update_with_permission(self):
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={
                "amount": 42.5,
                "reference": "Corrected",
                "member_id": self.other.pk,
                "ledger_id": self.ledger.pk,
            },
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 200, r.content)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal("42.50"))
        self.assertEqual(transaction.reference, "Corrected")
        self.assertEqual(transaction.member_id, self.other.pk)

    def test_update_ledger_null_rejected(self):
        # Transaction.ledger is null=True in the DB but blank=False, so the admin
        # form (and thus the API) requires it — clearing it to null is a 422.
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"ledger_id": None},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422, r.content)

    def test_update_rejected_when_not_submitted(self):
        statement = self.make_statement(status=Statement.UNSUBMITTED)
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"amount": 5},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal("10.00"))

    def test_update_rejected_when_confirmed(self):
        statement = self.make_statement(status=Statement.CONFIRMED)
        transaction = self.make_transaction(statement)
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"amount": 5},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422)

    def test_update_invalid_amount_returns_422(self):
        statement = self.make_statement()
        transaction = self.make_transaction(statement)
        # Six-plus integer digits exceed max_digits=6/decimal_places=2.
        r = self.client.patch(
            "/api/finance/transactions/{}".format(transaction.pk),
            data={"amount": 1234567.89},
            content_type="application/json",
            **self.auth(self.manager_user),
        )
        self.assertEqual(r.status_code, 422)
        transaction.refresh_from_db()
        self.assertEqual(transaction.amount, Decimal("10.00"))
