from datetime import date
from decimal import Decimal

import django.test
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class SplitPartsByOwnerMigrationTestCase(django.test.TransactionTestCase):
    """Test splitting material parts into one row per physical piece."""

    migrate_from = [("material", "0002_materialpart_owner")]
    migrate_to = [("material", "0004_remove_materialpart_quantity_delete_ownership")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        old_apps = executor.loader.project_state(self.migrate_from).apps
        MaterialCategory = old_apps.get_model("material", "MaterialCategory")
        MaterialPart = old_apps.get_model("material", "MaterialPart")
        Ownership = old_apps.get_model("material", "Ownership")
        Member = old_apps.get_model("members", "Member")

        self.alice = Member.objects.create(
            prename="Alice", lastname="Smith", birth_date=date(1985, 3, 15), gender=0
        ).pk
        self.bob = Member.objects.create(
            prename="Bob", lastname="Jones", birth_date=date(1990, 1, 1), gender=1
        ).pk
        self.category = MaterialCategory.objects.create(name="Hardware").pk

        def part(name, quantity, photo=""):
            p = MaterialPart.objects.create(
                name=name,
                description="desc " + name,
                quantity=quantity,
                buy_date=date(2021, 6, 1),
                lifetime=Decimal("10"),
                photo=photo,
            )
            p.material_cat.add(self.category)
            return p

        # 2 pieces with Alice, 3 with Bob and 1 nobody holds.
        self.shared = part("Carabiner", 6, photo="images/carabiner.jpg")
        Ownership.objects.create(material=self.shared, owner_id=self.alice, count=2)
        Ownership.objects.create(material=self.shared, owner_id=self.bob, count=3)
        # More pieces held than recorded in ``quantity``: the ownerships win.
        self.overbooked = part("Helmet", 1)
        Ownership.objects.create(material=self.overbooked, owner_id=self.alice, count=2)
        # Nobody holds any of them.
        self.unowned = part("Sling", 3)
        # No pieces at all: kept as a single unowned piece.
        self.empty = part("Rope", 0)

    def tearDown(self):
        # Leave the schema as the other tests expect it.
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def migrate(self, target):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(target)
        return executor.loader.project_state(target).apps

    def pieces(self, MaterialPart, name):
        return MaterialPart.objects.filter(name=name).order_by("pk")

    def test_split(self):
        new_apps = self.migrate(self.migrate_to)
        MaterialPart = new_apps.get_model("material", "MaterialPart")

        carabiners = self.pieces(MaterialPart, "Carabiner")
        self.assertEqual(
            [p.owner_id for p in carabiners],
            [self.alice, self.alice, self.bob, self.bob, self.bob, None],
        )
        # The original row is the first piece, so its primary key is kept.
        self.assertEqual(carabiners[0].pk, self.shared.pk)
        for piece in carabiners:
            self.assertEqual(piece.description, "desc Carabiner")
            self.assertEqual(piece.buy_date, date(2021, 6, 1))
            self.assertEqual(piece.lifetime, Decimal("10"))
            self.assertEqual(piece.photo.name, "images/carabiner.jpg")
            self.assertEqual([c.pk for c in piece.material_cat.all()], [self.category])

        self.assertEqual(
            [p.owner_id for p in self.pieces(MaterialPart, "Helmet")], [self.alice, self.alice]
        )
        self.assertEqual([p.owner_id for p in self.pieces(MaterialPart, "Sling")], [None] * 3)
        self.assertEqual(
            [(p.pk, p.owner_id) for p in self.pieces(MaterialPart, "Rope")],
            [(self.empty.pk, None)],
        )
        self.assertEqual(MaterialPart.objects.count(), 6 + 2 + 3 + 1)

    def test_reverse(self):
        self.migrate(self.migrate_to)
        old_apps = self.migrate(self.migrate_from)
        MaterialPart = old_apps.get_model("material", "MaterialPart")
        Ownership = old_apps.get_model("material", "Ownership")

        # Every piece comes back as a part of its own, with its owner as an ownership.
        carabiners = self.pieces(MaterialPart, "Carabiner")
        self.assertEqual([p.quantity for p in carabiners], [1] * 6)
        self.assertEqual(
            [
                list(Ownership.objects.filter(material=p).values_list("owner_id", "count"))
                for p in carabiners
            ],
            [[(self.alice, 1)]] * 2 + [[(self.bob, 1)]] * 3 + [[]],
        )
        self.assertEqual(Ownership.objects.count(), 2 + 3 + 2)
        self.assertEqual(MaterialPart.objects.count(), 6 + 2 + 3 + 1)
