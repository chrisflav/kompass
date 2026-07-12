"""Material API routes.

The material models (``MaterialCategory``, ``MaterialPart``, ``Ownership``) are
plain Django models with the default Django permissions, so every endpoint is
gated on the standard ``material.<verb>_<model>`` permission and returns the
full queryset — the member/row scoping used elsewhere does not apply here.
"""

from contrib.api.perms import authorize
from contrib.api.perms import set_scalar_fields
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from material.models import MaterialCategory
from material.models import MaterialPart
from material.models import Ownership
from members.models import Member
from ninja import File
from ninja import Form
from ninja import Router
from ninja import UploadedFile

from .schemas import MaterialCategoryBrief
from .schemas import MaterialCategoryIn
from .schemas import MaterialCategoryOut
from .schemas import MaterialPartBrief
from .schemas import MaterialPartIn
from .schemas import MaterialPartOut
from .schemas import MaterialPartUpdate
from .schemas import OwnershipIn
from .schemas import OwnershipOut
from .schemas import OwnershipUpdate

router = Router()

# ``MaterialPart.photo`` is a plain ``ImageField`` (no ``RestrictedFileField``),
# so the model defines no upload constraints. The API applies a basic image
# guard on upload to avoid accepting arbitrary binaries.
ALLOWED_PHOTO_TYPES = ("image/jpeg", "image/png", "image/gif")
MAX_PHOTO_SIZE = 10 * 1024 * 1024


def _validate_photo(photo):
    if photo.content_type not in ALLOWED_PHOTO_TYPES:
        raise ValidationError("Filetype not supported.")
    if photo.size > MAX_PHOTO_SIZE:
        raise ValidationError("File too large.")


# --- categories -----------------------------------------------------------


@router.get("/categories", response=list[MaterialCategoryBrief])
def list_categories(request):
    authorize(request, "material.view_materialcategory")
    return MaterialCategory.objects.all().order_by("name")


@router.get("/categories/{category_id}", response=MaterialCategoryOut)
def retrieve_category(request, category_id: int):
    authorize(request, "material.view_materialcategory")
    return get_object_or_404(MaterialCategory, pk=category_id)


@router.post("/categories", response=MaterialCategoryOut)
def create_category(request, payload: MaterialCategoryIn):
    authorize(request, "material.add_materialcategory")
    return MaterialCategory.objects.create(**payload.dict())


@router.put("/categories/{category_id}", response=MaterialCategoryOut)
def update_category(request, category_id: int, payload: MaterialCategoryIn):
    authorize(request, "material.change_materialcategory")
    category = get_object_or_404(MaterialCategory, pk=category_id)
    category.name = payload.name
    category.save()
    return category


@router.delete("/categories/{category_id}")
def delete_category(request, category_id: int):
    authorize(request, "material.delete_materialcategory")
    category = get_object_or_404(MaterialCategory, pk=category_id)
    category.delete()
    return {"success": True}


# --- parts ----------------------------------------------------------------


@router.get("/parts", response=list[MaterialPartBrief])
def list_parts(request):
    authorize(request, "material.view_materialpart")
    return MaterialPart.objects.all().order_by("name")


@router.get("/parts/{part_id}", response=MaterialPartOut)
def retrieve_part(request, part_id: int):
    authorize(request, "material.view_materialpart")
    return get_object_or_404(MaterialPart, pk=part_id)


@router.post("/parts", response=MaterialPartOut)
def create_part(request, payload: MaterialPartIn = Form(...), photo: UploadedFile = File(None)):
    """Create a part; ``photo`` is an optional multipart image upload."""
    authorize(request, "material.add_materialpart")
    if photo is not None:
        _validate_photo(photo)
    data = payload.dict()
    categories = data.pop("material_cat")
    part = MaterialPart(**data)
    if photo is not None:
        part.photo = photo
    part.save()
    if categories:
        part.material_cat.set(categories)
    return part


@router.patch("/parts/{part_id}", response=MaterialPartOut)
def update_part(request, part_id: int, payload: MaterialPartUpdate):
    authorize(request, "material.change_materialpart")
    part = get_object_or_404(MaterialPart, pk=part_id)
    data = payload.dict(exclude_unset=True)
    categories = data.pop("material_cat", None)
    set_scalar_fields(part, data, list(data.keys()))
    # Validate the model fields so bad values (e.g. lifetime exceeding the
    # DecimalField's max_digits) surface as a 422 instead of a DB error.
    part.full_clean(exclude=["photo", "material_cat"])
    part.save()
    if categories is not None:
        part.material_cat.set(categories)
    return part


@router.post("/parts/{part_id}/photo", response=MaterialPartOut)
def update_part_photo(request, part_id: int, photo: UploadedFile = File(...)):
    """Replace a part's photo via multipart upload.

    ``PATCH /parts/{id}`` is JSON-only and cannot carry a file, so the photo (an
    editable admin field) is updated through this dedicated multipart route.
    """
    authorize(request, "material.change_materialpart")
    part = get_object_or_404(MaterialPart, pk=part_id)
    _validate_photo(photo)
    part.photo = photo
    part.save()
    return part


@router.delete("/parts/{part_id}")
def delete_part(request, part_id: int):
    authorize(request, "material.delete_materialpart")
    part = get_object_or_404(MaterialPart, pk=part_id)
    part.delete()
    return {"success": True}


# --- ownerships -----------------------------------------------------------


@router.get("/ownerships", response=list[OwnershipOut])
def list_ownerships(request):
    authorize(request, "material.view_ownership")
    return Ownership.objects.all().order_by("pk")


@router.get("/ownerships/{ownership_id}", response=OwnershipOut)
def retrieve_ownership(request, ownership_id: int):
    authorize(request, "material.view_ownership")
    return get_object_or_404(Ownership, pk=ownership_id)


@router.post("/ownerships", response=OwnershipOut)
def create_ownership(request, payload: OwnershipIn):
    authorize(request, "material.add_ownership")
    material = get_object_or_404(MaterialPart, pk=payload.material)
    owner = get_object_or_404(Member, pk=payload.owner)
    return Ownership.objects.create(material=material, owner=owner, count=payload.count)


@router.patch("/ownerships/{ownership_id}", response=OwnershipOut)
def update_ownership(request, ownership_id: int, payload: OwnershipUpdate):
    authorize(request, "material.change_ownership")
    ownership = get_object_or_404(Ownership, pk=ownership_id)
    data = payload.dict(exclude_unset=True)
    if "material" in data:
        ownership.material = get_object_or_404(MaterialPart, pk=data.pop("material"))
    if "owner" in data:
        ownership.owner = get_object_or_404(Member, pk=data.pop("owner"))
    set_scalar_fields(ownership, data, list(data.keys()))
    ownership.save()
    return ownership


@router.delete("/ownerships/{ownership_id}")
def delete_ownership(request, ownership_id: int):
    authorize(request, "material.delete_ownership")
    ownership = get_object_or_404(Ownership, pk=ownership_id)
    ownership.delete()
    return {"success": True}
