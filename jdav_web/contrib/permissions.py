"""Shared, framework-agnostic permission helpers.

The row-level queryset-scoping algorithm lives here so that the Django admin
(`contrib.admin.FilteredQuerysetAdminMixin`) and the REST API use exactly one
implementation and can never diverge on what a user is allowed to see.
"""

from django.db import models


def scope_queryset(user, queryset, model=None):
    """Restrict ``queryset`` to the objects ``user`` is allowed to list.

    Mirrors the logic that previously lived inline in
    ``FilteredQuerysetAdminMixin.get_queryset``:

    * ``list_global_<model>`` grants listing; ``view_global_<model>`` additionally
      grants full visibility of every row.
    * Without ``view_global`` the rows are annotated with ``_viewable`` so callers
      can distinguish "may list" from "may view in full".
    * Without ``list_global`` the member-scoped filter is applied; users without a
      linked ``member`` see nothing.
    """
    if model is None:
        model = queryset.model
    opts = model._meta
    list_global_perm = "{}.list_global_{}".format(opts.app_label, opts.model_name)
    if user.has_perm(list_global_perm):
        view_global_perm = "{}.view_global_{}".format(opts.app_label, opts.model_name)
        if user.has_perm(view_global_perm):
            return queryset
        if hasattr(user, "member"):
            return user.member.annotate_view_permission(queryset, model=model)
        return queryset.annotate(_viewable=models.Value(False))

    if not hasattr(user, "member"):
        return model.objects.none()

    return user.member.filter_queryset_by_permissions(queryset, annotate=True, model=model)
