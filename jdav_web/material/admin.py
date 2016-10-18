from django.contrib import admin

from .models import MaterialPart, Ownership


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
    fields = ['name', 'buy_date']
    list_display = ('name', 'buy_date', 'should_be_replaced')
    inlines = [OwnershipInline]

admin.site.register(MaterialPart, MaterialAdmin)
