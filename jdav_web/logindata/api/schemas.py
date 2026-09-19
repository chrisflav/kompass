"""Read/write schemas for the public logindata (registration) API.

These back :func:`logindata.views.register`: a member sets their Kompass login
credentials from an emailed invite link. The verify step returns only non-secret
context (name, reset-mode flag, suggested username); the write step carries the
shared invite secret and the chosen password.
"""

from ninja import Schema


class RegisterInfo(Schema):
    """Non-secret context for rendering the registration/reset form."""

    name: str
    is_reset_mode: bool
    suggested_username: str


class RegisterIn(Schema):
    """Payload for setting a member's login password via an invite key.

    ``registration_password`` is the shared invite secret (an active
    ``RegistrationPassword``); ``new_password1``/``new_password2`` are the user's
    chosen credentials. ``username`` is only used when creating a new account
    (reset mode ignores it) and defaults to the member's suggested username.
    """

    key: str
    registration_password: str
    new_password1: str
    new_password2: str
    username: str | None = None


class RegisterResult(Schema):
    """Outcome of a successful password set / reset."""

    is_reset_mode: bool
