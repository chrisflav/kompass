"""Who makes the transfers, as a column of the version that declares it.

``Ruleset.payout`` is a declaration a section writes in its own rules package
(``"self"``: the person reviewing the statement transfers the money;
``"office"``: the Geschäftsstelle does, after the handoff). It is read off the
ruleset at import, written here, and copied onto every statement's snapshot —
so the terminal act of a review is described by the rules the statement was
created under rather than by whatever arrangement is in force today.

**Every existing row gets ``"self"``**, which is not a guess: it is what
Kompass did, and the only act it offered was "I have made these transfers". A
ruleset that says nothing still means ``"self"``
(:attr:`kompass.rules.Ruleset.payout`), so a section that does not touch its
rules sees nothing change — and a section that does touch them gets a new
version with a new hash, because the declaration is part of the sources the
version is hashed from.

The column joins ``IMMUTABLE_FIELDS``: who pays is part of what a version
*says*, so changing it is a new row like changing a rate.
"""

from django.db import migrations
from django.db import models


class Migration(migrations.Migration):
    dependencies = [
        ("finance", "0026_settlement_group"),
    ]

    operations = [
        migrations.AddField(
            model_name="ruleset",
            name="payout",
            field=models.CharField(
                choices=[
                    ("self", "The reviewer makes the transfers (ausgezahlt)"),
                    ("office", "The office makes the transfers (zur Auszahlung übergeben)"),
                ],
                default="self",
                help_text=(
                    "Who makes the bank transfers once a statement is released, as "
                    "this version of the rules declares it. Immutable, like the rest "
                    "of what a version says: a section that changes how it pays "
                    "imports a new version, and a statement keeps the arrangement it "
                    "was created under."
                ),
                max_length=10,
                verbose_name="Payout mode",
            ),
        ),
    ]
