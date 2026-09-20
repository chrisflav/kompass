#!/usr/bin/env python
"""Write the REST API's OpenAPI schema, the input to the frontend's types.

Run it from ``jdav_web/``, then regenerate the typed client::

    python export_openapi.py
    cd ../frontend && npm run gen:api

The export is reproducible down to the byte, from a checkout as much as from a
running container. Two things buy that, and neither of them is this script:
``render_schema`` imports the API under ``translation.override(None)``, which
is what keeps the compiled catalogues out of the document (see
``contrib.openapi``), and no model ``help_text`` interpolates a setting any
more — the forms that want to name a domain or a maximum do so themselves.
``contrib.tests.ExportOpenapiTest`` holds both ends down, including that the
committed document is the current one.

The script stays a script, and deactivates translations before
``django.setup()``, as defence in depth: anything a model does resolve while
it is imported is then resolved in the source language, which a management
command could no longer influence.
"""

import argparse
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_OUTPUT = HERE.parent / "frontend" / "openapi.json"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Export the OpenAPI schema.")
    parser.add_argument(
        "--output",
        default=str(DEFAULT_OUTPUT),
        help="Where to write the schema (default: frontend/openapi.json).",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, str(HERE))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "jdav_web.settings")

    from django.utils import translation

    translation.deactivate_all()

    import django

    django.setup()

    from contrib.openapi import render_schema

    output = Path(args.output)
    output.write_text(render_schema() + "\n", encoding="utf-8")
    print(f"Wrote {output} in the source language.")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
