import math
from itertools import groupby
from decimal import Decimal, ROUND_HALF_DOWN
from django.utils import timezone
from .rules import is_creator, not_submitted, leads_excursion
from members.rules import is_leader, statement_not_submitted

from django.db import models
from django.utils.translation import gettext_lazy as _
from members.models import Member, Freizeit, OEFFENTLICHE_ANREISE, MUSKELKRAFT_ANREISE
from django.conf import settings
import rules
from contrib.models import CommonModel
from contrib.rules import has_global_perm

# Create your models here.

class Ledger(models.Model):
    name = models.CharField(verbose_name=_('Name'), max_length=30)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Ledger')
        verbose_name_plural = _('Ledgers')


class TransactionIssue:
    def __init__(self, member, current, target):
        self.member, self.current, self.target = member, current, target

    @property
    def difference(self):
        return self.target - self.current


class StatementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(submitted=False, confirmed=False)


class Statement(CommonModel):
    MISSING_LEDGER, NON_MATCHING_TRANSACTIONS, VALID = 0, 1, 2

    short_description = models.CharField(verbose_name=_('Short description'),
                                         max_length=30,
                                         blank=True)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    excursion = models.OneToOneField(Freizeit, verbose_name=_('Associated excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    night_cost = models.DecimalField(verbose_name=_('Price per night'), default=0, decimal_places=2, max_digits=5)

    submitted = models.BooleanField(verbose_name=_('Submitted'), default=False)
    submitted_date = models.DateTimeField(verbose_name=_('Submitted on'), default=None, null=True)
    confirmed = models.BooleanField(verbose_name=_('Confirmed'), default=False)
    confirmed_date = models.DateTimeField(verbose_name=_('Paid on'), default=None, null=True)

    created_by = models.ForeignKey(Member, verbose_name=_('Created by'),
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL,
                                   related_name='created_statements')
    submitted_by = models.ForeignKey(Member, verbose_name=_('Submitted by'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL,
                                     related_name='submitted_statements')
    confirmed_by = models.ForeignKey(Member, verbose_name=_('Authorized by'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL,
                                     related_name='confirmed_statements')

    class Meta(CommonModel.Meta):
        verbose_name = _('Statement')
        verbose_name_plural = _('Statements')
        permissions = [
            ('may_edit_submitted_statements', 'Is allowed to edit submitted statements')
        ]
        rules_permissions = {
            # this is suboptimal, but Statement is only ever used as an inline on Freizeit
            # so we check for excursion permissions
            'add_obj': is_leader,
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader & statement_not_submitted,
            'delete_obj': is_leader & statement_not_submitted,
        }

    def __str__(self):
        if self.excursion is not None:
            return _('Statement: %(excursion)s') % {'excursion': str(self.excursion)}
        else:
            return self.short_description

    def submit(self, submitter=None):
        self.submitted = True
        self.submitted_date = timezone.now()
        self.submitted_by = submitter
        self.save()

    @property
    def transaction_issues(self):
        needed_paiments = [(b.paid_by, b.amount) for b in self.bill_set.all() if b.costs_covered and b.paid_by]

        if self.excursion is not None:
            needed_paiments.extend([(yl, self.real_per_yl) for yl in self.excursion.jugendleiter.all()])

        needed_paiments = sorted(needed_paiments, key=lambda p: p[0].pk)
        target = dict(map(lambda p: (p[0], sum([x[1] for x in p[1]])), groupby(needed_paiments, lambda p: p[0])))

        transactions = sorted(self.transaction_set.all(), key=lambda trans: trans.member.pk)
        current = dict(map(lambda p: (p[0], sum([t.amount for t in p[1]])), groupby(transactions, lambda trans: trans.member)))

        issues = []
        for member, amount in target.items():
            if amount == 0 and member not in current:
                continue
            elif member not in current:
                issue = TransactionIssue(member=member, current=0, target=amount)
                issues.append(issue)
            elif current[member] != amount:
                issue = TransactionIssue(member=member, current=current[member], target=amount)
                issues.append(issue)

        for member, amount in current.items():
            if amount != 0 and member not in target:
                issue = TransactionIssue(member=member, current=amount, target=0)
                issues.append(issue)

        return issues

    @property
    def ledgers_configured(self):
        return all([trans.ledger is not None for trans in self.transaction_set.all()])

    @property
    def transactions_match_expenses(self):
        return len(self.transaction_issues) == 0

    def is_valid(self):
        return self.ledgers_configured and self.transactions_match_expenses
    is_valid.boolean = True
    is_valid.short_description = _('Ready to confirm')

    @property
    def validity(self):
        if not self.transactions_match_expenses:
            return Statement.NON_MATCHING_TRANSACTIONS
        if not self.ledgers_configured:
            return Statement.MISSING_LEDGER
        else:
            return Statement.VALID

    def confirm(self, confirmer=None):
        if not self.submitted:
            return False

        if not self.validity == Statement.VALID:
            return False

        self.confirmed = True
        self.confirmed_date = timezone.now()
        self.confirmed_by = confirmer
        for trans in self.transaction_set.all():
            trans.confirmed = True
            trans.confirmed_date = timezone.now()
            trans.confirmed_by = confirmer
            trans.save()
        self.save()
        return True

    def generate_transactions(self):
        # bills
        for bill in self.bill_set.all():
            if not bill.costs_covered:
                continue
            if not bill.paid_by:
                return False
            ref = "{}: {}".format(str(self), bill.short_description)
            Transaction(statement=self, member=bill.paid_by, amount=bill.amount, confirmed=False, reference=ref).save()

        # excursion specific
        if self.excursion is None:
            return

        for yl in self.excursion.jugendleiter.all():
            ref = _("Compensation for %(excu)s") % {'excu': self.excursion.name}
            Transaction(statement=self, member=yl, amount=self.real_per_yl, confirmed=False, reference=ref).save()
        return True

    def reduce_transactions(self):
        # to minimize the number of needed bank transactions, we bundle transactions from same ledger to
        # same member
        transactions = self.transaction_set.all()
        if any((t.ledger is None for t in transactions)):
            return

        sort_key = lambda trans: (trans.member.pk, trans.ledger.pk)
        group_key = lambda trans: (trans.member, trans.ledger)
        transactions = sorted(transactions, key=sort_key)
        for pair, transaction_group in groupby(transactions, group_key):
            member, ledger = pair
            grp = list(transaction_group)
            if len(grp) == 1:
                continue

            new_amount = sum((trans.amount for trans in grp))
            new_ref = "\n".join((trans.reference for trans in grp))
            Transaction(statement=self, member=member, amount=new_amount, confirmed=False, reference=new_ref,
                        ledger=ledger).save()
            for trans in grp:
                trans.delete()

    @property
    def total_bills(self):
        return sum([bill.amount for bill in self.bill_set.all() if bill.costs_covered])

    @property
    def total_bills_theoretic(self):
        return sum([bill.amount for bill in self.bill_set.all()])

    @property
    def euro_per_km(self):
        if self.excursion is None:
            return 0

        if self.excursion.tour_approach == MUSKELKRAFT_ANREISE \
                or self.excursion.tour_approach == OEFFENTLICHE_ANREISE:
            return 0.15
        else:
            return 0.1

    @property
    def transportation_per_yl(self):
        if self.excursion is None:
            return 0

        return cvt_to_decimal(self.excursion.kilometers_traveled * self.euro_per_km)

    @property
    def allowance_per_yl(self):
        if self.excursion is None:
            return 0

        return cvt_to_decimal(self.excursion.duration * settings.ALLOWANCE_PER_DAY)

    @property
    def total_allowance(self):
        return self.allowance_per_yl * self.real_staff_count

    @property
    def total_transportation(self):
        return self.transportation_per_yl * self.real_staff_count

    @property
    def real_night_cost(self):
        return min(self.night_cost, settings.MAX_NIGHT_COST)

    @property
    def nights_per_yl(self):
        if self.excursion is None:
            return 0

        return self.excursion.night_count * self.real_night_cost

    @property
    def total_nights(self):
        return self.nights_per_yl * self.real_staff_count

    @property
    def total_per_yl(self):
        return self.transportation_per_yl \
                + self.allowance_per_yl \
                + self.nights_per_yl

    @property
    def real_per_yl(self):
        if self.excursion is None:
            return 0

        return cvt_to_decimal(self.total_staff / self.excursion.staff_count)

    @property
    def total_staff(self):
        return self.total_per_yl * self.real_staff_count

    @property
    def real_staff_count(self):
        if self.excursion is None:
            return 0

        return min(self.excursion.staff_count, self.admissible_staff_count)

    @property
    def admissible_staff_count(self):
        """An excursion can have as many youth leaders as the max bound on integers allows. Not all youth leaders
        are refinanced though."""
        if self.excursion is None:
            return 0

        #raw_staff_count = self.excursion.jugendleiter.count()
        participant_count = self.excursion.participant_count
        if participant_count < 4:
            return 0
        elif 4 <= participant_count <= 7:
            return 2
        else:
            return 2 + math.ceil((participant_count - 7) / 7)

    @property
    def total(self):
        return self.total_bills + self.total_staff

    @property
    def total_theoretic(self):
        return self.total_bills_theoretic + self.total_staff

    def total_pretty(self):
        return "{}€".format(self.total)
    total_pretty.short_description = _('Total')


class StatementUnSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(submitted=False, confirmed=False)


class StatementUnSubmitted(Statement):
    objects = StatementUnSubmittedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _('Statement in preparation')
        verbose_name_plural = _('Statements in preparation')
        rules_permissions = {
            'add_obj': rules.is_staff,
            'view_obj': is_creator | leads_excursion | has_global_perm('finance.view_global_statementunsubmitted'),
            'change_obj': is_creator | leads_excursion,
            'delete_obj': is_creator | leads_excursion,
        }


class StatementSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(submitted=True, confirmed=False)


class StatementSubmitted(Statement):
    objects = StatementSubmittedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _('Submitted statement')
        verbose_name_plural = _('Submitted statements')
        permissions = [
            ('process_statementsubmitted', 'Can manage submitted statements.'),
        ]


class StatementConfirmedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=True)


class StatementConfirmed(Statement):
    objects = StatementConfirmedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _('Paid statement')
        verbose_name_plural = _('Paid statements')
        permissions = [
            ('may_manage_confirmed_statements', 'Can view and manage confirmed statements.'),
        ]


class Bill(CommonModel):
    statement = models.ForeignKey(Statement, verbose_name=_('Statement'), on_delete=models.CASCADE)
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    paid_by = models.ForeignKey(Member, verbose_name=_('Paid by'), null=True,
                                on_delete=models.SET_NULL)
    costs_covered = models.BooleanField(verbose_name=_('Covered'), default=False)
    refunded = models.BooleanField(verbose_name=_('Refunded'), default=False)

    proof = models.ImageField(_('Proof'), upload_to='bill_images', blank=True)

    def __str__(self):
        return "{} ({}€)".format(self.short_description, self.amount)

    def pretty_amount(self):
        return "{}€".format(self.amount)
    pretty_amount.admin_order_field = 'amount'
    pretty_amount.short_description = _('Amount')

    class Meta(CommonModel.Meta):
        verbose_name = _('Bill')
        verbose_name_plural = _('Bills')


class BillOnExcursionProxy(Bill):
    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _('Bill')
        verbose_name_plural = _('Bills')
        rules_permissions = {
            'add_obj': leads_excursion & not_submitted,
            'view_obj': leads_excursion | has_global_perm('finance.view_global_billonexcursionproxy'),
            'change_obj': (leads_excursion | has_global_perm('finance.change_global_billonexcursionproxy')) & not_submitted,
            'delete_obj': (leads_excursion | has_global_perm('finance.delete_global_billonexcursionproxy')) & not_submitted,
        }


class BillOnStatementProxy(Bill):
    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _('Bill')
        verbose_name_plural = _('Bills')
        rules_permissions = {
            'add_obj': (is_creator | leads_excursion) & not_submitted,
            'view_obj': is_creator | leads_excursion | has_global_perm('finance.view_global_billonstatementproxy'),
            'change_obj': (is_creator | leads_excursion | has_global_perm('finance.change_global_billonstatementproxy'))
                     & (not_submitted | has_global_perm('finance.process_statementsubmitted')),
            'delete_obj': (is_creator | leads_excursion | has_global_perm('finance.delete_global_billonstatementproxy'))
                     & not_submitted,
        }


class Transaction(models.Model):
    reference = models.TextField(verbose_name=_('Reference'))
    amount = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_('Amount'))
    member = models.ForeignKey(Member, verbose_name=_('Recipient'),
                               on_delete=models.CASCADE)
    ledger = models.ForeignKey(Ledger, blank=False, null=True, default=None, verbose_name=_('Ledger'),
                               on_delete=models.SET_NULL)

    statement = models.ForeignKey(Statement, verbose_name=_('Statement'),
                                  on_delete=models.CASCADE)

    confirmed = models.BooleanField(verbose_name=_('Paid'), default=False)
    confirmed_date = models.DateTimeField(verbose_name=_('Paid on'), default=None, null=True)
    confirmed_by = models.ForeignKey(Member, verbose_name=_('Authorized by'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL,
                                     related_name='confirmed_transactions')

    def __str__(self):
        return "T#{}".format(self.pk)

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')


class Receipt(models.Model):
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    ledger = models.ForeignKey(Ledger, blank=False, null=False, verbose_name=_('Ledger'),
                               on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    comments = models.TextField()


def cvt_to_decimal(f):
    return Decimal(f).quantize(Decimal('.01'), rounding=ROUND_HALF_DOWN)
