from django.contrib import admin

from .models import MaterialPart

# Register your models here.


class MaterialAdmin(admin.ModelAdmin):
    fields = ['name', 'buy_date']
    list_display = ('name', 'buy_date', 'should_be_replaced')

admin.site.register(MaterialPart, MaterialAdmin)
