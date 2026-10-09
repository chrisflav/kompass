from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.utils.translation import gettext_lazy as _

from .models import MaterialCategory
from .models import MaterialPart

# from easy_select2 import apply_select2


class MaterialCategoryAdmin(admin.ModelAdmin):
    fields = ["name"]


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
        "owner",
        "buy_date",
        "lifetime",
        "not_too_old",
        "admin_thumbnail",
    )
    search_fields = ("name", "description")
    autocomplete_fields = ["owner"]
    list_filter = (NotTooOldFilter, "material_cat", "owner")
    # formfield_overrides = {
    #    models.ManyToManyField: {'widget': forms.CheckboxSelectMultiple}
    # }


admin.site.register(MaterialCategory, MaterialCategoryAdmin)
admin.site.register(MaterialPart, MaterialAdmin)
