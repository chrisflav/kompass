from django.contrib import admin

from .models import Post, Image, Section, MemberOnPost


class ImageInline(admin.TabularInline):
    model = Image
    extra = 0


class MemberOnPostInline(admin.TabularInline):
    model = MemberOnPost
    extra = 0


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    inlines = [ImageInline, MemberOnPostInline]
    list_display = ['title', 'date', 'section', 'absolute_urlname']
    list_filter = ['section']
    search_fields = ['title']


@admin.register(Section)
class SectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'absolute_urlname']
