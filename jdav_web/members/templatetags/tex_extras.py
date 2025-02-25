from django import template
from django.utils.safestring import mark_safe
from utils import normalize_name

register = template.Library()

@register.simple_tag
def checked_if_true(name, value):
    if name == value:
        return '\\tickedbox {} \qquad \qquad'.format(name)
    else:
        return '\\checkbox \\enspace \\enspace {} \qquad \qquad'.format(name)

@register.filter
def esc_all(val):
    return mark_safe(str(normalize_name(str(val), False, False)).replace('_', '\\_').replace('&', '\\&'))


@register.filter
def datetime_short(date):
    return date.strftime('%d.%m.%Y %H:%M')


@register.filter
def date_short(date):
    return date.strftime('%d.%m.%y')


@register.filter
def time_short(date):
    return date.strftime('%H:%M')
