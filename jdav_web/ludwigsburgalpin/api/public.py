"""Public (unauthenticated) ludwigsburgalpin endpoints.

Mirrors the public ``TerminForm`` submission in ``ludwigsburgalpin.views.index``:
anyone may propose an event (``Termin``) via the section's website. The route
takes ``auth=None`` and, like the view, persists the submission without running
``full_clean`` (the stricter validation lives on the authenticated management
router).

The legacy ``published`` view only renders a static confirmation page — it
exposes no queryset — so there is no public event-list endpoint to mirror.
"""

from ludwigsburgalpin.models import Termin
from ninja import Router

from .schemas import TerminOut
from .schemas import TerminSubmit

router = Router()


@router.post("/termine", auth=None, response={201: TerminOut})
def submit_termin(request, payload: TerminSubmit):
    """Create a Termin from a public submission (mirrors the ``TerminForm`` view)."""
    termin = Termin.objects.create(**payload.dict())
    return 201, termin
