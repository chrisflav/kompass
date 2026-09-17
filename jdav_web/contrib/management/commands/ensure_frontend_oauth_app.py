"""Register the public OAuth2 application the Kompass SPA logs in with.

The SPA is a browser app, so it is a *public* client: it cannot keep a secret,
and it uses Authorization-Code + PKCE. The code it receives is worthless without
the verifier it kept, which is what makes a secretless client safe.

``skip_authorization`` is set because this is a first-party application — asking
our own users to grant our own frontend access to their own data would be a
consent dialog with no decision in it.

Deployments run this once per frontend origin, e.g.::

    python manage.py ensure_frontend_oauth_app \\
        --client-id kompass-spa \\
        --redirect-uri https://neu.jdav-town.de/callback
"""

from django.core.management.base import BaseCommand
from oauth2_provider.models import get_application_model

DEFAULT_CLIENT_ID = "kompass-frontend-dev"
DEFAULT_REDIRECT_URIS = [
    # The Vite dev server, so a checkout works without arguments.
    "http://localhost:5173/callback",
    "http://127.0.0.1:5173/callback",
]


class Command(BaseCommand):
    help = "Create or update the public OAuth2 application the SPA logs in with."

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-id",
            default=DEFAULT_CLIENT_ID,
            help="OAuth2 client id the frontend build is configured with.",
        )
        parser.add_argument(
            "--redirect-uri",
            action="append",
            dest="redirect_uris",
            metavar="URL",
            help=(
                "Allowed redirect URI, normally <frontend-origin>/callback. "
                "Repeat for several; defaults to the local dev server."
            ),
        )
        parser.add_argument(
            "--name",
            default="Kompass Frontend",
            help="Human-readable name shown in the OAuth application list.",
        )

    def handle(self, *args, **options):
        Application = get_application_model()
        client_id = options["client_id"]
        redirect_uris = options["redirect_uris"] or DEFAULT_REDIRECT_URIS

        # Idempotent on purpose: a deployment re-runs this to add the redirect
        # URI of a new frontend origin without disturbing existing tokens.
        app, created = Application.objects.update_or_create(
            client_id=client_id,
            defaults={
                "name": options["name"],
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "client_secret": "",
                "redirect_uris": "\n".join(redirect_uris),
                "skip_authorization": True,
            },
        )
        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                "{} public OAuth2 application '{}' for: {}".format(
                    verb, app.client_id, ", ".join(redirect_uris)
                )
            )
        )
