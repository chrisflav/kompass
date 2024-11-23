from django.utils.translation import gettext_lazy as _
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseAuthGroupAdmin
from django.contrib.auth.models import User as BaseUser, Group as BaseAuthGroup
from .models import AuthGroup, LoginDatum, RegistrationPassword
from members.models import Member

# Register your models here.
class AuthGroupAdmin(BaseAuthGroupAdmin):
    pass


class UserInline(admin.StackedInline):
    model = Member
    can_delete = False
    verbose_name_plural = "member"


class LoginDatumAdmin(BaseUserAdmin):
    list_display = ('username', 'is_superuser')
    #inlines = [UserInline]
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )

admin.site.unregister(BaseUser)
admin.site.unregister(BaseAuthGroup)
admin.site.register(LoginDatum, LoginDatumAdmin)
admin.site.register(AuthGroup, AuthGroupAdmin)
admin.site.register(RegistrationPassword)
