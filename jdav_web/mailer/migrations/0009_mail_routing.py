# The help_text of EmailAddress.internal_only was rendered from settings back
# then, so makemigrations proposed an AlterField for it in every environment.
# It had no effect on the schema and is deliberately left out here, 0010
# records the settings independent value.

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("mailer", "0008_alter_emailaddress_name"),
    ]

    operations = [
        migrations.CreateModel(
            name="MailDeliveryState",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("email", models.EmailField(max_length=254, unique=True, verbose_name="email")),
                (
                    "hard_bounces",
                    models.PositiveIntegerField(default=0, verbose_name="hard bounces"),
                ),
                (
                    "soft_bounces",
                    models.PositiveIntegerField(default=0, verbose_name="soft bounces"),
                ),
                (
                    "last_bounce_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="last bounce"),
                ),
                (
                    "last_bounce_status",
                    models.CharField(blank=True, max_length=32, verbose_name="last status"),
                ),
                (
                    "last_bounce_detail",
                    models.TextField(blank=True, verbose_name="last bounce detail"),
                ),
                (
                    "suspended",
                    models.BooleanField(
                        default=False,
                        help_text="No mail is forwarded to this address until it is reactivated.",
                        verbose_name="suspended",
                    ),
                ),
            ],
            options={
                "verbose_name": "mail delivery state",
                "verbose_name_plural": "mail delivery states",
            },
        ),
        migrations.CreateModel(
            name="DeliveryAttempt",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("token", models.CharField(max_length=32, unique=True, verbose_name="token")),
                (
                    "message_id",
                    models.CharField(db_index=True, max_length=255, verbose_name="message id"),
                ),
                ("address", models.CharField(max_length=254, verbose_name="local address")),
                ("recipient", models.EmailField(max_length=254, verbose_name="recipient")),
                (
                    "envelope_from",
                    models.CharField(blank=True, max_length=254, verbose_name="envelope sender"),
                ),
                ("subject", models.CharField(blank=True, max_length=255, verbose_name="subject")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created")),
                ("sent_at", models.DateTimeField(blank=True, null=True, verbose_name="sent")),
                ("bounced_at", models.DateTimeField(blank=True, null=True, verbose_name="bounced")),
                (
                    "bounce_status",
                    models.CharField(blank=True, max_length=32, verbose_name="bounce status"),
                ),
            ],
            options={
                "verbose_name": "delivery attempt",
                "verbose_name_plural": "delivery attempts",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("message_id", "recipient"), name="unique_delivery_per_recipient"
                    )
                ],
            },
        ),
    ]
