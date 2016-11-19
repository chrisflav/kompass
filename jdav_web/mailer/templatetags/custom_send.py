from django import template

register = template.Library()


@register.inclusion_tag('change_form.html')
def custom_send():
    print("CUstom send!")
