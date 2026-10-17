"""When Kompass stopped applying a version, beside when its rules ended.

``valid_to`` was doing the work of both: with a past ``valid_from`` refused,
valid time could not differ from transaction time, so one column said "the
rules ended here" and "we were told here" at once. A correction resolved in
March and imported in May needs those apart — the predecessor's rules ended
in March, and Kompass went on applying them until May — and unrecorded
history cannot be retrofitted, which is why the column lands before the
feature that needs it is finished (R3 on taxis #495).

**What this does to existing rows.** Every row keeps its ``valid_to``
untouched. ``retired_at`` is back-filled, for retired rows only, from the
``imported_at`` of the row that superseded them: that import *is* the moment
Kompass stopped applying the older version, so the value is exact rather than
an approximation of one. A retired row with no successor recorded — one
retired by a path that left no ``supersedes`` pointer — keeps ``NULL``, which
reads as "not recorded" rather than as a timestamp nobody can stand behind.
An active row has not been retired and keeps ``NULL`` as well.

What it reads, to be exact: ``supersedes_id`` and ``imported_at`` to find the
import that closed a row, and ``valid_to`` to tell a retired row from a live
one. What it writes is ``retired_at`` and nothing else, so no version's
identity, validity or state moves — and nothing *reads* ``retired_at`` to take
a decision: it is a record.
"""

from django.db import migrations
from django.db import models


def record_when_kompass_was_told(apps, schema_editor):
    """``retired_at`` = the import that closed the row, where there was one."""
    RuleSet = apps.get_model("finance", "RuleSet")
    for successor in RuleSet.objects.exclude(supersedes_id=None).iterator():
        RuleSet.objects.filter(
            pk=successor.supersedes_id, valid_to__isnull=False, retired_at__isnull=True
        ).update(retired_at=successor.imported_at)


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0021_approval_constraint_superseded"),
    ]

    operations = [
        migrations.AddField(
            model_name="ruleset",
            name="retired_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text=(
                    "When Kompass stopped applying this version — transaction time, "
                    "beside 'Valid to', which is when its rules ceased to be in force. "
                    "The two are the same instant unless a correction was backdated, "
                    "and then the difference is the whole record."
                ),
                null=True,
                verbose_name="Retired on",
            ),
        ),
        migrations.RunPython(record_when_kompass_was_told, migrations.RunPython.noop),
    ]
