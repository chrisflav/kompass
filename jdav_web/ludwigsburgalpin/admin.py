from django.contrib import admin
from .models import Group, Termin


class GroupAdmin(admin.ModelAdmin):
    list_display = ('name',)


class TerminAdmin(admin.ModelAdmin):
    list_display = ('title','start_date', 'end_date', 'group')

# Register your models here.
admin.site.register(Group, GroupAdmin)
admin.site.register(Termin, TerminAdmin)
