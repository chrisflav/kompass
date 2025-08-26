from django.contrib import admin, messages
from django.utils.safestring import mark_safe
from django import forms
from django.forms import Textarea, ClearableFileInput
from django.http import HttpResponse, HttpResponseRedirect
from django.db.models import TextField, Q
from django.urls import path, reverse
from functools import update_wrapper
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render
from django.conf import settings

from contrib.admin import CommonAdminInlineMixin, CommonAdminMixin
from utils import get_member, RestrictedFileField

from rules.contrib.admin import ObjectPermissionsModelAdmin
from members.pdf import render_tex_with_attachments

from .models import Ledger, Statement, Receipt, Transaction, Bill, StatementSubmitted, StatementConfirmed,\
        StatementUnSubmitted, BillOnStatementProxy


@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    search_fields = ('name', )


class BillOnStatementInlineForm(forms.ModelForm):
    class Meta:
        model = BillOnStatementProxy
        fields = ['short_description', 'explanation', 'amount', 'paid_by', 'proof']
        widgets = {
            'proof': ClearableFileInput(attrs={'accept': 'application/pdf,image/jpeg,image/png'}),
            'explanation': Textarea(attrs={'rows': 1, 'cols': 40})
        }


class BillOnStatementInline(CommonAdminInlineMixin, admin.TabularInline):
    model = BillOnStatementProxy
    extra = 0
    sortable_options = []
    form = BillOnStatementInlineForm


def decorate_statement_view(model, perm=None):
    def decorator(fun):
        def aux(self, request, object_id):
            try:
                statement = model.objects.get(pk=object_id)
            except model.DoesNotExist:
                messages.error(request, _('Statement not found.'))
                return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))
            permitted = self.has_change_permission(request, statement) if not perm else request.user.has_perm(perm)
            if not permitted:
                messages.error(request, _('Insufficient permissions.'))
                return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))
            return fun(self, request, statement)
        return aux
    return decorator


@admin.register(StatementUnSubmitted)
class StatementUnSubmittedAdmin(CommonAdminMixin, admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'submitted']
    list_display = ['__str__', 'excursion', 'created_by']
    inlines = [BillOnStatementInline]

    def save_model(self, request, obj, form, change):
        if not change and hasattr(request.user, 'member'):
            obj.created_by = request.user.member
        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = ['submitted', 'excursion']
        if obj is not None and obj.submitted:
            return readonly_fields + self.fields
        else:
            return readonly_fields

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/submit/",
                wrap(self.submit_view),
                name="%s_%s_submit" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    @decorate_statement_view(Statement)
    def submit_view(self, request, statement):
        if statement.submitted:
            messages.error(request,
                    _("%(name)s is already submitted.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        if "apply" in request.POST:
            statement.submit(get_member(request))
            messages.success(request,
                    _("Successfully submited %(name)s. The finance department will notify the requestors as soon as possible.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        if statement.excursion:
            memberlist = statement.excursion
            context = dict(self.admin_site.each_context(request),
                       title=_('Finance overview'),
                       opts=self.opts,
                       memberlist=memberlist,
                       object=memberlist,
                       ljp_contributions=memberlist.payable_ljp_contributions,
                       total_relative_costs=memberlist.total_relative_costs,
                       **memberlist.statement.template_context())
            return render(request, 'admin/freizeit_finance_overview.html', context=context)
        else:
            context = dict(self.admin_site.each_context(request),
                title=_('Submit statement'),
                opts=self.opts,
                statement=statement)
            return render(request, 'admin/submit_statement.html', context=context)


class TransactionOnSubmittedStatementInline(admin.TabularInline):
    model = Transaction
    fields = ['amount', 'member', 'reference', 'text_length_warning', 'ledger']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    readonly_fields = ['text_length_warning']
    extra = 0

    def text_length_warning(self, obj):
        """Display reference length, warn if exceeds 140 characters."""
        len_reference = len(obj.reference)
        len_string = f"{len_reference}/140"
        if len_reference > 140:
            return mark_safe(f'<span style="color: red;">{len_string}</span>')

        return len_string
    text_length_warning.short_description = _("Length")


class BillOnSubmittedStatementInline(BillOnStatementInline):
    model = BillOnStatementProxy
    extra = 0
    sortable_options = []
    fields = ['short_description', 'explanation', 'amount', 'paid_by', 'proof', 'costs_covered']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }

    def get_readonly_fields(self, request, obj=None):
        return ['short_description', 'explanation', 'amount', 'paid_by', 'proof']


@admin.register(StatementSubmitted)
class StatementSubmittedAdmin(admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'submitted']
    list_display = ['__str__', 'is_valid', 'submitted_date', 'submitted_by']
    ordering = ('-submitted_date',)
    inlines = [BillOnSubmittedStatementInline, TransactionOnSubmittedStatementInline]

    def has_add_permission(self, request, obj=None):
        # Submitted statements should not be added directly, but instead be created
        # as unsubmitted statements and then submitted.
        return False

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('finance.process_statementsubmitted')

    def has_delete_permission(self, request, obj=None):
        # Submitted statements should not be deleted. Instead they can be rejected
        # and then deleted as unsubmitted statements.
        return False

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = ['submitted']
        if obj is not None and obj.submitted:
            return readonly_fields + self.fields
        else:
            return readonly_fields

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/overview/",
                wrap(self.overview_view),
                name="%s_%s_overview" % (self.opts.app_label, self.opts.model_name),
            ),
            path(
                "<path:object_id>/reduce_transactions/",
                wrap(self.reduce_transactions_view),
                name="%s_%s_reduce_transactions" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    @decorate_statement_view(StatementSubmitted)
    def overview_view(self, request, statement):
        if not statement.submitted:
            messages.error(request,
                    _("%(name)s is not yet submitted.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        if "transaction_execution_confirm" in request.POST or "transaction_execution_confirm_and_send" in request.POST:
            res = statement.confirm(confirmer=get_member(request))
            if not res:
                # this should NOT happen!
                messages.error(request,
                        _("An error occured while trying to confirm %(name)s. Please try again.") % {'name': str(statement)})
                return HttpResponseRedirect(reverse('admin:%s_%s_overview' % (self.opts.app_label, self.opts.model_name)))

            if "transaction_execution_confirm_and_send" in request.POST:
                statement.send_summary(cc=[request.user.member.email] if hasattr(request.user, 'member') else [])
                messages.success(request, _("Successfully sent receipt to the office."))
            messages.success(request,
                    _("Successfully confirmed %(name)s. I hope you executed the associated transactions, I wont remind you again.")
                    % {'name': str(statement)})
            download_link = reverse('admin:finance_statementconfirmed_summary', args=(statement.pk,))
            messages.success(request,
                             mark_safe(_("You can download a <a href='%(link)s', target='_blank'>receipt</a>.") % {'link': download_link}))
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))
        if "confirm" in request.POST:
            res = statement.validity
            if res == Statement.VALID:
                context = dict(self.admin_site.each_context(request),
                               title=_('Statement confirmed'),
                               opts=self.opts,
                               statement=statement)
                return render(request, 'admin/confirmed_statement.html', context=context)
            elif res == Statement.NON_MATCHING_TRANSACTIONS:
                messages.error(request,
                        _("Transactions do not match the covered expenses. Please correct the mistakes listed below.")
                        % {'name': str(statement)})
                return HttpResponseRedirect(reverse('admin:%s_%s_overview' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
            elif res == Statement.MISSING_LEDGER:
                messages.error(request,
                        _("Some transactions have no ledger configured. Please fill in the gaps.")
                        % {'name': str(statement)})
                return HttpResponseRedirect(reverse('admin:%s_%s_overview' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
            elif res == Statement.INVALID_ALLOWANCE_TO:
                messages.error(request,
                               _("The configured recipients for the allowance don't match the regulations. Please correct this on the excursion."))
                return HttpResponseRedirect(reverse('admin:%s_%s_overview' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
            elif res == Statement.INVALID_TOTAL:
                messages.error(request,
                               _("The calculated total amount does not match the sum of all transactions. This is most likely a bug."))
                return HttpResponseRedirect(reverse('admin:%s_%s_overview' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        if "reject" in request.POST:
            statement.submitted = False
            statement.save()
            messages.success(request,
                    _("Successfully rejected %(name)s. The requestor can reapply, when needed.")
                    % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        if "generate_transactions" in request.POST:
            if statement.transaction_set.count() > 0:
                messages.error(request,
                        _("%(name)s already has transactions. Please delete them first, if you want to generate new ones") % {'name': str(statement)})
            else:
                success = statement.generate_transactions()
                if success:
                    messages.success(request,
                            _("Successfully generated transactions for %(name)s") % {'name': str(statement)})
                else:
                    messages.error(request,
                            _("Error while generating transactions for %(name)s. Do all bills have a payer and, if this statement is attached to an excursion, was a person selected that receives the subsidies?") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        context = dict(self.admin_site.each_context(request),
                       title=_('View submitted statement'),
                       opts=self.opts,
                       statement=statement,
                       settings=settings,
                       transaction_issues=statement.transaction_issues,
                       **statement.template_context())

        return render(request, 'admin/overview_submitted_statement.html', context=context)

    @decorate_statement_view(StatementSubmitted)
    def reduce_transactions_view(self, request, statement):
        statement.reduce_transactions()
        messages.success(request,
                _("Successfully reduced transactions for %(name)s.") % {'name': str(statement)})
        return HttpResponseRedirect(request.GET['redirectTo'])
        #return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))


@admin.register(StatementConfirmed)
class StatementConfirmedAdmin(admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'confirmed']
    #readonly_fields = fields
    list_display = ['__str__', 'total_pretty', 'confirmed_date', 'confirmed_by']
    ordering = ('-confirmed_date',)
    inlines = [BillOnSubmittedStatementInline, TransactionOnSubmittedStatementInline]

    def has_add_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to add confirmed statements
        return False

    def has_change_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to change confirmed statements
        return False

    def has_delete_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to delete confirmed statements
        return False

    def get_urls(self):
        urls = super().get_urls()

        def wrap(view):
            def wrapper(*args, **kwargs):
                return self.admin_site.admin_view(view)(*args, **kwargs)

            wrapper.model_admin = self
            return update_wrapper(wrapper, view)

        custom_urls = [
            path(
                "<path:object_id>/unconfirm/",
                wrap(self.unconfirm_view),
                name="%s_%s_unconfirm" % (self.opts.app_label, self.opts.model_name),
            ),
            path(
                "<path:object_id>/summary/",
                wrap(self.statement_summary_view),
                name="%s_%s_summary" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    @decorate_statement_view(StatementConfirmed, perm='finance.may_manage_confirmed_statements')
    def unconfirm_view(self, request, statement):
        if not statement.confirmed:
            messages.error(request,
                    _("%(name)s is not yet confirmed.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        if "unconfirm" in request.POST:
            statement.confirmed = False
            statement.confirmed_date = None
            statement.confired_by = None
            statement.save()

            messages.success(request,
                    _("Successfully unconfirmed %(name)s. I hope you know what you are doing.")
                    % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_changelist' % (self.opts.app_label, self.opts.model_name)))

        context = dict(self.admin_site.each_context(request),
                       title=_('Unconfirm statement'),
                       opts=self.opts,
                       statement=statement)

        return render(request, 'admin/unconfirm_statement.html', context=context)

    @decorate_statement_view(StatementConfirmed, perm='finance.may_manage_confirmed_statements')
    def statement_summary_view(self, request, statement):
        if not statement.confirmed:
            messages.error(request,
                    _("%(name)s is not yet confirmed.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        excursion = statement.excursion
        context = dict(statement=statement.template_context(), excursion=excursion, settings=settings)

        pdf_filename = f"{excursion.code}_{excursion.name}_Zuschussbeleg" if excursion else f"Abrechnungsbeleg"
        attachments = [bill.proof.path for bill in statement.bills_covered if bill.proof]
        return render_tex_with_attachments(pdf_filename, 'finance/statement_summary.tex', context, attachments)

    statement_summary_view.short_description = _('Download summary')


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    """The transaction admin site. This is only used to display transactions. All editing
    is disabled on this site. All transactions should be changed on the respective statement
    at the correct stage of the approval chain."""
    list_display = ['member', 'ledger', 'amount', 'reference', 'statement', 'confirmed',
            'confirmed_date', 'confirmed_by']
    list_filter = ('ledger', 'member', 'statement', 'confirmed')
    search_fields = ('reference', )
    fields = ['reference', 'amount', 'member', 'ledger', 'statement']

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.confirmed:
            return self.fields
        return super(TransactionAdmin, self).get_readonly_fields(request, obj)

    def has_add_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to add transactions
        return False

    def has_change_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to change transactions
        return False

    def has_delete_permission(self, request, obj=None):
        # To preserve integrity, no one is allowed to delete transactions
        return False


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['__str__', 'statement', 'explanation', 'pretty_amount', 'paid_by', 'refunded']
    list_filter = ('statement', 'paid_by', 'refunded')
    search_fields = ('reference', 'statement')
