from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _

from .models import MaterialCategory
from .models import MaterialPart
from .models import Ownership

# from easy_select2 import apply_select2


class MaterialCategoryAdmin(admin.ModelAdmin):
    fields = ["name"]


# Register your models here.
class OwnershipInline(admin.TabularInline):
    """
    This shows the ownership selection directly in the MaterialPart edit
    view
    """

    model = Ownership
    extra = 0
    # formfield_overrides = {
    #    models.ForeignKey: {'widget': apply_select2(forms.Select)}
    # }


class NotTooOldFilter(SimpleListFilter):
    title = _("Age")
    parameter_name = "age"

    def lookups(self, request, model_admin):
        return (
            ("too_old", _("Not too old")),
            ("not_too_old", _("Too old")),
        )

    def queryset(self, request, queryset):
        if self.value() == "too_old":
            return queryset.filter(pk__in=[x.pk for x in queryset.all() if x.not_too_old()])
        if self.value() == "not_too_old":
            return queryset.filter(pk__in=[x.pk for x in queryset.all() if not x.not_too_old()])


class MaterialAdmin(admin.ModelAdmin):
    """Edit view of a MaterialPart"""

    list_display = (
        "name",
        "description",
        "quantity_real",
        "ownership_overview",
        "buy_date",
        "lifetime",
        "not_too_old",
        "admin_thumbnail",
    )
    search_fields = ("name", "description")
    inlines = [OwnershipInline]
    list_filter = (NotTooOldFilter, "material_cat", "ownership__owner")
    # formfield_overrides = {
    #    models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    # }


admin.site.register(MaterialCategory, MaterialCategoryAdmin)
admin.site.register(MaterialPart, MaterialAdmin)
