from decimal import Decimal

import django.test
from django.conf import settings
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from finance.engine.versions import version_hash


class StatusMigrationTestCase(django.test.TransactionTestCase):
    """Test the migration from submitted/confirmed fields to status field."""

    app = "finance"
    migrate_from = [("finance", "0009_statement_ljp_to")]
    migrate_to = [("finance", "0010_statement_status")]

    def setUp(self):
        # Get the state before migration
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        # Get the old models (before migration)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        self.Statement = old_apps.get_model(self.app, "Statement")

        # Create statements with different combinations of submitted/confirmed
        # created_by is nullable, so we don't need to create a Member
        self.unsubmitted = self.Statement.objects.create(
            short_description="Unsubmitted Statement", submitted=False, confirmed=False
        )

        self.submitted = self.Statement.objects.create(
            short_description="Submitted Statement", submitted=True, confirmed=False
        )

        self.confirmed = self.Statement.objects.create(
            short_description="Confirmed Statement", submitted=True, confirmed=True
        )

    def test_status_field_migration(self):
        """Test that status field is correctly set from old submitted/confirmed fields."""
        # Run the migration
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

        # Get the new models (after migration)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        Statement = new_apps.get_model(self.app, "Statement")

        # Constants from the Statement model
        UNSUBMITTED = 0
        SUBMITTED = 1
        CONFIRMED = 2

        # Verify the migration worked correctly
        unsubmitted = Statement.objects.get(pk=self.unsubmitted.pk)
        self.assertEqual(
            unsubmitted.status,
            UNSUBMITTED,
            "Statement with submitted=False, confirmed=False should have status=UNSUBMITTED",
        )

        submitted = Statement.objects.get(pk=self.submitted.pk)
        self.assertEqual(
            submitted.status,
            SUBMITTED,
            "Statement with submitted=True, confirmed=False should have status=SUBMITTED",
        )

        confirmed = Statement.objects.get(pk=self.confirmed.pk)
        self.assertEqual(
            confirmed.status,
            CONFIRMED,
            "Statement with submitted=True, confirmed=True should have status=CONFIRMED",
        )


class StatementSettingsSnapshotMigrationTestCase(django.test.TransactionTestCase):
    app = "finance"
    migrate_from = [("finance", "0012_statementonexcursionproxy")]
    migrate_to = [("finance", "0013_statement_settings_snapshot")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        self.Statement = old_apps.get_model(self.app, "Statement")

        self.unsubmitted = self.Statement.objects.create(
            short_description="Unsubmitted Statement",
            status=0,
        )
        self.submitted = self.Statement.objects.create(
            short_description="Submitted Statement",
            status=1,
        )
        self.confirmed = self.Statement.objects.create(
            short_description="Confirmed Statement",
            status=2,
        )

    def test_settings_snapshot_backfilled_for_submitted_and_confirmed(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

        new_apps = executor.loader.project_state(self.migrate_to).apps
        Statement = new_apps.get_model(self.app, "Statement")

        submitted = Statement.objects.get(pk=self.submitted.pk)
        confirmed = Statement.objects.get(pk=self.confirmed.pk)
        unsubmitted = Statement.objects.get(pk=self.unsubmitted.pk)

        self.assertIsInstance(submitted.settings_snapshot, dict)
        self.assertIn("ALLOWANCE_PER_DAY", submitted.settings_snapshot)
        self.assertIn("captured_at", submitted.settings_snapshot)
        self.assertEqual(
            confirmed.settings_snapshot["MAX_NIGHT_COST"],
            float(settings.MAX_NIGHT_COST),
        )
        self.assertEqual(unsubmitted.settings_snapshot, {})


class RulesetStoreMigrationTestCase(django.test.TransactionTestCase):
    """What ``0016`` does to a database that already holds statements.

    The four things the migration promises, in order: the reference ruleset
    becomes the first stored version, every statement is bound to it, a
    settled statement keeps the numbers it was submitted with, and a paid
    statement's transactions become its obligations.
    """

    app = "finance"
    migrate_from = [("finance", "0015_ruleset_store")]
    migrate_to = [("finance", "0016_import_reference_ruleset")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Statement = old_apps.get_model(self.app, "Statement")
        Transaction = old_apps.get_model(self.app, "Transaction")
        Member = old_apps.get_model("members", "Member")

        self.member = Member.objects.create(
            prename="Alt", lastname="Bestand", email=settings.TEST_MAIL, gender=0
        )
        self.draft = Statement.objects.create(short_description="Entwurf", status=0)
        self.submitted = Statement.objects.create(
            short_description="Eingereicht",
            status=1,
            settings_snapshot={"ALLOWANCE_PER_DAY": 17.0, "captured_at": "2020-01-01T00:00:00"},
        )
        self.paid = Statement.objects.create(
            short_description="Bezahlt",
            status=2,
            settings_snapshot={"ALLOWANCE_PER_DAY": 19.0},
        )
        Transaction.objects.create(
            reference="Beleg", amount=Decimal("42.00"), member=self.member, statement=self.paid
        )
        Transaction.objects.create(
            reference="abzüglich Org-Beitrag",
            amount=Decimal("-12.00"),
            member=self.member,
            statement=self.paid,
        )
        # A paid statement with nothing booked against it: there is nothing to
        # materialise, and that has to be as uneventful as it sounds.
        self.paid_without_transactions = Statement.objects.create(
            short_description="Bezahlt, leer", status=2
        )

    def _migrate(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        return executor.loader.project_state(self.migrate_to).apps

    def test_the_reference_ruleset_becomes_the_first_version(self):
        apps = self._migrate()
        RuleSet = apps.get_model(self.app, "RuleSet")
        version = RuleSet.objects.get()
        self.assertEqual(version.name, "heidelberg")
        self.assertEqual(version.state, 1)
        self.assertIn("__init__.py", version.sources)
        self.assertEqual(version.params["ALLOWANCE_PER_DAY"], str(settings.ALLOWANCE_PER_DAY))
        self.assertEqual(version.hash, version_hash(version.sources, version.params))

    def test_every_statement_is_bound_and_keeps_its_own_numbers(self):
        apps = self._migrate()
        Statement = apps.get_model(self.app, "Statement")
        draft = Statement.objects.get(pk=self.draft.pk)
        submitted = Statement.objects.get(pk=self.submitted.pk)
        paid = Statement.objects.get(pk=self.paid.pk)
        self.assertTrue(draft.ruleset_hash)
        self.assertEqual(
            draft.ruleset_snapshot["params"]["ALLOWANCE_PER_DAY"], str(settings.ALLOWANCE_PER_DAY)
        )
        # A statement that was submitted keeps what it was submitted with.
        self.assertEqual(submitted.ruleset_snapshot["params"]["ALLOWANCE_PER_DAY"], "17.0")
        self.assertEqual(paid.ruleset_snapshot["params"]["ALLOWANCE_PER_DAY"], "19.0")
        self.assertNotIn("captured_at", submitted.ruleset_snapshot["params"])

    def test_a_paid_statements_transactions_become_its_obligations(self):
        apps = self._migrate()
        Obligation = apps.get_model(self.app, "Obligation")
        rows = list(Obligation.objects.filter(statement_id=self.paid.pk).order_by("position"))
        self.assertEqual(len(rows), 3, "two transactions and the balancing row")
        self.assertEqual(rows[0].amount_cents, 4200)
        self.assertEqual(rows[0].source_kind, "section")
        self.assertEqual(rows[0].destination_member_id, self.member.pk)
        self.assertEqual(rows[0].destination_name, "Alt Bestand")
        self.assertEqual(rows[0].category, "legacy")
        self.assertIsNotNone(rows[0].frozen_at)
        # A negative transaction is money charged against the member.
        self.assertEqual(rows[1].amount_cents, 1200)
        self.assertEqual(rows[1].source_member_id, self.member.pk)
        self.assertEqual(rows[1].destination_kind, "section")
        # And the books close at what the section paid out net.
        self.assertEqual(rows[2].rule_id, "balance")
        self.assertEqual(rows[2].amount_cents, 3000)
        self.assertEqual(rows[2].source_kind, "participants")
        # Statements that are not paid out keep their figures the rules'.
        self.assertEqual(Obligation.objects.filter(statement_id=self.draft.pk).count(), 0)
        self.assertEqual(Obligation.objects.filter(statement_id=self.submitted.pk).count(), 0)
        self.assertEqual(
            Obligation.objects.filter(statement_id=self.paid_without_transactions.pk).count(), 0
        )

    def test_the_data_can_be_unwound_again(self):
        self._migrate()
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_from)
        apps = executor.loader.project_state(self.migrate_from).apps
        Statement = apps.get_model(self.app, "Statement")
        Obligation = apps.get_model(self.app, "Obligation")
        self.assertEqual(Obligation.objects.count(), 0)
        self.assertEqual(Statement.objects.exclude(ruleset_hash="").count(), 0)


class AnswersFromColumnsMigrationTestCase(django.test.TransactionTestCase):
    """What ``0021`` and ``0022`` do to a database that already holds statements.

    The one thing ``0021`` must not do is read ``Statement.inputs``. That field
    was written beside the four columns and read by nothing for three releases,
    so it drifts: the fixture below gives one statement a stale ``inputs`` that
    disagrees with its columns on every key, and the assertions say the columns
    won. Neuter the migration by having it start from ``statement.inputs``
    instead and ``test_the_columns_win_over_a_stale_inputs_field`` goes red on
    all four keys.
    """

    app = "finance"
    migrate_from = [("finance", "0020_approval_signers")]
    migrate_to = [("finance", "0022_remove_statement_heidelberg_columns")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Statement = old_apps.get_model(self.app, "Statement")
        Member = old_apps.get_model("members", "Member")

        self.anna = Member.objects.create(
            prename="Anna", lastname="Ärmel", email=settings.TEST_MAIL, gender=0
        )
        self.bodo = Member.objects.create(
            prename="Bodo", lastname="Biwak", email=settings.TEST_MAIL, gender=0
        )
        self.filled = Statement.objects.create(
            short_description="Alles ausgefüllt",
            status=0,
            night_cost=Decimal("27.00"),
            subsidy_to=self.anna,
            ljp_to=self.bodo,
        )
        self.filled.allowance_to.set([self.bodo, self.anna])
        # The drift this migration exists to not believe: every key disagrees
        # with the column beside it, plus one key no ruleset asks for.
        self.drifted = Statement.objects.create(
            short_description="Veraltete Antworten",
            status=1,
            night_cost=Decimal("9.50"),
            subsidy_to=self.bodo,
            inputs={
                "night_cost": "99.00",
                "allowance_to": [self.anna.pk],
                "subsidy_to": self.anna.pk,
                "ljp_to": self.anna.pk,
                "retired_question": "nobody asks this any more",
            },
        )
        self.empty = Statement.objects.create(short_description="Nichts davon", status=0)
        # Leave the database where the suite expects it. The through table that
        # reversing ``0022`` re-creates is not in the current model state, so
        # the flush between tests does not clear it and the next test's member
        # rows trip its foreign key.
        self.addCleanup(self._migrate)

    def _migrate(self, target=None):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target or self.migrate_to)
        return executor.loader.project_state(target or self.migrate_to).apps

    def test_every_answer_arrives_under_the_key_the_rules_declare(self):
        apps = self._migrate()
        Statement = apps.get_model(self.app, "Statement")
        answers = Statement.objects.get(pk=self.filled.pk).inputs
        self.assertEqual(answers["night_cost"], "27.00")
        # Sorted, which is the order the engine fed the rules before this, so
        # the migration cannot change an amount.
        self.assertEqual(answers["allowance_to"], sorted([self.anna.pk, self.bodo.pk]))
        self.assertEqual(answers["subsidy_to"], self.anna.pk)
        self.assertEqual(answers["ljp_to"], self.bodo.pk)

    def test_a_statement_that_answered_nothing_says_so(self):
        apps = self._migrate()
        Statement = apps.get_model(self.app, "Statement")
        answers = Statement.objects.get(pk=self.empty.pk).inputs
        self.assertEqual(answers["night_cost"], "0.00")
        self.assertEqual(answers["allowance_to"], [])
        self.assertIsNone(answers["subsidy_to"])
        self.assertIsNone(answers["ljp_to"])

    def test_the_columns_win_over_a_stale_inputs_field(self):
        apps = self._migrate()
        Statement = apps.get_model(self.app, "Statement")
        answers = Statement.objects.get(pk=self.drifted.pk).inputs
        self.assertEqual(answers["night_cost"], "9.50")
        self.assertEqual(answers["allowance_to"], [])
        self.assertEqual(answers["subsidy_to"], self.bodo.pk)
        self.assertIsNone(answers["ljp_to"])
        # A key no column holds is nobody's to overwrite, so it stays.
        self.assertEqual(answers["retired_question"], "nobody asks this any more")

    def test_the_columns_are_gone(self):
        apps = self._migrate()
        Statement = apps.get_model(self.app, "Statement")
        names = {field.name for field in Statement._meta.get_fields()}
        self.assertFalse(
            names & {"night_cost", "allowance_to", "subsidy_to", "ljp_to"},
            "the Heidelberg columns are still on the table",
        )

    def test_the_data_can_be_unwound_again(self):
        self._migrate()
        apps = self._migrate(self.migrate_from)
        Statement = apps.get_model(self.app, "Statement")
        filled = Statement.objects.get(pk=self.filled.pk)
        self.assertEqual(filled.night_cost, Decimal("27.00"))
        self.assertEqual(filled.subsidy_to_id, self.anna.pk)
        self.assertEqual(filled.ljp_to_id, self.bodo.pk)
        self.assertEqual(
            sorted(member.pk for member in filled.allowance_to.all()),
            sorted([self.anna.pk, self.bodo.pk]),
        )
        empty = Statement.objects.get(pk=self.empty.pk)
        self.assertEqual(empty.night_cost, Decimal(0))
        self.assertIsNone(empty.subsidy_to_id)

    def test_a_recipient_deleted_in_between_comes_back_as_nobody(self):
        """What reversing cannot restore, and why that is the right answer.

        The columns were ``SET_NULL`` and the through rows cascaded, so a
        member deleted while the answers lived in JSON would not have been in a
        foreign key either.
        """
        self._migrate()
        apps = self._migrate(self.migrate_to)
        Member = apps.get_model("members", "Member")
        Member.objects.filter(pk=self.anna.pk).delete()
        apps = self._migrate(self.migrate_from)
        Statement = apps.get_model(self.app, "Statement")
        filled = Statement.objects.get(pk=self.filled.pk)
        self.assertIsNone(filled.subsidy_to_id)
        self.assertEqual([member.pk for member in filled.allowance_to.all()], [self.bodo.pk])
