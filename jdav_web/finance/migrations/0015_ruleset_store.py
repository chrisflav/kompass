"""The store: immutable ruleset versions, role assignments, materialised rows.

Schema only. The data — importing the reference ruleset as the first version,
binding it to every existing statement and back-filling the obligation rows
from the transactions that are already there — is the next migration, so that
each can be read (and reverted) on its own.
"""

import django.db.models.deletion
import django.utils.timezone
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0014_alter_statement_night_cost"),
        ("members", "0049_group_show_website_registration"),
    ]

    operations = [
        migrations.AddField(
            model_name="statement",
            name="ruleset_hash",
            field=models.CharField(
                blank=True, default="", max_length=64, verbose_name="Ruleset hash"
            ),
        ),
        migrations.AddField(
            model_name="statement",
            name="ruleset_snapshot",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="The rules and numbers this statement was created under.",
                verbose_name="Ruleset snapshot",
            ),
        ),
        migrations.CreateModel(
            name="ApprovalConstraint",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Position")),
                ("name", models.CharField(max_length=100, verbose_name="Name")),
                (
                    "description",
                    models.TextField(blank=True, default="", verbose_name="Description"),
                ),
                ("applicable", models.BooleanField(default=True, verbose_name="Applicable")),
                (
                    "required",
                    models.PositiveIntegerField(default=1, verbose_name="Signatures required"),
                ),
                (
                    "eligible_member_ids",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Who the rules named, re-checked against the permission system.",
                        verbose_name="Eligible members",
                    ),
                ),
                (
                    "rule_version",
                    models.CharField(
                        blank=True, default="", max_length=64, verbose_name="Rule version"
                    ),
                ),
                (
                    "frozen_at",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="Frozen on"
                    ),
                ),
                (
                    "statement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="approval_constraint_set",
                        to="finance.statement",
                        verbose_name="Statement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Approval constraint",
                "verbose_name_plural": "Approval constraints",
                "ordering": ["statement_id", "position", "pk"],
            },
        ),
        migrations.CreateModel(
            name="Obligation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "position",
                    models.PositiveIntegerField(
                        default=0,
                        help_text="The order the rules produced this transfer in.",
                        verbose_name="Position",
                    ),
                ),
                (
                    "source_kind",
                    models.CharField(
                        choices=[
                            ("member", "Member"),
                            ("section", "Section"),
                            ("participants", "Participants"),
                        ],
                        default="section",
                        max_length=20,
                        verbose_name="Owed by",
                    ),
                ),
                (
                    "source_name",
                    models.CharField(
                        blank=True, default="", max_length=100, verbose_name="Owed by (name)"
                    ),
                ),
                (
                    "destination_kind",
                    models.CharField(
                        choices=[
                            ("member", "Member"),
                            ("section", "Section"),
                            ("participants", "Participants"),
                        ],
                        default="member",
                        max_length=20,
                        verbose_name="Owed to",
                    ),
                ),
                (
                    "destination_name",
                    models.CharField(
                        blank=True, default="", max_length=100, verbose_name="Owed to (name)"
                    ),
                ),
                ("amount_cents", models.BigIntegerField(default=0, verbose_name="Amount in cents")),
                (
                    "category",
                    models.CharField(
                        blank=True, default="", max_length=50, verbose_name="Category"
                    ),
                ),
                (
                    "label",
                    models.CharField(blank=True, default="", max_length=200, verbose_name="Label"),
                ),
                (
                    "explanation",
                    models.TextField(blank=True, default="", verbose_name="Explanation"),
                ),
                (
                    "rule_id",
                    models.CharField(blank=True, default="", max_length=100, verbose_name="Rule"),
                ),
                (
                    "rule_version",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="The hash of the ruleset version that produced this row.",
                        max_length=64,
                        verbose_name="Rule version",
                    ),
                ),
                ("computed_at", models.DateTimeField(auto_now=True, verbose_name="Computed on")),
                (
                    "frozen_at",
                    models.DateTimeField(
                        blank=True,
                        default=None,
                        help_text="Set when the statement was handed in; a frozen row is never recomputed.",
                        null=True,
                        verbose_name="Frozen on",
                    ),
                ),
                (
                    "destination_member",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="receives_obligations",
                        to="members.member",
                        verbose_name="Owed to (member)",
                    ),
                ),
                (
                    "source_member",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="owes_obligations",
                        to="members.member",
                        verbose_name="Owed by (member)",
                    ),
                ),
                (
                    "statement",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="obligation_set",
                        to="finance.statement",
                        verbose_name="Statement",
                    ),
                ),
            ],
            options={
                "verbose_name": "Obligation",
                "verbose_name_plural": "Obligations",
                "ordering": ["statement_id", "position", "pk"],
            },
        ),
        migrations.CreateModel(
            name="RoleAssignment",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "role",
                    models.CharField(
                        help_text="The name the section's rules read this role under, e.g. 'kassenwart'.",
                        max_length=50,
                        verbose_name="Role",
                    ),
                ),
                (
                    "valid_from",
                    models.DateField(
                        default=django.utils.timezone.localdate, verbose_name="Valid from"
                    ),
                ),
                (
                    "valid_to",
                    models.DateField(blank=True, default=None, null=True, verbose_name="Valid to"),
                ),
                ("comment", models.TextField(blank=True, default="", verbose_name="Comment")),
                (
                    "member",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="finance_roles",
                        to="members.member",
                        verbose_name="Member",
                    ),
                ),
            ],
            options={
                "verbose_name": "Role assignment",
                "verbose_name_plural": "Role assignments",
                "ordering": ["role", "-valid_from"],
            },
        ),
        migrations.CreateModel(
            name="RuleSet",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("name", models.CharField(max_length=50, verbose_name="Name")),
                ("hash", models.CharField(max_length=64, unique=True, verbose_name="Hash")),
                (
                    "manifest",
                    models.JSONField(
                        default=dict,
                        help_text="One SHA-256 per file of the ruleset, keyed by relative path.",
                        verbose_name="Manifest",
                    ),
                ),
                (
                    "sources",
                    models.JSONField(
                        default=dict,
                        help_text="The ruleset's whole source closure, keyed by relative path.",
                        verbose_name="Sources",
                    ),
                ),
                (
                    "revision",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="The commit the sources were read from, where there is one.",
                        max_length=64,
                        verbose_name="Revision",
                    ),
                ),
                (
                    "engine_version",
                    models.CharField(
                        blank=True,
                        default="",
                        help_text="The Kompass and interpreter version the sources were imported into.",
                        max_length=200,
                        verbose_name="Engine version",
                    ),
                ),
                (
                    "context_version",
                    models.PositiveIntegerField(default=1, verbose_name="Context version"),
                ),
                (
                    "params",
                    models.JSONField(
                        default=dict,
                        help_text="The section's numbers, as exact decimal strings.",
                        verbose_name="Parameters",
                    ),
                ),
                (
                    "state",
                    models.IntegerField(
                        choices=[(0, "Draft (not activated)"), (1, "Active"), (2, "Retired")],
                        default=0,
                        verbose_name="State",
                    ),
                ),
                (
                    "problems",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Why this version was not activated, where it was not.",
                        verbose_name="Problems",
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(
                        default=django.utils.timezone.now, verbose_name="Valid from"
                    ),
                ),
                (
                    "valid_to",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="Valid to"
                    ),
                ),
                (
                    "imported_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="Imported on"),
                ),
                (
                    "activated_at",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="Activated on"
                    ),
                ),
                (
                    "cases_passed_at",
                    models.DateTimeField(
                        blank=True, default=None, null=True, verbose_name="Cases passed on"
                    ),
                ),
                (
                    "supersedes",
                    models.ForeignKey(
                        blank=True,
                        default=None,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="superseded_by",
                        to="finance.ruleset",
                        verbose_name="Supersedes",
                    ),
                ),
            ],
            options={
                "verbose_name": "Ruleset version",
                "verbose_name_plural": "Ruleset versions",
                "ordering": ["-valid_from", "-imported_at"],
            },
        ),
        migrations.AddField(
            model_name="statement",
            name="ruleset",
            field=models.ForeignKey(
                blank=True,
                default=None,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="statements",
                to="finance.ruleset",
                verbose_name="Ruleset version",
            ),
        ),
    ]
