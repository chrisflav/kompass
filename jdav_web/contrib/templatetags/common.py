from django import template
from django.conf import settings

register = template.Library()


# settings value
@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")


_DOCUMENTATION_URL_PREFIX = "/static/docs/"


@register.simple_tag(takes_context=True)
def get_documentation_url(context):
    url = context.get("documentation_url")
    if not url:
        request = context.get("request")
        if request:
            url = getattr(request, "documentation_url", None)
    if url:
        return _DOCUMENTATION_URL_PREFIX + url
    return ""
