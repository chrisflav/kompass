import copy
from django.contrib.auth import get_permission_codename

from django.core.exceptions import PermissionDenied
from django.contrib import admin, messages
from django.utils.translation import gettext_lazy as _
from django.http import HttpResponse, HttpResponseRedirect
from django.urls import path, reverse
from django.db import models
from django.contrib.admin import helpers, widgets
import rules.contrib.admin
from rules.permissions import perm_exists


class FieldPermissionsAdminMixin:
    field_change_permissions = {}
    field_view_permissions = {}

    def may_view_field(self, field_desc, request, obj=None):
        if not type(field_desc) is tuple:
            field_desc = (field_desc,)
        for fd in field_desc:
            if fd not in self.field_view_permissions:
                continue
            if not request.user.has_perm(self.field_view_permissions[fd], obj):
                return False
        return True

    def get_fieldsets(self, request, obj=None):
        fieldsets = super(FieldPermissionsAdminMixin, self).get_fieldsets(request, obj)
        d = []
        for title, attrs in fieldsets:
            allowed = [f for f in attrs['fields'] if self.may_view_field(f, request, obj)]
            if len(allowed) == 0:
                continue
            d.append((title, dict(attrs, **{'fields': allowed})))
        return d

    def get_fields(self, request, obj=None):
        fields = super(FieldPermissionsAdminMixin, self).get_fields(request, obj)
        return [fd for fd in fields if self.may_view_field(fd, request, obj)]

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = super(FieldPermissionsAdminMixin, self).get_readonly_fields(request, obj)
        return list(readonly_fields) +\
            [fd for fd, perm in self.field_change_permissions.items() if not request.user.has_perm(perm, obj)]


class ChangeViewAdminMixin:
    def change_view(self, request, object_id, form_url="", extra_context=None):
        try:
            return super(ChangeViewAdminMixin, self).change_view(request, object_id,
                                                                 form_url=form_url,
                                                                 extra_context=extra_context)
        except PermissionDenied:
            opts = self.opts
            obj = self.model.objects.get(pk=object_id)
            messages.error(request,
                    _("You are not allowed to view %(name)s.") % {'name': str(obj)})
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (opts.app_label, opts.model_name)))


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
        list_global_perm = '%s.list_global_%s' % (self.opts.app_label, self.opts.model_name)
        if request.user.has_perm(list_global_perm):
            view_global_perm = '%s.view_global_%s' % (self.opts.app_label, self.opts.model_name)
            if request.user.has_perm(view_global_perm):
               return queryset
            if hasattr(request.user, 'member'):
                return request.user.member.annotate_view_permission(queryset, model=self.model)
            return queryset.annotate(_viewable=models.Value(False))

        if not hasattr(request.user, 'member'):
            return self.model.objects.none()

        return request.user.member.filter_queryset_by_permissions(queryset, annotate=True, model=self.model)

#class ObjectPermissionsInlineModelAdminMixin(rules.contrib.admin.ObjectPermissionsInlineModelAdminMixin):

class CommonAdminMixin(FieldPermissionsAdminMixin, ChangeViewAdminMixin, FilteredQuerysetAdminMixin):
    def has_add_permission(self, request, obj=None):
        assert obj is None
        opts = self.opts
        codename = get_permission_codename("add_global", opts)
        perm = "%s.%s" % (opts.app_label, codename)
        return request.user.has_perm(perm, obj)

    def has_view_permission(self, request, obj=None):
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("view", opts)
        else:
            codename = get_permission_codename("view_obj", opts)
        perm = "%s.%s" % (opts.app_label, codename)
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
        return request.user.has_perm("%s.%s" % (opts.app_label, codename), obj)

    def has_delete_permission(self, request, obj=None):
        opts = self.opts
        if obj is None:
            codename = get_permission_codename("delete_global", opts)
        else:
            codename = get_permission_codename("delete_obj", opts)
        return request.user.has_perm("%s.%s" % (opts.app_label, codename), obj)

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
            #if formfield and db_field.name not in self.raw_id_fields:
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
        #assert obj is not None
        if obj is None:
            return True
        if obj.pk is None:
            return True
        codename = get_permission_codename("add_obj", self.opts)
        return request.user.has_perm('%s.%s' % (self.opts.app_label, codename), obj)

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
        perm = "%s.%s" % (opts.app_label, codename)
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
        return request.user.has_perm("%s.%s" % (opts.app_label, codename), obj)

    def has_delete_permission(self, request, obj=None):  # pragma: no cover
        if obj is None:
            return True
        if obj.pk is None:
            return True
        if self.opts.auto_created:
            return self.has_change_permission(request, obj)
        return super().has_delete_permission(request, obj)
