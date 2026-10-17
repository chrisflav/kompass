"""A row says when a waiver did not carry onto it.

Supersession (``0021``) carries the decision recorded about a step onto the row
that takes over, so that a finance officer covering a receipt does not put a
payout the board has already waived back in front of the board. A waiver is a
permission, though, and ``ConstraintState.open`` reads it on every call — so
carrying one that the live path would now refuse defeats the control that
refuses it: ``Statement.override_approval`` turns down an override from
somebody a ``Forbid`` excludes, and the payee who waived a step and then
fronted a receipt is exactly such a person.

The waiver therefore stays on the superseded row and this column says why it
stopped applying. Existing rows get ``""``: nothing has been withdrawn,
because until now nothing could be.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0022_ruleset_retired_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="approvalconstraint",
            name="override_withdrawn",
            field=models.TextField(
                blank=True,
                default="",
                help_text=(
                    "Why an override recorded on this step did not carry onto this row: "
                    "the person who gave it is excluded from it now. The override itself "
                    "is on the row this one replaced, which is kept."
                ),
                verbose_name="Withdrawn override",
            ),
        ),
    ]
