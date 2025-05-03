import math
from itertools import groupby
from decimal import Decimal, ROUND_HALF_DOWN
from django.utils import timezone
from .rules import is_creator, not_submitted, leads_excursion
from members.rules import is_leader, statement_not_submitted

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils.translation import gettext_lazy as _
from members.models import Member, Freizeit, OEFFENTLICHE_ANREISE, MUSKELKRAFT_ANREISE
from django.conf import settings
import rules
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from utils import cvt_to_decimal, RestrictedFileField
from members.pdf import render_tex_with_attachments
from mailer.mailutils import send as send_mail
from contrib.media import media_path

from schwifty import IBAN
import re

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
    MISSING_LEDGER, NON_MATCHING_TRANSACTIONS, INVALID_ALLOWANCE_TO, INVALID_TOTAL, VALID = 0, 1, 2, 3, 4

    short_description = models.CharField(verbose_name=_('Short description'),
                                         max_length=30,
                                         blank=True)
    explanation = models.TextField(verbose_name=_('Explanation'), blank=True)

    excursion = models.OneToOneField(Freizeit, verbose_name=_('Associated excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    allowance_to = models.ManyToManyField(Member, verbose_name=_('Pay allowance to'),
                                          related_name='receives_allowance_for_statements',
                                          blank=True,
                                          help_text=_('The youth leaders to which an allowance should be paid.'))
    subsidy_to = models.ForeignKey(Member, verbose_name=_('Pay subsidy to'),
                                   null=True,
                                   blank=True,
                                   on_delete=models.SET_NULL,
                                   related_name='receives_subsidy_for_statements',
                                   help_text=_('The person that should receive the subsidy for night and travel costs. Typically the person who paid for them.'))

    ljp_to = models.ForeignKey(Member, verbose_name=_('Pay ljp contributions to'),
                               null=True,
                               blank=True,
                               on_delete=models.SET_NULL,
                               related_name='receives_ljp_for_statements',
                               help_text=_('The person that should receive the ljp contributions for the participants. Should be only selected if an ljp request was submitted.'))

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

    @property
    def title(self):
        if self.excursion is not None:
            return _('Excursion %(excursion)s') % {'excursion': str(self.excursion)}
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
            needed_paiments.extend([(yl, self.allowance_per_yl) for yl in self.allowance_to.all()])
        if self.subsidy_to:
            needed_paiments.append((self.subsidy_to, self.total_subsidies))

        # only include org fee if either allowance or subsidy is claimed (part of the property)
        if self.total_org_fee:
            needed_paiments.append((self.org_fee_payant, -self.total_org_fee))

        if self.ljp_to:
            needed_paiments.append((self.ljp_to, self.paid_ljp_contributions))

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

    @property
    def allowance_to_valid(self):
        """Checks if the configured `allowance_to` field matches the regulations."""
        if self.allowances_paid > self.real_staff_count:
            # it is allowed that less allowances are utilized than youth leaders are enlisted
            return False
        if self.excursion is not None:
            yls = self.excursion.jugendleiter.all()
            for yl in self.allowance_to.all():
                if yl not in yls:
                    return False
        return True

    @property
    def total_valid(self):
        """Checks if the calculated total agrees with the total amount of all transactions."""
        total_transactions = 0
        for transaction in self.transaction_set.all():
            total_transactions += transaction.amount
        return self.total == total_transactions

    @property
    def validity(self):
        if not self.transactions_match_expenses:
            return Statement.NON_MATCHING_TRANSACTIONS
        if not self.ledgers_configured:
            return Statement.MISSING_LEDGER
        if not self.allowance_to_valid:
            return Statement.INVALID_ALLOWANCE_TO
        if not self.total_valid:
            return Statement.INVALID_TOTAL
        else:
            return Statement.VALID

    def is_valid(self):
        return self.validity == Statement.VALID
    is_valid.boolean = True
    is_valid.short_description = _('Ready to confirm')

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
            return True

        # allowance
        for yl in self.allowance_to.all():
            ref = _("Allowance for %(excu)s") % {'excu': self.excursion.name}
            Transaction(statement=self, member=yl, amount=self.allowance_per_yl, confirmed=False, reference=ref).save()

        # subsidies (i.e. night and transportation costs)
        if self.subsidy_to:
            ref = _("Night and travel costs for %(excu)s") % {'excu': self.excursion.name}
            Transaction(statement=self, member=self.subsidy_to, amount=self.total_subsidies, confirmed=False, reference=ref).save()

        if self.total_org_fee:
            # if no subsidy receiver is given but org fees have to be paid. Just pick one of allowance receivers
            ref = _("reduced by org fee")
            Transaction(statement=self, member=self.org_fee_payant, amount=-self.total_org_fee, confirmed=False, reference=ref).save()

        if self.ljp_to:
            ref = _("LJP-Contribution %(excu)s") % {'excu': self.excursion.name}
            Transaction(statement=self, member=self.ljp_to, amount=self.paid_ljp_contributions,
                        confirmed=False, reference=ref).save()

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
            new_ref = ", ".join((f"{trans.reference} EUR{trans.amount: .2f}" for trans in grp))
            Transaction(statement=self, member=member, amount=new_amount, confirmed=False, reference=new_ref,
                        ledger=ledger).save()
            for trans in grp:
                trans.delete()

    @property
    def total_bills(self):
        return sum([bill.amount for bill in self.bills_covered])

    @property
    def bills_covered(self):
        """Returns the bills that are marked for reimbursement by the finance officer"""
        return [bill for bill in self.bill_set.all() if bill.costs_covered]

    @property
    def bills_without_proof(self):
        """Returns the bills that lack a proof file"""
        return [bill for bill in self.bill_set.all() if not bill.proof]
    
    @property
    def total_bills_theoretic(self):
        return sum([bill.amount for bill in self.bill_set.all()])

    @property
    def total_bills_not_covered(self):
        """Returns the sum of bills that are not marked for reimbursement by the finance officer"""
        return sum([bill.amount for bill in self.bill_set.all()]) - self.total_bills

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
    def allowances_paid(self):
        return self.allowance_to.count()

    @property
    def total_allowance(self):
        return self.allowance_per_yl * self.allowances_paid

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
    def total_org_fee_theoretical(self):
        """participants older than 26.99 years need to pay a specified organisation fee per person per day."""
        if self.excursion is None:
            return 0
        return cvt_to_decimal(settings.EXCURSION_ORG_FEE * self.excursion.duration * self.excursion.old_participant_count)

    @property
    def total_org_fee(self):
        """only calculate org fee if subsidies or allowances are claimed."""
        if self.subsidy_to or self.allowances_paid > 0:
            return self.total_org_fee_theoretical
        return cvt_to_decimal(0)

    @property
    def org_fee_payant(self):
        return self.subsidy_to if self.subsidy_to else self.allowance_to.all()[0]

    @property
    def total_subsidies(self):
        """
        The total amount of subsidies excluding the allowance, i.e. the transportation
        and night costs per youth leader multiplied with the real number of youth leaders.
        """
        if self.subsidy_to:
            return (self.transportation_per_yl + self.nights_per_yl) * self.real_staff_count
        else:
            return cvt_to_decimal(0)

    @property
    def subsidies_paid(self):
        return self.total_subsidies - self.total_org_fee

    @property
    def theoretical_total_staff(self):
        """
        the sum of subsidies and allowances if all eligible youth leaders would collect them. 
        """
        return self.total_per_yl * self.real_staff_count

    @property
    def total_staff(self):
        """
        the sum of subsidies and allowances that youth leaders are actually collecting
        """
        return self.total_allowance + self.total_subsidies

    @property
    def total_staff_paid(self):
        return self.total_staff - self.total_org_fee


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
        else:
            return self.excursion.approved_staff_count
        
    @property
    def paid_ljp_contributions(self):
        if hasattr(self.excursion, 'ljpproposal') and self.ljp_to:
            
            if self.excursion.theoretic_ljp_participant_count < 5:
                return 0
            
            return cvt_to_decimal(
                min(
                    (1-settings.LJP_TAX) * settings.LJP_CONTRIBUTION_PER_DAY * self.excursion.ljp_participant_count * self.excursion.ljp_duration,
                    (1-settings.LJP_TAX) * 0.9 * (float(self.total_bills_not_covered) + float(self.total_staff) ),
                    float(self.total_bills_not_covered)
                )
            )
        else:
            return 0

    @property
    def total(self):
        return self.total_bills + self.total_staff_paid  + self.paid_ljp_contributions

    @property
    def total_theoretic(self):
        """
        The theoretic total used in SJR and LJP applications. This is the sum of all
        bills (ignoring whether they are paid by the association or not) plus the
        total allowance. This does not include the subsidies for night and travel costs,
        since they are expected to be included in the bills.
        """
        return self.total_bills_theoretic + self.total_allowance

    def total_pretty(self):
        return "{}€".format(self.total)
    total_pretty.short_description = _('Total')

    def template_context(self):
        context = {
            'total_bills': self.total_bills,
            'total_bills_theoretic': self.total_bills_theoretic,
            'bills_covered': self.bills_covered,
            'total': self.total,
        }
        if self.excursion:
            excursion_context = {
                'nights': self.excursion.night_count,
                'price_per_night': self.real_night_cost,
                'duration': self.excursion.duration,
                'staff_count': self.real_staff_count,
                'kilometers_traveled': self.excursion.kilometers_traveled,
                'means_of_transport': self.excursion.get_tour_approach(),
                'euro_per_km': self.euro_per_km,
                'allowance_per_day': settings.ALLOWANCE_PER_DAY,
                'allowances_paid': self.allowances_paid,
                'nights_per_yl': self.nights_per_yl,
                'allowance_per_yl': self.allowance_per_yl,
                'total_allowance': self.total_allowance,
                'transportation_per_yl': self.transportation_per_yl,
                'total_per_yl': self.total_per_yl,
                'total_staff': self.total_staff,
                'total_allowance': self.total_allowance,
                'theoretical_total_staff': self.theoretical_total_staff,
                'real_staff_count': self.real_staff_count,
                'total_subsidies': self.total_subsidies,
                'total_allowance': self.total_allowance,
                'subsidy_to': self.subsidy_to,
                'allowance_to': self.allowance_to,
                'paid_ljp_contributions': self.paid_ljp_contributions,
                'ljp_to': self.ljp_to,
                'theoretic_ljp_participant_count': self.excursion.theoretic_ljp_participant_count,
                'participant_count': self.excursion.participant_count,
                'total_seminar_days': self.excursion.total_seminar_days,
                'ljp_tax': settings.LJP_TAX * 100,
                'total_org_fee_theoretical': self.total_org_fee_theoretical,
                'total_org_fee': self.total_org_fee,
                'old_participant_count': self.excursion.old_participant_count,
                'total_staff_paid': self.total_staff_paid,
                'org_fee': cvt_to_decimal(settings.EXCURSION_ORG_FEE),
            }
            return dict(context, **excursion_context)
        else:
            return context

    def grouped_bills(self):
        return self.bill_set.values('short_description')\
                            .order_by('short_description')\
                            .annotate(amount=Sum('amount'))

    def send_summary(self, cc=None):
        """
        Sends a summary of the statement to the central office of the association.
        """
        excursion = self.excursion
        context = dict(statement=self.template_context(), excursion=excursion, settings=settings)
        pdf_filename = f"{excursion.code}_{excursion.name}_Zuschussbeleg" if excursion else f"Abrechnungsbeleg"
        attachments = [bill.proof.path for bill in self.bills_covered if bill.proof]
        filename = render_tex_with_attachments(pdf_filename, 'finance/statement_summary.tex',
                                               context, attachments, save_only=True)
        send_mail(_('Statement summary for %(title)s') % { 'title': self.title },
                  settings.SEND_STATEMENT_SUMMARY.format(statement=self.title),
                  sender=settings.DEFAULT_SENDING_MAIL,
                  recipients=[settings.SEKTION_FINANCE_MAIL],
                  cc=cc,
                  attachments=[media_path(filename)])


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

    amount = models.DecimalField(verbose_name=_('Amount'), max_digits=6, decimal_places=2, default=0)
    paid_by = models.ForeignKey(Member, verbose_name=_('Paid by'), null=True,
                                on_delete=models.SET_NULL)
    costs_covered = models.BooleanField(verbose_name=_('Covered'), default=False)
    refunded = models.BooleanField(verbose_name=_('Refunded'), default=False)

    proof = RestrictedFileField(verbose_name=_('Proof'),
                                upload_to='bill_images',
                                blank=True,
                                max_upload_size=5,
                                content_types=['application/pdf',
                                                    'image/jpeg',
                                                    'image/png',
                                                    'image/gif'])

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

    @staticmethod
    def escape_reference(reference):
        umlaut_map = {
            'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
            'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
            'ß': 'ss'
        }
        pattern = re.compile('|'.join(umlaut_map.keys()))
        int_reference = pattern.sub(lambda x: umlaut_map[x.group()], reference)
        allowed_chars = r"[^a-z0-9 /?: .,'+-]"
        clean_reference = re.sub(allowed_chars, '', int_reference, flags=re.IGNORECASE)
        return clean_reference

    def code(self):

        if self.amount == 0:
            return ""

        iban = IBAN(self.member.iban, allow_invalid=True)
        if not iban.is_valid:
            return ""
        bic = iban.bic

        reference = self.escape_reference(self.reference)
        
        # also escaping receiver as umlaute are also not allowed here
        receiver = self.escape_reference(f"{self.member.prename} {self.member.lastname}")
        return f"""BCD
001
1
SCT
{bic}
{receiver}
{iban}
EUR{self.amount}


{reference}"""

    class Meta:
        verbose_name = _('Transaction')
        verbose_name_plural = _('Transactions')


class Receipt(models.Model):
    short_description = models.CharField(verbose_name=_('Short description'), max_length=30)
    ledger = models.ForeignKey(Ledger, blank=False, null=False, verbose_name=_('Ledger'),
                               on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    comments = models.TextField()
