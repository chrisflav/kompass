from django.core.management.base import BaseCommand
from members.csv import export_generalized_csv
from members.models import Member


class Command(BaseCommand):
    help = "Export members to a CSV file"

    def add_arguments(self, parser):
        parser.add_argument("csv_file", type=str, help="Path to the CSV file to export to")
        parser.add_argument("--filter", type=str, help="Filter members by group name", default=None)

    def handle(self, *args, **options):
        csv_file_path = options["csv_file"]
        filter_group = options.get("filter")

        try:
            # Get queryset
            queryset = Member.objects.all()
            if filter_group:
                queryset = queryset.filter(group__name=filter_group)

            # Export to CSV
            with open(csv_file_path, "w", encoding="utf-8", newline="") as file:
                export_generalized_csv(queryset, file)

            self.stdout.write(
                self.style.SUCCESS(
                    f"Successfully exported {queryset.count()} members to {csv_file_path}"
                )
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error exporting members: {str(e)}"))
