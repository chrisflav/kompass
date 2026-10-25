from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as BaseAuthGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group as BaseAuthGroup
from django.contrib.auth.models import Permission
from django.contrib.auth.models import User as BaseUser
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from members.models import Member

from .models import AuthGroup
from .models import LoginDatum
from .models import RegistrationPassword
from .rights import account_refusal
from .rights import MISSING_PERMISSIONS
from .rights import missing_permissions


def _check_granted(form, request, field, permissions):
    """Add an error to ``field`` for every permission the caller cannot grant."""
    missing = missing_permissions(request.user, permissions)
    if missing:
        form.add_error(
            field, ValidationError(MISSING_PERMISSIONS % {"permissions": ", ".join(missing)})
        )


class AuthGroupAdmin(BaseAuthGroupAdmin):
    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)

        class Form(base):
            def clean(self):
                cleaned = super().clean()
                if "permissions" in cleaned:
                    added = cleaned["permissions"]
                    if self.instance.pk:
                        added = added.exclude(group=self.instance)
                    _check_granted(self, request, "permissions", added)
                return cleaned

        return Form


class UserInline(admin.StackedInline):
    model = Member
    can_delete = False
    verbose_name_plural = "member"


class LoginDatumAdmin(BaseUserAdmin):
    list_display = ("username", "is_superuser")
    # inlines = [UserInline]
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
    superuser_only_fields = ("is_superuser", "user_permissions")
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("username", "password1", "password2"),
            },
        ),
    )

    # Only a superuser may make anyone one, or hand out a single permission;
    # an account holding rights the caller lacks is theirs to look at only.

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        if request.user.is_superuser:
            return fields
        return tuple(fields) + self.superuser_only_fields

    def has_change_permission(self, request, obj=None):
        if obj is not None and account_refusal(request.user, obj):
            return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        # Also what the changelist's bulk delete asks of every selected account.
        if obj is not None and account_refusal(request.user, obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_form(self, request, obj=None, **kwargs):
        base = super().get_form(request, obj, **kwargs)

        class Form(base):
            def clean(self):
                cleaned = super().clean()
                # The account's own groups need no exception: had it any
                # permission the caller lacks, it could not be changed at all.
                if "groups" in cleaned:
                    _check_granted(
                        self,
                        request,
                        "groups",
                        Permission.objects.filter(group__in=cleaned["groups"]),
                    )
                return cleaned

        return Form


admin.site.unregister(BaseUser)
admin.site.unregister(BaseAuthGroup)
admin.site.register(LoginDatum, LoginDatumAdmin)
admin.site.register(AuthGroup, AuthGroupAdmin)
admin.site.register(RegistrationPassword)
