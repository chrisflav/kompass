"""Object-level authorization helpers for the REST API.

These delegate straight into the existing ``django-rules`` machinery via
``user.has_perm(perm, obj)`` (resolved by ``ObjectPermissionBackend``), so the
API reuses the same predicates the admin enforces. See
``contrib.permissions.scope_queryset`` for the list/row-level counterpart.
"""

from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _


class Forbidden(PermissionDenied):
    """A 403 whose message is written for the user and may be shown to them.

    ``authorize`` raises a plain ``PermissionDenied`` carrying a permission
    codename — an internal detail the client must not print. A refusal that
    explains a rule ("a sent message can no longer be edited") is the opposite:
    it is the only thing that makes the 403 actionable. The two are told apart
    by type rather than by guessing at the string.
    """


def set_scalar_fields(instance, data, fields):
    """Assign the ``fields`` present in ``data`` onto ``instance`` for a PATCH.

    Returns the list of field names that were actually present in ``data`` — the
    changed set to hand to :func:`partial_clean`.

    ``None`` is coerced to ``""`` for a non-nullable string field. Such a field
    (``blank=True, null=False`` — e.g. ``Member.iban``) accepts ``None`` in
    Python and even passes ``full_clean`` (``clean_fields`` skips blank fields
    whose value is empty, and ``None`` counts as empty), yet writing ``NULL`` to
    its NOT NULL column raises an ``IntegrityError`` at ``save()``. Coercing here
    keeps these fields robust to an explicit ``null`` from the client.
    """
    field_map = {f.name: f for f in instance._meta.concrete_fields}
    changed = []
    for name in fields:
        if name not in data:
            continue
        value = data[name]
        field = field_map.get(name)
        if value is None and field is not None and not field.null and field.empty_strings_allowed:
            value = ""
        setattr(instance, name, value)
        changed.append(name)
    return changed


def partial_clean(instance, changed_fields):
    """``full_clean`` an instance validating ONLY the fields being changed.

    PATCH updates a subset of fields, but ``full_clean()`` validates every
    field — so an unchanged, still-empty required field on an existing record
    would spuriously fail. This excludes every concrete field not in
    ``changed_fields`` (M2M relations must be excluded anyway — they are set
    after ``save()``), so validation (choices, IBAN, FK existence, lengths)
    runs on exactly the fields the request touched.
    """
    changed = set(changed_fields)
    exclude = [f.name for f in instance._meta.concrete_fields if f.name not in changed]
    instance.full_clean(exclude=exclude)


def authorize(request, perm, obj=None):
    """Raise :class:`PermissionDenied` unless the user holds ``perm`` for ``obj``.

    ``perm`` is a rules codename such as ``"members.change_obj_member"`` or a
    global codename such as ``"finance.process_statementsubmitted"``.
    """
    if not request.user.has_perm(perm, obj):
        raise PermissionDenied(perm)


def get_authorized(request, model, pk, perm, manager="objects"):
    """Fetch ``model`` instance ``pk`` and authorize ``perm`` on it, or 403/404."""
    queryset = getattr(model, manager).all()
    obj = get_object_or_404(queryset, pk=pk)
    authorize(request, perm, obj)
    return obj


def get_member(request):
    """Return the ``Member`` linked to the authenticated user, or 403.

    The entire object-permission model is expressed in terms of a member, so
    member-scoped endpoints must reject users without one.
    """
    member = getattr(request.user, "member", None)
    if member is None:
        raise Forbidden(_("No member is linked to this account."))
    return member
