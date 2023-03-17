from django.contrib import admin, messages
from django.forms import Textarea
from django.http import HttpResponse, HttpResponseRedirect
from django.db.models import TextField
from django.urls import path, reverse
from functools import update_wrapper
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render

from .models import Ledger, Statement, Receipt, Transaction, Bill, StatementSubmitted, StatementConfirmed

@admin.register(Ledger)
class LedgerAdmin(admin.ModelAdmin):
    pass


class BillOnStatementInline(admin.TabularInline):
    model = Bill
    extra = 0
    sortable_options = []
    fields = ['short_description', 'explanation', 'amount', 'paid_by', 'proof']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }

    def get_readonly_fields(self, request, obj=None):
        if obj is not None and obj.submitted:
            return self.fields
        return super(BillOnStatementInline, self).get_readonly_fields(request, obj)


@admin.register(Statement)
class StatementAdmin(admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'submitted']
    inlines = [BillOnStatementInline]

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
                "<path:object_id>/submit/",
                wrap(self.submit_view),
                name="%s_%s_submit" % (self.opts.app_label, self.opts.model_name),
            ),
        ]
        return custom_urls + urls

    def submit_view(self, request, object_id):
        statement = Statement.objects.get(pk=object_id)
        if statement.submitted:
            messages.error(request,
                    _("%(name)s is already submitted.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (statement._meta.app_label, statement._meta.model_name), args=(statement.pk,)))

        if "apply" in request.POST:
            statement.submit()
            messages.success(request,
                    _("Successfully submited %(name)s. The finance department will notify the requestors as soon as possible.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (statement._meta.app_label, statement._meta.model_name), args=(statement.pk,)))
        context = dict(self.admin_site.each_context(request),
                       title=_('Submit statement'),
                       opts=self.opts,
                       statement=statement)

        return render(request, 'admin/submit_statement.html', context=context)


class TransactionOnSubmittedStatementInline(admin.TabularInline):
    model = Transaction
    fields = ['amount', 'member', 'reference']
    formfield_overrides = {
        TextField: {'widget': Textarea(attrs={'rows': 1, 'cols': 40})}
    }
    extra = 0


class BillOnSubmittedStatementInline(BillOnStatementInline):
    model = Bill
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
    inlines = [BillOnSubmittedStatementInline, TransactionOnSubmittedStatementInline]

    def has_add_permission(self, request, obj=None):
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

    def overview_view(self, request, object_id):
        statement = Statement.objects.get(pk=object_id)
        if not statement.submitted:
            messages.error(request,
                    _("%(name)s is not yet submitted.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        if "confirm" in request.POST:
            statement.confirmed = True
            statement.save()
            for trans in statement.transaction_set.all():
                trans.confirmed = True
                trans.save()

        if "generate_transactions" in request.POST:
            if statement.transaction_set.count() > 0:
                messages.error(request,
                        _("%(name)s already has transactions. Please delete them first, if you want to generate new ones") % {'name': str(statement)})
            else:
                statement.generate_transactions()
                messages.success(request,
                        _("Successfully generated transactions for %(name)s") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        context = dict(self.admin_site.each_context(request),
                       title=_('View submitted statement'),
                       opts=self.opts,
                       statement=statement,
                       nights=statement.excursion.night_count,
                       price_per_night=statement.real_night_cost,
                       duration=statement.excursion.duration,
                       staff_count=statement.real_staff_count,
                       kilometers_traveled=statement.excursion.kilometers_traveled,
                       means_of_transport=statement.excursion.get_tour_approach(),
                       euro_per_km=statement.euro_per_km,
                       allowance_per_day=statement.ALLOWANCE_PER_DAY,
                       total_bills=statement.total_bills,
                       nights_per_yl=statement.nights_per_yl,
                       allowance_per_yl=statement.allowance_per_yl,
                       transportation_per_yl=statement.transportation_per_yl,
                       total_per_yl=statement.total_per_yl,
                       total_staff=statement.total_staff,
                       total=statement.total())

        return render(request, 'admin/overview_submitted_statement.html', context=context)

    def reduce_transactions_view(self, request, object_id):
        statement = Statement.objects.get(pk=object_id)
        statement.reduce_transactions()
        messages.success(request,
                _("Successfully reduced transactions for %(name)s.") % {'name': str(statement)})
        return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))

@admin.register(StatementConfirmed)
class StatementConfirmedAdmin(admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'confirmed']
    readonly_fields = fields


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    pass


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    pass


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['short_description', 'pretty_amount', 'paid_by', 'refunded']
