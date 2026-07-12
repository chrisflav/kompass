"""Create the public OAuth2 application the frontend prototype logs in with.

Uses the Resource-Owner-Password-Credentials grant against ``/o/token/`` with a
public client (no secret) — appropriate for the first-party dev prototype. The
production SPA should use Authorization-Code + PKCE instead.
"""

from django.core.management.base import BaseCommand
from oauth2_provider.models import get_application_model

CLIENT_ID = "kompass-frontend-dev"


class Command(BaseCommand):
    help = "Create the public 'kompass-frontend-dev' OAuth2 application if missing."

    def handle(self, *args, **options):
        Application = get_application_model()
        if Application.objects.filter(client_id=CLIENT_ID).exists():
            self.stdout.write(
                self.style.SUCCESS("Frontend OAuth2 application already exists. Skipping.")
            )
            return

        Application.objects.create(
            client_id=CLIENT_ID,
            name="Kompass Frontend (dev)",
            client_type=Application.CLIENT_PUBLIC,
            authorization_grant_type=Application.GRANT_PASSWORD,
            client_secret="",
        )
        self.stdout.write(
            self.style.SUCCESS("Created public OAuth2 application '{}'.".format(CLIENT_ID))
        )
