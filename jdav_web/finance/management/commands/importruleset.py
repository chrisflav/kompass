"""``manage.py importruleset`` — read the section's rules and activate them.

Runs at every container start, on demand from the admin, and optionally from a
Celery beat poll. An unchanged package hashes to the version that is already
stored, so running it twice costs a hash and changes nothing.

A package that does not pass its checks or its cases is stored as a draft, the
previous version stays active, and the command exits non-zero. The container
still serves: a typo in a rule is not a reason to take a section's finances
offline, it is a reason to shout.
"""

from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from finance.engine import configured_directory
from finance.engine import import_from_directory
from finance.engine import ruleset_directory
from finance.store import RuleSet
from finance.tasks import ensure_poll_task
from finance.tasks import ensure_verify_task


class Command(BaseCommand):
    help = "Import the section's finance ruleset and activate it."

    def add_arguments(self, parser):
        parser.add_argument(
            "package",
            nargs="?",
            default=None,
            help="The ruleset package to import (default: the configured one).",
        )
        parser.add_argument(
            "--revision",
            default="",
            help="The commit the sources come from, recorded with the version.",
        )
        parser.add_argument("--name", default="", help="Store the version under this name instead.")

    def handle(self, *args, **options):
        directory = (
            configured_directory() if options["package"] is None else Path(options["package"])
        )
        if not directory.is_dir():
            raise CommandError(f"{directory} is not a directory")
        where = "the configured ruleset" if ruleset_directory() else "the reference ruleset"
        row, problems = import_from_directory(
            directory, name=options["name"], revision=options["revision"]
        )
        if problems:
            self.stderr.write(
                self.style.ERROR(f"{where} in {directory} was NOT activated ({row.short_hash}):")
            )
            for problem in problems:
                self.stderr.write(f"  {problem}")
            active = RuleSet.objects.active()
            self.stderr.write(
                self.style.WARNING(
                    f"the active version is still {active}" if active else "no version is active"
                )
            )
            raise CommandError("the ruleset was stored as a draft")
        ensure_poll_task()
        ensure_verify_task()
        self.stdout.write(self.style.SUCCESS(f"{where} is active: {row} ({directory})"))
