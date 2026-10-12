"""A settled obligation row is superseded, never overwritten.

The one edit that stays open after a statement is handed in — the finance
officer covering a bill — resolves the payout again. That used to delete the
frozen rows and write new ones in their place, which is exactly what §6's
appeal to the GoBD's *Unveränderbarkeit* argues against. The old rows are now
marked and kept; every read filters them out, and an auditor can see what the
payout said before.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0018_statement_inputs"),
    ]

    operations = [
        migrations.AddField(
            model_name="obligation",
            name="superseded_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Set when a later resolution replaced this row. It is kept, not deleted.",
                null=True,
                verbose_name="Superseded on",
            ),
        ),
        migrations.AlterField(
            model_name="obligation",
            name="frozen_at",
            field=models.DateTimeField(
                blank=True,
                default=None,
                help_text="Set when the statement was handed in. A frozen row is never changed: where the payout had to be resolved again, this row is superseded and the new one is written beside it.",
                null=True,
                verbose_name="Frozen on",
            ),
        ),
    ]
