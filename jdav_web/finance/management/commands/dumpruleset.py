"""``manage.py dumpruleset <hash>`` — print a stored version's source.

What an auditor, or whoever is debugging a statement from two years ago, needs:
the exact text that was executed, out of the database rather than out of a
repository that has moved on. With ``--path`` it prints one file; without, it
lists the manifest and the parameters.
"""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from finance.store import RuleSet


class Command(BaseCommand):
    help = "Print a stored ruleset version: its manifest, its parameters, its sources."

    def add_arguments(self, parser):
        parser.add_argument("hash", help="The version's hash, or the first characters of it.")
        parser.add_argument(
            "--path", default="", help="Print this file's source instead of the summary."
        )

    def handle(self, *args, **options):
        digest = options["hash"]
        row = RuleSet.objects.filter(hash__startswith=digest).first()
        if row is None:
            raise CommandError(f"no stored version starts with {digest}")
        if options["path"]:
            source = row.sources.get(options["path"])
            if source is None:
                raise CommandError(
                    f"{row} has no {options['path']}; it has {', '.join(sorted(row.sources))}"
                )
            self.stdout.write(source)
            return
        # Valid time on one line, transaction time on the next, and labelled
        # as such: the two differ whenever a correction was backdated, and
        # telling them apart is most of what somebody reads a stored version
        # for two years later (#560).
        retired = f"{row.retired_at:%Y-%m-%d %H:%M}" if row.retired_at else "—"
        self.stdout.write(f"{row} [{row.get_state_display()}]")
        self.stdout.write(
            f"  in force {row.valid_from:%Y-%m-%d %H:%M} to {row.valid_to or '—'} (valid time)"
        )
        self.stdout.write(
            f"  applied from {row.imported_at:%Y-%m-%d %H:%M} to {retired} (transaction time), "
            f"into {row.engine_version}"
        )
        self.stdout.write(
            f"  revision {row.revision or '—'}, context version {row.context_version}"
        )
        self.stdout.write("  parameters:")
        for key in sorted(row.params):
            self.stdout.write(f"    {key} = {row.params[key]}")
        self.stdout.write("  files:")
        for path in sorted(row.manifest):
            self.stdout.write(f"    {row.manifest[path][:12]}  {path}")
        for problem in row.problems:
            self.stdout.write(self.style.WARNING(f"  problem: {problem}"))
