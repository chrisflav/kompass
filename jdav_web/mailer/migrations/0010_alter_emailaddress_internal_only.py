# The help_text no longer depends on the deployment's settings, so this
# AlterField records the same value everywhere.

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("mailer", "0009_mail_routing"),
    ]

    operations = [
        migrations.AlterField(
            model_name="emailaddress",
            name="internal_only",
            field=models.BooleanField(
                default=False,
                help_text="Only allow forwarding to this e-mail address from one of the internal domains.",
                verbose_name="Restrict to internal email addresses",
            ),
        ),
    ]
