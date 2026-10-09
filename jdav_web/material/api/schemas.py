"""Read/write schemas for the material API.

Both material models are plain Django models with the default Django
permissions, so there is no member/row scoping here: the router gates every
endpoint on the standard ``material.<verb>_<model>`` permission. List rows use
the ``*Brief`` schemas, full detail is served by the richer ``*Out`` schemas.
"""

from datetime import date
from decimal import Decimal

from material.models import MaterialCategory
from material.models import MaterialPart
from members.api.schemas import MemberRef
from ninja import ModelSchema
from ninja import Schema


class MaterialCategoryBrief(ModelSchema):
    # Declared explicitly so the response contract types it as a required
    # non-null int (ModelSchema would otherwise mark the AutoField optional).
    id: int

    class Meta:
        model = MaterialCategory
        fields = ["name"]


class MaterialPartRef(Schema):
    """Minimal identity of a material part used inside related payloads."""

    id: int
    name: str


class MaterialCategoryOut(ModelSchema):
    id: int
    material_parts: list[MaterialPartRef]

    class Meta:
        model = MaterialCategory
        fields = ["name"]

    @staticmethod
    def resolve_material_parts(obj):
        return obj.materialpart_set.all()


class MaterialPartBrief(ModelSchema):
    id: int
    photo: str | None = None
    not_too_old: bool
    owner: MemberRef | None = None

    class Meta:
        model = MaterialPart
        fields = ["name", "description", "buy_date", "lifetime"]

    @staticmethod
    def resolve_photo(obj) -> str | None:
        return obj.photo.url if obj.photo else None

    @staticmethod
    def resolve_not_too_old(obj) -> bool:
        return obj.not_too_old()


class MaterialPartOut(ModelSchema):
    id: int
    photo: str | None = None
    not_too_old: bool
    categories: list[MaterialCategoryBrief]
    owner: MemberRef | None = None

    class Meta:
        model = MaterialPart
        fields = ["name", "description", "buy_date", "lifetime"]

    @staticmethod
    def resolve_photo(obj) -> str | None:
        return obj.photo.url if obj.photo else None

    @staticmethod
    def resolve_not_too_old(obj) -> bool:
        return obj.not_too_old()

    @staticmethod
    def resolve_categories(obj):
        return obj.material_cat.all()


class MaterialCategoryIn(Schema):
    name: str


class MaterialPartIn(Schema):
    name: str
    description: str = ""
    buy_date: date
    lifetime: Decimal
    material_cat: list[int] = []
    owner: int | None = None


class MaterialPartUpdate(Schema):
    """Editable subset for PATCH; only supplied fields are applied."""

    name: str | None = None
    description: str | None = None
    buy_date: date | None = None
    lifetime: Decimal | None = None
    material_cat: list[int] | None = None
    # ``null`` clears the owner; leaving the key out keeps it.
    owner: int | None = None
