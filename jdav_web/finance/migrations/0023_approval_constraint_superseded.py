"""A frozen approval constraint is superseded, never deleted.

``Obligation`` learned this in ``0019`` and the constraint rows beside it did
not: re-resolving a submitted statement — the finance officer covering a
receipt, which is the one edit that stays open — deleted every
``ApprovalConstraint`` row and wrote fresh ones. An override carries who
decided to pay out against a failing approval step and the reason they gave,
and the delete took both, silently, on an unrelated receipt edit (#555). That
is the record §6's appeal to the GoBD's *Unveränderbarkeit* exists to protect.

Existing rows are untouched and get ``NULL``, which means *live*: nothing has
been superseded, because until now nothing could be. Every read goes through
``ApprovalConstraint.objects``, which excludes the superseded rows, so the
column changes what a statement's approval record is only from the first
re-resolution after this migration onwards.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0022_remove_statement_heidelberg_columns"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalconstraint",
            name="superseded_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text=(
                    "Set when a later resolution replaced this row. It is kept, not "
                    "deleted: who signed a step off against the rules, and why, is a "
                    "record no edit elsewhere may destroy."
                ),
                null=True,
                verbose_name="Superseded on",
            ),
        ),
    ]
