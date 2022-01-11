from django import template

register = template.Library()

def blToColor(bl):
    if bl:
        return 'green'
    else:
        return 'red'

@register.simple_tag
def has_attendee_wrapper(klettertreff, member):
    return blToColor(klettertreff.has_attendee(member))

@register.simple_tag
def has_jugendleiter_wrapper(klettertreff, jugendleiter):
    return blToColor(klettertreff.has_jugendleiter(jugendleiter))
