"""The admin for the store: ruleset versions, roles, and the dry run.

Three pages, and between them they are what a treasurer needs from the store
without a shell:

* **the versions**, read-only, with their hash, their validity and whether
  their cases passed — plus the one action this page offers, "Import from
  configuration", which runs exactly what the container runs at start,
* **the roles**, which are the only editable thing here,
* **the dry run**, which is PR #257's two test pages generalised: pick a
  statement, see what *this* version would make of it — transfers, questions,
  checks, signatures — without touching the statement or its own snapshot.

Nothing in this module can change a stored version. The model refuses that
anyway (GoBD *Unveränderbarkeit*); the admin simply does not offer it.
"""

from contrib.admin import extra_button
from contrib.admin import ExtraButtonsMixin
from django.contrib import admin
from django.contrib import messages
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _

from .engine import ask
from .engine import configured_directory
from .engine import evaluate_statement
from .engine import import_from_directory
from .engine import no_queries
from .engine import ruleset_from_sources
from .engine import RulesetInvalid
from .engine import RulesetRejected
from .engine import statement_context
from .models import Statement
from .store import Obligation
from .store import RoleAssignment
from .store import RuleSet


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    """Who holds which section role, with dates.

    The rules read these as ``ctx.roles[…]``. What a role *means* is the
    section's business, so the name is free text rather than a choice list.
    """

    list_display = ["role", "member", "valid_from", "valid_to"]
    list_filter = ("role",)
    search_fields = ("role", "member__prename", "member__lastname")


class ObligationInline(admin.TabularInline):
    """The resolved payout, as it was written down.

    An obligation is a record, not a form: the rules write it and submission
    freezes it, so nothing here is editable — not even for a superuser, which
    is the point.
    """

    model = Obligation
    extra = 0
    can_delete = False
    fields = [
        "category",
        "source_display",
        "destination_display",
        "amount",
        "rule_id",
        "frozen_at",
    ]
    readonly_fields = fields
    verbose_name = _("Obligation")
    verbose_name_plural = _("Resolved payout")

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def get_queryset(self, request):
        # The current record. A superseded row is kept — the GoBD asks for that
        # — but the payout somebody is looking at is the one that stands.
        return super().get_queryset(request).filter(superseded_at__isnull=True)


@admin.register(RuleSet)
class RuleSetAdmin(ExtraButtonsMixin, admin.ModelAdmin):
    """The stored versions of the section's rules, read-only."""

    extra_buttons_model = RuleSet
    list_display = [
        "name",
        "short_hash",
        "state",
        "valid_from",
        "valid_to",
        "cases_passed_at",
        "statement_count",
    ]
    list_filter = ("name", "state")
    search_fields = ("hash", "name", "revision")
    fields = [
        "name",
        "hash",
        "state",
        "context_version",
        "revision",
        "engine_version",
        "valid_from",
        "valid_to",
        "imported_at",
        "activated_at",
        "retired_at",
        "cases_passed_at",
        "supersedes",
        "params",
        "manifest",
        "problems",
        "statement_count",
    ]
    readonly_fields = fields
    change_list_template = "admin/finance/ruleset/change_list.html"

    def has_add_permission(self, request, obj=None):
        # A version arrives by import, never by hand.
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def statement_count(self, obj):
        return obj.statements.count()

    statement_count.short_description = _("Statements")

    def changelist_view(self, request, extra_context=None):
        """The list, plus the one action this page offers: import.

        Posting to the changelist is how the button in the template asks for
        it, and the import itself is the same code the container start runs, so
        that the two can never drift apart.
        """
        if request.method == "POST" and "import_from_configuration" in request.POST:
            directory = configured_directory()
            if not directory.is_dir():
                messages.error(
                    request, _("There is no ruleset at %(path)s.") % {"path": str(directory)}
                )
            else:
                row, problems = import_from_directory(directory)
                if problems:
                    messages.error(
                        request,
                        _("%(name)s was stored as a draft and is not active.") % {"name": str(row)},
                    )
                    for problem in problems:
                        messages.warning(request, problem)
                else:
                    messages.success(request, _("%(name)s is now active.") % {"name": str(row)})
            return HttpResponseRedirect(request.get_full_path())
        context = dict(extra_context or {}, ruleset_directory=str(configured_directory()))
        return super().changelist_view(request, extra_context=context)

    # The button's default permission is "may change this object", and nobody
    # may change a stored version — so it asks for the permission that
    # actually applies: being allowed to look at one.
    @extra_button(_("Dry run"), permission="finance.view_ruleset")
    def dry_run_view(self, request, ruleset_row):
        """Resolve a real statement against this version, changing nothing."""
        statement_id = request.POST.get("statement") or request.GET.get("statement")
        statement = None
        result = None
        declarations = ()
        constraints = []
        try:
            loaded = ruleset_from_sources(ruleset_row.sources)
        except (RulesetInvalid, RulesetRejected) as refused:
            loaded = None
            messages.error(request, str(refused))
        if statement_id and loaded is not None:
            statement = Statement.objects.filter(pk=statement_id).first()
            if statement is None:
                messages.error(request, _("There is no statement %(id)s.") % {"id": statement_id})
            else:
                result = evaluate_statement(statement, ruleset=loaded)
                context = statement_context(statement, loaded, actors=True)
                # `ask` rather than `loaded.inputs`, so the dry run shows the
                # declarations as the form would serve them: the options of a
                # question that names an option source filled in, and a derived
                # question marked as one.
                declarations = tuple(ask(loaded, context))
                # The same guard the real evaluation runs under: a dry run of a
                # section's rules must not be the one place they may query.
                with no_queries():
                    constraints = loaded.approval(context, list(result.transfers))[0]
        return render(
            request,
            "admin/finance/ruleset/dry_run.html",
            context=dict(
                self.admin_site.each_context(request),
                title=_("Dry run"),
                view_header=_("Dry run"),
                opts=self.opts,
                object=ruleset_row,
                ruleset=ruleset_row,
                statement=statement,
                statements=Statement.objects.order_by("-pk")[:50],
                result=result,
                declarations=declarations,
                constraints=constraints,
            ),
        )
