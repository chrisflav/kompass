"""Read/write schemas for the material API.

All three material models are plain Django models with the default Django
permissions, so there is no member/row scoping here: the router gates every
endpoint on the standard ``material.<verb>_<model>`` permission. List rows use
the ``*Brief`` schemas, full detail is served by the richer ``*Out`` schemas.
"""

from datetime import date
from decimal import Decimal

from material.models import MaterialCategory
from material.models import MaterialPart
from material.models import Ownership
from members.api.schemas import MemberBrief
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


class PartOwnerBrief(Schema):
    """One ownership row as shown on a part (reproduces ``ownership_overview``).

    Resolved from an ``Ownership`` instance. ``owner_id`` is exposed for editing
    (the SPA can PATCH/create via the ``/ownerships`` endpoints), ``owner_name``
    for display. Named distinctly from ``OwnershipOut`` so ninja does not collide
    OpenAPI component keys.
    """

    id: int
    owner_id: int
    owner_name: str
    count: int

    @staticmethod
    def resolve_owner_name(obj) -> str:
        return str(obj.owner)


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
    quantity_real: str
    not_too_old: bool
    owners: list[PartOwnerBrief]

    class Meta:
        model = MaterialPart
        fields = ["name", "description", "quantity", "buy_date", "lifetime"]

    @staticmethod
    def resolve_photo(obj) -> str | None:
        return obj.photo.url if obj.photo else None

    @staticmethod
    def resolve_quantity_real(obj) -> str:
        return obj.quantity_real()

    @staticmethod
    def resolve_not_too_old(obj) -> bool:
        return obj.not_too_old()

    @staticmethod
    def resolve_owners(obj):
        return obj.ownership_set.all()


class MaterialPartOut(ModelSchema):
    id: int
    photo: str | None = None
    quantity_real: str
    not_too_old: bool
    categories: list[MaterialCategoryBrief]
    owners: list[PartOwnerBrief]

    class Meta:
        model = MaterialPart
        fields = ["name", "description", "quantity", "buy_date", "lifetime"]

    @staticmethod
    def resolve_photo(obj) -> str | None:
        return obj.photo.url if obj.photo else None

    @staticmethod
    def resolve_quantity_real(obj) -> str:
        return obj.quantity_real()

    @staticmethod
    def resolve_not_too_old(obj) -> bool:
        return obj.not_too_old()

    @staticmethod
    def resolve_categories(obj):
        return obj.material_cat.all()

    @staticmethod
    def resolve_owners(obj):
        return obj.ownership_set.all()


class OwnershipOut(ModelSchema):
    id: int
    owner: MemberBrief
    material: MaterialPartRef

    class Meta:
        model = Ownership
        fields = ["count"]


class MaterialCategoryIn(Schema):
    name: str


class MaterialPartIn(Schema):
    name: str
    description: str = ""
    quantity: int = 0
    buy_date: date
    lifetime: Decimal
    material_cat: list[int] = []


class MaterialPartUpdate(Schema):
    """Editable subset for PATCH; only supplied fields are applied."""

    name: str | None = None
    description: str | None = None
    quantity: int | None = None
    buy_date: date | None = None
    lifetime: Decimal | None = None
    material_cat: list[int] | None = None


class OwnershipIn(Schema):
    material: int
    owner: int
    count: int = 1


class OwnershipUpdate(Schema):
    material: int | None = None
    owner: int | None = None
    count: int | None = None
