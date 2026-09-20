"""Read/write schemas for the ludwigsburgalpin API.

``Termin`` is a plain Django model gated by the standard model permissions, so
there is no member/row scoping here: listing exposes the brief representation
and the retrieve endpoint returns the full detail. The choice fields are
serialized both as their stored code and, via ``resolve_*`` helpers, as their
human-readable display label.
"""

from datetime import date

from ludwigsburgalpin.models import Termin
from ninja import ModelSchema
from ninja import Schema


class TerminEnumChoice(Schema):
    """A single option for a Termin choice field.

    Consumed by ``GET /enums`` so the SPA can render labelled ``<select>``
    controls for the Termin choice fields (group/category/condition/technik/
    saison/eventart/klassifizierung). ``default`` marks the field's model
    default, which is what a blank create form preselects; a field without one
    (``group``) marks nothing and the form falls back to the first option.
    """

    value: str
    label: str
    default: bool


class TerminBrief(ModelSchema):
    # Declared explicitly so the response contract types it as a required
    # non-null int (ModelSchema would otherwise mark the AutoField optional).
    id: int
    start_date: date
    end_date: date
    group_display: str
    category_display: str

    class Meta:
        model = Termin
        fields = [
            "title",
            "subtitle",
            "group",
            "responsible",
            "category",
        ]

    @staticmethod
    def resolve_group_display(obj) -> str:
        return obj.get_group_display()

    @staticmethod
    def resolve_category_display(obj) -> str:
        return obj.get_category_display()


class TerminOut(ModelSchema):
    id: int
    start_date: date
    end_date: date
    group_display: str
    category_display: str
    condition_display: str
    technik_display: str
    saison_display: str
    eventart_display: str
    klassifizierung_display: str

    class Meta:
        model = Termin
        fields = [
            "title",
            "subtitle",
            "group",
            "responsible",
            "phone",
            "email",
            "category",
            "condition",
            "technik",
            "saison",
            "eventart",
            "klassifizierung",
            "equipment",
            "voraussetzungen",
            "description",
            "max_participants",
            "anforderung_hoehe",
            "anforderung_strecke",
            "anforderung_dauer",
        ]

    @staticmethod
    def resolve_group_display(obj) -> str:
        return obj.get_group_display()

    @staticmethod
    def resolve_category_display(obj) -> str:
        return obj.get_category_display()

    @staticmethod
    def resolve_condition_display(obj) -> str:
        return obj.get_condition_display()

    @staticmethod
    def resolve_technik_display(obj) -> str:
        return obj.get_technik_display()

    @staticmethod
    def resolve_saison_display(obj) -> str:
        return obj.get_saison_display()

    @staticmethod
    def resolve_eventart_display(obj) -> str:
        return obj.get_eventart_display()

    @staticmethod
    def resolve_klassifizierung_display(obj) -> str:
        return obj.get_klassifizierung_display()


class TerminIn(Schema):
    """Full writable payload for creating a ``Termin``.

    Required fields mirror the model's non-blank fields; the remaining fields
    carry the model defaults so a minimal create still validates.
    """

    title: str
    start_date: date
    end_date: date
    group: str
    responsible: str
    email: str
    subtitle: str = ""
    phone: str = ""
    category: str = "SON"
    condition: str = "mittel"
    technik: str = "mittel"
    saison: str = "ganzjährig"
    eventart: str = "Einzeltermin"
    klassifizierung: str = "Gemeinschaftstour"
    equipment: str = ""
    voraussetzungen: str = ""
    description: str = ""
    max_participants: int = 10
    anforderung_hoehe: int = 0
    anforderung_strecke: int = 0
    anforderung_dauer: int = 0


class TerminSubmit(Schema):
    """Public submission payload mirroring ``ludwigsburgalpin.views.TerminForm``.

    Field requiredness follows the public form, which is looser than the model's
    ``blank=False`` flags: the choice, date and numeric fields are required while
    the organizer / contact and free-text fields are optional. Like the view, the
    created ``Termin`` is *not* run through ``full_clean`` (that stricter check is
    reserved for the authenticated management router).
    """

    title: str
    subtitle: str
    start_date: date
    end_date: date
    group: str
    category: str
    condition: str
    technik: str
    saison: str
    eventart: str
    klassifizierung: str
    anforderung_hoehe: int
    anforderung_strecke: int
    anforderung_dauer: int
    max_participants: int
    description: str = ""
    equipment: str = ""
    voraussetzungen: str = ""
    responsible: str = ""
    phone: str = ""
    email: str = ""


class TerminUpdate(Schema):
    """Editable subset for PATCH semantics; only supplied fields are applied."""

    title: str | None = None
    subtitle: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    group: str | None = None
    responsible: str | None = None
    phone: str | None = None
    email: str | None = None
    category: str | None = None
    condition: str | None = None
    technik: str | None = None
    saison: str | None = None
    eventart: str | None = None
    klassifizierung: str | None = None
    equipment: str | None = None
    voraussetzungen: str | None = None
    description: str | None = None
    max_participants: int | None = None
    anforderung_hoehe: int | None = None
    anforderung_strecke: int | None = None
    anforderung_dauer: int | None = None
