from django import template
from django.utils.html import format_html

register = template.Library()


def blToColor(bl):
    if bl:
        return "green"
    else:
        return "red"


@register.simple_tag
def has_attendee_wrapper(klettertreff, member):
    return blToColor(klettertreff.has_attendee(member))


@register.simple_tag
def has_jugendleiter_wrapper(klettertreff, jugendleiter):
    return blToColor(klettertreff.has_jugendleiter(jugendleiter))


@register.filter
def render_bool(boolean_value):
    if not isinstance(boolean_value, bool):
        raise ValueError(
            f"""Custom Filter 'render_bool': Supplied value '{boolean_value}' is not bool, but {type(boolean_value)}."""
        )

    if boolean_value:  # True is a green tick
        color = "#bcd386"
        htmlclass = "icon-tick"
    else:  # False is a red cross
        color = "#dba4a4"
        htmlclass = "icon-cross"

    return format_html(f"""<span style="font-weight: bold; color: {color};"
    class="{htmlclass}"></span>""")
