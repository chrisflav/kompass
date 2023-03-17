import math
from itertools import groupby

from django.db import models
from django.utils.translation import gettext_lazy as _
from members.models import Member, Freizeit, OEFFENTLICHE_ANREISE, MUSKELKRAFT_ANREISE

# Create your models here.

class Ledger(models.Model):
    name = models.CharField(verbose_name=_('Name'), max_length=30)

    def __str__(self):
        return self.name


class Statement(models.Model):
    ALLOWANCE_PER_DAY = 10

    short_description = models.CharField(verbose_name=_('Short description'),
                                         max_length=30,
                                         blank=True)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    excursion = models.OneToOneField(Freizeit, verbose_name=_('Associated excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    night_cost = models.DecimalField(verbose_name=_('Price per night'), default=0, decimal_places=2, max_digits=3)

    submitted = models.BooleanField(verbose_name=_('Submitted'), default=False)
    confirmed = models.BooleanField(verbose_name=_('Confirmed'), default=False)

    class Meta:
        permissions = [('may_edit_submitted_statements', 'Is allowed to edit submitted statements')]

    def __str__(self):
        if self.excursion is not None:
            return _('Statement: %(excursion)s') % {'excursion': str(self.excursion)}
        else:
            return self.short_description

    def submit(self):
        self.submitted = True
        self.save()

    def generate_transactions(self):
        # bills
        for bill in self.bill_set.all():
            if not bill.costs_covered:
                continue
            ref = "{}: {}".format(self.excursion.name, bill.short_description)
            Transaction(statement=self, member=bill.paid_by, amount=bill.amount, confirmed=False, reference=ref).save()

        # excursion specific
        if self.excursion is None:
            return

        for yl in self.excursion.jugendleiter.all():
            real_per_yl = self.total_staff / self.excursion.jugendleiter.count()
            ref = _("Compensation for %(excu)s.") % {'excu': self.excursion.name}
            Transaction(statement=self, member=yl, amount=real_per_yl, confirmed=False, reference=ref).save()

    def reduce_transactions(self):
        transactions = sorted(self.transaction_set.all(), key=lambda trans: trans.member.pk)
        for member, transaction_group in groupby(transactions, lambda trans: trans.member):
            grp = list(transaction_group)
            if len(grp) == 1:
                continue

            new_amount = sum((trans.amount for trans in grp))
            new_ref = "\n".join((trans.reference for trans in grp))
            Transaction(statement=self, member=member, amount=new_amount, confirmed=False, reference=new_ref).save()
            for trans in grp:
                trans.delete()

    @property
    def total_bills(self):
        return sum([bill.amount for bill in self.bill_set.all() if bill.costs_covered])

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

        return self.excursion.kilometers_traveled * self.euro_per_km

    @property
    def allowance_per_yl(self):
        if self.excursion is None:
            return 0

        return self.excursion.duration * self.ALLOWANCE_PER_DAY

    @property
    def real_night_cost(self):
        return min(self.night_cost, 11)

    @property
    def nights_per_yl(self):
        if self.excursion is None:
            return 0

        return float(self.excursion.night_count * self.real_night_cost)

    @property
    def total_per_yl(self):
        return self.transportation_per_yl \
                + self.allowance_per_yl \
                + self.nights_per_yl

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

    def total(self):
        return float(self.total_bills) + self.total_staff


class StatementSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(submitted=True, confirmed=False)


class StatementSubmitted(Statement):
    objects = StatementSubmittedManager()

    class Meta:
        proxy = True
        verbose_name = _('Submitted statement')
        verbose_name_plural = _('Submitted statements')
        permissions = (('may_manage_submitted_statements', 'Can view and manage submitted statements.'),)


class StatementConfirmedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=True)


class StatementConfirmed(Statement):
    objects = StatementConfirmedManager()

    class Meta:
        proxy = True
        verbose_name = _('Confirmed statement')
        verbose_name_plural = _('Confirmed statements')
        permissions = (('may_manage_confirmed_statements', 'Can view and manage confirmed statements.'),)


class Bill(models.Model):
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
        return "{} €".format(self.amount)
    pretty_amount.admin_order_field = 'amount'


class Transaction(models.Model):
    reference = models.TextField(verbose_name=_('Reference'))
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    member = models.ForeignKey(Member, verbose_name=_('Recipient'),
                               on_delete=models.CASCADE)

    statement = models.ForeignKey(Statement, verbose_name=_('Statement'),
                                  on_delete=models.CASCADE)

    confirmed = models.BooleanField(verbose_name=_('Confirmed'), default=False)


class Receipt(models.Model):
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    ledger = models.ForeignKey(Ledger, blank=False, null=False, verbose_name=_('Ledger'),
                               on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    comments = models.TextField()
