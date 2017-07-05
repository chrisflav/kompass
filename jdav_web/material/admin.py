from django.contrib import admin
from django.utils.translation import ugettext_lazy as _
from django.contrib.admin import SimpleListFilter
from django.db import models
from django import forms

from .models import MaterialPart, Ownership
from easy_select2 import apply_select2


# Register your models here.
class OwnershipInline(admin.StackedInline):
    """
    This shows the ownership selection directly in the MaterialPart edit
    view
    """
    model = Ownership
    extra = 0
    formfield_overrides = {
        models.ForeignKey: {'widget': apply_select2(forms.Select)}
    }


class NotTooOldFilter(SimpleListFilter):
	title = _('Age')
	parameter_name = 'age'

	def lookups(self, request, model_admin):
		return (
        	('too_old', _('Not too old')),
        	('not_too_old', _('Too old')),
		)

	def queryset(self, request, queryset):
		if self.value() == 'too_old':
			return queryset.filter(pk__in=[x.pk for x in queryset.all() if x.not_too_old()])
		if self.value() == 'not_too_old':
			return queryset.filter(pk__in=[x.pk for x in queryset.all() if not x.not_too_old()])



class MaterialAdmin(admin.ModelAdmin):
    """Edit view of a MaterialPart"""

    list_display = ('name', 'description', 'quantity_real', 'buy_date',
                    'lifetime', 'not_too_old', 'admin_thumbnail')
    inlines = [OwnershipInline]
    list_filter = (NotTooOldFilter,)


admin.site.register(MaterialPart, MaterialAdmin)
