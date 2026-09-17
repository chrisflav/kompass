"""Authenticated logindata administration routes.

Reproduces the three ``logindata`` model admins the SPA had no counterpart for:

* ``LoginDatumAdmin`` — Django users (a ``User`` proxy). Gated on the standard
  ``auth.*_user`` permissions, which is what ``UserAdmin`` checks.
* ``AuthGroupAdmin`` — permission groups (a ``Group`` proxy), gated on
  ``auth.*_group``.
* ``RegistrationPassword`` — the shared secret behind the "set your password"
  invite flow, gated on ``logindata.*_registrationpassword``.

Creating a user and changing a password go through Django's own
``UserCreationForm`` / ``SetPasswordForm``, so password validators, the
confirmation check and hashing behave exactly as in the admin; their errors
surface as 422 through the root API's ``ValidationError`` handler.
"""

from contrib.api.perms import authorize
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from logindata.models import AuthGroup
from logindata.models import LoginDatum
from logindata.models import RegistrationPassword
from ninja import Router

from .admin_schemas import AuthGroupBrief
from .admin_schemas import AuthGroupIn
from .admin_schemas import AuthGroupOut
from .admin_schemas import LoginUserBrief
from .admin_schemas import LoginUserCreate
from .admin_schemas import LoginUserOut
from .admin_schemas import LoginUserUpdate
from .admin_schemas import PermissionBrief
from .admin_schemas import RegistrationPasswordIn
from .admin_schemas import RegistrationPasswordOut
from .admin_schemas import SetPasswordIn

router = Router()


def _raise_form_errors(form):
    """Re-raise a Django auth form's errors as a ``ValidationError`` (→ 422)."""
    raise ValidationError({field: list(msgs) for field, msgs in form.errors.items()})


def _member_of(user):
    return getattr(user, "member", None)


def _user_payload(user):
    member = _member_of(user)
    return {
        "id": user.pk,
        "username": user.username,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login,
        "date_joined": user.date_joined,
        "groups": [_group_brief(g) for g in user.groups.all()],
        "member_id": member.pk if member else None,
        "member_name": member.name if member else None,
    }


def _group_brief(group):
    return {
        "id": group.pk,
        "name": group.name,
        "permission_count": group.permissions.count(),
        "user_count": group.user_set.count(),
    }


def _permission_brief(perm):
    return {
        "id": perm.pk,
        "codename": "{}.{}".format(perm.content_type.app_label, perm.codename),
        "label": perm.name,
        "app_label": perm.content_type.app_label,
    }


# --- users ----------------------------------------------------------------


@router.get("/users", response=list[LoginUserBrief])
def list_users(request):
    """All login accounts (``LoginDatumAdmin.list_display`` plus their groups)."""
    authorize(request, "auth.view_user")
    users = LoginDatum.objects.all().prefetch_related("groups").order_by("username")
    out = []
    for user in users:
        member = _member_of(user)
        out.append(
            {
                "id": user.pk,
                "username": user.username,
                "is_active": user.is_active,
                "is_staff": user.is_staff,
                "is_superuser": user.is_superuser,
                "last_login": user.last_login,
                "groups": [g.name for g in user.groups.all()],
                "member_name": member.name if member else None,
            }
        )
    return out


@router.post("/users", response={201: LoginUserOut})
def create_user(request, payload: LoginUserCreate):
    """Create a login account via Django's ``UserCreationForm`` (as the admin does)."""
    authorize(request, "auth.add_user")
    form = UserCreationForm(
        {
            "username": payload.username,
            "password1": payload.password1,
            "password2": payload.password2,
        }
    )
    if not form.is_valid():
        _raise_form_errors(form)
    user = form.save()
    return 201, _user_payload(user)


@router.get("/users/{user_id}", response=LoginUserOut)
def retrieve_user(request, user_id: int):
    authorize(request, "auth.view_user")
    return _user_payload(get_object_or_404(LoginDatum, pk=user_id))


@router.patch("/users/{user_id}", response=LoginUserOut)
def update_user(request, user_id: int, payload: LoginUserUpdate):
    """Update the admin's editable user fields (never the password)."""
    authorize(request, "auth.change_user")
    user = get_object_or_404(LoginDatum, pk=user_id)
    data = payload.dict(exclude_unset=True)
    for field in ("username", "is_active", "is_staff", "is_superuser"):
        if field in data and data[field] is not None:
            setattr(user, field, data[field])
    user.full_clean(exclude=["password", "last_login", "date_joined"])
    user.save()
    if data.get("group_ids") is not None:
        user.groups.set(AuthGroup.objects.filter(pk__in=data["group_ids"]))
    return _user_payload(user)


@router.post("/users/{user_id}/set-password", response=LoginUserOut)
def set_user_password(request, user_id: int, payload: SetPasswordIn):
    """Set a user's password via ``SetPasswordForm`` (same validators as the admin)."""
    authorize(request, "auth.change_user")
    user = get_object_or_404(LoginDatum, pk=user_id)
    form = SetPasswordForm(
        user, {"new_password1": payload.new_password1, "new_password2": payload.new_password2}
    )
    if not form.is_valid():
        _raise_form_errors(form)
    form.save()
    return _user_payload(user)


@router.delete("/users/{user_id}", response={204: None})
def delete_user(request, user_id: int):
    """Delete a login account, refusing to delete the caller's own."""
    authorize(request, "auth.delete_user")
    user = get_object_or_404(LoginDatum, pk=user_id)
    if user.pk == request.user.pk:
        raise ValidationError(_("You cannot delete your own account."))
    user.delete()
    return 204, None


# --- permission groups ----------------------------------------------------


@router.get("/permission-groups", response=list[AuthGroupBrief])
def list_permission_groups(request):
    authorize(request, "auth.view_group")
    return [_group_brief(g) for g in AuthGroup.objects.all().order_by("name")]


@router.post("/permission-groups", response={201: AuthGroupOut})
def create_permission_group(request, payload: AuthGroupIn):
    authorize(request, "auth.add_group")
    group = AuthGroup(name=payload.name)
    group.full_clean()
    group.save()
    if payload.permission_ids is not None:
        group.permissions.set(Permission.objects.filter(pk__in=payload.permission_ids))
    return 201, _group_payload(group)


def _group_payload(group):
    return {
        "id": group.pk,
        "name": group.name,
        "permissions": [
            _permission_brief(p)
            for p in group.permissions.select_related("content_type").order_by(
                "content_type__app_label", "codename"
            )
        ],
        "user_count": group.user_set.count(),
    }


@router.get("/permission-groups/{group_id}", response=AuthGroupOut)
def retrieve_permission_group(request, group_id: int):
    authorize(request, "auth.view_group")
    return _group_payload(get_object_or_404(AuthGroup, pk=group_id))


@router.patch("/permission-groups/{group_id}", response=AuthGroupOut)
def update_permission_group(request, group_id: int, payload: AuthGroupIn):
    authorize(request, "auth.change_group")
    group = get_object_or_404(AuthGroup, pk=group_id)
    group.name = payload.name
    group.full_clean()
    group.save()
    if payload.permission_ids is not None:
        group.permissions.set(Permission.objects.filter(pk__in=payload.permission_ids))
    return _group_payload(group)


@router.delete("/permission-groups/{group_id}", response={204: None})
def delete_permission_group(request, group_id: int):
    authorize(request, "auth.delete_group")
    get_object_or_404(AuthGroup, pk=group_id).delete()
    return 204, None


@router.get("/permissions", response=list[PermissionBrief])
def list_permissions(request):
    """Every assignable Django permission, for the group editor's picker."""
    authorize(request, "auth.view_group")
    perms = Permission.objects.select_related("content_type").order_by(
        "content_type__app_label", "codename"
    )
    return [_permission_brief(p) for p in perms]


# --- registration password ------------------------------------------------


@router.get("/registration-passwords", response=list[RegistrationPasswordOut])
def list_registration_passwords(request):
    """The shared secrets that gate the "set your password" invite flow."""
    authorize(request, "logindata.view_registrationpassword")
    return RegistrationPassword.objects.all().order_by("pk")


@router.post("/registration-passwords", response={201: RegistrationPasswordOut})
def create_registration_password(request, payload: RegistrationPasswordIn):
    authorize(request, "logindata.add_registrationpassword")
    entry = RegistrationPassword(password=payload.password)
    entry.full_clean()
    entry.save()
    return 201, entry


@router.patch("/registration-passwords/{password_id}", response=RegistrationPasswordOut)
def update_registration_password(request, password_id: int, payload: RegistrationPasswordIn):
    authorize(request, "logindata.change_registrationpassword")
    entry = get_object_or_404(RegistrationPassword, pk=password_id)
    entry.password = payload.password
    entry.full_clean()
    entry.save()
    return entry


@router.delete("/registration-passwords/{password_id}", response={204: None})
def delete_registration_password(request, password_id: int):
    authorize(request, "logindata.delete_registrationpassword")
    get_object_or_404(RegistrationPassword, pk=password_id).delete()
    return 204, None
