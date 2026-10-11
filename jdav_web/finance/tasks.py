"""Background work for the finance app: picking up a rule change.

A section edits its rules in its own repository, the host pulls, and the
instance notices. Noticing is one of three things: the import that runs at
every container start, the admin's "Import from configuration", or — if the
section asks for it with ``[finance] ruleset_poll_minutes`` — this task.

The poll is cheap by construction: an unchanged package hashes to the version
that is already stored, so the task reads some files and stops. No container
restart, no release, no downtime.
"""

import logging

from celery import shared_task
from django.conf import settings
from django_celery_beat.models import IntervalSchedule
from django_celery_beat.models import PeriodicTask
from finance.engine import configured_directory
from finance.engine import import_from_directory

logger = logging.getLogger(__name__)

#: The beat entry's name, which is also how it is found again to be removed.
POLL_TASK_NAME = "finance: import the section's ruleset"


@shared_task
def import_ruleset():
    """Import the configured ruleset; return the version's hash.

    Failure is reported, not raised: the previous version stays active (the
    import stores a failing package as a draft), and a rule that does not
    compile must not turn into a retry storm.
    """
    directory = configured_directory()
    if not directory.is_dir():
        logger.warning("the configured finance ruleset %s is not a directory", directory)
        return ""
    row, problems = import_from_directory(directory)
    if problems:
        logger.error("the finance ruleset %s was not activated: %s", row.short_hash, problems)
    return row.hash


def ensure_poll_task(minutes=None):
    """Keep the beat entry in step with ``[finance] ruleset_poll_minutes``.

    Called from the import command, so that a section turns the poll on by
    editing its ``settings.toml`` and restarting — not by clicking through the
    periodic-task admin. Zero or unset removes the entry again.
    """
    every = getattr(settings, "FINANCE_RULESET_POLL_MINUTES", 0) if minutes is None else minutes
    every = int(every or 0)
    if every <= 0:
        PeriodicTask.objects.filter(name=POLL_TASK_NAME).delete()
        return None
    schedule, _created = IntervalSchedule.objects.get_or_create(
        every=every, period=IntervalSchedule.MINUTES
    )
    task, _created = PeriodicTask.objects.update_or_create(
        name=POLL_TASK_NAME,
        defaults={"interval": schedule, "task": "finance.tasks.import_ruleset", "enabled": True},
    )
    return task
