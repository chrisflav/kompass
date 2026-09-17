from datetime import date
from datetime import datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone
from material.models import MaterialCategory
from material.models import MaterialPart
from material.models import Ownership
from material.models import yearsago
from members.models import FEMALE
from members.models import MALE
from members.models import Member


class MaterialCategoryTestCase(TestCase):
    def setUp(self):
        self.category = MaterialCategory.objects.create(name="Climbing Gear")

    def test_str(self):
        """Test string representation of MaterialCategory"""
        self.assertEqual(str(self.category), "Climbing Gear")

    def test_verbose_names(self):
        """Test verbose names are set correctly"""
        meta = MaterialCategory._meta
        self.assertTrue(hasattr(meta, "verbose_name"))
        self.assertTrue(hasattr(meta, "verbose_name_plural"))


class MaterialPartTestCase(TestCase):
    def setUp(self):
        self.category = MaterialCategory.objects.create(name="Ropes")
        self.material_part = MaterialPart.objects.create(
            name="Dynamic Rope 10mm",
            description="60m dynamic climbing rope",
            quantity=5,
            buy_date=date(2020, 1, 15),
            lifetime=Decimal("8"),
        )
        self.material_part.material_cat.add(self.category)

        self.member = Member.objects.create(
            prename="John",
            lastname="Doe",
            birth_date=date(1990, 1, 1),
            email="john@example.com",
            gender=MALE,
        )

    def test_str(self):
        """Test string representation of MaterialPart"""
        self.assertEqual(str(self.material_part), "Dynamic Rope 10mm")

    def test_quantity_real_no_ownership(self):
        """Test quantity_real when no ownership exists"""
        result = self.material_part.quantity_real()
        self.assertEqual(result, "0/5")

    def test_quantity_real_with_ownership(self):
        """Test quantity_real with ownership records"""
        Ownership.objects.create(material=self.material_part, owner=self.member, count=3)
        Ownership.objects.create(material=self.material_part, owner=self.member, count=1)
        result = self.material_part.quantity_real()
        self.assertEqual(result, "4/5")

    def test_verbose_names(self):
        """Test field verbose names"""
        # Just test that verbose names exist, since they might be translated
        field_names = [
            "name",
            "description",
            "quantity",
            "buy_date",
            "lifetime",
            "photo",
            "material_cat",
        ]

        for field_name in field_names:
            field = self.material_part._meta.get_field(field_name)
            self.assertTrue(hasattr(field, "verbose_name"))
            self.assertIsNotNone(field.verbose_name)

    def test_ownership_overview(self):
        """Test ownership_overview method"""
        Ownership.objects.create(material=self.material_part, owner=self.member, count=2)
        result = self.material_part.ownership_overview()
        self.assertIn(str(self.member), result)
        self.assertIn("2", result)

    def test_not_too_old(self):
        """Test not_too_old method"""
        # Set a buy_date that makes the material old
        old_date = date(2000, 1, 1)
        self.material_part.buy_date = old_date
        self.material_part.lifetime = Decimal("5")
        result = self.material_part.not_too_old()
        self.assertFalse(result)


class OwnershipTestCase(TestCase):
    def setUp(self):
        self.category = MaterialCategory.objects.create(name="Hardware")
        self.material_part = MaterialPart.objects.create(
            name="Carabiner Set",
            description="Lightweight aluminum carabiners",
            quantity=10,
            buy_date=date(2021, 6, 1),
            lifetime=Decimal("10"),
        )

        self.member = Member.objects.create(
            prename="Alice",
            lastname="Smith",
            birth_date=date(1985, 3, 15),
            email="alice@example.com",
            gender=FEMALE,
        )

        self.ownership = Ownership.objects.create(
            material=self.material_part, owner=self.member, count=6
        )

    def test_ownership_creation(self):
        """Test ownership record creation"""
        self.assertEqual(self.ownership.material, self.material_part)
        self.assertEqual(self.ownership.owner, self.member)
        self.assertEqual(self.ownership.count, 6)

    def test_material_part_relationship(self):
        """Test relationship between MaterialPart and Ownership"""
        ownerships = Ownership.objects.filter(material=self.material_part)
        self.assertEqual(ownerships.count(), 1)
        self.assertEqual(ownerships.first(), self.ownership)

    def test_str(self):
        """Test string representation of Ownership"""
        result = str(self.ownership)
        self.assertEqual(result, str(self.member))


class UtilityFunctionTestCase(TestCase):
    def test_yearsago_with_from_date(self):
        """Test yearsago function with explicit from_date"""
        test_date = timezone.make_aware(datetime(2020, 5, 15, 12, 0, 0))
        result = yearsago(5, from_date=test_date)
        expected = timezone.make_aware(datetime(2015, 5, 15, 12, 0, 0))
        self.assertEqual(result, expected)

    def test_yearsago_default_from_date(self):
        """Test yearsago function with default from_date (None)"""
        # This will use timezone.now() internally
        result = yearsago(1)
        self.assertIsNotNone(result)
        self.assertLess(result, timezone.now())

    def test_yearsago_leap_year_edge_case(self):
        """Test yearsago function with leap year edge case (Feb 29)"""
        # Feb 29, 2020 (leap year) minus 1 year should become Feb 28, 2019
        leap_date = timezone.make_aware(datetime(2020, 2, 29, 12, 0, 0))
        result = yearsago(1, from_date=leap_date)
        expected = timezone.make_aware(datetime(2019, 2, 28, 12, 0, 0))
        self.assertEqual(result, expected)
