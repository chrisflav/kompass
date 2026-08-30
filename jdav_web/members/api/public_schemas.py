"""Schemas for the members app's PUBLIC (unauthenticated) secret-key flows.

These mirror the forms in ``members/views.py`` (``MemberForm``,
``MemberRegistrationForm``, ``EmergencyContactsFormSet`` etc.). They live in a
separate module from ``schemas.py`` so the authenticated API surface is left
untouched. Every endpoint that consumes/produces them is keyed by one of the
model secret tokens rather than by the object's primary key.
"""

from datetime import date
from typing import Annotated

from ninja import Schema
from pydantic import StringConstraints

from .schemas import GroupBrief

# The Django forms these schemas mirror rejected blank values for every field
# that is required on the model (``prename``/``lastname``/``email``/``gender``)
# plus the ones listed in each form's ``Meta.required``. Plain ``str`` would
# accept "" and let a caller create an entirely empty member, so required text
# fields use this trimmed, non-empty alias.
RequiredStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class EmergencyContactIn(Schema):
    """One emergency contact (mirrors ``EmergencyContactForm``)."""

    prename: RequiredStr
    lastname: RequiredStr
    phone_number: RequiredStr
    email: str = ""


class EmergencyContactOut(Schema):
    prename: str
    lastname: str
    phone_number: str
    email: str = ""


# --- echo -----------------------------------------------------------------


class EchoVerifyOut(Schema):
    """Result of verifying an echo key (mirrors the password prompt step)."""

    valid: bool = True


class EchoPasswordIn(Schema):
    password: str


class EchoMemberFields(Schema):
    """The subset of member fields the echo edit form exposes (``MemberForm``).

    Permissive on purpose: this is the shape of the prefill RESPONSE, and an
    existing member may legitimately have blanks in any of these fields.
    """

    prename: str
    lastname: str
    gender: int
    street: str = ""
    plz: str = ""
    town: str = ""
    address_extra: str = ""
    phone_number: str = ""
    dav_badge_no: str = ""
    photos_may_be_taken: bool = False


class EchoMemberData(EchoMemberFields):
    """Same fields on the way IN, with the form's required ones enforced."""

    prename: RequiredStr
    lastname: RequiredStr


class EchoPrefillOut(Schema):
    member: EchoMemberFields
    emergency_contacts: list[EmergencyContactOut] = []


class EchoSubmitIn(EchoMemberData):
    password: str
    emergency_contacts: list[EmergencyContactIn]


class EchoSuccessOut(Schema):
    name: str
    # When the member has no registration form yet, the view forwards them to
    # the upload page; the key is surfaced so the frontend can do the same.
    needs_registration_form_upload: bool
    upload_registration_form_key: str | None = None


# --- register (public self-registration) ----------------------------------


class RegisterPasswordIn(Schema):
    password: str


class RegisterVerifyOut(Schema):
    group: GroupBrief


class RegisterMemberFields(Schema):
    """Fields of ``MemberRegistrationForm``, permissive — the prefill RESPONSE
    shape, where the applicant's address is not known yet."""

    prename: str
    lastname: str
    gender: int
    email: str
    street: str
    plz: str
    town: str
    address_extra: str = ""
    phone_number: str = ""
    birth_date: date | None = None
    alternative_email: str | None = None
    photos_may_be_taken: bool = False


class RegisterMemberData(RegisterMemberFields):
    """Same fields on the way IN, with the form's required ones enforced.

    ``street``/``plz``/``town`` are blank-able on the model but listed in the
    form's ``Meta.required``, so they are required here too.
    """

    prename: RequiredStr
    lastname: RequiredStr
    email: RequiredStr
    street: RequiredStr
    plz: RequiredStr
    town: RequiredStr


class RegisterSubmitIn(RegisterMemberData):
    password: str
    emergency_contacts: list[EmergencyContactIn]


class InvitedRegisterSubmitIn(RegisterMemberData):
    emergency_contacts: list[EmergencyContactIn]


class InvitedRegisterPrefillOut(Schema):
    group: GroupBrief
    member: RegisterMemberFields


class RegistrationSuccessOut(Schema):
    name: str
    upload_registration_form_key: str


# --- upload registration form ---------------------------------------------


class UploadFormVerifyOut(Schema):
    name: str
    has_registration_form: bool


class UploadFormSuccessOut(Schema):
    name: str


# --- waiting list registration --------------------------------------------


class WaitingListRegisterIn(Schema):
    """Fields of ``MemberRegistrationWaitingListForm`` (``birth_date`` required)."""

    prename: RequiredStr
    lastname: RequiredStr
    gender: int
    email: RequiredStr
    birth_date: date
    application_text: str = ""


class WaitingListRegisterOut(Schema):
    name: str


# --- confirm waiting ------------------------------------------------------


class ConfirmWaitingOut(Schema):
    prename: str
    already_confirmed: bool


# --- leave waiting list ---------------------------------------------------


class LeaveWaitingOut(Schema):
    name: str


# --- invitations ----------------------------------------------------------


class InvitationDetailOut(Schema):
    groupname: str
    contact_email: str | None = None
    timeinfo: str


class RejectInvitationIn(Schema):
    # ``reject`` declines the group invitation only; ``leave`` additionally
    # removes the applicant from the waiting list (mirrors the two POST buttons).
    action: str = "reject"


class RejectInvitationOut(Schema):
    groupname: str
    left_waitinglist: bool


class ConfirmInvitationOut(Schema):
    groupname: str


# --- confirm mail ---------------------------------------------------------


class ConfirmMailOut(Schema):
    name: str
    email: str
