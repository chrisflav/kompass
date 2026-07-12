"""Schemas for the members app's PUBLIC (unauthenticated) secret-key flows.

These mirror the forms in ``members/views.py`` (``MemberForm``,
``MemberRegistrationForm``, ``EmergencyContactsFormSet`` etc.). They live in a
separate module from ``schemas.py`` so the authenticated API surface is left
untouched. Every endpoint that consumes/produces them is keyed by one of the
model secret tokens rather than by the object's primary key.
"""

from datetime import date

from ninja import Schema

from .schemas import GroupBrief


class EmergencyContactIn(Schema):
    """One emergency contact (mirrors ``EmergencyContactForm``)."""

    prename: str
    lastname: str
    phone_number: str
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


class EchoMemberData(Schema):
    """The subset of member fields the echo edit form exposes (``MemberForm``)."""

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


class EchoPrefillOut(Schema):
    member: EchoMemberData
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


class RegisterMemberData(Schema):
    """Fields of ``MemberRegistrationForm``."""

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


class RegisterSubmitIn(RegisterMemberData):
    password: str
    emergency_contacts: list[EmergencyContactIn]


class InvitedRegisterSubmitIn(RegisterMemberData):
    emergency_contacts: list[EmergencyContactIn]


class InvitedRegisterPrefillOut(Schema):
    group: GroupBrief
    member: RegisterMemberData


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
    """Fields of ``MemberRegistrationWaitingListForm``."""

    prename: str
    lastname: str
    gender: int
    email: str
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
