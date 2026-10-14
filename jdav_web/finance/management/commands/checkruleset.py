"""``manage.py checkruleset`` — is this ruleset fit to be imported?

What a section's own CI runs, inside the image it deploys, before the pull
request is merged::

    docker run --rm -v "$PWD":/app/config:ro ghcr.io/chrisflav/kompass:<tag> \\
        python jdav_web/manage.py checkruleset /app/config/rules --fuzz 200

It touches no data: the whitelist and the cases are pure, and the fuzzer builds
its statements out of thin air. Nothing here imports or activates anything —
that is ``importruleset``, which runs the same checks and gates on them.
"""

from pathlib import Path

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from finance.engine import configured_directory
from finance.engine.fuzz import check_and_fuzz


class Command(BaseCommand):
    help = "Check a finance ruleset: its imports, its cases and optionally a fuzz run."

    def add_arguments(self, parser):
        parser.add_argument(
            "package",
            nargs="?",
            default=None,
            help="The ruleset package to check (default: the configured one).",
        )
        parser.add_argument(
            "--fuzz",
            type=int,
            default=0,
            metavar="N",
            help="Also run N random statements through the rules.",
        )
        parser.add_argument(
            "--seed", type=int, default=None, help="Seed the fuzzer, to reproduce a failure."
        )

    def handle(self, *args, **options):
        directory = (
            configured_directory() if options["package"] is None else Path(options["package"])
        )
        if not directory.is_dir():
            raise CommandError(f"{directory} is not a directory")
        problems = check_and_fuzz(directory, options["fuzz"], seed=options["seed"])
        if problems:
            for problem in problems:
                self.stderr.write(f"  {problem}")
            raise CommandError(f"{directory} is not fit to import ({len(problems)} problems)")
        checked = "its imports and its cases"
        if options["fuzz"]:
            checked += f", and {options['fuzz']} random statements"
        self.stdout.write(self.style.SUCCESS(f"{directory} passes {checked}"))
