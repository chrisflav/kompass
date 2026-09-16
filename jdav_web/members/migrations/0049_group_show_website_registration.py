from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0048_group_website_display_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="show_website_registration",
            field=models.BooleanField(
                default=False, verbose_name="show registration link on website"
            ),
        ),
    ]
