import django.test
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django_celery_beat.models import PeriodicTask

TASK_NAME = "equipment: daily notices"


class ScheduleNoticesMigrationTestCase(django.test.TransactionTestCase):
    """Test the beat entry for the daily notices."""

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)

    def test_forwards_and_back(self):
        self.migrate([("equipment", "0002_schedule_notices")])
        task = PeriodicTask.objects.get(name=TASK_NAME)
        self.assertEqual(task.task, "equipment.tasks.send_material_notices")
        self.migrate([("equipment", "0001_initial")])
        self.assertFalse(PeriodicTask.objects.filter(name=TASK_NAME).exists())
