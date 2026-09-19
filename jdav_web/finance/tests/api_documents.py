"""End-to-end tests for the finance *documents* REST API.

These exercise the real OAuth2 bearer authentication path and the permission
gate the admin enforces on the downloadable statement summary
(``StatementAdmin.statement_summary_view`` →
``finance.may_manage_confirmed_statements`` + a ``confirmed`` precondition),
but through the HTTP API. The documents router is mounted centrally at
``/api/finance/documents``.

The authorized happy path compiles a PDF via ``pdflatex``; where that binary is
unavailable the body/content-type assertion is skipped, but the permission gate
(403) and the ``confirmed`` precondition (422) are always verified since neither
reaches the PDF compiler.
"""

import datetime
import shutil
import uuid

from django.conf import settings
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from finance.models import Statement
from members.models import DIVERSE
from members.models import Member
from oauth2_provider.models import get_access_token_model
from oauth2_provider.models import get_application_model

Application = get_application_model()
AccessToken = get_access_token_model()

PDFLATEX_AVAILABLE = shutil.which("pdflatex") is not None


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


class FinanceDocumentsApiTestCase(TestCase):
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
        self.manager_user, self.manager = make_member_user("manager")
        self.manager_user = grant(self.manager_user, "may_manage_confirmed_statements")

    def auth(self, user):
        token = AccessToken.objects.create(
            user=user,
            application=self.application,
            token="tok-{}-{}".format(user.username, uuid.uuid4().hex[:8]),
            expires=timezone.now() + datetime.timedelta(days=1),
            scope="read write",
        )
        return {"HTTP_AUTHORIZATION": "Bearer {}".format(token.token)}

    def make_confirmed_statement(self):
        stmt = Statement.objects.create(
            short_description="Confirmed statement",
            explanation="",
            night_cost=0,
            created_by=self.manager,
        )
        stmt.submit(self.manager)
        # A bare statement is VALID, so it confirms directly (mirrors the admin
        # confirm flow used in the finance router tests).
        self.assertTrue(stmt.confirm(self.manager))
        return stmt

    def summary_url(self, statement_id):
        return "/api/finance/documents/statements/{}/summary".format(statement_id)

    # --- authentication ---------------------------------------------------

    def test_requires_authentication(self):
        stmt = self.make_confirmed_statement()
        self.assertEqual(self.client.get(self.summary_url(stmt.pk)).status_code, 401)

    def test_invalid_token_rejected(self):
        stmt = self.make_confirmed_statement()
        r = self.client.get(self.summary_url(stmt.pk), HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(r.status_code, 401)

    # --- permission gate --------------------------------------------------

    def test_summary_forbidden_without_permission(self):
        # The owner lacks ``may_manage_confirmed_statements`` → 403, without ever
        # reaching the PDF compiler.
        stmt = self.make_confirmed_statement()
        r = self.client.get(self.summary_url(stmt.pk), **self.auth(self.owner_user))
        self.assertEqual(r.status_code, 403)

    def test_summary_unconfirmed_rejected(self):
        # The manager holds the permission, but an unconfirmed statement has no
        # summary → 422 (the confirmed precondition, checked before generation).
        stmt = Statement.objects.create(
            short_description="Draft",
            explanation="",
            night_cost=0,
            created_by=self.manager,
        )
        stmt.submit(self.manager)
        self.assertFalse(stmt.confirmed)
        r = self.client.get(self.summary_url(stmt.pk), **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 422)

    def test_summary_missing_statement_404(self):
        r = self.client.get(self.summary_url(999999), **self.auth(self.manager_user))
        self.assertEqual(r.status_code, 404)

    # --- authorized download (requires pdflatex) --------------------------

    def test_summary_authorized_returns_pdf(self):
        stmt = self.make_confirmed_statement()
        r = self.client.get(self.summary_url(stmt.pk), **self.auth(self.manager_user))
        if not PDFLATEX_AVAILABLE:  # pragma: no cover
            # Without pdflatex the generator cannot compile the document; the
            # permission gate and confirmed precondition are covered by the
            # dedicated 403/422 tests above. CI always has pdflatex, so this
            # arm never runs there — hence the pragma.
            self.skipTest("pdflatex is not available in this environment")
        self.assertEqual(r.status_code, 200, getattr(r, "content", b"")[:500])
        self.assertEqual(r["Content-Type"], "application/pdf")
