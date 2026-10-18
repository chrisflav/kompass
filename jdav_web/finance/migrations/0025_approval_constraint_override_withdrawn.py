"""A row says when a waiver did not carry onto it.

Supersession (``0023``) carries the decision recorded about a step onto the row
that takes over, so that a finance officer covering a receipt does not put a
payout the board has already waived back in front of the board. A waiver is a
permission, though, and ``ConstraintState.open`` reads it on every call — so
carrying one that the live path would now refuse defeats the control that
refuses it. There are three such controls, each measured paying a statement
out: a ``Forbid`` that now excludes the person who gave the waiver (the payee
who waived a step and then fronted a receipt), a step that can no longer be
resolved (a waiver from before the rule broke un-sticks a payout that is
supposed to stay stuck), and a step that is not being asked for on the row the
waiver lands on (the board's signatures pre-authorised before the rules asked
for them).

The waiver therefore stays on the superseded row and this column says why it
stopped applying. Existing rows get ``""``: nothing has been withdrawn,
because until now nothing could be.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0024_ruleset_retired_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalconstraint",
            name="override_withdrawn",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Why an override recorded on this step did not carry onto this row: a "
                    "rule now excludes the person who gave it, or the step can no longer "
                    "be resolved, or it is not being asked for here. The override itself "
                    "is on the row this one replaced, which is kept."
                ),
                verbose_name="Withdrawn override",
            ),
        ),
    ]
