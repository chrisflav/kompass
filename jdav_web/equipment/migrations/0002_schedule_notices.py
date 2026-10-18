"""Run the material notices every morning.

The task declines requests nobody answered, asks holders to bring back reserved
pieces and reminds borrowers of pickups and returns. Without a beat entry none
of that happens, so it is created here rather than left to the periodic-task
admin.
"""

from django.db import migrations

TASK_NAME = "equipment: daily notices"


def create_schedule(apps, schema_editor):
    CrontabSchedule = apps.get_model("django_celery_beat", "CrontabSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    schedule, _created = CrontabSchedule.objects.get_or_create(
        minute="0", hour="7", day_of_week="*", day_of_month="*", month_of_year="*"
    )
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "crontab": schedule,
            "task": "equipment.tasks.send_material_notices",
            "enabled": True,
        },
    )


def remove_schedule(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=TASK_NAME).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0001_initial"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(create_schedule, remove_schedule),
    ]
