"""The commands, the poll task and the admin pages the store brings with it.

Between them they are how a section's rules get from a pull request into an
instance without a release: ``importruleset`` at every container start,
``checkruleset`` in the section's own CI, ``verifyrulesets`` from beat, and the
admin for the two things a treasurer does by hand — import, and try a version
against a real statement.
"""

from decimal import Decimal
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.contrib.auth.models import Permission
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.test import TestCase
from django.urls import reverse
from django.utils.translation import gettext as _
from django_celery_beat.models import PeriodicTask
from finance.engine import reference_directory
from finance.engine.versions import active_version
from finance.models import Bill
from finance.models import Statement
from finance.store import RuleSet
from finance.tasks import ensure_poll_task
from finance.tasks import import_ruleset
from finance.tasks import POLL_TASK_NAME
from members.models import MALE
from members.models import Member

#: A ruleset nobody should be able to import.
REFUSED = "import socket\nruleset = None\n"


def refused_package(directory):
    (Path(directory) / "__init__.py").write_text(REFUSED, encoding="utf-8")
    return Path(directory)


class ImportRulesetCommandTestCase(TestCase):
    def test_importing_the_configured_ruleset(self):
        RuleSet.objects.all().delete()
        out = StringIO()
        call_command("importruleset", stdout=out)
        self.assertIn("the reference ruleset is active", out.getvalue())
        self.assertIsNotNone(active_version())

    def test_importing_a_named_package_records_where_it_came_from(self):
        out = StringIO()
        # A different number makes it a different version, which is the only
        # way a second import of the same sources stores anything new.
        with override_settings(ALLOWANCE_PER_DAY=24):
            call_command(
                "importruleset",
                str(reference_directory()),
                "--revision=deadbeef",
                "--name=heidelberg-24",
                stdout=out,
            )
        row = RuleSet.objects.get(revision="deadbeef")
        self.assertEqual(row.name, "heidelberg-24")
        self.assertEqual(active_version(), row)
        self.assertIn("is active", out.getvalue())

    def test_a_package_that_is_not_there(self):
        with self.assertRaises(CommandError) as caught:
            call_command("importruleset", "/nowhere/at/all")
        self.assertIn("not a directory", str(caught.exception))

    def test_a_package_that_fails_its_checks_leaves_the_previous_one_active(self):
        before = active_version()
        err = StringIO()
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command("importruleset", str(refused_package(directory)), stderr=err)
        self.assertIn("was NOT activated", err.getvalue())
        self.assertIn("may not import socket", err.getvalue())
        self.assertIn("the active version is still", err.getvalue())
        self.assertEqual(active_version(), before)

    def test_without_any_version_the_failure_says_so(self):
        RuleSet.objects.all().delete()
        err = StringIO()
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command("importruleset", str(refused_package(directory)), stderr=err)
        self.assertIn("no version is active", err.getvalue())

    @override_settings(FINANCE_RULESET_POLL_MINUTES=15)
    def test_the_import_keeps_the_poll_in_step_with_the_setting(self):
        call_command("importruleset", stdout=StringIO())
        task = PeriodicTask.objects.get(name=POLL_TASK_NAME)
        self.assertEqual(task.interval.every, 15)
        self.assertEqual(task.task, "finance.tasks.import_ruleset")


class CheckRulesetCommandTestCase(TestCase):
    def test_the_reference_ruleset_passes_with_a_fuzz_run(self):
        out = StringIO()
        call_command("checkruleset", "--fuzz=20", "--seed=1", stdout=out)
        self.assertIn("passes its imports and its cases, and 20 random statements", out.getvalue())

    def test_the_reference_ruleset_passes_without_one(self):
        out = StringIO()
        call_command("checkruleset", str(reference_directory()), stdout=out)
        self.assertIn("passes its imports and its cases", out.getvalue())

    def test_a_package_that_is_not_there(self):
        with self.assertRaises(CommandError):
            call_command("checkruleset", "/nowhere/at/all")

    def test_a_package_that_does_not_pass(self):
        err = StringIO()
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError) as caught:
                call_command("checkruleset", str(refused_package(directory)), stderr=err)
        self.assertIn("not fit to import", str(caught.exception))
        self.assertIn("may not import socket", err.getvalue())


class VerifyRulesetsCommandTestCase(TestCase):
    def test_what_is_stored_verifies(self):
        out = StringIO()
        call_command("verifyrulesets", stdout=out)
        self.assertIn("verified", out.getvalue())

    def test_a_tampered_version_fails_the_command(self):
        row = active_version()
        RuleSet.objects.filter(pk=row.pk).update(sources={"__init__.py": "x = 1\n"})
        err = StringIO()
        with self.assertRaises(CommandError) as caught:
            call_command("verifyrulesets", "--sample=1", stderr=err)
        self.assertIn("problems with what is stored", str(caught.exception))
        self.assertIn("do not match the stored manifest", err.getvalue())


class DumpRulesetCommandTestCase(TestCase):
    def test_dumping_a_version(self):
        row = active_version()
        out = StringIO()
        call_command("dumpruleset", row.short_hash, stdout=out)
        printed = out.getvalue()
        self.assertIn(row.short_hash, printed)
        self.assertIn("ALLOWANCE_PER_DAY = 22", printed)
        self.assertIn("__init__.py", printed)

    def test_dumping_one_file_of_a_version(self):
        row = active_version()
        out = StringIO()
        call_command("dumpruleset", row.hash, "--path=__init__.py", stdout=out)
        self.assertIn("class HeidelbergRules", out.getvalue())

    def test_dumping_a_version_that_was_refused_shows_why(self):
        with TemporaryDirectory() as directory:
            with self.assertRaises(CommandError):
                call_command("importruleset", str(refused_package(directory)), stderr=StringIO())
        row = RuleSet.objects.get(state=RuleSet.DRAFT)
        out = StringIO()
        call_command("dumpruleset", row.short_hash, stdout=out)
        self.assertIn("problem:", out.getvalue())

    def test_a_hash_nobody_stored(self):
        with self.assertRaises(CommandError):
            call_command("dumpruleset", "0" * 12)

    def test_a_file_the_version_does_not_have(self):
        row = active_version()
        with self.assertRaises(CommandError) as caught:
            call_command("dumpruleset", row.hash, "--path=nope.py")
        self.assertIn("__init__.py", str(caught.exception))


class PollTaskTestCase(TestCase):
    def test_the_task_imports_the_configured_ruleset(self):
        RuleSet.objects.all().delete()
        self.assertEqual(import_ruleset(), active_version().hash)

    def test_the_task_reports_a_package_that_is_not_there(self):
        with override_settings(FINANCE_RULESET="nowhere", CONFIG_DIR_PATH="/tmp"):
            with self.assertLogs("finance.tasks", level="WARNING"):
                self.assertEqual(import_ruleset(), "")

    def test_the_task_complains_about_a_package_that_fails(self):
        with TemporaryDirectory() as directory:
            refused_package(directory)
            with override_settings(FINANCE_RULESET="", CONFIG_DIR_PATH=""):
                with override_settings(
                    FINANCE_RULESET=Path(directory).name,
                    CONFIG_DIR_PATH=str(Path(directory).parent),
                ):
                    with self.assertLogs("finance.tasks", level="ERROR"):
                        import_ruleset()

    def test_the_poll_entry_follows_the_setting(self):
        self.assertIsNone(ensure_poll_task(0))
        self.assertFalse(PeriodicTask.objects.filter(name=POLL_TASK_NAME).exists())
        task = ensure_poll_task(30)
        self.assertEqual(task.interval.every, 30)
        again = ensure_poll_task(60)
        self.assertEqual(again.pk, task.pk)
        self.assertEqual(again.interval.every, 60)
        self.assertIsNone(ensure_poll_task(0))
        self.assertFalse(PeriodicTask.objects.filter(name=POLL_TASK_NAME).exists())


class RulesetAdminTestCase(TestCase):
    """The two pages the store adds to the admin."""

    def setUp(self):
        self.user = User.objects.create_superuser("treasurer", "t@localhost", "secret")
        self.member = Member.objects.create(
            prename="Kassen", lastname="Wart", email="k@localhost", gender=MALE, user=self.user
        )
        # `login` rather than `force_login`: with OIDC enabled, forcing a login
        # picks the OIDC backend and the session-refresh middleware sends the
        # request off to the provider. This is how the other admin tests do it.
        self.assertTrue(self.client.login(username="treasurer", password="secret"))
        self.statement = Statement.objects.create(short_description="Admin", night_cost=0)
        Bill.objects.create(
            statement=self.statement,
            short_description="Seil",
            amount=Decimal("10.00"),
            costs_covered=True,
            paid_by=self.member,
        )
        self.row = active_version()

    def test_the_version_list_names_where_the_rules_come_from(self):
        response = self.client.get(reverse("admin:finance_ruleset_changelist"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "heidelberg")
        self.assertContains(response, "Import")

    def test_importing_from_the_configuration(self):
        Statement.objects.all().update(ruleset=None)
        RuleSet.objects.all().delete()
        response = self.client.post(
            reverse("admin:finance_ruleset_changelist"),
            data={"import_from_configuration": "1"},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(active_version())
        self.assertContains(response, _("%(name)s is now active.") % {"name": ""})

    def test_importing_from_a_configuration_that_is_not_there(self):
        with override_settings(FINANCE_RULESET="nowhere", CONFIG_DIR_PATH="/tmp"):
            response = self.client.post(
                reverse("admin:finance_ruleset_changelist"),
                data={"import_from_configuration": "1"},
                follow=True,
            )
        self.assertContains(
            response, _("There is no ruleset at %(path)s.") % {"path": "/tmp/nowhere"}
        )

    def test_importing_a_configuration_that_fails_its_checks(self):
        with TemporaryDirectory() as directory:
            refused_package(directory)
            with override_settings(
                FINANCE_RULESET=Path(directory).name, CONFIG_DIR_PATH=str(Path(directory).parent)
            ):
                response = self.client.post(
                    reverse("admin:finance_ruleset_changelist"),
                    data={"import_from_configuration": "1"},
                    follow=True,
                )
        # The admin capitalises a message, so the assertion looks for the
        # part of it that does not start with the version name.
        self.assertContains(
            response, _("%(name)s was stored as a draft and is not active.") % {"name": ""}
        )
        self.assertContains(response, "may not import socket")

    def test_the_version_page_is_read_only(self):
        response = self.client.get(reverse("admin:finance_ruleset_change", args=[self.row.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.row.short_hash)
        # Read-only: the page carries no editable field for what the rules say.
        self.assertNotContains(response, 'name="sources"')
        self.assertNotContains(response, 'name="params"')

    def test_a_dry_run_against_a_real_statement(self):
        url = reverse("admin:finance_ruleset_dry_run", args=[self.row.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        response = self.client.post(url, data={"statement": self.statement.pk})
        self.assertEqual(response.status_code, 200)
        # The payout, the questions the rules would ask, and the signature.
        self.assertContains(response, "participant_contribution")
        self.assertContains(response, "Seil")
        self.assertContains(response, "Aufwandsentschädigung an")
        self.assertContains(response, "Freigabe")
        # Nothing was written: the statement keeps its own record.
        self.assertEqual(self.statement.obligation_set.count(), 2)

    def test_a_dry_run_against_a_statement_that_is_not_there(self):
        url = reverse("admin:finance_ruleset_dry_run", args=[self.row.pk])
        response = self.client.post(url, data={"statement": 9999}, follow=True)
        self.assertContains(response, _("There is no statement %(id)s.") % {"id": "9999"})

    def test_a_dry_run_of_a_version_that_cannot_be_loaded(self):
        row = RuleSet.objects.create(
            name="kaputt",
            hash="e" * 64,
            sources={"__init__.py": "ruleset = 1\n"},
            params={},
            state=RuleSet.DRAFT,
        )
        url = reverse("admin:finance_ruleset_dry_run", args=[row.pk])
        response = self.client.post(url, data={"statement": self.statement.pk}, follow=True)
        self.assertContains(response, "does not export")

    def test_the_resolved_payout_is_shown_on_a_submitted_statement(self):
        self.statement.submit(submitter=self.member)
        permission = Permission.objects.get(codename="process_statementsubmitted")
        self.user.user_permissions.add(permission)
        response = self.client.get(
            reverse("admin:finance_statement_change", args=[self.statement.pk])
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, _("Resolved payout"))

    def test_a_role_can_be_assigned(self):
        response = self.client.post(
            reverse("admin:finance_roleassignment_add"),
            data={
                "role": "kassenwart",
                "member": self.member.pk,
                "valid_from": "2026-01-01",
                "comment": "",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.member.finance_roles.get().role, "kassenwart")
