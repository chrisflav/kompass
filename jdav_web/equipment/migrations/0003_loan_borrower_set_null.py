import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("equipment", "0002_schedule_notices"),
        ("members", "0049_group_show_website_registration"),
    ]

    operations = [
        migrations.AlterField(
            model_name="loan",
            name="borrower",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="material_loans",
                to="members.member",
                verbose_name="borrower",
            ),
        ),
    ]
