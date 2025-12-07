import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Creates a super-user non-interactively if it doesn't exist."

    def handle(self, *args, **options):
        User = get_user_model()

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME", "")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD", "")

        if not username or not password:
            self.stdout.write(self.style.WARNING("Superuser data was not set. Skipping."))
            return

        if not User.objects.filter(username=username).exists():
            User.objects.create_superuser(username=username, password=password)
            self.stdout.write(self.style.SUCCESS("Successfully created superuser."))
        else:
            self.stdout.write(
                self.style.SUCCESS("Superuser with configured username already exists. Skipping.")
            )
