from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.template import Template, Variable, TemplateSyntaxError

import re

register = template.Library()


class RenderAsTemplateNode(template.Node):
    """
    Renders passed content as template. This is probably dangerous and should only be exposed
    to admins!
    """
    def __init__(self, item_to_be_rendered, var_name):
        self.item_to_be_rendered = Variable(item_to_be_rendered)
        self.var_name = var_name

    def render(self, context):
        try:
            actual_item = self.item_to_be_rendered.resolve(context)
            context[self.var_name] = Template(actual_item).render(context)
            return ""
        except template.VariableDoesNotExist:
            return ''


def render_as_template(parser, token):
    # This version uses a regular expression to parse tag contents.
    try:
        # Splitting by None == splitting by spaces.
        tag_name, arg = token.contents.split(None, 1)
    except ValueError:
        raise template.TemplateSyntaxError(
            "%r tag requires arguments" % token.contents.split()[0]
        )
    m = re.search(r"(.*?) as (\w+)", arg)
    if not m:
        raise template.TemplateSyntaxError("%r tag had invalid arguments" % tag_name)
    format_string, var_name = m.groups()
    if not (format_string[0] == format_string[-1] and format_string[0] in ('"', "'")):
        raise template.TemplateSyntaxError(
            "%r tag's argument should be in quotes" % tag_name
        )
    return RenderAsTemplateNode(format_string[1:-1], var_name)


render_as_template = register.tag(render_as_template)
