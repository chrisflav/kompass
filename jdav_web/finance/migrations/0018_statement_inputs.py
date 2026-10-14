"""One column for the answers, beside the four it will eventually replace.

Additive on purpose. The rules read ``night_cost``, ``allowance_to``,
``subsidy_to`` and ``ljp_to`` through the engine's input declarations today,
and those columns stay the source of truth; this column is written beside them
so that the API can speak in declarations now and a later migration can move
the data and drop the columns without a flag day.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0017_approvals"),
    ]

    operations = [
        migrations.AddField(
            model_name="statement",
            name="inputs",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="The answers to the questions the section's rules ask, by key. The four columns above are still the ones the rules read; this is written beside them until they are migrated into it.",
                verbose_name="Answers",
            ),
        ),
    ]
