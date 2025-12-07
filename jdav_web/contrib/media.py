import os
from wsgiref.util import FileWrapper

from django import template
from django.conf import settings
from django.http import HttpResponse


def find_template(template_name):
    for engine in template.engines.all():
        for loader in engine.engine.template_loaders:
            for origin in loader.get_template_sources(template_name):
                if os.path.exists(origin.name):
                    return origin.name
    raise template.TemplateDoesNotExist(f"Could not find template: {template_name}")


def media_path(fp):
    return os.path.join(os.path.join(settings.MEDIA_ROOT, "memberlists"), fp)


def media_dir():
    return os.path.join(settings.MEDIA_ROOT, "memberlists")


def serve_media(filename, content_type):
    """
    Serve the media file with the given `filename` as an HTTP response.
    """
    with open(media_path(filename), "rb") as f:
        response = HttpResponse(FileWrapper(f))
        response["Content-Type"] = content_type
        # download other files than pdf, show pdfs in the browser
        response["Content-Disposition"] = (
            "filename=" + filename
            if content_type == "application/pdf"
            else "attachment; filename=" + filename
        )

    return response


def ensure_media_dir():
    if not os.path.exists(media_dir()):
        os.makedirs(media_dir())
