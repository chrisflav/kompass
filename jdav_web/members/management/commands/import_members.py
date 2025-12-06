from django.core.management.base import BaseCommand
from members.csv import import_generalized_csv


class Command(BaseCommand):
    help = "Import members from a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file to import")

    def handle(self, *args, **options):
        csv_file_path = options["csv_file"]

        try:
            with open(csv_file_path, encoding="utf-8") as file:
                created_members = import_generalized_csv(file)
                self.stdout.write(
                    self.style.SUCCESS(f"Successfully imported {len(created_members)} members")
                )
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f"File not found: {csv_file_path}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error importing members: {str(e)}"))
