"""``manage.py verifyrulesets`` — does what is stored still say what it said?

Three checks, and they are the three ways a stored version can quietly stop
meaning what it meant:

* a version whose sources no longer hash to its manifest, or whose manifest no
  longer hashes to its hash — somebody wrote to the row,
* a statement bound to a closure nobody imported — a snapshot from somewhere
  else,
* a settled statement whose obligations no longer reproduce: the rules are
  replayed from the statement's *own* snapshot and the amounts compared to the
  cent. This is the one that is worth running: it is the difference between
  "we kept a copy of the rules" and "the copy still produces the figures we
  paid out".

Run it from Celery beat, or from a section's CI against a restored dump.
"""

from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from finance.engine import verify
from finance.models import Statement
from finance.store import RuleSet


class Command(BaseCommand):
    help = "Re-hash every stored ruleset version and replay settled statements."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sample",
            type=int,
            default=10,
            help="How many paid statements to replay (default: 10).",
        )

    def handle(self, *args, **options):
        statements = Statement.objects.all().order_by("-pk")
        problems = verify(statements, sample=options["sample"])
        if problems:
            for problem in problems:
                self.stderr.write(f"  {problem}")
            raise CommandError(f"{len(problems)} problems with what is stored")
        self.stdout.write(
            self.style.SUCCESS(
                f"{RuleSet.objects.count()} versions and {statements.count()} statements verified"
            )
        )
