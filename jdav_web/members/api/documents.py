"""Document / artifact generation endpoints for the members API.

Per ``MIGRATION.md`` the backend generates PDFs / spreadsheets / documents on
request and serves them as artifacts. These routes own the generator functions
(``members.pdf`` / ``members.excel``, including the shared
``generate_crisis_intervention_list_pdf`` helper), each behind the permission
gate the retired admin enforced:

* **group overview / checklist** — the plain ``members.view_group`` permission.
* **excursion / note-list documents** — the ``may_view_excursion`` /
  ``may_view_notelist`` gate, i.e. ``view_global_member`` *or* a linked member
  that ``may_view`` every member on the list. That is captured exactly by the
  ``members.view_obj_member`` object permission (``may_view |
  view_global_member``), so authorizing each member on the list reproduces the
  gate without duplicating its logic (see :func:`_authorize_list_members`).

The generators return ready-made :class:`~django.http.HttpResponse` objects
(``serve_media`` / ``serve_pdf``) that already carry the correct ``Content-Type``
and ``Content-Disposition``; django-ninja returns such a response verbatim, so
the routes declare no ``response`` schema.
"""

from datetime import date

from contrib.api.perms import authorize
from contrib.media import ensure_media_dir
from contrib.media import serve_media
from django.conf import settings
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from finance.models import Bill
from members.excel import generate_group_overview
from members.excel import generate_ljp_vbk
from members.models import Freizeit
from members.models import Group
from members.models import Member
from members.models import MemberNoteList
from members.models import WEEKDAYS
from members.pdf import fill_pdf_form
from members.pdf import generate_crisis_intervention_list_pdf
from members.pdf import render_docx
from members.pdf import render_tex
from members.pdf import render_tex_with_attachments
from ninja import Router
from ninja import Schema
from utils import mondays_until_nth

router = Router()


# --- request schemas ------------------------------------------------------


class AdHocCrisisListIn(Schema):
    """Fields the admin's ``CrisisInterventionListForm`` collects for an ad-hoc
    crisis intervention list, plus the explicit member selection.
    """

    activity: str
    place: str
    start_date: date
    end_date: date
    description: str = ""
    member_ids: list[int]
    youth_leader_ids: list[int] = []
    group_ids: list[int] = []


class SjrApplicationIn(Schema):
    """The invoice selection the admin's ``GenerateSjrForm`` collects.

    ``bill_id`` identifies the bill whose uploaded proof is embedded as the
    invoice attachment; ``None`` produces the application without an invoice.
    """

    bill_id: int | None = None


# --- helpers --------------------------------------------------------------


def _authorize_list_members(request, memberlist):
    """Reproduce the admin's ``may_view_excursion`` / ``may_view_notelist`` gate.

    Authorizing every member on the list with ``view_obj_member`` (which is
    ``may_view | view_global_member``) is exactly equivalent to the admin's
    ``view_global_member or all(may_view(...))`` check.
    """
    for member_on_list in memberlist.membersonlist.all():
        authorize(request, "members.view_obj_member", member_on_list.member)


def _require_ljp_proposal(excursion):
    """Mirror ``decorate_download``: the LJP downloads need an LJP proposal."""
    if not hasattr(excursion, "ljpproposal"):
        raise ValidationError(
            _("This excursion does not have a LJP proposal. Please add one and try again.")
        )


# --- group documents ------------------------------------------------------


@router.post("/groups/overview")
def group_overview(request):
    """Excel overview of all groups (``GroupAdmin.group_overview``).

    Gated on ``members.view_group``.
    """
    authorize(request, "members.view_group")
    ensure_media_dir()
    filename = generate_group_overview(all_groups=Group.objects.all())
    return serve_media(filename=filename, content_type="application/xlsx")


@router.post("/groups/checklist")
def group_checklist(request):
    """PDF attendance checklist for the public groups (``group_checklist``).

    Gated on ``members.view_group``.
    """
    authorize(request, "members.view_group")
    ensure_media_dir()
    n_weeks = settings.GROUP_CHECKLIST_N_WEEKS
    n_members = settings.GROUP_CHECKLIST_N_MEMBERS
    context = {
        "groups": Group.objects.filter(show_website=True),
        "settings": settings,
        "week_range": range(n_weeks),
        "member_range": range(n_members),
        "dates": mondays_until_nth(n_weeks),
        "weekdays": [long for i, long in WEEKDAYS],
        "header_text": settings.GROUP_CHECKLIST_TEXT,
    }
    return render_tex("Gruppen-Checkliste", "members/group_checklist.tex", context)


# --- excursion documents --------------------------------------------------


@router.post("/excursions/{excursion_id}/crisis-intervention-list")
def excursion_crisis_intervention_list(request, excursion_id: int):
    """Crisis intervention list PDF for an excursion (``crisis_intervention_list``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    members = [mol.member for mol in excursion.membersonlist.all()]
    return generate_crisis_intervention_list_pdf(
        name=excursion.name,
        description=excursion.description,
        code=excursion.code,
        place=excursion.place,
        destination=excursion.destination,
        groups=excursion.groups.all(),
        staff=excursion.jugendleiter.all(),
        start_date=excursion.date,
        end_date=excursion.end,
        tour_type=excursion.get_tour_type_display(),
        tour_approach=excursion.get_tour_approach_display(),
        members=members,
    )


@router.post("/excursions/{excursion_id}/notes-list")
def excursion_notes_list(request, excursion_id: int):
    """Notes / skills overview PDF for an excursion (``notes_list``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    people, skills = excursion.skill_summary
    context = dict(memberlist=excursion, people=people, skills=skills, settings=settings)
    return render_tex(
        f"{excursion.code}_{excursion.name}_Notizen",
        "members/notes_list.tex",
        context,
        date=excursion.date,
    )


@router.post("/excursions/{excursion_id}/seminar-vbk")
def excursion_seminar_vbk(request, excursion_id: int):
    """Filled LJP V-BK Excel form for a seminar (``download_seminar_vbk``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    _require_ljp_proposal(excursion)
    ensure_media_dir()
    filename = generate_ljp_vbk(excursion)
    return serve_media(filename, "application/xlsx")


@router.post("/excursions/{excursion_id}/seminar-report-docx")
def excursion_seminar_report_docx(request, excursion_id: int):
    """Seminar report as a Word document (``download_seminar_report_docx``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    _require_ljp_proposal(excursion)
    title = excursion.ljpproposal.title
    context = dict(memberlist=excursion, settings=settings)
    return render_docx(
        f"{excursion.code}_{title}_Seminarbericht",
        "members/seminar_report_docx.tex",
        context,
        date=excursion.date,
    )


@router.post("/excursions/{excursion_id}/seminar-report-costs")
def excursion_seminar_report_costs(request, excursion_id: int):
    """Seminar cost / participant report PDF (``download_seminar_report_costs_and_participants``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    _require_ljp_proposal(excursion)
    title = excursion.ljpproposal.title
    context = dict(memberlist=excursion, settings=settings)
    return render_tex(
        f"{excursion.code}_{title}_TN_Kosten",
        "members/seminar_report.tex",
        context,
        date=excursion.date,
    )


@router.post("/excursions/{excursion_id}/ljp-proofs")
def excursion_ljp_proofs(request, excursion_id: int):
    """LJP proof PDF with the bill scans attached (``download_ljp_proofs``)."""
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    _require_ljp_proposal(excursion)
    if not hasattr(excursion, "statement"):
        raise ValidationError(_("This excursion does not have a statement."))
    statement = excursion.statement
    all_bills = list(statement.bill_set.all())
    context = dict(
        statement=statement,
        excursion=excursion,
        all_bills=all_bills,
        total_bills=statement.total_bills_theoretic,
        total_allowance=statement.total_allowance,
        total_theoretic=statement.total_theoretic,
        allowance_to=statement.allowance_to.all(),
        allowance_per_yl=statement.allowance_per_yl,
        settings=settings,
    )
    pdf_filename = f"{excursion.code}_{excursion.name}_LJP_Nachweis"
    attachments = [bill.proof.path for bill in all_bills if bill.proof]
    return render_tex_with_attachments(
        pdf_filename, "finance/ljp_statement.tex", context, attachments
    )


@router.post("/excursions/{excursion_id}/sjr-application")
def excursion_sjr_application(request, excursion_id: int, payload: SjrApplicationIn):
    """Filled SJR application PDF for an excursion (``sjr_application``).

    ``payload.bill_id`` selects the bill whose proof is embedded as the invoice;
    the bill must belong to the excursion's statement and carry a proof.
    """
    excursion = get_object_or_404(Freizeit, pk=excursion_id)
    _authorize_list_members(request, excursion)
    selected_attachments = []
    if payload.bill_id is not None:
        bill = get_object_or_404(Bill, pk=payload.bill_id)
        statement = getattr(excursion, "statement", None)
        if statement is None or bill.statement_id != statement.pk:
            raise ValidationError(_("The selected invoice does not belong to this excursion."))
        if not bill.proof:
            raise ValidationError(_("The selected invoice has no uploaded proof."))
        selected_attachments = [bill.proof.path]
    context = excursion.sjr_application_fields()
    title = excursion.ljpproposal.title if hasattr(excursion, "ljpproposal") else excursion.name
    return fill_pdf_form(
        f"{excursion.code}_{title}_SJR_Antrag",
        "members/sjr_template.pdf",
        context,
        selected_attachments,
        date=excursion.date,
    )


# --- note-list documents --------------------------------------------------


@router.post("/note-lists/{notelist_id}/summary")
def note_list_summary(request, notelist_id: int):
    """PDF summary of a member note list (``MemberNoteListAdmin.summary``)."""
    notelist = get_object_or_404(MemberNoteList, pk=notelist_id)
    _authorize_list_members(request, notelist)
    context = dict(memberlist=notelist, settings=settings)
    return render_tex(
        f"{notelist.title}_Zusammenfassung",
        "members/notelist_summary.tex",
        context,
        date=notelist.date,
    )


# --- ad-hoc crisis intervention list --------------------------------------


@router.post("/crisis-intervention-list")
def ad_hoc_crisis_intervention_list(request, payload: AdHocCrisisListIn):
    """Crisis intervention list PDF for an ad-hoc activity.

    Mirrors ``MemberAdmin.create_crisis_intervention_list_view``: the members are
    selected explicitly (``member_ids``) and the remaining activity details come
    from the request body. Every selected member is authorized with
    ``view_obj_member`` because the list exposes their (emergency) data.
    """
    members = list(Member.objects.filter(pk__in=payload.member_ids))
    if not members:
        raise ValidationError(_("Invalid member selection."))
    for member in members:
        authorize(request, "members.view_obj_member", member)
    groups = Group.objects.filter(pk__in=payload.group_ids)
    youth_leaders = Member.objects.filter(pk__in=payload.youth_leader_ids)
    return generate_crisis_intervention_list_pdf(
        name=payload.activity,
        description=payload.description,
        code=f"K-{timezone.now():%y%m%d}",
        place=payload.place,
        destination="",
        groups=list(groups),
        staff=list(youth_leaders),
        start_date=payload.start_date,
        end_date=payload.end_date,
        tour_type="",
        tour_approach="",
        members=members,
    )
