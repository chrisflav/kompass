from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("material", "0003_split_parts_by_owner"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="materialpart",
            name="quantity",
        ),
        migrations.DeleteModel(
            name="Ownership",
        ),
    ]
