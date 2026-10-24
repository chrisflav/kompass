"""Which amounts may not share a bank transfer, as a column.

A section's rules can now put a *settlement group* on a transfer — a token of
their own choosing — and two amounts owed to the same person out of the same
ledger are bundled into one payment only when their tokens are equal. The
column is that token, on the resolved obligation row and on the booking the
payout screen makes from it.

**What this does to existing rows.** It adds two ``VARCHAR(50) NOT NULL
DEFAULT ''`` columns and nothing else: no row is read, no row is rewritten, no
value is recomputed. Every obligation and every transaction that exists lands
on the empty string, which means *no group* — and amounts with no group are
bundled with each other exactly as they were before this column existed. So a
statement that was already settled, a booking already generated and a ruleset
that declares no groups at all are all unchanged, including mid-flight: a
submitted statement whose bookings were generated before the migration keeps
merging the way its finance officer expects.

Additive and reversible. Dropping the columns loses only the separations a
ruleset declared after this point, which would then merge again.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0025_approval_constraint_override_withdrawn"),
    ]

    operations = [
        migrations.AddField(
            model_name="obligation",
            name="settlement_group",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "The group of bank transfers this amount may share, as the section's "
                    "rules named it. Two amounts owed to the same person out of the same "
                    "account are bundled into one payment only when this is equal. Empty "
                    "means no group, which is what bundles with everything else."
                ),
                max_length=50,
                verbose_name="Settlement group",
            ),
        ),
        migrations.AddField(
            model_name="transaction",
            name="settlement_group",
            field=models.CharField(
                blank=True,
                default="",
                help_text=(
                    "The group of bank transfers this booking may share, carried over "
                    "from the transfer the section's rules resolved. Bookings are "
                    "bundled into one payment only within one group, so an amount that "
                    "names its own is transferred separately. Empty means no group."
                ),
                max_length=50,
                verbose_name="Settlement group",
            ),
        ),
    ]
