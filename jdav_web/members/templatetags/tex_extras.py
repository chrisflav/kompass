from django import template
from django.utils.safestring import mark_safe
from datetime import timedelta

register = template.Library()

@register.simple_tag
def checked_if_true(name, value):
    if name == value:
        return '\\tickedbox {} \qquad \qquad'.format(name)
    else:
        return '\\checkbox \\enspace \\enspace {} \qquad \qquad'.format(name)

@register.filter
def esc_all(val):
    return mark_safe(str(val).replace('_', '\\_').replace('&', '\\&').replace('%', '\\%'))

@register.filter
def index(sequence, position):
    try:
        return sequence[position]
    except (IndexError, TypeError):
        return ''

@register.filter
def datetime_short(date):
    return date.strftime('%d.%m.%Y %H:%M')


@register.filter
def date_short(date):
    return date.strftime('%d.%m.%y')

@register.filter
def date_vs(date):
    return date.strftime('%d.%m.')

@register.filter
def time_short(date):
    return date.strftime('%H:%M')

@register.filter
def add(date, days):
    if days:
        return date + timedelta(days=days)
    return date

@register.filter
def plus(num1, num2):
    if num2:
        return num1 + num2
    return num1
