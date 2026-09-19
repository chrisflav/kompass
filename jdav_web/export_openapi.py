#!/usr/bin/env python
"""Write the REST API's OpenAPI schema, the input to the frontend's types.

Run it from ``jdav_web/``, then regenerate the typed client::

    python export_openapi.py
    cd ../frontend && npm run gen:api

This is a script rather than a management command on purpose. ``manage.py``
calls ``django.setup()`` before it hands over, and a couple of ``help_text``\\s
interpolate with ``%`` at model-definition time — which resolves their lazy
string as the models are imported, freezing whichever language was active
during setup. No command can undo that afterwards. Deactivating translations
first is the only point early enough, so the export is reproducible down to
the byte whether or not the catalogues happen to be compiled.
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
