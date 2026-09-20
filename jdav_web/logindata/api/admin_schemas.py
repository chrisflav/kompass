"""Schemas for the authenticated logindata administration surface.

These back the SPA counterparts of ``LoginDatumAdmin``, ``AuthGroupAdmin`` and
the ``RegistrationPassword`` admin — the last app that had no API at all, which
forced administrators back into ``/kompass`` to create a user, adjust a
permission group or rotate the shared registration password.

Passwords are write-only: no schema here ever surfaces a hash.
"""

from datetime import datetime

from ninja import Schema


class PermissionBrief(Schema):
    """One Django permission, identified by its app-qualified codename."""

    id: int
    codename: str
    label: str
    app_label: str


class AuthGroupBrief(Schema):
    id: int
    name: str
    permission_count: int
    user_count: int


class AuthGroupOut(Schema):
    id: int
    name: str
    permissions: list[PermissionBrief] = []
    user_count: int


class AuthGroupIn(Schema):
    name: str
    permission_ids: list[int] | None = None


class LoginUserBrief(Schema):
    id: int
    username: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    last_login: datetime | None = None
    groups: list[str] = []
    member_name: str | None = None


class LoginUserOut(Schema):
    id: int
    username: str
    is_active: bool
    is_staff: bool
    is_superuser: bool
    last_login: datetime | None = None
    date_joined: datetime | None = None
    groups: list[AuthGroupBrief] = []
    member_id: int | None = None
    member_name: str | None = None


class LoginUserCreate(Schema):
    """Mirrors ``LoginDatumAdmin.add_fieldsets`` (username + password twice)."""

    username: str
    password1: str
    password2: str


class LoginUserUpdate(Schema):
    """Mirrors ``LoginDatumAdmin.fieldsets`` minus the password field.

    The password is changed through the dedicated ``set-password`` route so it is
    never mixed into an ordinary field update.
    """

    username: str | None = None
    is_active: bool | None = None
    is_staff: bool | None = None
    is_superuser: bool | None = None
    group_ids: list[int] | None = None


class SetPasswordIn(Schema):
    new_password1: str
    new_password2: str


class RegistrationPasswordOut(Schema):
    id: int
    password: str


class RegistrationPasswordIn(Schema):
    password: str
