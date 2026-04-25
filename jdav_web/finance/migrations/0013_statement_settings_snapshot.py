from django.db import migrations
from django.db import models


def _current_statement_settings_snapshot():
    from django.conf import settings
    from django.utils import timezone

    return {
        "ALLOWANCE_PER_DAY": float(settings.ALLOWANCE_PER_DAY),
        "MAX_NIGHT_COST": float(settings.MAX_NIGHT_COST),
        "AID_PER_KM_TRAIN": float(settings.AID_PER_KM_TRAIN),
        "AID_PER_KM_CAR": float(settings.AID_PER_KM_CAR),
        "EXCURSION_ORG_FEE": float(settings.EXCURSION_ORG_FEE),
        "LJP_CONTRIBUTION_PER_DAY": float(settings.LJP_CONTRIBUTION_PER_DAY),
        "LJP_TAX": float(settings.LJP_TAX),
        "captured_at": timezone.now().isoformat(),
    }


def backfill_settings_snapshot(apps, _schema_editor):
    Statement = apps.get_model("finance", "Statement")
    snapshot = _current_statement_settings_snapshot()
    # use historical values of Statements state constants
    for statement in Statement.objects.filter(status__in=[1, 2]):
        if not statement.settings_snapshot:
            statement.settings_snapshot = snapshot
            statement.save(update_fields=["settings_snapshot"])


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0012_statementonexcursionproxy"),
    ]

    operations = [
        migrations.AddField(
            model_name="statement",
            name="settings_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Financial settings captured at time of submission/confirmation.",
                verbose_name="Settings snapshot",
            ),
        ),
        migrations.RunPython(backfill_settings_snapshot, migrations.RunPython.noop),
    ]
