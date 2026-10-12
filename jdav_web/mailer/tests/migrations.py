import datetime

import django.test
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


class MessageCreatedAtMigrationTestCase(django.test.TransactionTestCase):
    """The creation time of existing messages is recovered from the admin log."""

    # the admin log and the apps it refers to are part of the old state as well
    migrate_from = [
        ("mailer", "0010_alter_emailaddress_internal_only"),
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
    ]
    migrate_to = [("mailer", "0011_message_created_at")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        Message = old_apps.get_model("mailer", "Message")
        ContentType = old_apps.get_model("contenttypes", "ContentType")
        LogEntry = old_apps.get_model("admin", "LogEntry")
        User = old_apps.get_model("auth", "User")

        user = User.objects.create(username="logger")
        message_type, _ = ContentType.objects.get_or_create(app_label="mailer", model="message")
        user_type, _ = ContentType.objects.get_or_create(app_label="auth", model="user")
        self.now = timezone.now()
        self.two_years_ago = self.now - datetime.timedelta(days=730)
        self.one_year_ago = self.now - datetime.timedelta(days=365)

        def log(content_type, pk, action_time):
            LogEntry.objects.create(
                user=user,
                content_type=content_type,
                object_id=str(pk),
                object_repr="entry",
                action_flag=1,
                action_time=action_time,
            )

        def message(subject, *logged_at):
            msg = Message.objects.create(subject=subject, content="Body")
            for action_time in logged_at:
                log(message_type, msg.pk, action_time)
            return msg

        # ids grow with creation time
        self.logged = message("logged", self.two_years_ago)
        self.unlogged = message("unlogged")
        # created outside the admin and changed there twice later on
        self.changed = message(
            "changed", self.now - datetime.timedelta(days=180), self.one_year_ago
        )
        self.newest = message("newest")
        # an entry about some other kind of object is ignored
        log(user_type, self.newest.pk, self.two_years_ago)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_created_at_backfilled(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(self.migrate_to)
        new_apps = executor.loader.project_state(self.migrate_to).apps
        Message = new_apps.get_model("mailer", "Message")
        created = dict(Message.objects.values_list("pk", "created_at"))

        self.assertEqual(created[self.logged.pk], self.two_years_ago)
        self.assertEqual(created[self.changed.pk], self.one_year_ago)
        # no entry: the next newer message's time is an upper bound
        self.assertEqual(created[self.unlogged.pk], self.one_year_ago)
        # no entry and nothing newer: the time of the migration
        self.assertGreaterEqual(created[self.newest.pk], self.now)
