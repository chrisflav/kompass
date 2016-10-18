from django.contrib import admin

from .models import Member, Group


# Register your models here.
class MemberAdmin(admin.ModelAdmin):
    fields = ['prename', 'lastname', 'email', 'birth_date', 'group']
    list_display = ('name', 'birth_date')


class GroupAdmin(admin.ModelAdmin):
    fields = ['name', 'min_age']
    list_display = ('name', 'min_age')


admin.site.register(Member, MemberAdmin)
admin.site.register(Group, GroupAdmin)
