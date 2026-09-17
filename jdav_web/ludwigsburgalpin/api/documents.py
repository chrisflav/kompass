"""Document / artifact generation endpoints for the ludwigsburgalpin API.

Exports the selected ``Termin`` rows as an Excel workbook, via
:func:`ludwigsburgalpin.excel.generate_termin_overview` — the generator the
retired admin action used to carry.

``Termin`` used the default Django model permissions and the export action
carried no extra restriction, so it is gated on the read-only
``ludwigsburgalpin.view_termin`` permission, the same gate the list/retrieve
routes use.

The generator returns a ready-made :class:`~django.http.HttpResponse`
(``serve_media``) that already carries the correct ``Content-Type`` and
``Content-Disposition``; django-ninja returns such a response verbatim, so the
route declares no ``response`` schema.
"""

from contrib.api.perms import authorize
from ludwigsburgalpin.excel import generate_termin_overview
from ludwigsburgalpin.models import Termin
from ninja import Router
from ninja import Schema

router = Router()


class LudwigsburgalpinTerminOverviewIn(Schema):
    """Termin selection for the overview export.

    ``termin_ids`` restricts the export to the given Termine; ``None`` exports
    every Termin.
    """

    termin_ids: list[int] | None = None


@router.post("/termine/overview")
def termin_overview(request, payload: LudwigsburgalpinTerminOverviewIn):
    """Excel overview of the selected Termine.

    Gated on ``ludwigsburgalpin.view_termin``.
    """
    authorize(request, "ludwigsburgalpin.view_termin")
    queryset = Termin.objects.all().order_by("start_date", "end_date")
    if payload.termin_ids is not None:
        queryset = queryset.filter(pk__in=payload.termin_ids)
    return generate_termin_overview(queryset)
