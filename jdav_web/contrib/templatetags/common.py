from django import template
from django.conf import settings

register = template.Library()


# settings value
@register.simple_tag
def settings_value(name):
    return getattr(settings, name, "")


@register.simple_tag
def get_external_links():
    from startpage.models import Link

    return Link.objects.filter(visible=True)
