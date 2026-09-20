"""Read schemas for the members API.

The ``may_list`` vs ``may_view`` distinction of the permission model is honored
structurally: list endpoints return the brief identity representation (what
"listing" exposes), while full detail is only served by retrieve endpoints that
are gated on ``view_obj_<model>``.
"""

from datetime import date as Date
from datetime import datetime
from datetime import time
from typing import Any

from members.models import ActivityCategory
from members.models import annotate_activity_score
from members.models import Freizeit
from members.models import Group
from members.models import InvitationToGroup
from members.models import Klettertreff
from members.models import Member
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberWaitingList
from members.models import TrainingCategory
from ninja import ModelSchema
from ninja import Schema


class MeOut(Schema):
    """The authenticated user's own identity.

    Drives the SPA's top bar (name → profile link) and the personal ("Meine …")
    views. ``member_id`` is null for accounts without a linked ``Member``; the
    frontend then falls back to the username for display and hides the personal
    section.
    """

    user_id: int
    username: str
    name: str
    member_id: int | None = None
    is_staff: bool = False
    is_superuser: bool = False
    # Every global permission codename the caller holds ("app.codename"). The
    # SPA uses these to hide actions it knows will be refused, the way the admin
    # hid buttons the user had no permission for. Object-level rules still
    # decide per row, and the backend re-checks everything.
    permissions: list[str] = []


class GroupBrief(Schema):
    id: int
    name: str


class MemberRef(Schema):
    """Identity representation of a member named inside another object.

    Deliberately not :class:`MemberBrief`, which carries birth date, email,
    phone number and comments: a group listing has no business shipping those
    about every youth leader. Callers that need the full record fetch the
    member itself, where the object permissions apply.
    """

    id: int
    name: str


class MemberBrief(ModelSchema):
    # Declared explicitly so the response contract types it as a required
    # non-null int (ModelSchema would otherwise mark the AutoField optional).
    id: int
    name: str
    # Underlying values behind the admin ``list_display`` columns (the admin
    # renders these as mailto/tel links and joined group names; the API exposes
    # the raw values so the SPA can search / filter / sort client-side).
    age: int | None = None
    groups: list[str] = []
    activity_score: int | None = None

    class Meta:
        model = Member
        # ``confirmed`` lets the frontend distinguish unconfirmed registrations
        # from confirmed members in the plain listing. The remaining fields back
        # the admin list columns (birth date, email, phone, echoed, comments).
        fields = [
            "prename",
            "lastname",
            "confirmed",
            "birth_date",
            "email",
            "phone_number",
            "echoed",
            "comments",
        ]

    @staticmethod
    def resolve_age(obj) -> int | None:
        return obj.age() if obj.birth_date else None

    @staticmethod
    def resolve_groups(obj) -> list[str]:
        return [g.name for g in obj.group.all()]

    @staticmethod
    def resolve_activity_score(obj) -> int | None:
        # Present only when the queryset was annotated (list endpoints);
        # absent for members nested in other schemas (jugendleiter, attendees).
        return getattr(obj, "_activity_score", None)


class AuthUserBrief(Schema):
    """One login account, for the member change view's "Nutzer" picker.

    The admin renders ``Member.user`` as a plain select over every ``User``, so
    the list is unfiltered here too. ``member_name`` names the member an account
    is already linked to — the relation is one-to-one, so picking such an
    account fails on uniqueness, and saying so in the option beats letting the
    user find out from a 422.
    """

    id: int
    username: str
    member_name: str | None = None


class MemberOut(ModelSchema):
    id: int
    name: str
    age: int | None = None
    gender_str: str
    place: str
    address: str
    iban_valid: bool
    groups: list[GroupBrief]
    # Choice display / computed / relational values covering the remaining admin
    # change-view fields (Skills / Others / Organizational fieldsets).
    gender_display: str
    good_conduct_certificate_valid: bool
    activity_score: int | None = None
    registration_form: str | None = None
    image: str | None = None
    user_id: int | None = None
    user_display: str | None = None
    skills: dict[str, int] = {}
    activities: list["ExcursionBrief"] = []

    class Meta:
        model = Member
        fields = [
            "prename",
            "lastname",
            "email",
            "alternative_email",
            "birth_date",
            "gender",
            "phone_number",
            "street",
            "plz",
            "town",
            "address_extra",
            "country",
            "dav_badge_no",
            "ticket_no",
            "iban",
            "join_date",
            "leave_date",
            "has_key",
            "has_free_ticket_gym",
            "swimming_badge",
            "climbing_badge",
            "alpine_experience",
            "allergies",
            "medication",
            "tetanus_vaccination",
            "may_cancel_appointment_independently",
            "good_conduct_certificate_presented_date",
            "legal_guardians",
            "comments",
            "echoed",
            "photos_may_be_taken",
            "gets_newsletter",
            "active",
            "confirmed",
            "confirmed_mail",
            "confirmed_alternative_mail",
            "created",
        ]

    @staticmethod
    def resolve_age(obj) -> int | None:
        return obj.age() if obj.birth_date else None

    @staticmethod
    def resolve_groups(obj):
        return obj.group.all()

    @staticmethod
    def resolve_gender_display(obj) -> str:
        return obj.get_gender_display()

    @staticmethod
    def resolve_good_conduct_certificate_valid(obj) -> bool:
        return obj.good_conduct_certificate_valid()

    @staticmethod
    def resolve_activity_score(obj) -> int | None:
        score = getattr(obj, "_activity_score", None)
        if score is not None:
            return score
        annotated = annotate_activity_score(Member.objects.filter(pk=obj.pk)).first()
        return getattr(annotated, "_activity_score", None)

    @staticmethod
    def resolve_registration_form(obj) -> str | None:
        return obj.registration_form.url if obj.registration_form else None

    @staticmethod
    def resolve_image(obj) -> str | None:
        return obj.image.url if obj.image else None

    @staticmethod
    def resolve_user_display(obj) -> str | None:
        return obj.user.get_username() if obj.user_id else None

    @staticmethod
    def resolve_skills(obj) -> dict[str, int]:
        return obj.get_skills()

    @staticmethod
    def resolve_activities(obj):
        return obj.get_activities()


class GroupOut(ModelSchema):
    id: int
    weekday_display: str
    time_info: str
    age_info: str
    leiters: list[MemberRef]
    contact_email_display: str | None = None
    has_registration_password: bool = False
    # Prefill for the waiting-list invite dialog's editable text (the admin form's
    # initial value).
    invitation_text_template: str = ""

    class Meta:
        model = Group
        fields = [
            "name",
            "description",
            "show_website",
            "year_from",
            "year_to",
            "weekday",
            "start_time",
            "end_time",
            "contact_email",
            "show_website_year",
            "show_website_weekday",
            "show_website_time",
            "show_website_contact_email",
            "show_website_registration",
        ]

    @staticmethod
    def resolve_contact_email_display(obj) -> str | None:
        return str(obj.contact_email) if obj.contact_email_id else None

    @staticmethod
    def resolve_has_registration_password(obj) -> bool:
        return obj.has_registration_password()

    @staticmethod
    def resolve_invitation_text_template(obj) -> str:
        return obj.get_invitation_text_template()

    @staticmethod
    def resolve_weekday_display(obj) -> str:
        # These helpers can return None (unset weekday/time) or a lazy
        # translation proxy; the field is a non-null str, so coerce explicitly.
        return str(obj.get_weekday_display_info() or "")

    @staticmethod
    def resolve_time_info(obj) -> str:
        return str(obj.get_time_info() or "")

    @staticmethod
    def resolve_age_info(obj) -> str:
        return str(obj.get_age_info() or "")

    @staticmethod
    def resolve_leiters(obj):
        return obj.leiters.all()


class ExcursionBrief(ModelSchema):
    id: int
    code: str
    date: datetime
    # Back the list's group + participant filters (the admin's list_filter).
    groups: list[GroupBrief] = []
    participant_ids: list[int] = []

    class Meta:
        model = Freizeit
        # ``place`` and ``approved`` back the admin list columns.
        fields = ["name", "place", "approved"]

    @staticmethod
    def resolve_code(obj) -> str:
        return obj.code

    @staticmethod
    def resolve_groups(obj):
        return obj.groups.all()

    @staticmethod
    def resolve_participant_ids(obj) -> list[int]:
        # Anyone on the member list OR a youth leader — matches the admin's
        # ParticipantFilter (Q(membersonlist__member) | Q(jugendleiter)).
        member_ids = {mol.member_id for mol in obj.membersonlist.all()}
        member_ids |= {j.pk for j in obj.jugendleiter.all()}
        return sorted(member_ids)


class ActivityCategoryBrief(Schema):
    """Identity representation of an activity category (M2M selector option)."""

    id: int
    name: str


class ExcursionOut(ModelSchema):
    id: int
    date: datetime
    end: datetime
    code: str
    tour_type_str: str
    tour_approach_str: str
    difficulty_str: str
    night_count: int
    duration: float
    staff_count: int
    participant_count: int
    head_count: int
    # The id of the associated statement (Statement.excursion is a OneToOne), or
    # null when the excursion has no statement yet. Lets the SPA statement tab
    # detect / reach the excursion's abrechnung.
    statement_id: int | None = None
    groups: list[GroupBrief]
    jugendleiter: list[MemberBrief]
    activity: list[ActivityCategoryBrief]

    class Meta:
        model = Freizeit
        fields = [
            "name",
            "place",
            "postcode",
            "destination",
            "description",
            "tour_type",
            "tour_approach",
            "kilometers_traveled",
            "difficulty",
            "approved",
            "approval_comments",
            "approved_extra_youth_leader_count",
        ]

    @staticmethod
    def resolve_code(obj) -> str:
        return obj.code

    @staticmethod
    def resolve_statement_id(obj) -> int | None:
        # Statement.excursion is a OneToOne; the reverse accessor raises
        # DoesNotExist (not AttributeError) when absent, so guard with hasattr.
        return obj.statement.pk if hasattr(obj, "statement") else None

    @staticmethod
    def resolve_tour_type_str(obj) -> str:
        return obj.get_tour_type()

    @staticmethod
    def resolve_tour_approach_str(obj) -> str:
        return obj.get_tour_approach()

    @staticmethod
    def resolve_difficulty_str(obj) -> str:
        return str(obj.get_difficulty_display())

    @staticmethod
    def resolve_groups(obj):
        return obj.groups.all()

    @staticmethod
    def resolve_jugendleiter(obj):
        return obj.jugendleiter.all()

    @staticmethod
    def resolve_activity(obj):
        return obj.activity.all()


class ExcursionUpdate(Schema):
    """Editable excursion fields (every editable change-view field).

    All fields optional for PATCH semantics; only supplied fields are applied.
    The Approval fieldset (``approved``, ``approval_comments``,
    ``approved_extra_youth_leader_count``) is gated on
    ``members.manage_approval_excursion`` in the route. Relations
    (``groups``, ``jugendleiter``, ``activity``) are applied via ids.
    """

    name: str | None = None
    place: str | None = None
    postcode: str | None = None
    destination: str | None = None
    date: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    difficulty: int | None = None
    tour_type: int | None = None
    tour_approach: int | None = None
    kilometers_traveled: int | None = None
    group_ids: list[int] | None = None
    jugendleiter_ids: list[int] | None = None
    activity_ids: list[int] | None = None
    # Gated on members.manage_approval_excursion.
    approved: bool | None = None
    approval_comments: str | None = None
    approved_extra_youth_leader_count: int | None = None


EXCURSION_UPDATE_SCALAR_FIELDS = (
    "name",
    "place",
    "postcode",
    "destination",
    "date",
    "end",
    "description",
    "difficulty",
    "tour_type",
    "tour_approach",
    "kilometers_traveled",
)

EXCURSION_APPROVAL_FIELDS = (
    "approved",
    "approval_comments",
    "approved_extra_youth_leader_count",
)


class ExcursionCreate(Schema):
    """Create payload for an excursion.

    ``difficulty`` and ``tour_type`` are required (no model default); other
    scalars fall back to the model defaults when omitted. Relations
    (``group_ids`` / ``jugendleiter_ids`` / ``activity_ids``) are applied in the
    route. Approval fields are not settable at create (they mirror the admin's
    permission-gated Approval fieldset, edited afterwards).
    """

    name: str | None = None
    place: str | None = None
    postcode: str | None = None
    destination: str | None = None
    date: datetime | None = None
    end: datetime | None = None
    description: str | None = None
    difficulty: int
    tour_type: int
    tour_approach: int | None = None
    kilometers_traveled: int | None = None
    group_ids: list[int] = []
    jugendleiter_ids: list[int] = []
    activity_ids: list[int] = []


class MemberUpdate(Schema):
    """Editable member fields (every non-readonly change-view field).

    All fields optional for PATCH semantics; only supplied fields are applied.
    Per-field permission gates (``group`` → ``may_change_member_group``; ``user``
    → ``may_set_auth_user``; the organizational fields → ``may_change_organizationals``)
    are enforced in the route, not here.
    """

    prename: str | None = None
    lastname: str | None = None
    email: str | None = None
    alternative_email: str | None = None
    phone_number: str | None = None
    birth_date: Date | None = None
    gender: int | None = None
    street: str | None = None
    plz: str | None = None
    town: str | None = None
    address_extra: str | None = None
    country: str | None = None
    iban: str | None = None
    join_date: Date | None = None
    leave_date: Date | None = None
    dav_badge_no: str | None = None
    ticket_no: str | None = None
    swimming_badge: bool | None = None
    climbing_badge: str | None = None
    alpine_experience: str | None = None
    allergies: str | None = None
    medication: str | None = None
    tetanus_vaccination: str | None = None
    legal_guardians: str | None = None
    comments: str | None = None
    active: bool | None = None
    photos_may_be_taken: bool | None = None
    may_cancel_appointment_independently: bool | None = None
    # Relational fields (applied via *_id / .set() in the route).
    group_ids: list[int] | None = None
    user_id: int | None = None
    # Per-field permission-gated (members.may_change_organizationals).
    good_conduct_certificate_presented_date: Date | None = None
    has_key: bool | None = None
    has_free_ticket_gym: bool | None = None


# Scalar member fields that are safe to ``setattr`` directly; excludes the
# relational and per-field-gated fields handled explicitly in the route.
MEMBER_UPDATE_SCALAR_FIELDS = (
    "prename",
    "lastname",
    "email",
    "alternative_email",
    "phone_number",
    "birth_date",
    "gender",
    "street",
    "plz",
    "town",
    "address_extra",
    "country",
    "iban",
    "join_date",
    "leave_date",
    "dav_badge_no",
    "ticket_no",
    "swimming_badge",
    "climbing_badge",
    "alpine_experience",
    "allergies",
    "medication",
    "tetanus_vaccination",
    "legal_guardians",
    "comments",
    "active",
    "photos_may_be_taken",
    "may_cancel_appointment_independently",
)

# Fields gated on members.may_change_organizationals (Organizational fieldset).
MEMBER_ORGANIZATIONAL_FIELDS = (
    "good_conduct_certificate_presented_date",
    "has_key",
    "has_free_ticket_gym",
)


class RegistrationBrief(ModelSchema):
    """List representation of an unconfirmed registration (MemberUnconfirmedProxy).

    Backs the admin's registration ``list_display`` columns: name, birth date,
    age, groups, email-confirmation flags and whether the signed registration
    form was uploaded.
    """

    id: int
    name: str
    age: int | None = None
    groups: list[str] = []
    registration_form_uploaded: bool = False

    class Meta:
        model = Member
        fields = [
            "prename",
            "lastname",
            "email",
            "alternative_email",
            "birth_date",
            "confirmed_mail",
            "confirmed_alternative_mail",
        ]

    @staticmethod
    def resolve_age(obj) -> int | None:
        return obj.age() if obj.birth_date else None

    @staticmethod
    def resolve_groups(obj) -> list[str]:
        return [g.name for g in obj.group.all()]

    @staticmethod
    def resolve_registration_form_uploaded(obj) -> bool:
        return bool(obj.registration_form)


class TrainingBrief(ModelSchema):
    id: int
    member_id: int
    member_name: str
    category_id: int
    category_name: str
    activities: list[str] = []
    certificate: str | None = None

    class Meta:
        model = MemberTraining
        fields = ["title", "date", "participated", "passed"]

    @staticmethod
    def resolve_member_name(obj) -> str:
        return obj.member.name

    @staticmethod
    def resolve_category_name(obj) -> str:
        return obj.category.name

    @staticmethod
    def resolve_activities(obj) -> list[str]:
        return [a.name for a in obj.activity.all()]

    @staticmethod
    def resolve_certificate(obj) -> str | None:
        return obj.certificate.url if obj.certificate else None


class TrainingOut(ModelSchema):
    id: int
    member: MemberBrief
    category: str
    category_id: int
    activities: list[str]
    activity_ids: list[int] = []
    certificate: str | None = None

    class Meta:
        model = MemberTraining
        fields = ["title", "date", "comments", "participated", "passed"]

    @staticmethod
    def resolve_category(obj) -> str:
        return obj.category.name

    @staticmethod
    def resolve_activities(obj) -> list[str]:
        return [a.name for a in obj.activity.all()]

    @staticmethod
    def resolve_activity_ids(obj) -> list[int]:
        return [a.id for a in obj.activity.all()]

    @staticmethod
    def resolve_certificate(obj) -> str | None:
        return obj.certificate.url if obj.certificate else None


class MemberTrainingUpdate(Schema):
    """Editable training fields (the change-view fields, JSON-editable).

    All fields optional for PATCH semantics; only supplied fields are applied.
    ``member``/``category`` are set via their ids, ``activity`` via a list of
    ids. The ``certificate`` file is uploaded via a separate multipart route and
    is intentionally not part of this JSON schema.
    """

    title: str | None = None
    comments: str | None = None
    participated: bool | None = None
    passed: bool | None = None
    date: Date | None = None
    member_id: int | None = None
    category_id: int | None = None
    activity_ids: list[int] | None = None


class MemberTrainingCreate(Schema):
    """Create payload for a training record.

    ``member_id``, ``title`` and ``category_id`` are required (the model's
    non-null fields); ``activity_ids`` (M2M) is applied in the route.
    """

    title: str
    member_id: int
    category_id: int
    date: Date | None = None
    comments: str | None = None
    participated: bool | None = None
    passed: bool | None = None
    activity_ids: list[int] = []


class GroupUpdate(Schema):
    """Editable group fields (every editable change-view field).

    All fields optional for PATCH semantics; only supplied fields are applied.
    ``leiters`` (M2M) and ``contact_email`` (FK) are applied via ids in the route.
    """

    name: str | None = None
    description: str | None = None
    show_website: bool | None = None
    year_from: int | None = None
    year_to: int | None = None
    weekday: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    show_website_year: bool | None = None
    show_website_weekday: bool | None = None
    show_website_time: bool | None = None
    show_website_contact_email: bool | None = None
    show_website_registration: bool | None = None
    contact_email_id: int | None = None
    leiter_ids: list[int] | None = None


class GroupCreate(Schema):
    """Create payload for a group (``name`` required, everything else optional).

    Omitted scalar fields fall back to the model defaults; ``leiter_ids`` (M2M)
    and ``contact_email_id`` (FK) are applied in the route.
    """

    name: str
    description: str | None = None
    show_website: bool | None = None
    year_from: int | None = None
    year_to: int | None = None
    weekday: int | None = None
    start_time: time | None = None
    end_time: time | None = None
    contact_email_id: int | None = None
    leiter_ids: list[int] = []


# Scalar group fields that are safe to ``setattr`` directly (excludes the
# relational fields handled explicitly in the route).
GROUP_UPDATE_SCALAR_FIELDS = (
    "name",
    "description",
    "show_website",
    "year_from",
    "year_to",
    "weekday",
    "start_time",
    "end_time",
    "show_website_year",
    "show_website_weekday",
    "show_website_time",
    "show_website_contact_email",
    "show_website_registration",
)


class KlettertreffBrief(ModelSchema):
    id: int
    group: GroupBrief
    jugendleiter: list[str] = []

    class Meta:
        model = Klettertreff
        fields = ["date", "location", "topic"]

    @staticmethod
    def resolve_jugendleiter(obj) -> list[str]:
        return [jl.name for jl in obj.jugendleiter.all()]


class KlettertreffOut(ModelSchema):
    id: int
    group: GroupBrief
    jugendleiter: list[MemberBrief]
    attendees: list[MemberBrief]

    class Meta:
        model = Klettertreff
        fields = ["date", "location", "topic"]

    @staticmethod
    def resolve_jugendleiter(obj):
        return obj.jugendleiter.all()

    @staticmethod
    def resolve_attendees(obj):
        return [a.member for a in obj.klettertreffattendee_set.all()]


class KlettertreffUpdate(Schema):
    """Editable Klettertreff fields (every editable change-view field).

    All fields optional for PATCH semantics; only supplied fields are applied.
    ``group`` (FK) and ``jugendleiter`` (M2M) are applied via ids in the route.
    """

    date: Date | None = None
    location: str | None = None
    topic: str | None = None
    group_id: int | None = None
    jugendleiter_ids: list[int] | None = None


class KlettertreffCreate(Schema):
    """Create payload for a Klettertreff (``group_id`` required)."""

    date: Date | None = None
    location: str | None = None
    topic: str | None = None
    group_id: int
    jugendleiter_ids: list[int] = []


class MemberNoteListBrief(ModelSchema):
    id: int

    class Meta:
        model = MemberNoteList
        fields = ["title", "date"]


class MemberNoteListOut(ModelSchema):
    id: int
    members: list[MemberBrief]

    class Meta:
        model = MemberNoteList
        fields = ["title", "date"]

    @staticmethod
    def resolve_members(obj):
        return [mol.member for mol in obj.membersonlist.all()]


class MemberNoteListUpdate(Schema):
    """Editable member-note-list fields (the change-view fields).

    All fields optional for PATCH semantics; only supplied fields are applied.
    """

    title: str | None = None
    date: Date | None = None


class MemberNoteListCreate(Schema):
    """Create payload for a member note list (both fields optional)."""

    title: str | None = None
    date: Date | None = None


class MemberCreate(Schema):
    """Create payload for a member.

    Mirrors the required subset of the admin add form: ``prename`` / ``lastname``
    / ``gender`` are the model's non-defaulted fields; ``email`` and group
    membership are collected too (the admin form requires them). Other fields
    default per the model and are edited afterwards. ``group_ids`` (M2M) is
    applied in the route.
    """

    prename: str
    lastname: str
    gender: int
    email: str | None = None
    birth_date: Date | None = None
    phone_number: str | None = None
    comments: str | None = None
    group_ids: list[int] = []


class WaiterInviteIn(Schema):
    """Group selection + optional custom invitation text for the invite action."""

    group_id: int
    # When omitted, the group's default invitation template is used (mirrors the
    # admin's two-step form, which prefills the same template for editing).
    text: str | None = None


class InvitationBrief(ModelSchema):
    """Read-only representation of a waiter's group invitation (admin inline)."""

    id: int
    group: GroupBrief
    status: str

    class Meta:
        model = InvitationToGroup
        fields = ["date"]

    @staticmethod
    def resolve_status(obj) -> str:
        return str(obj.status())


class WaiterBrief(ModelSchema):
    id: int
    name: str
    age: int | None = None
    latest_group_invitation: str
    waiting_confirmed: bool | None = None

    class Meta:
        model = MemberWaitingList
        # The remaining fields back the admin ``list_display`` columns so the
        # SPA can search / filter / sort client-side.
        fields = [
            "prename",
            "lastname",
            "email",
            "birth_date",
            "gender",
            "application_date",
            "confirmed_mail",
            "sent_reminders",
        ]

    @staticmethod
    def resolve_age(obj) -> int | None:
        return obj.age() if obj.birth_date else None

    @staticmethod
    def resolve_latest_group_invitation(obj) -> str:
        return obj.latest_group_invitation()

    @staticmethod
    def resolve_waiting_confirmed(obj) -> bool | None:
        return obj.waiting_confirmed()


class WaiterOut(ModelSchema):
    id: int
    name: str
    age: int | None = None
    gender_str: str
    waiting_confirmed: bool | None = None
    latest_group_invitation: str
    invitations: list[InvitationBrief] = []

    class Meta:
        model = MemberWaitingList
        fields = [
            "prename",
            "lastname",
            "email",
            "birth_date",
            "gender",
            "application_text",
            "application_date",
            "comments",
            "confirmed_mail",
            "sent_reminders",
        ]

    @staticmethod
    def resolve_age(obj) -> int | None:
        return obj.age() if obj.birth_date else None

    @staticmethod
    def resolve_gender_str(obj) -> str:
        return obj.gender_str

    @staticmethod
    def resolve_waiting_confirmed(obj) -> bool | None:
        return obj.waiting_confirmed()

    @staticmethod
    def resolve_latest_group_invitation(obj) -> str:
        return obj.latest_group_invitation()

    @staticmethod
    def resolve_invitations(obj):
        return obj.invitationtogroup_set.order_by("-pk")


class WaiterUpdate(Schema):
    """Editable waiting-list fields (the change-view fields).

    All fields optional for PATCH semantics; only supplied fields are applied.
    """

    prename: str | None = None
    lastname: str | None = None
    email: str | None = None
    birth_date: Date | None = None
    gender: int | None = None
    application_text: str | None = None
    comments: str | None = None


# --- selector / choice schemas -------------------------------------------


class ActivityCategoryOut(ModelSchema):
    id: int
    ljp_category_display: str

    class Meta:
        model = ActivityCategory
        fields = ["name", "ljp_category", "description"]

    @staticmethod
    def resolve_ljp_category_display(obj) -> str:
        return str(obj.get_ljp_category_display())


class ActivityCategoryUpdate(Schema):
    """Create/patch payload for an activity category (all fields required for
    create; all optional for PATCH — only supplied fields are applied)."""

    name: str | None = None
    ljp_category: str | None = None
    description: str | None = None


class TrainingCategoryOut(ModelSchema):
    id: int

    class Meta:
        model = TrainingCategory
        fields = ["name", "permission_needed"]


class TrainingCategoryUpdate(Schema):
    """Create/patch payload for a training category."""

    name: str | None = None
    permission_needed: bool | None = None


class MemberEnumChoice(Schema):
    """A single ``{value, label}`` option of a member choice field."""

    value: Any
    label: str


# Rebuild MemberOut now that ExcursionBrief (used as a forward reference in
# ``activities``) is defined.
MemberOut.model_rebuild()
