# Messages had no timestamp so far. The creation time of an existing message is
# recovered from the admin log where it has one: the first entry about it is its
# creation, or an upper bound for messages created outside the admin. Messages
# without any entry take the time of the next newer message (ids grow with
# time), and the newest ones the time of this migration. Each estimate is at or
# after the real creation, so a recent message is never dated as an old one.

from django.db import migrations
from django.db import models
from django.db.models import Min
from django.utils import timezone


def backfill_created_at(apps, _schema_editor):
    Message = apps.get_model("mailer", "Message")
    ContentType = apps.get_model("contenttypes", "ContentType")
    LogEntry = apps.get_model("admin", "LogEntry")
    logged = {}
    content_type = ContentType.objects.filter(app_label="mailer", model="message").first()
    if content_type is not None:
        first_entries = (
            LogEntry.objects.filter(content_type=content_type)
            .order_by()
            .values("object_id")
            .annotate(first=Min("action_time"))
            .values_list("object_id", "first")
        )
        logged = {int(pk): first for pk, first in first_entries if pk.isdigit()}
    later = timezone.now()
    messages = list(Message.objects.order_by("-id").only("id"))
    for message in messages:
        later = min(logged.get(message.pk, later), later)
        message.created_at = later
    Message.objects.bulk_update(messages, ["created_at"], batch_size=500)


class Migration(migrations.Migration):
    dependencies = [
        ("admin", "0003_logentry_add_action_flag_choices"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("mailer", "0010_alter_emailaddress_internal_only"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="created_at",
            field=models.DateTimeField(null=True, verbose_name="created"),
        ),
        migrations.RunPython(backfill_created_at, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="message",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, verbose_name="created"),
        ),
    ]
