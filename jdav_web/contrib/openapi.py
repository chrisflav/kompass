"""Rendering the REST API's OpenAPI document."""

import json

from django.core.serializers.json import DjangoJSONEncoder
from django.utils import translation


def render_schema():
    """Return the OpenAPI document as JSON text, in the source language.

    Every field's ``verbose_name`` and ``help_text`` reaches the schema as a
    title or description, and those are lazy translations. Left to the ambient
    locale they make the export irreproducible: compiled ``.mo`` files are
    gitignored and built at container start, so the same code exported from a
    fresh checkout and from a running container disagrees on hundreds of
    strings, none of them an intended change.

    Pinning to the source language removes the dependency instead of guarding
    it, and English is the right language for this artifact anyway — a
    machine-readable contract read by developers and fed to a type generator,
    not a page shown to a member.

    Both steps must happen under the override. django-ninja resolves some
    titles to plain strings while building the schema classes on first import,
    and leaves others as lazy proxies that only become text when the encoder
    touches them; dumping outside would resolve that second kind under
    whatever language happened to be active.
    """
    with translation.override(None):
        from jdav_web.api import api

        return json.dumps(
            api.get_openapi_schema(), cls=DjangoJSONEncoder, ensure_ascii=False, indent=2
        )
