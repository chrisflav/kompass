from django.shortcuts import redirect, get_object_or_404
from django import shortcuts
from django.conf import settings
from django.urls import reverse
from django.http import HttpResponseNotFound, Http404
from itertools import chain

from members.models import Group
from .models import Post, Section


# render shortcut adding additional context variables, needed for navbar
def render(request, template_path, context={}):
    context['groups'] = Group.objects.filter(show_website=True)
    context['sections'] = Section.objects.all()
    return shortcuts.render(request, template_path, context)


def index(request):
    context = {
        'posts': Post.objects.filter(section=None)
    }
    return render(request, 'startpage/index.html', context)


# static view factory
def static_view(template_path):
    def view(request):
        return render(request, template_path)
    return view


def jugendleiterinnen(request):
    group = get_object_or_404(Group, name='Jugendleiter')
    people = group.member_set.all()
    context = {
        'people': people
    }
    return render(request, 'startpage/jugendleiterinnen.html', context)


def gruppe_detail(request, group_name):
    try:
        group = Group.objects.get(name=group_name)
    except Group.DoesNotExist:
        raise Http404
    if not group.show_website:
        raise Http404

    context = {
        'group': group,
        'people': group.leiters.all(),
    }
    return render(request, 'startpage/gruppen/detail.html', context)


def aktuelles(request):
    posts = Post.objects.filter(section=None)
    context = {
        'posts': posts,
    }
    return render(request, 'startpage/aktuelles.html', context)


def post(request, section_name, post_name):
    if section_name == 'aktuelles':
        section = None
    else:
        section = get_object_or_404(Section, urlname=section_name)
    post = get_object_or_404(Post, section=section, urlname=post_name)
    context = {
        'post': post,
        'section': section,
        'people': [m for group in post.groups.all() for m in group.member_set.all()],
    }
    return render(request, 'startpage/post.html', context)


def section(request, section_name):
    assert section_name != 'aktuelles'
    section = get_object_or_404(Section, urlname=section_name)
    context = {
        'section': section,
    }
    return render(request, 'startpage/section.html', context)


def handler404(request, exception):
    response = render(request, 'startpage/404.html')
    response.status_code = 404
    return response


def handler500(request):
    response = render(request, 'startpage/500.html')
    response.status_code = 500
    return response
