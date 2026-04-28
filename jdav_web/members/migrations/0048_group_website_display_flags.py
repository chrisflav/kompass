from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0047_alter_excursion_field_options"),
    ]

    operations = [
        migrations.AddField(
            model_name="group",
            name="show_website_year",
            field=models.BooleanField(default=False, verbose_name="show year range on website"),
        ),
        migrations.AddField(
            model_name="group",
            name="show_website_weekday",
            field=models.BooleanField(default=False, verbose_name="show weekday on website"),
        ),
        migrations.AddField(
            model_name="group",
            name="show_website_time",
            field=models.BooleanField(default=False, verbose_name="show time on website"),
        ),
        migrations.AddField(
            model_name="group",
            name="show_website_contact_email",
            field=models.BooleanField(default=False, verbose_name="show contact email on website"),
        ),
    ]
