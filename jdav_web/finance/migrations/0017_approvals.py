"""Signatures: who signed a statement off, and which constraint that satisfied.

The constraint rows already existed — frozen at submission with the eligible
set the forbids and the permission check left — and they gain the three states
§7 of the proposal asks to keep apart: whether the quorum is in, whether
somebody overrode it instead, and who did that and why. `Approval` is the
signature itself, on the statement rather than on a constraint, because one
signature counts against every constraint it satisfies.
"""

import django.db.models.deletion
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0016_import_reference_ruleset"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalconstraint",
            name="excluded",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Who a forbid or the permission check removed, and which one.",
                verbose_name="Excluded",
            ),
        ),
        migrations.AddField(
            model_name="approvalconstraint",
            name="overridden_at",
            field=models.DateTimeField(
                blank=True, default=None, null=True, verbose_name="Overridden on"
            ),
        ),
        migrations.AddField(
            model_name="approvalconstraint",
            name="overridden_by",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="overridden_approval_constraints",
                to="members.member",
                verbose_name="Overridden by",
            ),
        ),
        migrations.AddField(
            model_name="approvalconstraint",
            name="override_reason",
            field=models.TextField(blank=True, default="", verbose_name="Reason for the override"),
        ),
        migrations.AddField(
            model_name="approvalconstraint",
            name="satisfied",
            field=models.BooleanField(
                default=False,
                help_text="Whether the signatures this constraint asks for are in.",
                verbose_name="Satisfied",
            ),
        ),
        migrations.CreateModel(
            name="Approval",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("at", models.DateTimeField(auto_now_add=True, verbose_name="Signed on")),
                ("note", models.TextField(blank=True, default="", verbose_name="Note")),
                (
                    "member",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="finance_approvals",
                        to="members.member",
                        verbose_name="Signed by",
                    ),
                ),
                (
                    "statement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approval_set",
                        to="finance.statement",
                        verbose_name="Statement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Approval",
                "verbose_name_plural": "Approvals",
                "ordering": ["statement_id", "at", "pk"],
            },
        ),
    ]
