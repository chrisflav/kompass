"""
Management command to populate the database with test data.

Usage:
    python manage.py populate_test_data
    python manage.py populate_test_data --force  # Force population even if members exist
"""

import os
import sys

from django.core.management.base import BaseCommand
from django.db import transaction
from members.models import Member
from test_data.populate import populate_test_data


class Command(BaseCommand):
    help = "Populate the database with test data from members CSV and create sample excursions and statements"

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force population even if members already exist',
        )

    def handle(self, *args, **options):
        # Add parent directory to path
        test_data_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        parent_dir = os.path.dirname(test_data_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)

        # Check if members already exist
        if Member.objects.exists() and not options['force']:
            self.stdout.write(
                self.style.WARNING(
                    "Members already exist in the database. Skipping test data population."
                )
            )
            self.stdout.write(
                "Use --force flag to populate test data anyway: python manage.py populate_test_data --force"
            )
            return

        self.stdout.write("Populating database with test data...")
        try:
            with transaction.atomic():
                populate_test_data()

            self.stdout.write(self.style.SUCCESS("Successfully populated database with test data!"))
            self.stdout.write("")
            self.stdout.write("Created or verified:")
            self.stdout.write("  - 5 groups")
            self.stdout.write(
                "  - Members with emergency contacts (from members/test_data/members.csv)"
            )
            self.stdout.write("  - 3 excursions")
            self.stdout.write("  - 2 financial statements with bills")
            self.stdout.write("")
            self.stdout.write("Superuser associated with member: Tobias Werner")
            self.stdout.write("Email: tobias.werner@alpenverein-heidelberg.de")
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("Note: Members are imported from the CSV file."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error populating database: {e}"))
            raise
