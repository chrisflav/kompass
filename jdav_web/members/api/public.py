"""PUBLIC (unauthenticated) members API — the secret-key self-service flows.

Every endpoint here is the JSON counterpart of a view in ``members/views.py``
and is keyed by one of the secret tokens on the models (``echo_key``,
``upload_registration_form_key``, ``confirm_mail_key`` /
``confirm_alternative_mail_key``, ``wait_confirmation_key``, ``leave_key``,
``registration_key`` and the ``InvitationToGroup.key``). They carry no OAuth
requirement (``auth=None``) because the bearer of a valid secret is the
authorization — exactly as the corresponding views operate.

The logic, validation and guards mirror the views verbatim. Invalid tokens
resolve to ``404``; state guards that the views turn into an error page
(expired key, wrong password, invalid emergency contacts) are surfaced as
django ``ValidationError`` (rendered as ``422`` by the root API handler).
"""

from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from members.models import confirm_mail_by_key
from members.models import EmergencyContact
from members.models import InvitationToGroup
from members.models import Member
from members.models import MemberWaitingList
from members.models import RegistrationPassword
from ninja import File
from ninja import Router
from ninja.files import UploadedFile

from .public_schemas import ConfirmInvitationOut
from .public_schemas import ConfirmMailOut
from .public_schemas import ConfirmWaitingOut
from .public_schemas import EchoPasswordIn
from .public_schemas import EchoPrefillOut
from .public_schemas import EchoSubmitIn
from .public_schemas import EchoSuccessOut
from .public_schemas import EchoVerifyOut
from .public_schemas import InvitationDetailOut
from .public_schemas import InvitedRegisterPrefillOut
from .public_schemas import InvitedRegisterSubmitIn
from .public_schemas import LeaveWaitingOut
from .public_schemas import RegisterPasswordIn
from .public_schemas import RegisterSubmitIn
from .public_schemas import RegisterVerifyOut
from .public_schemas import RegistrationSuccessOut
from .public_schemas import RejectInvitationIn
from .public_schemas import RejectInvitationOut
from .public_schemas import UploadFormSuccessOut
from .public_schemas import UploadFormVerifyOut
from .public_schemas import WaitingListRegisterIn
from .public_schemas import WaitingListRegisterOut

router = Router()

# Mirrors the ``RestrictedFileField`` constraints on ``Member.registration_form``.
REGISTRATION_FORM_CONTENT_TYPES = ["application/pdf", "image/jpeg", "image/png", "image/gif"]
REGISTRATION_FORM_MAX_UPLOAD_SIZE_MB = 5

# Fields the echo edit form (``MemberForm``) writes back onto a member.
_ECHO_FIELDS = [
    "prename",
    "lastname",
    "gender",
    "street",
    "plz",
    "town",
    "address_extra",
    "phone_number",
    "dav_badge_no",
    "photos_may_be_taken",
]


def _validate_registration_form(upload):
    """Enforce the ``Member.registration_form`` upload constraints."""
    if upload.content_type not in REGISTRATION_FORM_CONTENT_TYPES:
        raise ValidationError(_("Filetype not supported."))
    limit = REGISTRATION_FORM_MAX_UPLOAD_SIZE_MB * 1024 * 1024
    if upload.size > limit:
        raise ValidationError(
            _("Please keep filesize under %(mb)s MiB.")
            % {"mb": REGISTRATION_FORM_MAX_UPLOAD_SIZE_MB}
        )


def _require_emergency_contacts(contacts):
    """Reproduce the formset's ``min_num=1``/``validate_min`` guard."""
    if len(contacts) < 1:
        raise ValidationError(_("At least one emergency contact is required."))


def _replace_emergency_contacts(member, contacts):
    """Replace the member's emergency contacts (mirrors the inline formset save)."""
    member.emergencycontact_set.all().delete()
    for contact in contacts:
        EmergencyContact.objects.create(
            member=member,
            prename=contact.prename,
            lastname=contact.lastname,
            email=contact.email,
            phone_number=contact.phone_number,
        )


def _create_member_from_registration(payload, group, waiter):
    """Create a member from a registration payload (mirrors ``register``'s save).

    ``form.save`` then ``formset.save`` then ``create_from_registration`` then
    ``send_upload_registration_form_link``. ``waiter`` is ``None`` for the
    password path and the invitation's applicant for the invited path.
    """
    member = Member(
        prename=payload.prename,
        lastname=payload.lastname,
        gender=payload.gender,
        email=payload.email,
        street=payload.street,
        plz=payload.plz,
        town=payload.town,
        address_extra=payload.address_extra,
        phone_number=payload.phone_number,
        birth_date=payload.birth_date,
        photos_may_be_taken=payload.photos_may_be_taken,
    )
    if payload.alternative_email is not None:
        member.alternative_email = payload.alternative_email
    member.save()
    _replace_emergency_contacts(member, payload.emergency_contacts)
    member.create_from_registration(waiter, group)
    member.send_upload_registration_form_link()
    return member


# --- echo -----------------------------------------------------------------


@router.get("/echo/{key}", auth=None, response=EchoVerifyOut)
def echo_verify(request, key: str):
    """Verify an echo key exists (the view's password-prompt step)."""
    get_object_or_404(Member, echo_key=key)
    return EchoVerifyOut(valid=True)


@router.post("/echo/{key}/prefill", auth=None, response=EchoPrefillOut)
def echo_prefill(request, key: str, payload: EchoPasswordIn):
    """Return the prefilled member edit form after the echo password check."""
    member = get_object_or_404(Member, echo_key=key)
    if not member.may_echo(key):
        raise ValidationError(_("The echo key has expired."))
    if payload.password != member.echo_password:
        raise ValidationError(_("The entered password is wrong."))
    return {
        "member": member,
        "emergency_contacts": member.emergencycontact_set.all(),
    }


@router.post("/echo/{key}", auth=None, response=EchoSuccessOut)
def echo_submit(request, key: str, payload: EchoSubmitIn):
    """Persist the echoed member data and emergency contacts."""
    member = get_object_or_404(Member, echo_key=key)
    if not member.may_echo(key):
        raise ValidationError(_("The echo key has expired."))
    if payload.password != member.echo_password:
        raise ValidationError(_("The entered password is wrong."))
    _require_emergency_contacts(payload.emergency_contacts)
    for field in _ECHO_FIELDS:
        setattr(member, field, getattr(payload, field))
    # The echo key is intentionally not invalidated (the view keeps it too), so
    # the member can echo again if desired.
    member.echoed = True
    member.save()
    _replace_emergency_contacts(member, payload.emergency_contacts)
    if not member.registration_form:
        member.request_registration_form()
        return EchoSuccessOut(
            name=member.prename,
            needs_registration_form_upload=True,
            upload_registration_form_key=member.upload_registration_form_key,
        )
    return EchoSuccessOut(name=member.prename, needs_registration_form_upload=False)


# --- register (public self-registration) ----------------------------------


@router.post("/register/verify", auth=None, response=RegisterVerifyOut)
def register_verify(request, payload: RegisterPasswordIn):
    """Verify a registration password and return the associated group."""
    try:
        pwd = RegistrationPassword.objects.get(password=payload.password)
    except RegistrationPassword.DoesNotExist:
        raise ValidationError(_("The entered password is wrong."))
    return {"group": pwd.group}


@router.post("/register", auth=None, response=RegistrationSuccessOut)
def register_submit(request, payload: RegisterSubmitIn):
    """Create a member from a password-gated public self-registration."""
    try:
        pwd = RegistrationPassword.objects.get(password=payload.password)
    except RegistrationPassword.DoesNotExist:
        raise ValidationError(_("The entered password is wrong."))
    _require_emergency_contacts(payload.emergency_contacts)
    member = _create_member_from_registration(payload, pwd.group, waiter=None)
    return RegistrationSuccessOut(
        name=member.prename,
        upload_registration_form_key=member.upload_registration_form_key,
    )


# --- invited registration -------------------------------------------------


@router.get("/invited-registration/{key}", auth=None, response=InvitedRegisterPrefillOut)
def invited_registration_prefill(request, key: str):
    """Return the group and applicant-prefilled form for an invitation key."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    if invitation.is_expired() or invitation.rejected:
        raise ValidationError(_("The invitation has expired."))
    waiter = invitation.waiter
    return {
        "group": invitation.group,
        "member": {
            "prename": waiter.prename,
            "lastname": waiter.lastname,
            "gender": waiter.gender,
            "email": waiter.email,
            "street": "",
            "plz": "",
            "town": "",
            "address_extra": "",
            "phone_number": "",
            "birth_date": waiter.birth_date,
            "alternative_email": None,
            "photos_may_be_taken": False,
        },
    }


@router.post("/invited-registration/{key}", auth=None, response=RegistrationSuccessOut)
def invited_registration_submit(request, key: str, payload: InvitedRegisterSubmitIn):
    """Register an invited applicant into the invitation's group."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    _require_emergency_contacts(payload.emergency_contacts)
    member = _create_member_from_registration(payload, invitation.group, waiter=invitation.waiter)
    return RegistrationSuccessOut(
        name=member.prename,
        upload_registration_form_key=member.upload_registration_form_key,
    )


# --- upload registration form ---------------------------------------------


@router.get("/upload-registration-form/{key}", auth=None, response=UploadFormVerifyOut)
def upload_registration_form_verify(request, key: str):
    """Verify an upload key and report whether a form is already present."""
    member = get_object_or_404(Member.all_objects, upload_registration_form_key=key)
    return {"name": member.prename, "has_registration_form": bool(member.registration_form)}


@router.post("/upload-registration-form/{key}", auth=None, response=UploadFormSuccessOut)
def upload_registration_form_submit(request, key: str, registration_form: UploadedFile = File(...)):
    """Attach a registration form to the member identified by the upload key."""
    member = get_object_or_404(Member.all_objects, upload_registration_form_key=key)
    _validate_registration_form(registration_form)
    member.registration_form = registration_form
    member.save()
    member.validate_registration_form()
    return {"name": member.prename}


# --- waiting list registration --------------------------------------------


@router.post("/waiting-list", auth=None, response=WaitingListRegisterOut)
def register_waiting_list(request, payload: WaitingListRegisterIn):
    """Create a waiting-list applicant and request their mail confirmation."""
    waiter = MemberWaitingList(
        prename=payload.prename,
        lastname=payload.lastname,
        gender=payload.gender,
        email=payload.email,
        birth_date=payload.birth_date,
        application_text=payload.application_text,
    )
    waiter.save()
    waiter.request_mail_confirmation()
    return {"name": waiter.prename}


# --- confirm waiting ------------------------------------------------------


@router.post("/confirm-waiting/{key}", auth=None, response=ConfirmWaitingOut)
def confirm_waiting(request, key: str):
    """Confirm a waiting-list applicant's intent to keep waiting."""
    waiter = get_object_or_404(MemberWaitingList, wait_confirmation_key=key)
    status = waiter.confirm_waiting(key)
    if status == MemberWaitingList.WAITING_CONFIRMATION_SUCCESS:
        return ConfirmWaitingOut(prename=waiter.prename, already_confirmed=False)
    if status == MemberWaitingList.WAITING_CONFIRMED:
        return ConfirmWaitingOut(prename=waiter.prename, already_confirmed=True)
    # WAITING_CONFIRMATION_INVALID and WAITING_CONFIRMATION_EXPIRED share a value.
    raise ValidationError(_("The waiting confirmation link is invalid or has expired."))


# --- leave waiting list ---------------------------------------------------


@router.get("/leave-waitinglist/{key}", auth=None, response=LeaveWaitingOut)
def leave_waitinglist_verify(request, key: str):
    """Verify a leave key and return the applicant to be removed."""
    try:
        waiter = MemberWaitingList.objects.get(leave_key=key)
    except (MemberWaitingList.DoesNotExist, MemberWaitingList.MultipleObjectsReturned):
        raise Http404("Waiter with given leave key does not exist.")
    return {"name": waiter.name}


@router.post("/leave-waitinglist/{key}", auth=None, response=LeaveWaitingOut)
def leave_waitinglist_submit(request, key: str):
    """Remove the applicant identified by the leave key from the waiting list."""
    try:
        waiter = MemberWaitingList.objects.get(leave_key=key)
    except (MemberWaitingList.DoesNotExist, MemberWaitingList.MultipleObjectsReturned):
        raise Http404("Waiter with given leave key does not exist.")
    name = waiter.name
    waiter.unregister()
    return {"name": name}


# --- invitation reject ----------------------------------------------------


@router.get("/reject-invitation/{key}", auth=None, response=InvitationDetailOut)
def reject_invitation_verify(request, key: str):
    """Verify an invitation reject key and return its details."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    if invitation.rejected or invitation.is_expired():
        raise ValidationError(_("The invitation is no longer valid."))
    group = invitation.group
    return {
        "groupname": group.name,
        "contact_email": str(group.contact_email) if group.contact_email else None,
        "timeinfo": group.get_time_info(),
    }


@router.post("/reject-invitation/{key}", auth=None, response=RejectInvitationOut)
def reject_invitation_submit(request, key: str, payload: RejectInvitationIn):
    """Reject a group invitation, optionally leaving the waiting list too."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    groupname = invitation.group.name
    if payload.action == "reject":
        invitation.reject()
        return RejectInvitationOut(groupname=groupname, left_waitinglist=False)
    if payload.action == "leave":
        invitation.notify_left_waitinglist()
        invitation.waiter.unregister()
        return RejectInvitationOut(groupname=groupname, left_waitinglist=True)
    raise ValidationError(_("Unknown action."))


# --- invitation confirm ---------------------------------------------------


@router.get("/confirm-invitation/{key}", auth=None, response=InvitationDetailOut)
def confirm_invitation_verify(request, key: str):
    """Verify an invitation confirm key and return its details."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    if invitation.rejected or invitation.is_expired():
        raise ValidationError(_("The invitation is no longer valid."))
    group = invitation.group
    return {
        "groupname": group.name,
        "contact_email": str(group.contact_email) if group.contact_email else None,
        "timeinfo": group.get_time_info(),
    }


@router.post("/confirm-invitation/{key}", auth=None, response=ConfirmInvitationOut)
def confirm_invitation_submit(request, key: str):
    """Confirm attendance for a group invitation."""
    try:
        invitation = InvitationToGroup.objects.get(key=key)
    except InvitationToGroup.DoesNotExist:
        raise Http404("Invitation with given key does not exist.")
    invitation.confirm()
    return ConfirmInvitationOut(groupname=invitation.group.name)


# --- confirm mail ---------------------------------------------------------


@router.post("/confirm-mail/{key}", auth=None, response=ConfirmMailOut)
def confirm_mail(request, key: str):
    """Confirm an email address via its confirmation key.

    Reuses ``confirm_mail_by_key``, which resolves the key against unconfirmed
    registrations, waiting-list applicants and emergency contacts.
    """
    res = confirm_mail_by_key(key)
    if not res:
        raise Http404("No pending confirmation matches the given key.")
    person, email = res
    return ConfirmMailOut(name=person.prename, email=email)
