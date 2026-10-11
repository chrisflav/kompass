import re
from decimal import Decimal
from itertools import groupby

import rules
from contrib.media import media_path
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.conf import settings
from django.db import models
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import send as send_mail
from members.models import Freizeit
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE
from members.models import OEFFENTLICHE_ANREISE
from members.pdf import render_tex_with_attachments
from members.rules import is_leader
from members.rules import statement_not_submitted
from schwifty import IBAN
from utils import cvt_to_decimal
from utils import RestrictedFileField

from .engine import evaluate_statement
from .engine import parameters as engine_parameters
from .rules import is_creator
from .rules import leads_excursion
from .rules import not_submitted
from .rules_api import Member as RuleMember
from .rules_api import SECTION

# Create your models here.


class Ledger(models.Model):
    name = models.CharField(verbose_name=_("Name"), max_length=30)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Ledger")
        verbose_name_plural = _("Ledgers")


class TransactionIssue:
    def __init__(self, member, current, target):
        self.member, self.current, self.target = member, current, target

    @property
    def difference(self):
        return self.target - self.current


class StatementManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Statement.UNSUBMITTED)


class Statement(CommonModel):
    MISSING_LEDGER, NON_MATCHING_TRANSACTIONS, INVALID_ALLOWANCE_TO, INVALID_TOTAL, VALID = (
        0,
        1,
        2,
        3,
        4,
    )
    UNSUBMITTED, SUBMITTED, CONFIRMED = 0, 1, 2
    STATUS_CHOICES = [
        (UNSUBMITTED, _("In preparation")),
        (SUBMITTED, _("Submitted")),
        (CONFIRMED, _("Completed")),
    ]
    STATUS_CSS_CLASS = {SUBMITTED: "submitted", CONFIRMED: "confirmed", UNSUBMITTED: "unsubmitted"}

    short_description = models.CharField(
        verbose_name=_("Short description"), max_length=30, blank=False
    )
    explanation = models.TextField(verbose_name=_("Explanation"), blank=True)

    excursion = models.OneToOneField(
        Freizeit,
        verbose_name=_("Associated excursion"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
    )

    allowance_to = models.ManyToManyField(
        Member,
        verbose_name=_("Pay allowance to"),
        related_name="receives_allowance_for_statements",
        blank=True,
        help_text=_("The youth leaders to which an allowance should be paid."),
    )
    subsidy_to = models.ForeignKey(
        Member,
        verbose_name=_("Pay subsidy to"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receives_subsidy_for_statements",
        help_text=_(
            "The person that should receive the subsidy for night and travel costs. Typically the person who paid for them."
        ),
    )

    ljp_to = models.ForeignKey(
        Member,
        verbose_name=_("Pay ljp contributions to"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="receives_ljp_for_statements",
        help_text=_(
            "The person that should receive the ljp contributions for the participants. Should be only selected if an ljp request was submitted."
        ),
    )

    night_cost = models.DecimalField(
        verbose_name=_("Price per night"),
        default=0,
        decimal_places=2,
        max_digits=5,
        # the help_text stays free of settings so that it is the same in every
        # deployment, the admin form names the configured maximum
        help_text=_(
            "Price for the overnight stay of a youth leader. This is required for the calculation of the subsidies for night costs."
        ),
    )

    status = models.IntegerField(
        verbose_name=_("Status"), choices=STATUS_CHOICES, default=UNSUBMITTED
    )
    settings_snapshot = models.JSONField(
        verbose_name=_("Settings snapshot"),
        default=dict,
        blank=True,
        help_text=_("Financial settings captured at time of submission/confirmation."),
    )
    submitted_date = models.DateTimeField(verbose_name=_("Submitted on"), default=None, null=True)
    confirmed_date = models.DateTimeField(verbose_name=_("Paid on"), default=None, null=True)

    created_by = models.ForeignKey(
        Member,
        verbose_name=_("Created by"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_statements",
    )
    submitted_by = models.ForeignKey(
        Member,
        verbose_name=_("Submitted by"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="submitted_statements",
    )
    confirmed_by = models.ForeignKey(
        Member,
        verbose_name=_("Authorized by"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_statements",
    )

    class Meta(CommonModel.Meta):
        verbose_name = _("Statement")
        verbose_name_plural = _("Statements")
        permissions = [("may_edit_submitted_statements", "Is allowed to edit submitted statements")]
        rules_permissions = {
            # All users may add draft statements.
            "add_obj": rules.is_staff,
            # All users may view their own statements and statements of excursions they are responsible for.
            "view_obj": is_creator
            | leads_excursion
            | has_global_perm("finance.view_global_statement"),
            # All users may change relevant (see above) draft statements.
            "change_obj": (not_submitted & (is_creator | leads_excursion))
            | has_global_perm("finance.change_global_statement"),
            # All users may delete relevant (see above) draft statements.
            "delete_obj": not_submitted
            & (is_creator | leads_excursion | has_global_perm("finance.delete_global_statement")),
        }

    @property
    def title(self):
        if self.excursion is not None:
            return _("Excursion %(excursion)s") % {"excursion": str(self.excursion)}
        else:
            return self.short_description

    def __str__(self):
        return str(self.title)

    def _get_setting(self, key: str) -> Decimal:
        """The section's number for ``key``, as it applies to this statement.

        A submitted statement reads its own snapshot, a draft the live
        settings. The value is a ``Decimal``: the snapshot holds JSON numbers
        and the settings may hold either, and every amount column in this app
        is a ``DecimalField``, so the conversion happens once, here, through
        the text form — ``Decimal(str(0.15))`` is ``Decimal("0.15")`` and not
        the binary expansion ``Decimal(0.15)`` would give.
        """
        return engine_parameters(self)[key]

    def _capture_settings_snapshot(self, force=False):
        if self.settings_snapshot and not force:
            return

        self.settings_snapshot = {
            "ALLOWANCE_PER_DAY": float(settings.ALLOWANCE_PER_DAY),
            "MAX_NIGHT_COST": float(settings.MAX_NIGHT_COST),
            "AID_PER_KM_TRAIN": float(settings.AID_PER_KM_TRAIN),
            "AID_PER_KM_CAR": float(settings.AID_PER_KM_CAR),
            "EXCURSION_ORG_FEE": float(settings.EXCURSION_ORG_FEE),
            "LJP_CONTRIBUTION_PER_DAY": float(settings.LJP_CONTRIBUTION_PER_DAY),
            "LJP_TAX": float(settings.LJP_TAX),
            "captured_at": timezone.now().isoformat(),
        }

    @property
    def submitted(self):
        return self.status == Statement.SUBMITTED or self.status == Statement.CONFIRMED

    @property
    def confirmed(self):
        return self.status == Statement.CONFIRMED

    def status_badge(self):
        code = Statement.STATUS_CSS_CLASS[self.status]
        return format_html(
            f'<span class="statement-{code}">{Statement.STATUS_CHOICES[self.status][1]}</span>'
        )

    status_badge.short_description = _("Status")
    status_badge.allow_tags = True
    status_badge.admin_order_field = "status"

    def submit(self, submitter=None):
        self._capture_settings_snapshot(force=True)
        self.status = self.SUBMITTED
        self.submitted_date = timezone.now()
        self.submitted_by = submitter
        self.save()

    @property
    def rule_result(self):
        """This statement resolved against the section's rules.

        The single seam between the finance app and the rules engine: who is
        owed what, what is wrong with the statement, and what still has to be
        asked (:class:`finance.engine.Result`). Every money figure below is
        read off it rather than recomputed here.

        It is resolved on each access on purpose. A draft follows its own
        fields — change the subsidy recipient and the next read says so — and
        caching that correctly means fingerprinting the recipients, the bills
        and the excursion, which costs the queries it would save. Step 2 of the
        refactor materialises the transfers as rows, which removes the question.
        """
        return evaluate_statement(self)

    @property
    def transfers(self):
        """The transfers this statement resolves to, balancing one last."""
        return self.rule_result.transfers

    def _transfer_members(self, result):
        """The members a result touches, by id, in one query."""
        return Member.objects.in_bulk([party.id for party in result.members()])

    def _transfer_reference(self, transfer):
        """The payment reference a transfer is booked under.

        The wording is the association's, not the ruleset's: a transfer carries
        a category and a short label, and the context the rules see holds no
        names, so the excursion's name is interpolated here. A category this
        app has no wording for falls back to the ruleset's own label, which is
        what a section with its own categories gets.
        """
        if transfer.category == "bill":
            return "{}: {}".format(str(self), transfer.label)
        excursion = self.excursion
        if excursion is not None:
            if transfer.category == "allowance":
                return _("Allowance for %(excu)s") % {"excu": excursion.name}
            if transfer.category == "subsidy":
                return _("Night and travel costs for %(excu)s") % {"excu": excursion.name}
            if transfer.category == "org_fee":
                return _("reduced by org fee")
            if transfer.category == "ljp":
                return _("LJP-Contribution %(excu)s") % {"excu": excursion.name}
        return transfer.label or transfer.category

    def transfer_payload(self):
        """The transfers with their parties resolved to members, for the API."""
        result = self.rule_result
        members = self._transfer_members(result)

        def party(value):
            if isinstance(value, RuleMember):
                return {"kind": "member", "member": members.get(value.id)}
            return {"kind": "section" if value == SECTION else "participants", "member": None}

        return [
            {
                "source": party(transfer.source),
                "destination": party(transfer.destination),
                "amount": transfer.amount,
                "category": transfer.category,
                "rule_id": transfer.rule_id,
                "label": str(transfer.label),
                "explanation": str(transfer.explanation),
                "reference": str(self._transfer_reference(transfer)),
            }
            for transfer in result.transfers
        ]

    @property
    def transaction_issues(self):
        """
        Returns a list of critical problems with the currently configured transactions. This is done
        by resolving the statement against the section's rules. From the resulting transfers, we
        deduce the total amount every member should receive (this amount can be negative, due to
        org fees). Finally, the amounts are compared to the total amounts paid out by currently
        setup transactions.

        Only transfers that touch a member can be an issue: a covered bill with no payer is money
        the statement owes somebody it cannot name, which is reported as a rule error instead.
        (Note: This means that `transaction_issues` might return an empty list, but the calculated
        total still differs from the transaction total.)
        """
        result = self.rule_result
        members = self._transfer_members(result)
        target = {
            members[party.id]: result.amount_for(party)
            for party in sorted(result.members(), key=lambda party: party.id)
            if party.id in members
        }

        transactions = sorted(self.transaction_set.all(), key=lambda trans: trans.member.pk)
        current = dict(
            map(
                lambda p: (p[0], sum([t.amount for t in p[1]])),
                groupby(transactions, lambda trans: trans.member),
            )
        )

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
        """Returns true iff there are no transaction issues."""
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
        """
        Checks if the calculated total agrees with the total amount of all transactions.
        Note: This is not the same as `transactions_match_expenses`. For details see the
        docstring of `transaction_issues`.
        """
        total_transactions = 0
        for transaction in self.transaction_set.all():
            total_transactions += transaction.amount
        return self.total == total_transactions

    @property
    def validity(self):
        """
        Returns the validity status of the statement. This is one of:
        - `Statement.VALID`:
          Everything is correct.
        - `Statement.NON_MATCHING_TRANSACTIONS`:
          There is a transaction issue (in the sense of `transaction_issues`).
        - `Statement.MISSING_LEDGER`:
          At least one transaction has no ledger configured.
        - `Statement.INVALID_ALLOWANCE_TO`:
          The members receiving allowance don't match the regulations.
        - `Statement.INVALID_TOTAL`:
          The total amount of transactions differs from the calculated total payout.
        """
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
    is_valid.short_description = _("Ready to confirm")

    @property
    def validity_display(self):
        """Human-readable reason for the current :attr:`validity`.

        Explains why a submitted statement is (not yet) ready to be confirmed,
        mirroring the states described in the ``validity`` docstring.
        """
        return {
            Statement.MISSING_LEDGER: _("At least one transaction has no ledger configured."),
            Statement.NON_MATCHING_TRANSACTIONS: _(
                "The transactions do not match the calculated costs."
            ),
            Statement.INVALID_ALLOWANCE_TO: _(
                "The members receiving the allowance don't match the regulations."
            ),
            Statement.INVALID_TOTAL: _(
                "The total of all transactions differs from the calculated total payout."
            ),
            Statement.VALID: _("Everything is correct."),
        }[self.validity]

    def confirm(self, confirmer=None):
        if not self.submitted:
            return False

        if not self.validity == Statement.VALID:
            return False

        self._capture_settings_snapshot()
        self.status = self.CONFIRMED
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
        """Book one transaction per member a transfer touches.

        Returns ``False`` without writing anything when the rules reported a
        problem — a covered bill with no payer is the one Heidelberg reports —
        so a statement that cannot be paid out leaves no half-generated rows
        behind. Money owed to a member is a transfer *to* them and money
        charged against their reimbursement a transfer *from* them, which is
        where the negative amount of an org-fee row comes from.
        """
        result = self.rule_result
        if result.errors:
            return False
        members = self._transfer_members(result)
        for transfer in result.transfers:
            reference = self._transfer_reference(transfer)
            for party, sign in ((transfer.destination, 1), (transfer.source, -1)):
                if not isinstance(party, RuleMember):
                    continue
                Transaction(
                    statement=self,
                    member=members[party.id],
                    amount=sign * transfer.amount,
                    confirmed=False,
                    reference=reference,
                ).save()
        return True

    def reduce_transactions(self):
        # to minimize the number of needed bank transactions, we bundle transactions from same ledger to
        # same member
        transactions = self.transaction_set.all()
        if any(t.ledger is None for t in transactions):
            return

        def sort_key(trans):
            return (trans.member.pk, trans.ledger.pk)

        def group_key(trans):
            return (trans.member, trans.ledger)

        transactions = sorted(transactions, key=sort_key)
        for pair, transaction_group in groupby(transactions, group_key):
            member, ledger = pair
            grp = list(transaction_group)
            if len(grp) == 1:
                continue

            new_amount = sum(trans.amount for trans in grp)
            new_ref = ", ".join(f"{trans.reference} EUR{trans.amount: .2f}" for trans in grp)
            Transaction(
                statement=self,
                member=member,
                amount=new_amount,
                confirmed=False,
                reference=new_ref,
                ledger=ledger,
            ).save()
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

        if (
            self.excursion.tour_approach == MUSKELKRAFT_ANREISE
            or self.excursion.tour_approach == OEFFENTLICHE_ANREISE
        ):
            return self._get_setting("AID_PER_KM_TRAIN")
        else:
            return self._get_setting("AID_PER_KM_CAR")

    @property
    def transportation_per_yl(self):
        if self.excursion is None:
            return 0

        return cvt_to_decimal(self.excursion.kilometers_traveled * self.euro_per_km)

    @property
    def allowance_per_yl(self):
        if self.excursion is None:
            return 0

        duration = cvt_to_decimal(self.excursion.duration)
        return cvt_to_decimal(duration * self._get_setting("ALLOWANCE_PER_DAY"))

    @property
    def allowances_paid(self):
        return self.allowance_to.count()

    @property
    def total_allowance(self):
        """What the youth leaders actually receive as an allowance."""
        return self.rule_result.total_of("allowance")

    @property
    def total_transportation(self):
        return self.transportation_per_yl * self.real_staff_count

    @property
    def real_night_cost(self):
        return min(cvt_to_decimal(self.night_cost), self._get_setting("MAX_NIGHT_COST"))

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
        return self.transportation_per_yl + self.allowance_per_yl + self.nights_per_yl

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
        return cvt_to_decimal(
            self._get_setting("EXCURSION_ORG_FEE")
            * cvt_to_decimal(self.excursion.duration)
            * self.excursion.old_participant_count
        )

    @property
    def total_org_fee(self):
        """The organisation fee actually charged against this statement."""
        return self.rule_result.total_of("org_fee")

    @property
    def org_fee_payant(self):
        """Whose reimbursement the organisation fee is charged against."""
        for transfer in self.rule_result.of_category("org_fee"):
            if isinstance(transfer.source, RuleMember):
                return Member.objects.filter(pk=transfer.source.id).first()
        return None

    @property
    def total_subsidies(self):
        """
        The total amount of subsidies excluding the allowance, i.e. the transportation
        and night costs per youth leader multiplied with the real number of youth leaders.
        """
        return self.rule_result.total_of("subsidy")

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
        """The Landesjugendplan contribution this statement passes on."""
        return self.rule_result.total_of("ljp")

    @property
    def total(self):
        """What this statement costs the section, net.

        Read off the transfers as the money that leaves the section minus the
        money that comes back to it — which is the same figure the engine's
        balancing transfer resolves, and the same one the participants'
        contributions have to cover.
        """
        return self.rule_result.net_out(SECTION)

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

    total_pretty.short_description = _("Total")
    total_pretty.admin_order_field = "total"

    def template_context(self):
        context = {
            "total_bills": self.total_bills,
            "total_bills_theoretic": self.total_bills_theoretic,
            "bills_covered": self.bills_covered,
            "total": self.total,
        }
        if self.excursion:
            excursion_context = {
                "nights": self.excursion.night_count,
                "price_per_night": self.real_night_cost,
                "duration": self.excursion.duration,
                "staff_count": self.real_staff_count,
                "kilometers_traveled": self.excursion.kilometers_traveled,
                "means_of_transport": self.excursion.get_tour_approach(),
                "euro_per_km": self.euro_per_km,
                "allowance_per_day": self._get_setting("ALLOWANCE_PER_DAY"),
                "allowances_paid": self.allowances_paid,
                "nights_per_yl": self.nights_per_yl,
                "allowance_per_yl": self.allowance_per_yl,
                "total_allowance": self.total_allowance,
                "transportation_per_yl": self.transportation_per_yl,
                "total_per_yl": self.total_per_yl,
                "total_staff": self.total_staff,
                "theoretical_total_staff": self.theoretical_total_staff,
                "real_staff_count": self.real_staff_count,
                "total_subsidies": self.total_subsidies,
                "subsidy_to": self.subsidy_to,
                "allowance_to": self.allowance_to,
                "paid_ljp_contributions": self.paid_ljp_contributions,
                "ljp_to": self.ljp_to,
                "theoretic_ljp_participant_count": self.excursion.theoretic_ljp_participant_count,
                "ljp_participant_count": self.excursion.ljp_participant_count,
                "participant_count": self.excursion.participant_count,
                "total_seminar_days": self.excursion.total_seminar_days,
                "ljp_tax": self._get_setting("LJP_TAX") * 100,
                "total_org_fee_theoretical": self.total_org_fee_theoretical,
                "total_org_fee": self.total_org_fee,
                "old_participant_count": self.excursion.old_participant_count,
                "total_staff_paid": self.total_staff_paid,
                "org_fee": cvt_to_decimal(self._get_setting("EXCURSION_ORG_FEE")),
            }
            return dict(context, **excursion_context)
        else:
            return context

    def grouped_bills(self):
        return (
            self.bill_set.values("short_description")
            .order_by("short_description")
            .annotate(amount=Sum("amount"))
        )

    def send_summary(self, cc=None):
        """
        Sends a summary of the statement to the central office of the association.
        """
        excursion = self.excursion
        context = dict(statement=self.template_context(), excursion=excursion, settings=settings)
        pdf_filename = (
            f"{excursion.code}_{excursion.name}_Zuschussbeleg" if excursion else "Abrechnungsbeleg"
        )
        attachments = [bill.proof.path for bill in self.bills_covered if bill.proof]
        filename = render_tex_with_attachments(
            pdf_filename, "finance/statement_summary.tex", context, attachments, save_only=True
        )
        send_mail(
            _("Statement summary for %(title)s") % {"title": self.title},
            settings.SEND_STATEMENT_SUMMARY.format(statement=self.title),
            sender=settings.DEFAULT_SENDING_MAIL,
            recipients=[settings.SEKTION_FINANCE_MAIL],
            cc=cc,
            attachments=[media_path(filename)],
        )


class StatementOnExcursionProxy(Statement):
    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Statement")
        verbose_name_plural = _("Statements")
        rules_permissions = {
            # This is used as an inline on excursions, so we check for excursion permissions.
            "add_obj": is_leader,
            "view_obj": is_leader | has_global_perm("members.view_global_freizeit"),
            "change_obj": is_leader & statement_not_submitted,
            "delete_obj": is_leader & statement_not_submitted,
        }


class StatementUnSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Statement.UNSUBMITTED)


class StatementUnSubmitted(Statement):
    objects = StatementUnSubmittedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Statement in preparation")
        verbose_name_plural = _("Statements in preparation")
        rules_permissions = {
            "add_obj": rules.is_staff,
            "view_obj": is_creator
            | leads_excursion
            | has_global_perm("finance.view_global_statementunsubmitted"),
            "change_obj": is_creator | leads_excursion,
            "delete_obj": is_creator | leads_excursion,
        }


class StatementSubmittedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Statement.SUBMITTED)


class StatementSubmitted(Statement):
    objects = StatementSubmittedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Submitted statement")
        verbose_name_plural = _("Submitted statements")
        permissions = [
            ("process_statementsubmitted", "Can manage submitted statements."),
        ]


class StatementConfirmedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=Statement.CONFIRMED)


class StatementConfirmed(Statement):
    objects = StatementConfirmedManager()

    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Paid statement")
        verbose_name_plural = _("Paid statements")
        permissions = [
            ("may_manage_confirmed_statements", "Can view and manage confirmed statements."),
        ]


class Bill(CommonModel):
    statement = models.ForeignKey(Statement, verbose_name=_("Statement"), on_delete=models.CASCADE)
    short_description = models.CharField(
        verbose_name=_("Short description"), max_length=30, blank=False
    )
    explanation = models.TextField(verbose_name=_("Explanation"), blank=True)

    amount = models.DecimalField(
        verbose_name=_("Amount"), max_digits=6, decimal_places=2, default=0
    )
    paid_by = models.ForeignKey(
        Member, verbose_name=_("Paid by"), null=True, on_delete=models.SET_NULL
    )
    costs_covered = models.BooleanField(verbose_name=_("Covered"), default=False)
    refunded = models.BooleanField(verbose_name=_("Refunded"), default=False)

    proof = RestrictedFileField(
        verbose_name=_("Proof"),
        upload_to="bill_images",
        blank=True,
        max_upload_size=5,
        content_types=["application/pdf", "image/jpeg", "image/png", "image/gif"],
    )

    def __str__(self):
        return "{} ({}€)".format(self.short_description, self.amount)

    def pretty_amount(self):
        return "{}€".format(self.amount)

    pretty_amount.admin_order_field = "amount"
    pretty_amount.short_description = _("Amount")

    class Meta(CommonModel.Meta):
        verbose_name = _("Bill")
        verbose_name_plural = _("Bills")


class BillOnExcursionProxy(Bill):
    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Bill")
        verbose_name_plural = _("Bills")
        rules_permissions = {
            "add_obj": leads_excursion & not_submitted,
            "view_obj": leads_excursion
            | has_global_perm("finance.view_global_billonexcursionproxy"),
            "change_obj": (
                leads_excursion | has_global_perm("finance.change_global_billonexcursionproxy")
            )
            & not_submitted,
            "delete_obj": (
                leads_excursion | has_global_perm("finance.delete_global_billonexcursionproxy")
            )
            & not_submitted,
        }


class BillOnStatementProxy(Bill):
    class Meta(CommonModel.Meta):
        proxy = True
        verbose_name = _("Bill")
        verbose_name_plural = _("Bills")
        rules_permissions = {
            "add_obj": (is_creator | leads_excursion) & not_submitted,
            "view_obj": is_creator
            | leads_excursion
            | has_global_perm("finance.view_global_billonstatementproxy"),
            "change_obj": (
                is_creator
                | leads_excursion
                | has_global_perm("finance.change_global_billonstatementproxy")
            )
            & (not_submitted | has_global_perm("finance.process_statementsubmitted")),
            "delete_obj": (
                is_creator
                | leads_excursion
                | has_global_perm("finance.delete_global_billonstatementproxy")
            )
            & not_submitted,
        }


class Transaction(models.Model):
    reference = models.TextField(verbose_name=_("Reference"))
    amount = models.DecimalField(max_digits=6, decimal_places=2, verbose_name=_("Amount"))
    member = models.ForeignKey(Member, verbose_name=_("Recipient"), on_delete=models.CASCADE)
    ledger = models.ForeignKey(
        Ledger,
        blank=False,
        null=True,
        default=None,
        verbose_name=_("Ledger"),
        on_delete=models.SET_NULL,
    )

    statement = models.ForeignKey(Statement, verbose_name=_("Statement"), on_delete=models.CASCADE)

    confirmed = models.BooleanField(verbose_name=_("Paid"), default=False)
    confirmed_date = models.DateTimeField(verbose_name=_("Paid on"), default=None, null=True)
    confirmed_by = models.ForeignKey(
        Member,
        verbose_name=_("Authorized by"),
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name="confirmed_transactions",
    )

    def __str__(self):
        return "T#{}".format(self.pk)

    @staticmethod
    def escape_reference(reference):
        umlaut_map = {"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"}
        pattern = re.compile("|".join(umlaut_map.keys()))
        int_reference = pattern.sub(lambda x: umlaut_map[x.group()], reference)
        allowed_chars = r"[^a-z0-9 /?: .,'+-]"
        clean_reference = re.sub(allowed_chars, "", int_reference, flags=re.IGNORECASE)
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
        verbose_name = _("Transaction")
        verbose_name_plural = _("Transactions")


class Receipt(models.Model):
    short_description = models.CharField(verbose_name=_("Short description"), max_length=30)
    ledger = models.ForeignKey(
        Ledger, blank=False, null=False, verbose_name=_("Ledger"), on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=6, decimal_places=2)
    comments = models.TextField()
