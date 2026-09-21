"""Public (unauthenticated) ludwigsburgalpin endpoints.

Mirrors the public ``TerminForm`` submission in ``ludwigsburgalpin.views.index``:
anyone may propose an event (``Termin``) via the section's website. The routes
take ``auth=None``; the submission, like the view, is persisted without running
``full_clean`` (the stricter validation lives on the authenticated management
router), and ``/enums`` serves the choice lists the form's selects are built
from.

The legacy ``published`` view only renders a static confirmation page — it
exposes no queryset — so there is no public event-list endpoint to mirror.
"""

from ludwigsburgalpin.models import Termin
from ninja import Router

from .choices import termin_choice_options
from .schemas import TerminEnumChoice
from .schemas import TerminOut
from .schemas import TerminSubmit

router = Router()


@router.get("/enums", auth=None, response=dict[str, list[TerminEnumChoice]])
def public_termin_enums(request):
    """Choice options for the submission form, mirroring the authenticated ``/enums``.

    The legacy ``TerminForm`` rendered these selects server-side for anonymous
    visitors, so the SPA needs the same lists without a bearer token; they are
    model metadata, not data about anyone.
    """
    return termin_choice_options()


@router.post("/termine", auth=None, response={201: TerminOut})
def submit_termin(request, payload: TerminSubmit):
    """Create a Termin from a public submission (mirrors the ``TerminForm`` view)."""
    termin = Termin.objects.create(**payload.dict())
    return 201, termin
