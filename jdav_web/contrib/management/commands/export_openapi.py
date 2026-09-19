"""Export the REST API's OpenAPI schema, the input to the frontend's types.

Run this whenever the API changes, then regenerate the typed client::

    python manage.py export_openapi
    cd frontend && npm run gen:api

The schema embeds every field's ``verbose_name`` and ``help_text`` as a title
and description, and those are lazy translations. They are resolved once, when
django-ninja builds the schema classes — so the export captures whatever
language was active and whatever catalogues were readable at that moment.

That is easy to get wrong in a way nothing complains about. Compiled ``.mo``
files are gitignored and built at container start, so exporting from a fresh
checkout (or from an image whose source tree has been mounted over, which hides
them) silently falls back to the msgids and writes an English schema over a
German one — a diff of hundreds of titles, none of them an intended change.

So this command pins the language to ``LANGUAGE_CODE`` and refuses to run at
all when the catalogues behind it are missing, rather than producing a
plausible-looking file. Run ``manage.py compilemessages --locale de`` first.
"""

import json
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management.base import CommandError
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import translation

DEFAULT_OUTPUT = Path(settings.BASE_DIR).parent / "frontend" / "openapi.json"


def uncompiled_catalogues(language):
    """Locale directories holding a ``.po`` for ``language`` but no ``.mo``.

    Only this project's own apps are checked: a dependency shipping an
    uncompiled catalogue is not something an export can or should fix.
    """
    base = Path(settings.BASE_DIR)
    # LOCALE_PATHS entries are locale directories already; an app contributes
    # one at <app>/locale.
    locale_dirs = [Path(path) for path in settings.LOCALE_PATHS]
    locale_dirs += [
        Path(config.path) / "locale"
        for config in apps.get_app_configs()
        if Path(config.path) == base or base in Path(config.path).parents
    ]
    missing = set()
    for locale_dir in locale_dirs:
        messages = locale_dir / language / "LC_MESSAGES"
        if (messages / "django.po").exists() and not (messages / "django.mo").exists():
            missing.add(messages)
    return sorted(missing)


class Command(BaseCommand):
    help = "Write the OpenAPI schema for the REST API to frontend/openapi.json."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(DEFAULT_OUTPUT),
            help="Where to write the schema (default: frontend/openapi.json).",
        )

    def handle(self, *args, **options):
        language = settings.LANGUAGE_CODE
        missing = uncompiled_catalogues(language)
        if missing:
            raise CommandError(
                "Translations for '{}' are not compiled, so the schema would be "
                "written in the source language. Run `manage.py compilemessages "
                "--locale {}` first. Missing .mo in:\n  {}".format(
                    language, language, "\n  ".join(str(path) for path in missing)
                )
            )

        with translation.override(language):
            # Imported inside the override: django-ninja resolves the titles
            # while building the schema classes, which happens on first import.
            from jdav_web.api import api

            schema = api.get_openapi_schema()

        output = Path(options["output"])
        output.write_text(
            json.dumps(schema, cls=DjangoJSONEncoder, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.stdout.write(self.style.SUCCESS(f"Wrote {output} in '{language}'."))
