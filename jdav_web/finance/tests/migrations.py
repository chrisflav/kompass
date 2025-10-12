import django.test
from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class StatusMigrationTestCase(django.test.TransactionTestCase):
    """Test the migration from submitted/confirmed fields to status field."""

    app = 'finance'
    migrate_from = [('finance', '0009_statement_ljp_to')]
    migrate_to = [('finance', '0010_statement_status')]

    def setUp(self):
        # Get the state before migration
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)

        # Get the old models (before migration)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        self.Statement = old_apps.get_model(self.app, 'Statement')

        # Create statements with different combinations of submitted/confirmed
        # created_by is nullable, so we don't need to create a Member
        self.unsubmitted = self.Statement.objects.create(
            short_description='Unsubmitted Statement',
            submitted=False,
            confirmed=False
        )

        self.submitted = self.Statement.objects.create(
            short_description='Submitted Statement',
            submitted=True,
            confirmed=False
        )

        self.confirmed = self.Statement.objects.create(
            short_description='Confirmed Statement',
            submitted=True,
            confirmed=True
        )

    def test_status_field_migration(self):
        """Test that status field is correctly set from old submitted/confirmed fields."""
        # Run the migration
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)

        # Get the new models (after migration)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        Statement = new_apps.get_model(self.app, 'Statement')

        # Constants from the Statement model
        UNSUBMITTED = 0
        SUBMITTED = 1
        CONFIRMED = 2

        # Verify the migration worked correctly
        unsubmitted = Statement.objects.get(pk=self.unsubmitted.pk)
        self.assertEqual(unsubmitted.status, UNSUBMITTED,
                        'Statement with submitted=False, confirmed=False should have status=UNSUBMITTED')

        submitted = Statement.objects.get(pk=self.submitted.pk)
        self.assertEqual(submitted.status, SUBMITTED,
                        'Statement with submitted=True, confirmed=False should have status=SUBMITTED')

        confirmed = Statement.objects.get(pk=self.confirmed.pk)
        self.assertEqual(confirmed.status, CONFIRMED,
                        'Statement with submitted=True, confirmed=True should have status=CONFIRMED')
