"""ludwigsburgalpin API routes.

``Termin`` is a plain Django model with the default model permissions, so the
endpoints gate on the standard ``ludwigsburgalpin.<verb>_termin`` permissions
and return the full queryset (there is no member/row scoping for this model).
"""

from contrib.api.perms import authorize
from contrib.api.perms import set_scalar_fields
from django.shortcuts import get_object_or_404
from ludwigsburgalpin.models import Termin
from ninja import Router

from .choices import termin_choice_options
from .schemas import TerminBrief
from .schemas import TerminEnumChoice
from .schemas import TerminIn
from .schemas import TerminOut
from .schemas import TerminUpdate

router = Router()


@router.get("/enums", response=dict[str, list[TerminEnumChoice]])
def termin_enums(request):
    """Choice options for every Termin choice field, gated on ``view_termin``.

    Declared before the ``/termine/{termin_id}`` route so ninja's greedy string
    converter cannot shadow this static path.
    """
    authorize(request, "ludwigsburgalpin.view_termin")
    return termin_choice_options()


@router.get("/termine", response=list[TerminBrief])
def list_termine(request):
    """Termine the user may view (plain ``ludwigsburgalpin.view_termin`` perm)."""
    authorize(request, "ludwigsburgalpin.view_termin")
    return Termin.objects.all().order_by("start_date", "end_date")


@router.get("/termine/{termin_id}", response=TerminOut)
def retrieve_termin(request, termin_id: int):
    """Full Termin detail, gated on ``ludwigsburgalpin.view_termin``."""
    authorize(request, "ludwigsburgalpin.view_termin")
    return get_object_or_404(Termin, pk=termin_id)


@router.post("/termine", response={201: TerminOut})
def create_termin(request, payload: TerminIn):
    """Create a Termin, gated on ``ludwigsburgalpin.add_termin``.

    ``full_clean`` is run so invalid choices / values are rejected, matching the
    admin. The raised Django ``ValidationError`` is mapped to a 422 response by
    the root API's exception handler.
    """
    authorize(request, "ludwigsburgalpin.add_termin")
    termin = Termin(**payload.dict())
    termin.full_clean()
    termin.save()
    return 201, termin


@router.patch("/termine/{termin_id}", response=TerminOut)
def update_termin(request, termin_id: int, payload: TerminUpdate):
    """Update the editable subset of a Termin, gated on ``change_termin``.

    ``full_clean`` validates the mutated instance so invalid choices / values are
    rejected with 422, matching the admin.
    """
    authorize(request, "ludwigsburgalpin.change_termin")
    termin = get_object_or_404(Termin, pk=termin_id)
    data = payload.dict(exclude_unset=True)
    set_scalar_fields(termin, data, list(data.keys()))
    termin.full_clean()
    termin.save()
    return termin


@router.delete("/termine/{termin_id}", response={204: None})
def delete_termin(request, termin_id: int):
    """Delete a Termin, gated on ``ludwigsburgalpin.delete_termin``."""
    authorize(request, "ludwigsburgalpin.delete_termin")
    termin = get_object_or_404(Termin, pk=termin_id)
    termin.delete()
    return 204, None
