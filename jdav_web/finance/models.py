from django.db import models
from django.utils.translation import gettext_lazy as _
from members.models import Member, Freizeit

# Create your models here.

class Ledger(models.Model):
    name = models.CharField(verbose_name=_('Name'), max_length=30)

    def __str__(self):
        return self.name


class Statement(models.Model):
    short_description = models.CharField(verbose_name=_('Short description'),
                                         max_length=30,
                                         blank=True)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    excursion = models.OneToOneField(Freizeit, verbose_name=_('Associated excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    submitted = models.BooleanField(verbose_name=_('Submitted'), default=False)

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

    def total_bills(self):
        return sum([bill.amount for bill in self.bill_set.all()])

    def total_transportation(self):
        if self.excursion is None:
            return 0

        exc = self.excursion
        return exc.kilometers_traveled * 0.2

    def total(self):
        return float(self.total_bills()) + self.total_transportation()


class StatementSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(submitted=True)


class StatementSubmitted(Statement):
    objects = StatementSubmittedManager()

    class Meta:
        proxy = True
        verbose_name = _('Submitted statement')
        verbose_name_plural = _('Submitted statements')
        permissions = (('may_manage_submitted_statements', 'Can view and manage submitted statements.'),)

class Bill(models.Model):
    statement = models.ForeignKey(Statement, verbose_name=_('Statement'),
                                  on_delete=models.CASCADE)
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    amount = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    paid_by = models.ForeignKey(Member, verbose_name=_('Paid by'), null=True,
                                on_delete=models.SET_NULL)
    refunded = models.BooleanField(verbose_name=_('Refunded'), default=False)

    proof = models.ImageField(_('Proof'), upload_to='bill_images', blank=True)

    def __str__(self):
        return "{} ({}€)".format(self.short_description, self.amount)

    def pretty_amount(self):
        return "{} €".format(self.amount)
    pretty_amount.admin_order_field = 'amount'


class Transaction(models.Model):
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    member = models.ForeignKey(Member, verbose_name=_('Recipient'),
                               on_delete=models.CASCADE)

    statement = models.ForeignKey(Statement, verbose_name=_('Statement'),
                                  on_delete=models.CASCADE)

    confirmed = models.BooleanField(verbose_name=_('Confirmed'))


class Receipt(models.Model):
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    ledger = models.ForeignKey(Ledger, blank=False, null=False, verbose_name=_('Ledger'),
                               on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    comments = models.TextField()
