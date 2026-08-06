from django.conf import settings
from django.db import migrations


def create_youth_leader_group(apps, schema_editor):
    Group = apps.get_model("members", "Group")
    group_name = getattr(settings, "YOUTH_LEADER_GROUP", "Jugendleiter")
    Group.objects.get_or_create(name=group_name)


class Migration(migrations.Migration):
    dependencies = [
        ("members", "0047_alter_excursion_field_options"),
    ]

    operations = [
        migrations.RunPython(create_youth_leader_group, migrations.RunPython.noop),
    ]
