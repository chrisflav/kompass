from django.contrib import admin, messages
from django.forms import Textarea
from django.http import HttpResponse, HttpResponseRedirect
from django.db.models import TextField
from django.urls import path, reverse
from functools import update_wrapper
from django.utils.translation import gettext_lazy as _
from django.shortcuts import render

from .models import Ledger, Statement, Receipt, Transaction, Bill, StatementSubmitted

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


@admin.register(StatementSubmitted)
class StatementSubmittedAdmin(admin.ModelAdmin):
    fields = ['short_description', 'explanation', 'excursion', 'submitted']
    inlines = [BillOnStatementInline]

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
        ]
        return custom_urls + urls

    def overview_view(self, request, object_id):
        statement = Statement.objects.get(pk=object_id)
        if not statement.submitted:
            messages.error(request,
                    _("%(name)s is not yet submitted.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))

        if "apply" in request.POST:
            #statement.submit()
            #messages.success(request,
            #        _("Successfully submited %(name)s. The finance department will notify the requestors as soon as possible.") % {'name': str(statement)})
            return HttpResponseRedirect(reverse('admin:%s_%s_change' % (self.opts.app_label, self.opts.model_name), args=(statement.pk,)))
        context = dict(self.admin_site.each_context(request),
                       title=_('View submitted statement'),
                       opts=self.opts,
                       statement=statement,
                       total_bills=statement.total_bills(),
                       total_transportation=statement.total_transportation(),
                       total=statement.total())
        
        return render(request, 'admin/overview_submitted_statement.html', context=context)


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    pass


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    pass


@admin.register(Bill)
class BillAdmin(admin.ModelAdmin):
    list_display = ['short_description', 'pretty_amount', 'paid_by', 'refunded']
