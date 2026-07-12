"""Document / artifact generation endpoints for the ludwigsburgalpin API.

``TerminAdmin.make_overview`` is the admin action that exports the selected
``Termin`` rows as an Excel workbook. This route exposes that exact generator
(the bound admin method) so the spreadsheet layout can never diverge from the
admin, behind the same permission gate.

``Termin`` is a plain :class:`~django.contrib.admin.ModelAdmin` (not a
``CommonAdminMixin``), so it uses the default Django model permissions. The
``make_overview`` action carries no ``allowed_permissions`` restriction, so it
is available to anyone who can reach the changelist — i.e. the read-only
``ludwigsburgalpin.view_termin`` permission, which is what this export is gated
on (matching the ``view_termin`` gate the list/retrieve routes already use).

The admin method returns a ready-made :class:`~django.http.HttpResponse`
(``serve_media``) that already carries the correct ``Content-Type`` and
``Content-Disposition``; django-ninja returns such a response verbatim, so the
route declares no ``response`` schema.
"""

from contrib.api.perms import authorize
from django.contrib import admin
from ludwigsburgalpin.admin import TerminAdmin
from ludwigsburgalpin.models import Termin
from ninja import Router
from ninja import Schema

router = Router()


class LudwigsburgalpinTerminOverviewIn(Schema):
    """Termin selection for the overview export.

    ``termin_ids`` restricts the export to the given Termine (mirroring the
    admin action operating on the selected changelist queryset); ``None``
    exports every Termin.
    """

    termin_ids: list[int] | None = None


@router.post("/termine/overview")
def termin_overview(request, payload: LudwigsburgalpinTerminOverviewIn):
    """Excel overview of the selected Termine (``TerminAdmin.make_overview``).

    Gated on ``ludwigsburgalpin.view_termin``. The admin's bound generator is
    reused verbatim so the workbook layout stays identical.
    """
    authorize(request, "ludwigsburgalpin.view_termin")
    queryset = Termin.objects.all().order_by("start_date", "end_date")
    if payload.termin_ids is not None:
        queryset = queryset.filter(pk__in=payload.termin_ids)
    termin_admin = TerminAdmin(Termin, admin.site)
    return termin_admin.make_overview(request, queryset)
