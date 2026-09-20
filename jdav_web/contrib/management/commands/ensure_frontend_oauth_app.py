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
                "Repeat for several. Added to any already registered; the local "
                "dev defaults are used only when creating the application."
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
        app = Application.objects.filter(client_id=client_id).first()

        # Redirect URIs are ADDED, never replaced: re-running this to register a
        # second frontend origin must not silently unregister the first, and an
        # argument-less run against an existing application must not swap
        # production's URIs for the local development defaults.
        existing = app.redirect_uris.split() if app else []
        supplied = options["redirect_uris"] or ([] if app else DEFAULT_REDIRECT_URIS)
        redirect_uris = existing + [uri for uri in supplied if uri not in existing]

        if app is None:
            app = Application(client_id=client_id)
        app.name = options["name"]
        app.client_type = Application.CLIENT_PUBLIC
        app.authorization_grant_type = Application.GRANT_AUTHORIZATION_CODE
        app.client_secret = ""
        app.redirect_uris = "\n".join(redirect_uris)
        app.skip_authorization = True
        created = app.pk is None
        app.save()

        verb = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                "{} public OAuth2 application '{}' for: {}".format(
                    verb, app.client_id, ", ".join(redirect_uris) or "(no redirect URI)"
                )
            )
        )
