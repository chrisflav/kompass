from django import template
from startpage.models import Link

register = template.Library()


@register.simple_tag
def get_external_links():
    return Link.objects.filter(visible=True)
