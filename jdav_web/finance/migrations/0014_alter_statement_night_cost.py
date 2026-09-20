# The help_text no longer depends on the deployment's settings, so this
# AlterField records the same value everywhere. makemigrations proposes two
# more alters alongside it, for Statement.short_description and
# Statement.status. Those are older drift and unrelated to the help_text, so
# they are left out here.

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0013_statement_settings_snapshot"),
    ]

    operations = [
        migrations.AlterField(
            model_name="statement",
            name="night_cost",
            field=models.DecimalField(
                decimal_places=2,
                default=0,
                help_text="Price for the overnight stay of a youth leader. This is required for the calculation of the subsidies for night costs.",
                max_digits=5,
                verbose_name="Price per night",
            ),
        ),
    ]
