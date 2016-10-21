from django.contrib import admin
from django import forms

from .models import MaterialPart, MaterialPartForm, Ownership


# Register your models here.
class OwnershipInline(admin.StackedInline):
    """
    This shows the ownership selection directly in the MaterialPart edit
    view
    """
    model = Ownership
    extra = 0


class MaterialAdmin(admin.ModelAdmin):
    """Edit view of a MaterialPart"""

    form = MaterialPartForm
    list_display = ('name', 'buy_date', 'lifetime', 'not_too_old', 'photo')
    inlines = [OwnershipInline]

admin.site.register(MaterialPart, MaterialAdmin)
