from django.contrib import admin
from django.conf import settings
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Post, Image, Section, MemberOnPost


class ImageInline(admin.TabularInline):
    model = Image
    extra = 0


class MemberOnPostInline(admin.TabularInline):
    model = MemberOnPost
    extra = 0


class PostForm(forms.ModelForm):
    urlname = forms.RegexField(regex=r'^{pattern}+$'.format(pattern=settings.STARTPAGE_URL_NAME_PATTERN),
                               label=_('URL'),
                               error_messages={'invalid': _('The url may only consist of letters, numerals, _, -, :, * and spaces.')})


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    inlines = [ImageInline, MemberOnPostInline]
    list_display = ['title', 'date', 'section', 'absolute_urlname']
    list_filter = ['section']
    search_fields = ['title']
    form = PostForm


class SectionForm(forms.ModelForm):
    urlname = forms.RegexField(regex=r'^{pattern}+$'.format(pattern=settings.STARTPAGE_URL_NAME_PATTERN),
                               label=_('URL'),
                               error_messages={'invalid': _('The url may only consist of letters, numerals, _, -, :, * and spaces.')})

@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'absolute_urlname']
    form = SectionForm
