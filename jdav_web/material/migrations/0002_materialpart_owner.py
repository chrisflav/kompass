import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("material", "0001_initial_squashed_0002_auto_20171011_2045"),
        ("members", "0049_group_show_website_registration"),
    ]

    operations = [
        migrations.AddField(
            model_name="materialpart",
            name="owner",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="members.member",
                verbose_name="owner",
            ),
        ),
    ]
