from django.contrib import admin
from django.utils. translation import ugettext_lazy as translate
from django.contrib.admin import SimpleListFilter

from .models import MaterialPart, Ownership


# Register your models here.
class OwnershipInline(admin.StackedInline):
    """
    This shows the ownership selection directly in the MaterialPart edit
    view
    """
    model = Ownership
    extra = 0


class NotTooOldFilter(SimpleListFilter):
	title = translate('Age')
	parameter_name = 'age'

	def lookups(self, request, model_admin):
		return (
        	('too_old', translate('Not Too Old')),
        	('not_too_old', translate('Too old')),
		)

	def queryset(self, request, queryset):
		if self.value() == 'too_old':
			return queryset.filter(pk__in=[x.pk for x in queryset.all() if x.not_too_old()])
		if self.value() == 'not_too_old':
			return queryset.filter(pk__in=[x.pk for x in queryset.all() if not x.not_too_old()])

                           

class MaterialAdmin(admin.ModelAdmin):
    """Edit view of a MaterialPart"""

    list_display = ('name', 'buy_date', 'lifetime', 'not_too_old', 'photo')
    inlines = [OwnershipInline]
    list_filter = (NotTooOldFilter,)


admin.site.register(MaterialPart, MaterialAdmin)