from django import template

register = template.Library()

@register.assignment_tag
def has_attendee_wrapper(klettertreff, member):
    return klettertreff.has_attendee(member)
