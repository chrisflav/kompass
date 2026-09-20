"""Public (unauthenticated) logindata registration routes.

Mirrors :func:`logindata.views.register`: a member sets their Kompass login
credentials by following an emailed invite link carrying their
``invite_as_user_key``. If the member already has a linked ``User`` the flow is a
password *reset* (``SetPasswordForm``); otherwise it creates the account
(``UserCreationForm`` + ``initial_user_setup``). The shared
``RegistrationPassword`` secret gates the whole flow, exactly as the view does.

Every route takes ``auth=None`` — the caller is an invited member who has no
Kompass account yet — and the secret keys are validated manually. The same
Django auth forms are reused so password-strength / confirmation validation is
identical to the view; their errors surface as 422 via the root API's Django
``ValidationError`` handler.
"""

from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.http import Http404
from django.utils.translation import gettext_lazy as _
from logindata.models import initial_user_setup
from logindata.models import RegistrationPassword
from members.models import Member
from ninja import Router

from .schemas import RegisterIn
from .schemas import RegisterInfo
from .schemas import RegisterResult

router = Router()


def _member_for_invite_key(key):
    """Return the member for an ``invite_as_user_key`` or raise 404.

    Mirrors the lookup in ``logindata.views.register``; an empty key never
    resolves a member (the field default is ``""``).
    """
    if not key:
        raise Http404(_("Registration key is invalid or has expired."))
    try:
        return Member.objects.get(invite_as_user_key=key)
    except (Member.DoesNotExist, Member.MultipleObjectsReturned):
        raise Http404(_("Registration key is invalid or has expired."))


def _form_error_messages(form):
    """Flatten a form's field / non-field errors into a message list for 422."""
    messages = []
    for errors in form.errors.values():
        messages.extend(errors)
    return messages


@router.get("/register", auth=None, response=RegisterInfo)
def verify_register_key(request, key: str):
    """Verify an invite key and report the member name and reset-mode flag."""
    member = _member_for_invite_key(key)
    is_reset_mode = bool(member.user)
    return RegisterInfo(
        name=member.name,
        is_reset_mode=is_reset_mode,
        suggested_username="" if is_reset_mode else member.suggested_username(),
    )


@router.post("/register", auth=None, response=RegisterResult)
def set_password(request, payload: RegisterIn):
    """Set the member's login password (reset an existing account or create one).

    Wrong shared secret → 422; invalid key → 404; form validation errors → 422.
    """
    member = _member_for_invite_key(payload.key)
    is_reset_mode = bool(member.user)
    if not RegistrationPassword.objects.filter(password=payload.registration_password).exists():
        raise ValidationError(_("You entered a wrong password."))
    if is_reset_mode:
        form = SetPasswordForm(
            member.user,
            {
                "new_password1": payload.new_password1,
                "new_password2": payload.new_password2,
            },
        )
        if not form.is_valid():
            raise ValidationError(_form_error_messages(form))
        form.save()
        member.invite_as_user_key = ""
        member.save()
    else:
        form = UserCreationForm(
            {
                "username": payload.username or member.suggested_username(),
                "password1": payload.new_password1,
                "password2": payload.new_password2,
            }
        )
        if not form.is_valid():
            raise ValidationError(_form_error_messages(form))
        user = form.save(commit=False)
        if not initial_user_setup(user, member):
            raise ValidationError(_("Registration failed."))
    return RegisterResult(is_reset_mode=is_reset_mode)
