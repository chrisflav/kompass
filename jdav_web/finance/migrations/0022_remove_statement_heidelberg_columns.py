"""The last Heidelberg-shaped thing in the schema, removed.

``0021`` copied the four answers into ``inputs``; this drops the columns they
came from. Reversing it re-creates them **empty** — the data comes back by
reversing ``0021`` as well, which is why the two are separate migrations rather
than one: on MariaDB a schema change is not transactional, so a single
migration that copied and then dropped could fail between the two and leave
neither.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [("finance", "0021_statement_answers_from_columns")]

    operations = [
        migrations.RemoveField(model_name="statement", name="allowance_to"),
        migrations.RemoveField(model_name="statement", name="ljp_to"),
        migrations.RemoveField(model_name="statement", name="night_cost"),
        migrations.RemoveField(model_name="statement", name="subsidy_to"),
        migrations.AlterField(
            model_name="statement",
            name="inputs",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text=(
                    "The answers to the questions the section's rules ask, by key. "
                    "Which questions those are is the ruleset's declaration, so this "
                    "is the only place a statement keeps them."
                ),
                verbose_name="Answers",
            ),
        ),
    ]
