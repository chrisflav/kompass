"""One signature per signer, and a reason when the rules cannot be resolved.

``Approval.user`` records the account behind a signature beside the member it
credits, which is what makes "one signature per person" expressible for an
administrator who has no member record: without it, such signatures were an
anonymous tally, and two clicks from one account satisfied a quorum of two.
The two constraints are conditional because both columns are nullable, and
``NULL`` does not collide with ``NULL`` in any database this runs on.

``ApprovalConstraint.error`` is why a constraint names nobody. A rule that
raises used to be swallowed, which quietly turned the section's most
restrictive instruction into none at all; now it is written down, the
constraint is satisfied by nobody, and the payout is stuck until somebody
fixes the rule.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0019_obligation_superseded"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="approval",
            name="user",
            field=models.ForeignKey(
                blank=True,
                default=None,
                help_text=(
                    "The account that signed. Recorded beside the member so that a signature "
                    "from an administrator with no member record is still one signature from "
                    "one person rather than an anonymous tally."
                ),
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="finance_approvals",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Signed by account",
            ),
        ),
        migrations.AddField(
            model_name="approvalconstraint",
            name="error",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Why the rules could not say who may sign this. A constraint with a reason "
                    "here names nobody and is satisfied by nobody: a broken rule may not be "
                    "signed away."
                ),
                verbose_name="Could not be resolved",
            ),
        ),
        migrations.AddConstraint(
            model_name="approval",
            constraint=models.UniqueConstraint(
                condition=models.Q(("member__isnull", False)),
                fields=("statement", "member"),
                name="finance_approval_once_per_member",
            ),
        ),
        migrations.AddConstraint(
            model_name="approval",
            constraint=models.UniqueConstraint(
                condition=models.Q(("member__isnull", True), ("user__isnull", False)),
                fields=("statement", "user"),
                name="finance_approval_once_per_account",
            ),
        ),
    ]
