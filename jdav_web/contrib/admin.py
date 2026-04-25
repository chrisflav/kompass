import copy
from dataclasses import dataclass
from dataclasses import field
from functools import update_wrapper
from typing import Callable
from typing import Union

from django.contrib import messages
from django.contrib.auth import get_permission_codename
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpResponseRedirect
from django.urls import path
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from rules.permissions import perm_exists


@dataclass
class ExtraButton:
    """Represents an extra button in the admin change form object tools."""

    view_name: str
    label: str
    url_name: str = None
    permission: Union[str, Callable] = None
    condition: Callable = None
    method: str = "GET"
    css_class: str = "historylink"
    target: str = None
    dynamic_label: Callable = field(default=None)
    include_redirect: bool = False
    model: type = None  # Optional proxy model for fetching the object

    def __post_init__(self):
        if self.url_name is None:
            # Strip _view suffix if present for cleaner URLs
            self.url_name = self.view_name.removesuffix("_view")


def extra_button(label, **kwargs):
    """Decorator to mark a method as an extra button handler."""

    def decorator(func):
        func._extra_button = ExtraButton(view_name=func.__name__, label=label, **kwargs)
        return func

    return decorator


class ExtraButtonsMixin:
    """
    Mixin that provides a declarative way to add extra buttons to admin change views.

    Usage:
        class MyAdmin(ExtraButtonsMixin, admin.ModelAdmin):

            @extra_button(_("My Action"), permission="myapp.my_permission")
            def my_action_view(self, request, obj):
                # obj is already fetched and permission-checked
                ...
    """

    extra_buttons_model = None

    def _get_extra_button_definitions(self):
        """Collect all ExtraButton definitions from decorated methods."""
        buttons = []
        # Iterate through class hierarchy to find methods with _extra_button
        # This avoids using getattr which can trigger property accessors like 'urls'
        for cls in type(self).__mro__:
            for name, attr in vars(cls).items():
                if name.startswith("_"):
                    continue
                if hasattr(attr, "_extra_button"):
                    buttons.append(attr._extra_button)
        return buttons

    def _check_button_permission(self, button, request, obj):
        """Check if the user has permission to see/use this button."""
        if button.permission is None:
            return self.has_change_permission(request, obj)
        if callable(button.permission):
            return button.permission(request, obj)
        return request.user.has_perm(button.permission)

    def _check_button_condition(self, button, obj):
        """Check if the button's condition is met."""
        if button.condition is None:
            return True
        return button.condition(obj)

    def get_extra_buttons(self, request, obj):
        """Return list of buttons to display for the given object."""
        buttons = []
        for button in self._get_extra_button_definitions():
            if not self._check_button_permission(button, request, obj):
                continue
            if not self._check_button_condition(button, obj):
                continue

            url = reverse(
                "admin:{}_{}_{}".format(self.opts.app_label, self.opts.model_name, button.url_name),
                args=(obj.pk,),
            )

            if button.include_redirect:
                url = "javascript:requestWithCurrentURL('{}')".format(url)

            label = button.label
            if button.dynamic_label:
                label = button.dynamic_label(obj)

            buttons.append(
                {
                    "url": url,
                    "label": label,
                    "method": button.method,
                    "css_class": button.css_class,
                    "target": button.target,
                    "include_redirect": button.include_redirect,
                }
            )
        return buttons

    def change_view(self, request, object_id, form_url="", extra_context=None):
        extra_context = extra_context or {}
        try:
            obj = self.model.objects.get(pk=object_id)
            extra_context["extra_buttons"] = self.get_extra_buttons(request, obj)
        except self.model.DoesNotExist:
            extra_context["extra_buttons"] = []
        return super().change_view(request, object_id, form_url, extra_context)

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = []
        for button in self._get_extra_button_definitions():
            view_method = getattr(self, button.view_name)
            wrapped_view = self._wrap_extra_button_view(view_method, button)
            custom_urls.append(
                path(
                    "<path:object_id>/{}/".format(button.url_name),
                    wrap(wrapped_view),
                    name="{}_{}_{}".format(
                        self.opts.app_label, self.opts.model_name, button.url_name
                    ),
                )
            )
        return custom_urls + urls

    def _wrap_extra_button_view(self, view_method, button):
        """Wrap a view method to fetch the object and check permissions."""
        # Use per-button model if specified, otherwise class-level or default
        model = button.model or self.extra_buttons_model or self.model

        def wrapped_view(request, object_id):
            try:
                obj = model.objects.get(pk=object_id)
            except model.DoesNotExist:
                messages.error(
                    request, _("%(modelname)s not found.") % {"modelname": self.opts.verbose_name}
                )
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name)
                    )
                )

            if not self._check_button_permission(button, request, obj):
                messages.error(request, _("Insufficient permissions."))
                return HttpResponseRedirect(
                    reverse(
                        "admin:{}_{}_changelist".format(self.opts.app_label, self.opts.model_name)
                    )
                )

            return view_method(request, obj)

        return wrapped_view


class FieldPermissionsAdminMixin:
    field_change_permissions = {}
    field_view_permissions = {}

    def may_view_field(self, field_desc, request, obj=None):
        if type(field_desc) is not tuple:
            field_desc = (field_desc,)
        for fd in field_desc:
            if fd not in self.field_view_permissions:
                continue
            if not request.user.has_perm(self.field_view_permissions[fd]):
                return False
        return True

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)
        d = []
        for title, attrs in fieldsets:
            allowed = [f for f in attrs["fields"] if self.may_view_field(f, request, obj)]
            if len(allowed) == 0:
                continue
            d.append((title, dict(attrs, **{"fields": allowed})))
        return d

    def get_fields(self, request, obj=None):
        fields = super().get_fields(request, obj)
        return [fd for fd in fields if self.may_view_field(fd, request, obj)]

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super().get_readonly_fields(request, obj)
        return list(readonly_fields) + [
            fd
            for fd, perm in self.field_change_permissions.items()
            if not request.user.has_perm(perm)
        ]


class ChangeViewAdminMixin:
    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            return super().change_view(
                request, object_id, form_url=form_url, extra_context=extra_context
            )
        except PermissionDenied:
            opts = self.opts
            obj = self.model.objects.get(pk=object_id)
            messages.error(request, _("You are not allowed to view %(name)s.") % {"name": str(obj)})
            return HttpResponseRedirect(
                reverse("admin:{}_{}_changelist".format(opts.app_label, opts.model_name))
            )


class FilteredQuerysetAdminMixin:
    def get_queryset(self, request):
        """
        Return a QuerySet of all model instances that can be edited by the
        admin site. This is used by changelist_view.
        """
        qs = self.model._default_manager.get_queryset()
        ordering = self.get_ordering(request)
        if ordering:
            qs = qs.order_by(*ordering)
        queryset = qs
        list_global_perm = "{}.list_global_{}".format(self.opts.app_label, self.opts.model_name)
        if request.user.has_perm(list_global_perm):
            view_global_perm = "{}.view_global_{}".format(self.opts.app_label, self.opts.model_name)
            if request.user.has_perm(view_global_perm):
                return queryset
            if hasattr(request.user, "member"):
                return request.user.member.annotate_view_permission(queryset, model=self.model)
            return queryset.annotate(_viewable=models.Value(False))

        if not hasattr(request.user, "member"):
            return self.model.objects.none()

        return request.user.member.filter_queryset_by_permissions(
            queryset, annotate=True, model=self.model
        )


# class ObjectPermissionsInlineModelAdminMixin(rules.contrib.admin.ObjectPermissionsInlineModelAdminMixin):


class CommonAdminMixin(
    FieldPermissionsAdminMixin, ChangeViewAdminMixin, FilteredQuerysetAdminMixin
):
    def has_add_permission(self, request, obj=None):
        assert obj is None
        opts = self.opts
        codename = get_permission_codename("add_global", opts)
        perm = "{}.{}".format(opts.app_label, codename)
        return request.user.has_perm(perm, obj)

    def has_view_permission(self, request, obj=None):
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("view", opts)
        else:
            codename = get_permission_codename("view_obj", opts)
        perm = "{}.{}".format(opts.app_label, codename)
        if perm_exists(perm):
            return request.user.has_perm(perm, obj)
        else:
            return self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("view", opts)
        else:
            codename = get_permission_codename("change_obj", opts)
        return request.user.has_perm("{}.{}".format(opts.app_label, codename), obj)

    def has_delete_permission(self, request, obj=None):
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("delete_global", opts)
        else:
            codename = get_permission_codename("delete_obj", opts)
        return request.user.has_perm("{}.{}".format(opts.app_label, codename), obj)

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        """
        COPIED from django to disable related actions

        Hook for specifying the form Field instance for a given database Field
        instance.

        If kwargs are given, they're passed to the form Field's constructor.
        """
        # If the field specifies choices, we don't need to look for special
        # admin widgets - we just need to use a select widget of some kind.
        if db_field.choices:
            return self.formfield_for_choice_field(db_field, request, **kwargs)

        # ForeignKey or ManyToManyFields
        if isinstance(db_field, (models.ForeignKey, models.ManyToManyField)):
            # Combine the field kwargs with any options for formfield_overrides.
            # Make sure the passed in **kwargs override anything in
            # formfield_overrides because **kwargs is more specific, and should
            # always win.
            if db_field.__class__ in self.formfield_overrides:
                kwargs = {**self.formfield_overrides[db_field.__class__], **kwargs}

            # Get the correct formfield.
            if isinstance(db_field, models.ForeignKey):
                formfield = self.formfield_for_foreignkey(db_field, request, **kwargs)
            elif isinstance(db_field, models.ManyToManyField):
                formfield = self.formfield_for_manytomany(db_field, request, **kwargs)

            # For non-raw_id fields, wrap the widget with a wrapper that adds
            # extra HTML -- the "add other" interface -- to the end of the
            # rendered output. formfield can be None if it came from a
            # OneToOneField with parent_link=True or a M2M intermediary.
            # if formfield and db_field.name not in self.raw_id_fields:
            #    formfield.widget = widgets.RelatedFieldWidgetWrapper(
            #        formfield.widget,
            #        db_field.remote_field,
            #        self.admin_site,
            #    )

            return formfield

        # If we've got overrides for the formfield defined, use 'em. **kwargs
        # passed to formfield_for_dbfield override the defaults.
        for klass in db_field.__class__.mro():
            if klass in self.formfield_overrides:
                kwargs = {**copy.deepcopy(self.formfield_overrides[klass]), **kwargs}
                return db_field.formfield(**kwargs)

        # For any other type of field, just call its formfield() method.
        return db_field.formfield(**kwargs)


class CommonAdminInlineMixin(CommonAdminMixin):
    def has_add_permission(self, request, obj):
        # assert obj is not None
        if obj is None:
            return True
        if obj.pk is None:
            return True
        codename = get_permission_codename("add_obj", self.opts)
        return request.user.has_perm("{}.{}".format(self.opts.app_label, codename), obj)

    def has_view_permission(self, request, obj=None):  # pragma: no cover
        if obj is None:
            return True
        if obj.pk is None:
            return True
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("view", opts)
        else:
            codename = get_permission_codename("view_obj", opts)
        perm = "{}.{}".format(opts.app_label, codename)
        if perm_exists(perm):
            return request.user.has_perm(perm, obj)
        else:
            return self.has_change_permission(request, obj)

    def has_change_permission(self, request, obj=None):  # pragma: no cover
        if obj is None:
            return True
        if obj.pk is None:
            return True
        opts = self.opts
        if opts.auto_created:
            for field in opts.fields:
                if field.rel and field.rel.to != self.parent_model:
                    opts = field.rel.to._meta
                    break
        codename = get_permission_codename("change_obj", opts)
        return request.user.has_perm("{}.{}".format(opts.app_label, codename), obj)

    def has_delete_permission(self, request, obj=None):  # pragma: no cover
        if obj is None:
            return True
        if obj.pk is None:
            return True
        if self.opts.auto_created:
            return self.has_change_permission(request, obj)
        return super().has_delete_permission(request, obj)
