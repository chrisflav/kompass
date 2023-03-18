from django import template
from django.utils.safestring import mark_safe

register = template.Library()

@register.simple_tag
def checked_if_true(name, value):
    if name == value:
        return '\\tickedbox {} \qquad \qquad'.format(name)
    else:
        return '\\checkbox \\enspace \\enspace {} \qquad \qquad'.format(name)

@register.filter
def esc_all(val):
    return mark_safe(str(val).replace('_', '\\_').replace('&', '\\&'))


@register.filter
def datetime_short(date):
    return date.strftime('%d.%m.%Y %H:%M')
