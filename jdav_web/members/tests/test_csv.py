import csv
import os
from io import StringIO

from django.conf import settings
from django.test import TestCase
from members.csv import export_generalized_csv
from members.csv import import_generalized_csv
from members.models import EmergencyContact
from members.models import Group
from members.models import Member


class CSVRoundtripTestCase(TestCase):
    """Test CSV import/export using the actual test data file"""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.test_csv_path = os.path.join(settings.BASE_DIR, "test_data", "members.csv")

    def test_csv_file_exists(self):
        """Verify the test CSV file exists"""
        self.assertTrue(
            os.path.exists(self.test_csv_path),
            f"Test CSV file not found at {self.test_csv_path}",
        )

    def test_roundtrip_csv_equality(self):
        """Test that importing and exporting produces identical CSV"""
        # Read original CSV
        with open(self.test_csv_path, encoding="utf-8") as f:
            _ = f.read()
            f.seek(0)
            original_rows = list(csv.DictReader(f))

        # Import from original CSV
        with open(self.test_csv_path, encoding="utf-8") as f:
            created_members = import_generalized_csv(f)

        self.assertEqual(len(created_members), 30, "Should import 30 members")

        # Export to new CSV
        export_buffer = StringIO()
        export_generalized_csv(Member.objects.all().order_by("pk"), export_buffer)

        # Read exported CSV
        export_buffer.seek(0)
        exported_rows = list(csv.DictReader(export_buffer))

        # Compare row counts
        self.assertEqual(
            len(original_rows),
            len(exported_rows),
            "Exported CSV should have same number of rows as original",
        )

        # Compare each row
        for i, (original_row, exported_row) in enumerate(zip(original_rows, exported_rows)):
            # Compare all fields except 'id' which may differ
            for field in original_row.keys():
                if field == "id":
                    continue

                original_value = original_row[field].strip()
                exported_value = exported_row[field].strip()

                self.assertEqual(
                    original_value,
                    exported_value,
                    f"Row {i}, field '{field}' differs:\n"
                    f"  Original: {original_value}\n"
                    f"  Exported: {exported_value}",
                )

    def test_data_integrity_after_import(self):
        """Verify data integrity after import"""
        with open(self.test_csv_path, encoding="utf-8") as f:
            import_generalized_csv(f)

        # Check member count
        self.assertEqual(Member.objects.count(), 30)

        # Check group count
        expected_groups = {
            "Alpingruppe",
            "Klettergruppe",
            "Spielgruppe",
            "Jugendausschuss",
            "Jugendleiter",
        }
        actual_groups = set(Group.objects.values_list("name", flat=True))
        self.assertTrue(expected_groups.issubset(actual_groups))

        # Check emergency contacts were created
        total_emergency_contacts = EmergencyContact.objects.count()
        self.assertGreater(total_emergency_contacts, 0, "Should have emergency contacts")

        # Spot check a specific member
        emma = Member.objects.get(prename="Emma", lastname="Bergmann")
        self.assertEqual(emma.dav_badge_no, "114/00/245891")
        self.assertEqual(emma.emergencycontact_set.count(), 2)
        self.assertTrue(emma.swimming_badge)
