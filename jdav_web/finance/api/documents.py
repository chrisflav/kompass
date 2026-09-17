"""Finance document/artifact endpoints.

These expose the downloadable file artifacts the admin produces, returning the
generated file itself (not a JSON representation). The only genuine file
artifact ``StatementAdmin`` renders is the *statement summary* PDF
(``statement_summary_view`` → ``admin:finance_statement_summary``); the
"overview"/"submit" admin views only render interactive HTML admin pages bound
to the admin chrome, so they are intentionally not mirrored here.

Permission reuse: the summary download preserves the exact gate the admin's
``@extra_button`` enforces — the global ``finance.may_manage_confirmed_statements``
permission plus the ``statement.confirmed`` precondition. Generation reuses the
authoritative :func:`members.pdf.render_tex_with_attachments` helper and the
``finance/statement_summary.tex`` template, exactly as
``StatementAdmin.statement_summary_view`` does, so the two can never diverge.
"""

from contrib.api.perms import authorize
from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext_lazy as _
from finance.models import Statement
from members.pdf import render_tex_with_attachments
from ninja import Router

router = Router()


@router.get("/statements/{statement_id}/summary")
def statement_summary(request, statement_id: int):
    """Generate and return the statement summary PDF (the reimbursement receipt).

    Mirrors ``StatementAdmin.statement_summary_view``: only *confirmed*
    statements have a summary, and access is gated on the global
    ``finance.may_manage_confirmed_statements`` permission. The response is the
    compiled PDF (with every covered bill's proof appended as an attachment),
    served with ``Content-Type: application/pdf``.
    """
    statement = get_object_or_404(Statement, pk=statement_id)
    authorize(request, "finance.may_manage_confirmed_statements")
    if not statement.confirmed:
        raise ValidationError(_("Statement is not yet confirmed."))
    excursion = statement.excursion
    context = dict(statement=statement.template_context(), excursion=excursion, settings=settings)
    pdf_filename = (
        f"{excursion.code}_{excursion.name}_Zuschussbeleg" if excursion else "Abrechnungsbeleg"
    )
    attachments = [bill.proof.path for bill in statement.bills_covered if bill.proof]
    return render_tex_with_attachments(
        pdf_filename, "finance/statement_summary.tex", context, attachments
    )
