"""Split every material part into one row per physical piece.

Before this migration a ``MaterialPart`` described ``quantity`` identical pieces,
distributed over several members by ``Ownership`` rows with a ``count``. Afterwards
every row is a single piece with at most one ``owner``.

Forwards, a part with ownerships ``(A, 2), (B, 3)`` and ``quantity = 6`` becomes six
rows: two owned by A, three owned by B and one without an owner. If the ownership
counts add up to more than ``quantity``, the counts win, since they describe pieces
somebody actually holds. A part without any pieces is kept as a single unowned row,
so that no data is lost. The original row is reused for the first piece, so its
primary key, photo and categories stay where they were; the other pieces are copies
of it.

Backwards, every piece becomes a part with ``quantity = 1`` and, if it has an owner,
one ``Ownership`` with ``count = 1``. The pieces are not merged back into one part:
which pieces belonged together is not recorded, and guessing from equal names would
merge parts that were distinct before.
"""

from django.db import migrations


def split_parts(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    MaterialPart = apps.get_model("material", "MaterialPart")
    Ownership = apps.get_model("material", "Ownership")

    for part in MaterialPart.objects.using(db_alias).order_by("pk"):
        owners = []
        for ownership in Ownership.objects.using(db_alias).filter(material=part).order_by("pk"):
            owners.extend([ownership.owner_id] * max(ownership.count, 0))
        owners.extend([None] * max(part.quantity - len(owners), 0))
        if not owners:
            owners = [None]

        categories = list(part.material_cat.all())
        part.owner_id = owners[0]
        part.quantity = 1
        part.save()
        for owner_id in owners[1:]:
            piece = MaterialPart.objects.using(db_alias).create(
                name=part.name,
                description=part.description,
                quantity=1,
                buy_date=part.buy_date,
                lifetime=part.lifetime,
                photo=part.photo.name,
                owner_id=owner_id,
            )
            piece.material_cat.set(categories)

    Ownership.objects.using(db_alias).all().delete()


def merge_ownerships(apps, schema_editor):
    db_alias = schema_editor.connection.alias
    MaterialPart = apps.get_model("material", "MaterialPart")
    Ownership = apps.get_model("material", "Ownership")

    for part in MaterialPart.objects.using(db_alias).order_by("pk"):
        part.quantity = 1
        part.save()
        if part.owner_id is not None:
            Ownership.objects.using(db_alias).create(material=part, owner_id=part.owner_id, count=1)


class Migration(migrations.Migration):
    dependencies = [
        ("material", "0002_materialpart_owner"),
    ]

    operations = [
        migrations.RunPython(split_parts, merge_ownerships),
    ]
