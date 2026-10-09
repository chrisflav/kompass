from datetime import date
from datetime import datetime
from decimal import Decimal
from unittest.mock import Mock

from django.contrib.auth.models import User
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from material.admin import MaterialAdmin
from material.admin import NotTooOldFilter
from material.models import MaterialCategory
from material.models import MaterialPart
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

    def test_verbose_names(self):
        """Test field verbose names"""
        # Just test that verbose names exist, since they might be translated
        field_names = [
            "name",
            "description",
            "buy_date",
            "lifetime",
            "photo",
            "material_cat",
            "owner",
        ]

        for field_name in field_names:
            field = self.material_part._meta.get_field(field_name)
            self.assertTrue(hasattr(field, "verbose_name"))
            self.assertIsNotNone(field.verbose_name)

    def test_admin_thumbnail_with_photo(self):
        """Test admin_thumbnail when photo exists"""
        mock_photo = Mock()
        mock_photo.url = "/media/test.jpg"
        self.material_part.photo = mock_photo
        result = self.material_part.admin_thumbnail()
        self.assertIn("/media/test.jpg", result)
        self.assertIn("<img", result)

    def test_admin_thumbnail_without_photo(self):
        """Test admin_thumbnail when no photo exists"""
        self.material_part.photo = None
        result = self.material_part.admin_thumbnail()
        self.assertIn("kein Bild", result)

    def test_not_too_old(self):
        """Test not_too_old method"""
        # Set a buy_date that makes the material old
        old_date = date(2000, 1, 1)
        self.material_part.buy_date = old_date
        self.material_part.lifetime = Decimal("5")
        result = self.material_part.not_too_old()
        self.assertFalse(result)


class OwnerTestCase(TestCase):
    def setUp(self):
        self.material_part = MaterialPart.objects.create(
            name="Carabiner",
            description="Lightweight aluminum carabiner",
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

    def test_owner_is_optional(self):
        """A piece does not need an owner"""
        self.assertIsNone(self.material_part.owner)

    def test_owner(self):
        """A piece has at most one owner"""
        self.material_part.owner = self.member
        self.material_part.save()
        self.material_part.refresh_from_db()
        self.assertEqual(self.material_part.owner, self.member)
        self.assertEqual(list(self.member.materialpart_set.all()), [self.material_part])

    def test_deleting_the_owner_keeps_the_piece(self):
        """Deleting the owning member leaves the piece without an owner"""
        self.material_part.owner = self.member
        self.material_part.save()
        self.member.delete()
        self.material_part.refresh_from_db()
        self.assertIsNone(self.material_part.owner)

    def test_admin_shows_and_filters_by_owner(self):
        """The admin lists the owner, filters by it and edits it"""
        self.material_part.owner = self.member
        self.material_part.save()
        User.objects.create_superuser(username="superuser", password="secret")
        self.client.login(username="superuser", password="secret")

        url = reverse("admin:material_materialpart_changelist")
        response = self.client.get(url, {"owner__id__exact": self.member.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Carabiner")
        self.assertContains(response, str(self.member))

        url = reverse("admin:material_materialpart_change", args=[self.material_part.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'name="owner"')


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


class NotTooOldFilterTestCase(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.filter = NotTooOldFilter(None, {}, MaterialPart, MaterialAdmin)

        # Create test data
        self.member = Member.objects.create(
            prename="Test",
            lastname="User",
            birth_date=date(1990, 1, 1),
            email="test@example.com",
            gender=MALE,
        )

        # Create old material (should be too old)
        self.old_material = MaterialPart.objects.create(
            name="Old Material",
            description="Old material",
            buy_date=date(2000, 1, 1),  # Very old
            lifetime=Decimal("5"),
        )

        # Create new material (should not be too old)
        self.new_material = MaterialPart.objects.create(
            name="New Material",
            description="New material",
            buy_date=date.today(),  # Today
            lifetime=Decimal("10"),
        )

    def test_not_too_old_filter_lookups(self):
        """Test NotTooOldFilter lookups method"""
        request = self.factory.get("/")
        lookups = self.filter.lookups(request, None)
        self.assertEqual(len(lookups), 2)
        self.assertEqual(lookups[0][0], "too_old")
        self.assertEqual(lookups[1][0], "not_too_old")

    def test_not_too_old_filter_queryset_too_old(self):
        """Test NotTooOldFilter queryset method with 'too_old' value"""
        request = self.factory.get("/?age=too_old")
        self.filter.used_parameters = {"age": "too_old"}

        queryset = MaterialPart.objects.all()
        filtered = self.filter.queryset(request, queryset)

        # Should return materials that are not too old (i.e., new materials)
        self.assertIn(self.new_material, filtered)
        self.assertNotIn(self.old_material, filtered)

    def test_not_too_old_filter_queryset_not_too_old(self):
        """Test NotTooOldFilter queryset method with 'not_too_old' value"""
        request = self.factory.get("/?age=not_too_old")
        self.filter.used_parameters = {"age": "not_too_old"}

        queryset = MaterialPart.objects.all()
        filtered = self.filter.queryset(request, queryset)

        # Should return materials that are too old
        self.assertIn(self.old_material, filtered)
        self.assertNotIn(self.new_material, filtered)
