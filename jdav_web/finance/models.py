import re
from decimal import Decimal
from itertools import groupby

import rules
from contrib.media import media_path
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.conf import settings
from django.db import models
from django.db.models import Q
from django.db.models import Sum
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import send as send_mail
from mailer.mailutils import SENT
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

from .engine import approval_states
from .engine import bind as bind_ruleset
from .engine import current_constraint_rows
from .engine import evaluate_statement
from .engine import forbid_against
from .engine import freeze as freeze_obligations
from .engine import fully_approved
from .engine import materialise
from .engine import may_sign
from .engine import override_policy
from .engine import result_from_rows
from .engine import rows_exist
from .engine import statement_params
from .engine.approval import PERMISSION_EXCLUSION
from .rules import is_creator
from .rules import is_named_signer
from .rules import leads_excursion
from .rules import may_sign_now
from .rules import not_submitted
from .rules_api import Member as RuleMember
from .rules_api import OFFICE_PAYMENT
from .rules_api import PAYOUT_MODES
from .rules_api import SECTION
from .rules_api import SELF_PAYMENT
from .rules_api import SETTLEMENT_GROUP_LENGTH
from .store import Approval
from .store import ApprovalConstraint
from .store import RoleAssignment
from .store import RuleSet

# Create your models here.


class Ledger(models.Model):
    name = models.CharField(verbose_name=_("Name"), max_length=30)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Ledger")
        verbose_name_plural = _("Ledgers")


def _as_id(value) -> int | None:
    """``value`` as a member id, or ``None`` when it is not one at all.

    ``OverflowError`` for the same reason as in :func:`finance.inputs._as_member`:
    a JSON ``1e400`` is ``float('inf')`` by the time it gets here, and this is a
    readout, so it has to answer rather than raise.
    """
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return None


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
    (
        MISSING_LEDGER,
        NON_MATCHING_TRANSACTIONS,
        INVALID_ALLOWANCE_TO,
        INVALID_TOTAL,
        VALID,
        UNRESOLVED,
    ) = (0, 1, 2, 3, 4, 5)
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

    inputs = models.JSONField(
        verbose_name=_("Answers"),
        default=dict,
        blank=True,
        help_text=_(
            "The answers to the questions the section's rules ask, by key. "
            "Which questions those are is the ruleset's declaration, so this "
            "is the only place a statement keeps them."
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
    # The rules this statement is settled under, bound when it is created and
    # never afterwards. `ruleset` is the row (PROTECT: a version a statement
    # depends on cannot be deleted), `ruleset_hash` is the dedup and audit key,
    # and `ruleset_snapshot` is the whole closure plus its parameters, so the
    # statement can be evaluated from itself alone.
    ruleset = models.ForeignKey(
        RuleSet,
        verbose_name=_("Ruleset version"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.PROTECT,
        related_name="statements",
    )
    ruleset_hash = models.CharField(
        verbose_name=_("Ruleset hash"), max_length=64, blank=True, default=""
    )
    ruleset_snapshot = models.JSONField(
        verbose_name=_("Ruleset snapshot"),
        default=dict,
        blank=True,
        help_text=_("The rules and numbers this statement was created under."),
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
            # All users may view their own statements and statements of excursions they are
            # responsible for — and so may whoever the section's rules asked to sign it.
            # Being named a signer confers the sight of exactly the statements the rules
            # ask you to sign, for as long as they ask: see `Statement.names_as_signer`.
            # `may_sign_now` is the same object as `approve_obj` below, so the right to
            # sign can never again mean the right to look is missing — which is the hole
            # these two lines close.
            "view_obj": is_creator
            | leads_excursion
            | has_global_perm("finance.view_global_statement")
            | is_named_signer
            | may_sign_now,
            # All users may change relevant (see above) draft statements.
            "change_obj": (not_submitted & (is_creator | leads_excursion))
            | has_global_perm("finance.change_global_statement"),
            # All users may delete relevant (see above) draft statements.
            "delete_obj": not_submitted
            & (is_creator | leads_excursion | has_global_perm("finance.delete_global_statement")),
            # Signing a statement off is the capability plus the section's own
            # routing: whoever may act as an approver at all, and whom the
            # rules still leave something to sign.
            "approve_obj": may_sign_now,
        }

    @property
    def title(self):
        if self.excursion is not None:
            return _("Excursion %(excursion)s") % {"excursion": str(self.excursion)}
        else:
            return self.short_description

    def __str__(self):
        return str(self.title)

    # --- the answers ------------------------------------------------------
    #
    # ``night_cost``, ``allowance_to``, ``subsidy_to`` and ``ljp_to`` were four
    # columns on this table, which is to say that the shape of the Heidelberg
    # regulation was the shape of the schema: a section whose rules ask a fifth
    # question had nowhere to put the answer and no way to be asked it. They
    # are now four keys in ``inputs``, declared by the ruleset that reads them
    # (:meth:`kompass.rules.Ruleset.inputs`) and validated against that
    # declaration on the way in (:func:`finance.inputs.clean`).
    #
    # What stays here are *read* accessors, for the pages that still narrate
    # the Heidelberg payout — the excursion's finance overview, the submitted
    # statement's admin page, the LJP proof — plus the derived figures those
    # pages print. They are deliberately read-only: an answer is written by the
    # one path that checks it against the declaration, and a writable
    # ``statement.subsidy_to = somebody`` is how the field drifted from the
    # rules in the first place.

    @property
    def answers(self) -> dict:
        """The answers this statement carries, by input key, as JSON."""
        return dict(self.inputs or {})

    def answer_member_ids(self, key: str) -> list[int]:
        """The member ids answering ``key``, in the order they were stored.

        Anything in there that is not an id is skipped rather than raised on,
        for the same reason :func:`finance.engine.answers.coerce_input` hands a
        value that does not fit through: a section may change what a question
        asks for while statements still hold the old answer, and a page that
        only wanted to print a name must not be the thing that breaks. The
        *rules* refuse it — the typed accessor raises and ``evaluate`` reports
        it — so nothing is paid on a figure this invented.
        """
        value = self.answers.get(key)
        if value is None:
            return []
        if not isinstance(value, list):
            value = [value]
        return [pk for pk in (_as_id(entry) for entry in value) if pk is not None]

    def answer_members(self, key: str) -> list[Member]:
        """The members answering ``key``, in one bulk lookup: ids are the record.

        A member who has since been deleted drops out rather than raising,
        which is what the ``SET_NULL`` on the old columns did.
        """
        ids = self.answer_member_ids(key)
        if not ids:
            return []
        by_id = Member.objects.in_bulk(ids)
        return [by_id[pk] for pk in ids if pk in by_id]

    def answer_member(self, key: str) -> Member | None:
        """The one member answering ``key``, or ``None``."""
        members = self.answer_members(key)
        return members[0] if members else None

    @property
    def night_cost(self) -> Decimal:
        """What a night cost per youth leader, as answered — zero if not an amount.

        See :meth:`answer_member_ids`: a readout renders, the rules refuse.
        """
        try:
            return cvt_to_decimal(self.answers.get("night_cost") or 0)
        except (TypeError, ValueError, ArithmeticError):
            return Decimal(0)

    @property
    def allowance_to(self) -> list[Member]:
        """Who receives an allowance, as answered."""
        return self.answer_members("allowance_to")

    @property
    def subsidy_to(self) -> Member | None:
        """Who receives the travel and overnight subsidy, as answered."""
        return self.answer_member("subsidy_to")

    @property
    def ljp_to(self) -> Member | None:
        """Who receives the LJP contributions, as answered."""
        return self.answer_member("ljp_to")

    def _get_setting(self, key: str) -> Decimal:
        """The section's number for ``key``, as it applies to this statement.

        The statement's own ruleset snapshot, taken when it was created, so
        that a draft is settled against the numbers that were in force the day
        it was opened rather than whatever the settings say today. A statement
        from before the store falls back to the old behaviour: its
        ``settings_snapshot`` once submitted, the live settings while a draft.

        The value is a ``Decimal``: the snapshots hold JSON and the settings
        may hold either, and every amount column in this app is a
        ``DecimalField``, so the conversion happens once, here, through the
        text form — ``Decimal(str(0.15))`` is ``Decimal("0.15")`` and not the
        binary expansion ``Decimal(0.15)`` would give.
        """
        return statement_params(self)[key]

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
    def payout_mode(self):
        """Who makes this statement's bank transfers — ``"self"`` or ``"office"``.

        The declaration of the rules this statement is **bound** to
        (:attr:`kompass.rules.Ruleset.payout`), read off its own snapshot, so
        it costs no query and no evaluation: it is a string the version was
        imported with.

        Bound rather than current, which is the decision in this property. A
        section that changes how it pays imports a new version, and the
        statements created before it keep the old arrangement — the same rule
        that keeps June's rates on a statement opened in June. The alternative,
        reading whatever version is in force at the moment somebody looks, would
        make a settled statement's terminal act change meaning afterwards: a
        payout released as *zur Auszahlung übergeben* would read as *ausgezahlt*
        once the section took the transfers back in house, which is the record
        saying something that did not happen. The cost is the other way round
        and it is bounded: a statement opened before the change is reviewed
        under the old wording, once, and re-settling it under a correction is
        the deliberate act #561 is for.

        A statement bound to no version at all — an instance that has imported
        none — reads ``"self"``, like a ruleset that declares nothing.
        """
        snapshot = self.ruleset_snapshot or {}
        declared = snapshot.get("payout") or SELF_PAYMENT
        return declared if declared in PAYOUT_MODES else SELF_PAYMENT

    @property
    def payout_handoff(self):
        """Whether releasing this statement is a handoff rather than a payment.

        The one question every mode-dependent branch asks. ``True`` means the
        section's Geschäftsstelle makes the transfers, so what Kompass records
        is that the statement was handed over — and :meth:`_pay_out` will not
        record even that until the summary has actually gone.
        """
        return self.payout_mode == OFFICE_PAYMENT

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

    def save(self, *args, **kwargs):
        """Bind a new statement to the active rules, then write its rows.

        Binding happens once, on creation: from then on the statement carries
        the rules it was opened under. The obligation rows are rewritten on
        every draft save and left alone once the statement is submitted, which
        is what makes them the record rather than a cache.
        """
        creating = self._state.adding
        if creating and self.ruleset_id is None:
            bind_ruleset(self)
        super().save(*args, **kwargs)
        if not self.submitted:
            materialise(self)

    def submit(self, submitter=None):
        """Hand the statement in, and freeze the payout it was handed in with.

        One wrinkle worth knowing about: a statement whose rules report a
        problem (the one Heidelberg reports is a covered receipt with no payer)
        is submitted but **not** frozen, because freezing a payout that is
        known to be wrong would make the record say something false. Such a
        statement keeps resolving live, cannot generate transactions and cannot
        be paid out, and freezes on the first save after the problem is fixed.
        """
        self._capture_settings_snapshot(force=True)
        self.status = self.SUBMITTED
        self.submitted_date = timezone.now()
        self.submitted_by = submitter
        self.save()
        # The rows the statement is handed in with are the ones it is settled
        # from: frozen here, read everywhere afterwards, never recomputed.
        freeze_obligations(self)

    @property
    def rule_result(self):
        """This statement resolved against the section's rules.

        The single seam between the finance app and the rules engine: who is
        owed what, what is wrong with the statement, and what still has to be
        asked (:class:`finance.engine.Result`). Every money figure below is
        read off it rather than recomputed here.

        A **submitted** statement reads the rows that were frozen when it was
        handed in, and reads them once per instance: that record is what it is
        settled from, and no code needs to run again to render it. A **draft**
        is resolved live on every access, because it follows its own fields —
        change the subsidy recipient and the next read says so — and
        fingerprinting the recipients, the bills and the excursion to cache
        that correctly would cost the queries it saves.
        """
        if "_frozen_result" in self.__dict__:
            return self.__dict__["_frozen_result"]
        if self.submitted and rows_exist(self):
            self.__dict__["_frozen_result"] = result_from_rows(self)
            return self.__dict__["_frozen_result"]
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
            return f"{self!s}: {transfer.label}"
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

    def payout_lines(self, exclude=("bill",)):
        """The payout as the rules resolved it, one line per transfer.

        What the summary document prints instead of four hardcoded line kinds.
        Each line carries what a person reading the paper needs — who gets it,
        what it is called, the arithmetic behind it — and the amount is signed
        from the recipient's point of view, so a deduction prints as a negative
        rather than as a special case in the template.

        The bills are excluded by default: a receipt is a fact about what was
        spent, not a line the rules invented, and the document lists those
        separately from its own evidence.
        """
        result = self.rule_result
        members = self._transfer_members(result)
        lines = []
        for transfer in result.rule_transfers:
            if transfer.category in exclude:
                continue
            for party, sign in ((transfer.destination, 1), (transfer.source, -1)):
                if not isinstance(party, RuleMember):
                    continue
                member = members.get(party.id)
                amount = sign * transfer.amount
                lines.append(
                    {
                        "label": str(transfer.label) or transfer.category,
                        "explanation": str(transfer.explanation),
                        "recipient": member.name if member is not None else "",
                        "amount": amount,
                        # Both, because a document says "abzüglich 120,00 €"
                        # rather than "-120,00 €", and a template cannot do
                        # arithmetic.
                        "amount_abs": abs(amount),
                        "negative": amount < 0,
                        "category": transfer.category,
                        "rule_id": transfer.rule_id,
                    }
                )
        return lines

    def payment_orders(self):
        """One bank transfer somebody has to make, per booking.

        The payout as an **instruction** rather than as arithmetic:
        :meth:`payout_lines` says what the rules awarded and to whom, and this
        says what to type into a banking form — the recipient, their account,
        the reference the money arrives under, the amount, and whether this
        amount may be added to another one for the same person.

        It reads the :class:`Transaction` rows, which is the only record that
        carries all four. A payout line is a rule's output and knows nothing
        about accounts; a booking is what :meth:`reduce_transactions` has
        already bundled, so what is listed here is the set of transfers that
        actually have to be made, not a list that would have to be bundled
        again by whoever reads it.

        ``separate`` is the fact the paper could not previously carry. The
        section's rules may keep an amount out of every other bank transfer —
        a Tourenleitervergütung is tax-relevant under § 3 Nr. 26 EStG and has
        to arrive on its own — and two rows for one person then read as a
        duplicate somebody forgot to combine. It is set when this person has
        another booking in a *different* settlement group, which is exactly the
        condition under which combining them would be wrong, and it carries the
        group's own token as the reason: the token is the ruleset's vocabulary
        rather than German prose, so the paper states the consequence and names
        the group beside it.

        Ordered by recipient and then by booking, so that two amounts to one
        person are adjacent and the reader can see the pair the note is about.
        """
        bookings = sorted(
            self.transaction_set.select_related("member", "ledger"),
            key=lambda booking: (booking.member.name, booking.pk),
        )
        groups = {}
        for booking in bookings:
            groups.setdefault(booking.member_id, set()).add(booking.settlement_group)
        orders = []
        for booking in bookings:
            iban = IBAN(booking.member.iban or "", allow_invalid=True)
            orders.append(
                {
                    "recipient": booking.member.name,
                    "iban": str(iban) if iban.is_valid else "",
                    "reference": booking.reference,
                    "amount": booking.amount,
                    "ledger": booking.ledger.name if booking.ledger is not None else "",
                    "separate": len(groups[booking.member_id]) > 1,
                    "settlement_group": booking.settlement_group,
                }
            )
        return orders

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
                "settlement_group": transfer.settlement_group,
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
        """Whether the answered allowance recipients match the regulations.

        Asked of the answered ids rather than of the members behind them, so
        the statement list can ask it per row without a query each.
        """
        if self.allowances_paid > self.real_staff_count:
            # it is allowed that less allowances are utilized than youth leaders are enlisted
            return False
        if self.excursion is not None:
            leaders = {yl.pk for yl in self.excursion.jugendleiter.all()}
            for member_id in self.answer_member_ids("allowance_to"):
                if member_id not in leaders:
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
        - `Statement.UNRESOLVED`:
          The section's rules could not resolve the statement at all, so there
          is no payout to compare anything against.

        ``UNRESOLVED`` is asked **last**, after every more specific diagnosis.
        A covered bill with nobody to pay back is a rule error *and* a total
        that does not match, and "the total differs" is the more useful of the
        two sentences to show. What is left for this to catch is the case with
        no other symptom at all: an answer that no longer fits the type its
        declaration promises reads as its type's empty value in the readouts —
        deliberately, so the page renders and somebody can reach the form — and
        then every figure is zero, the arithmetic agrees with itself, and the
        statement used to report "everything is correct", which is exactly when
        it is not. `confirm` refuses on `is_valid`, so this is also what keeps
        money from moving on a statement the rules could not settle.

        ``INVALID_ALLOWANCE_TO`` is asked **first**, by the same argument read
        the other way. It is the only one of these about an *answer* rather
        than about the bookkeeping that follows from one, and it names the
        thing to go and change. Everything downstream of a bad answer — no
        rows written, so no transactions, so a total that does not match — is a
        symptom, and showing a symptom when the cause has a sentence of its own
        is the mistake this ordering exists to avoid.
        """
        if not self.allowance_to_valid:
            return Statement.INVALID_ALLOWANCE_TO
        if not self.transactions_match_expenses:
            return Statement.NON_MATCHING_TRANSACTIONS
        if not self.ledgers_configured:
            return Statement.MISSING_LEDGER
        if not self.total_valid:
            return Statement.INVALID_TOTAL
        if self.rule_result.errors:
            return Statement.UNRESOLVED
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
            Statement.UNRESOLVED: _(
                "The section's rules could not settle this statement. Check the answers it gives."
            ),
        }[self.validity]

    def _signatures(self):
        """Who has signed, split into the named and the unattributable."""
        signatures = list(self.approval_set.all())
        members = [approval.member_id for approval in signatures if approval.member_id]
        others = {approval.signer for approval in signatures if not approval.member_id}
        return members, others

    @property
    def approval_states(self):
        """Each signature the rules asked for, and whether it is in: the record.

        Read off the :class:`~finance.store.ApprovalConstraint` rows that were
        frozen at submission and the :class:`~finance.store.Approval` rows
        signed since. This is what the statement's page *shows* — who the
        rules named when it was handed in — and deliberately not what decides
        whether somebody may sign now; see :attr:`live_approval_states`.
        """
        members, others = self._signatures()
        return approval_states(
            [row.as_row() for row in self.approval_constraint_set.all()],
            members,
            uncredited=others,
            recorded=True,
        )

    @property
    def live_approval_states(self):
        """The same constraints, with eligibility resolved against today.

        The gate rather than the record. Who *has* signed and what was
        overridden come from the rows; who *may* sign is asked of the rules
        again, because the alternative regresses against the behaviour before
        the store: a treasurer appointed after a statement was handed in held
        the capability and was still refused. Cached per instance, because a
        page asks this three times.
        """
        if "_live_states" not in self.__dict__:
            members, others = self._signatures()
            self.__dict__["_live_states"] = approval_states(
                current_constraint_rows(self), members, uncredited=others
            )
        return self.__dict__["_live_states"]

    @property
    def fully_approved(self):
        """Whether every applicable constraint has its quorum or an override."""
        if self.confirmed:
            return True
        if not self.submitted:
            return False
        return fully_approved(self.live_approval_states)

    def names_as_signer(self, member):
        """Whether this statement's approval record names ``member`` a signer.

        What :func:`finance.rules.is_named_signer` asks, and therefore what
        lets somebody the rules asked for a signature **see** the statement
        they have to sign. Three things it is not, each of them load-bearing:

        *Not the gate.* :meth:`may_be_approved_by` answers "is there anything
        left for you to sign", which goes false the moment you sign — and a
        page that vanishes when you use it is no use. This asks the longer
        question: are you among the people the rules named.

        *Not the rules, asked again.* It reads the eligible sets off the
        **record** — the live :class:`~finance.store.ApprovalConstraint` rows,
        through :attr:`approval_states` — and never re-resolves the ruleset,
        because the same question is asked of every row of a statement list
        (:meth:`naming_signer_q`) and a resolution per row is not affordable
        there. That is also why the two cannot drift: the list's SQL and this
        read the same column of the same rows.

        *Not every step on the record.* Only a step that **applies** counts. A
        section's threshold step names its treasurer whatever the payout comes
        to (``applicable=False`` under it), and reading those would have handed
        the treasurer every small statement in the section — a global
        permission in all but name.

        A statement that is not submitted names nobody: a draft is its
        author's, the rules have asked for no signature yet, and a statement
        handed back for rework keeps its rows but stops being anybody's to
        sign. A **settled** one still names whoever signed it, which is the
        point — the record of what you put your name to is yours to read.
        """
        if member is None or not self.submitted:
            return False
        return any(
            state.applicable and member.pk in state.eligible for state in self.approval_states
        )

    @staticmethod
    def naming_signer_q(member):
        """A ``Q`` matching the statements :meth:`names_as_signer` says yes to.

        The statement *list* is a queryset filter rather than a per-row
        permission check (``Member.filter_statements_by_permissions``), so the
        signer's right to see has to be expressible as SQL — and the eligible
        set is a JSON array, whose ``contains`` lookup Django does not support
        on SQLite. So the membership test runs in Python over one bulk read of
        the applicable rows (``ApprovalConstraint.objects.naming``) and the
        ids come back as a literal: **one extra query per list request**,
        constant in the number of statements, with no ruleset resolved.

        The status clause is what makes a draft name nobody, exactly as
        :meth:`names_as_signer` does — including a submitted statement that
        was rejected back to its author, which keeps its rows.
        """
        return ~Q(status=Statement.UNSUBMITTED) & Q(
            pk__in=ApprovalConstraint.objects.naming(member)
        )

    def may_be_approved_by(self, member):
        """Whether ``member`` can still advance any open constraint.

        The capability — ``finance.process_statementsubmitted`` — is checked by
        the caller, as it always was; this is the second half of the question:
        is there anything left for this person to sign? A constraint that named
        nobody is answered by the capability alone; one whose named people were
        all excluded is answered by nobody.
        """
        if member is None or not self.submitted or self.confirmed:
            return False
        return may_sign(self.live_approval_states, member.pk)

    def signature_completes_approval(self, member=None, user=None):
        """Whether one signature from this signer would settle the last step.

        The question an interface has to ask *before* the click, because
        :meth:`approve` pays out on the signature that completes the quorum
        and records one that does not — two different acts behind the same
        call. A page that cannot tell them apart has to describe one of them
        wrongly, and the one it described wrongly was the signature short of a
        quorum: it reported "not ready to be confirmed" over a signature it had
        just taken.

        Asked of the *gate* rather than the record, with this signer's
        signature added to the ones already in — as a member if they have a
        member record, otherwise as their account, which is how
        :attr:`finance.store.Approval.signer` counts them. A signer who has
        already signed gets the honest answer for free: adding their signature
        again changes nothing, so this is then simply whether the statement is
        approved already.

        Nobody — no member and no account — is not a signer, and the answer is
        no rather than "whatever the statement says", because the point of the
        question is what *this person's* next click does.
        """
        if not self.submitted or self.confirmed:
            return False
        if member is None and user is None:
            return False
        members, others = self._signatures()
        if member is not None:
            members = [*members, member.pk]
        else:
            others = {*others, ("user", user.pk)}
        return fully_approved(
            approval_states(current_constraint_rows(self), members, uncredited=others)
        )

    def approve(self, member=None, note="", user=None):
        """Record a signature, and pay out once the last one is in.

        Returns whether the statement ended up confirmed. A signature is
        recorded even when it does not complete the quorum — that is the point
        of having more than one — and the payout happens on the signature that
        does. Signing twice is signing once: the row is unique per signer, and
        ``user`` is recorded so that an administrator with no member record is
        still *one* person rather than an anonymous tally that can reach any
        quorum by clicking twice.

        Each constraint's ``satisfied`` column is written here **once** — by
        the first of these calls that finds the step satisfied — and no later
        signature writes it again. It is a record and not a cache of the gate:
        re-syncing every row to today's answer on every signature made the
        column say, of a step that was signed, that it was not — a signer who
        has since lost the capability stops advancing the step at the *gate*,
        which is what the gate is for, and the next signature on any other
        step then wrote that verdict over the record of hers. The ``Approval``
        row she left is the trail that matters and it stood all along, so
        nothing was ever paid out wrongly; what §6's appeal to the GoBD's
        *Unveränderbarkeit* cannot live with is the record being edited at all.

        "The first call that finds it satisfied" rather than "the signature
        that satisfied it", because those differ in exactly the case above: a
        step the gate has stopped counting is not recorded by the signature
        that reached its quorum.

        And **once here** is the honest scope: the row this writes is the
        live one, and a re-freeze writes a *new* row from outside this method.
        :func:`finance.engine.statements.materialise` supersedes
        the rows it finds and carries their decision — this column and the
        three ``overridden_*`` fields — onto the row that takes over, so what
        a row says stays true of the row for as long as it was live. It used
        to delete them and start blank, which cost an override its record and
        handed a waived payout back to the board on nothing worse than a
        finance officer covering a receipt (#555).
        """
        if not self.submitted or self.confirmed:
            return False
        if not self._has_signed(member, user):
            Approval.objects.create(statement=self, member=member, user=user, note=note)
        self.__dict__.pop("_live_states", None)
        states = self.live_approval_states
        # Only the rows that have not been answered yet, so that the write can
        # go one way and the column cannot be revised.
        for row in self.approval_constraint_set.filter(satisfied=False):
            state = next((s for s in states if s.name == row.name), None)
            if state is not None and state.satisfied:
                row.satisfied = True
                row.save(update_fields=["satisfied"])
        if not fully_approved(states):
            return False
        return self._pay_out(member)

    def _has_signed(self, member, user):
        """Whether this signer already has a signature on this statement.

        Asked per *identity*, not per row: a `get_or_create` on the whole
        triple missed the case where somebody signed once as an account with
        no member record and again once their member record existed, which
        then violated the account's own uniqueness constraint and raised a raw
        `IntegrityError` — a 500 where the answer should have been "signing
        twice is signing once".
        """
        conflict = Q(member__isnull=True, user__isnull=True)
        if member is not None or user is not None:
            conflict = Q(pk__in=[])
            if member is not None:
                conflict |= Q(member=member)
            if user is not None:
                conflict |= Q(user=user)
        return self.approval_set.filter(conflict).exists()

    def override_approval(self, name, member, reason):
        """Sign a constraint off without its quorum, on the record.

        An override is a state, not an absence: the constraint stays in the
        list with who overrode it and why, because "we went ahead anyway" is
        exactly the thing an audit has to be able to find.

        It does **not** escape the forbids. Somebody a forbid excluded from a
        constraint may not override that constraint: a rule that says "nobody
        this statement pays may approve it" would otherwise be a formality for
        anybody holding the permission, and recording that they did it is a
        mitigation rather than a control.

        Nor does it clear a constraint the rules could not resolve at all. A
        broken forbid is a rule that *failed to say* who is excluded, so there
        is no answer to the question "may this person sign it off" — and the
        person with the most reason to ask is the one the forbid was written
        for. Such a payout stays stuck until the rule is fixed, which is what
        "stuck" has to mean to be worth claiming.

        And a step that **does not apply** cannot be waived, which is new and
        is the honest place for it. Such a step is not in the way —
        :func:`~finance.engine.approval.fully_approved` ignores it — so the
        request has nothing to grant, and granting it anyway wrote a waiver
        for a question nobody had asked. That record then came due: a payout
        under the section's threshold let one person waive the board's two
        signatures *before the rules asked for them*, and when a covered
        receipt pushed the statement over the threshold the step the rules now
        asked for took the waiver over. One unrelated signature paid it out.
        The carry re-asks this too — a waiver does not pass onto a step that
        was asking nothing when it was given
        (:func:`finance.engine.statements._why_the_waiver_does_not_carry`) —
        and that is where the money is actually stopped; refusing here stops
        the meaningless record being written at all, which is the difference
        between a control and a repair.

        The refusals themselves live in :meth:`override_refusal`, because the
        API endpoint has to report *which* one it was and a second hand-kept
        copy of this list is what let the new refusal answer 200 there.
        Returns whether the statement ended up confirmed.
        """
        if self.override_refusal(name, member) is not None:
            return False
        row = self.approval_constraint_set.filter(name=name).first()
        row.overridden_by = member
        row.overridden_at = timezone.now()
        row.override_reason = reason
        row.save(update_fields=["overridden_by", "overridden_at", "override_reason"])
        self.__dict__.pop("_live_states", None)
        if not self.fully_approved:
            return False
        return self._pay_out(member)

    def override_refusal(self, name, member):
        """Why ``member`` may not waive the step ``name``, in words, or ``None``.

        The refusals of :meth:`override_approval`, in one place because they
        are asked in two: the method returns ``False``, which is all a model
        caller needs, and the endpoint has to *say* which refusal it was —
        every one of them answers 422, so that a 200 means the override is on
        the record (#548). Kept as two parallel lists, they drifted the first
        time one was added: the step that does not apply was refused by the
        method and answered 200 by the endpoint, with ``overridden: false``
        buried in a body that also said ``approved: true``.

        The order is the order a person wants to be told about: whether the
        statement can be approved at all, then whether this step exists, then
        whether the section allows overrides at all, then whether the step is
        being asked for, then whether anybody could sign it, and last whether
        this particular person may. The caller checks its own payload — an
        override has to say why — before asking any of it.

        *Whether this person may* is the part that is about the override
        rather than about the step, and it has two halves
        (:meth:`_override_scope_refusal`): the section's own declaration of
        who may give one (:attr:`kompass.rules.Ruleset.override`), and the
        limit that holds in every section — an override reaches only a step
        your signature would have counted towards. Without that limit the first
        of two required signers could waive the second, and a rule requiring
        two people was a rule requiring one.
        """
        if not self.submitted or self.confirmed:
            return _("Only submitted, unconfirmed statements can be approved.")
        row = self.approval_constraint_set.filter(name=name).first()
        if row is None:
            return _("This statement has no approval step called %(name)s.") % {"name": name}
        policy = override_policy(self)
        if not policy.allowed:
            return _(
                "The section's rules do not allow an approval step to be signed off "
                "without its signatures. Ask somebody who may sign it."
            )
        if not row.applicable:
            return _(
                "The rules are not asking for this approval step, so there is nothing to override."
            )
        if self.approval_cannot_be_resolved(name):
            return _(
                "The section's rules could not say who may sign this approval step, "
                "so it cannot be overridden either."
            )
        if member is not None and self.forbids_approval_by(name, member):
            return _("The section's rules exclude you from this approval step.")
        return self._override_scope_refusal(name, member, policy)

    def _override_scope_refusal(self, name, member, policy):
        """Whether ``member`` is somebody this step's override may come from.

        **Only a step you could have signed.** Your signature counts on a
        step when you are in its eligible set as the gate resolves it now —
        or, for an account with no member record, when the set is not empty,
        which is how :func:`~finance.engine.approval.states` credits such a
        signature. That is the bound: an override is what you can do instead
        of the quorum, so it reaches no further than your own signature does.

        **Unless the step named nobody**, which is what the override exists
        for: a vacant office leaves its step with no group and no exclusion,
        and nothing in Kompass can be signed in its place. There the forbids
        are asked about you directly (:func:`finance.engine.forbid_against`),
        because a step that named nobody recorded nobody against them — and a
        rules failure there refuses, like a step the rules could not resolve.

        **And the section's own restriction**, when it names roles: the person
        has to hold one of them today.
        """
        state = next(state for state in self.live_approval_states if state.name == name)
        named_nobody = not state.eligible and not state.excluded
        if named_nobody:
            if member is not None:
                try:
                    barred = forbid_against(self, self.rule_result, member.pk)
                except Exception:
                    return _(
                        "The section's rules could not say whether they exclude you from "
                        "this approval step, so you cannot override it."
                    )
                if barred is not None:
                    return _("The section's rules exclude you from this approval step.")
        elif member.pk not in state.eligible if member is not None else not state.eligible:
            # An account with no member record counts only where the group is
            # not empty, so a step whose every named person a forbid excluded
            # is one its signature would not have counted on either.
            return _("You may only override an approval step you could sign yourself.")
        if policy.roles:
            holders = RoleAssignment.roles_at()
            if member is None or not any(
                member.pk in holders.get(role, ()) for role in policy.roles
            ):
                return _(
                    "The section's rules only let the holders of these roles override "
                    "an approval step: %(roles)s."
                ) % {"roles": ", ".join(policy.roles)}
        return None

    def approval_cannot_be_resolved(self, name):
        """Whether the rules failed to say who may sign the step ``name``."""
        return any(state.name == name and bool(state.error) for state in self.live_approval_states)

    def forbids_approval_by(self, name, member):
        """Whether a forbid excludes ``member`` from the constraint ``name``.

        The permission re-check is not a forbid: somebody excluded because they
        did not hold the capability when the statement was handed in may hold
        it now, and the capability is checked by the caller anyway.
        """
        for state in self.live_approval_states:
            if state.name != name:
                continue
            return any(
                exclusion.member == member.pk and exclusion.forbid != PERMISSION_EXCLUSION
                for exclusion in state.excluded
            )
        return False

    def _pay_out(self, confirmer=None):
        """Flip to paid: the last step, once the signatures are in.

        In a section whose Geschäftsstelle makes the transfers
        (:attr:`payout_mode`) the last step is not a payment but a **handoff**,
        and the handoff is the mail: the summary with its payment orders is
        what the office works from. So the mail is sent here, from the one
        funnel every release goes through — :meth:`approve` and
        :meth:`override_approval` both end up here, and an endpoint that sent
        it instead would leave the other two able to mark a statement handed
        over with nothing handed over.

        **And the status does not move until the mail has gone.** Nothing else
        would be true: in handoff mode "Completed" asserts that somebody else
        now has the instruction, and asserting it over a mail that was refused
        is precisely the defect — a status that claims an act that did not
        happen. A send that fails therefore leaves the statement submitted, and
        leaves the signatures that are already in standing: pressing the button
        again retries the handoff and records no second signature
        (:meth:`_has_signed`), which is why the failure costs a click rather
        than a statement.
        """
        if self.rule_result.errors:
            # A statement whose rules report a problem has no settled payout to
            # pay out: its rows were never frozen, and `generate_transactions`
            # refused for the same reason.
            return False
        if not self.validity == Statement.VALID:
            return False
        if self.payout_handoff and not self.hand_over(confirmer):
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

    def confirm(self, confirmer=None, user=None):
        """Sign the statement off and pay it out if that completes the quorum.

        The name the admin and the API have always used. It is now one
        signature among however many the section's rules ask for — for
        Heidelberg, which asks for exactly one from the finance department,
        this is behaviourally what it always was.
        """
        if not self.submitted:
            return False
        if not self.validity == Statement.VALID:
            return False
        return self.approve(confirmer, user=user)

    def generate_transactions(self):
        """Book one transaction per member a transfer touches.

        Returns ``False`` without writing anything when the rules reported a
        problem — a covered bill with no payer is the one Heidelberg reports —
        so a statement that cannot be paid out leaves no half-generated rows
        behind. Money owed to a member is a transfer *to* them and money
        charged against their reimbursement a transfer *from* them, which is
        where the negative amount of an org-fee row comes from.

        The transfer's settlement group rides along onto the booking, because
        the rules decided it and :meth:`reduce_transactions` is what reads it
        back: which amounts may not share a bank transfer is a property of the
        money, not of the screen that bundles it.
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
                    settlement_group=transfer.settlement_group,
                ).save()
        return True

    def reduce_transactions(self):
        """Bundle what may share a bank transfer, and only that.

        To minimise the number of transfers somebody has to make, bookings to
        the same person out of the same ledger become one — *within one
        settlement group*. The group is the token the section's rules put on
        the transfer (:attr:`kompass.rules.Transfer.settlement_group`), carried
        through to the booking, and it is the third part of the key here.

        Which is the whole of the feature: the Tourenleitervergütung is
        tax-relevant under § 3 Nr. 26 EStG and has to reach the recipient as
        its own transfer, although it is one statement, one approval and one
        process with their travel costs. Before, the two were added together
        and paid out as one amount under a reference that concatenated both, so
        the taxable part was not a payment anybody could point at. A ruleset
        that names no group merges exactly as it always did.

        **The reference text is deliberately unchanged.** A merged row still
        itemises what it covers (``"Fahrtkosten EUR 24.00, Tagegeld EUR
        28.00"``), which is what a reader reconciling one bank line against the
        paper needs, and a row that stayed on its own still carries its own
        transfer's reference verbatim — which is precisely what merging used to
        destroy. The group token itself is *not* written into the reference: it
        is the ruleset's internal vocabulary rather than German a stranger
        reads, and what tells the reader the two rows are deliberate is that
        each one says what it is for. The demanding reader is the one who gets
        the statement as a PDF and was never in Kompass; "Tourenleitervergütung"
        on its own line is an instruction they can act on, and the concatenation
        was not.
        """
        transactions = self.transaction_set.all()
        if any(t.ledger is None for t in transactions):
            return

        def sort_key(trans):
            return (trans.member.pk, trans.ledger.pk, trans.settlement_group)

        def group_key(trans):
            return (trans.member, trans.ledger, trans.settlement_group)

        transactions = sorted(transactions, key=sort_key)
        for key, transaction_group in groupby(transactions, group_key):
            member, ledger, settlement_group = key
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
                settlement_group=settlement_group,
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
        return len(self.answer_member_ids("allowance_to"))

    @property
    def total_allowance(self):
        """What the youth leaders actually receive as an allowance."""
        return self.rule_result.total_of("allowance")

    @property
    def total_transportation(self):
        return self.transportation_per_yl * self.real_staff_count

    @property
    def real_night_cost(self):
        return min(self.night_cost, self._get_setting("MAX_NIGHT_COST"))

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
        return f"{self.total}€"

    total_pretty.short_description = _("Total")
    total_pretty.admin_order_field = "total"

    def template_context(self):
        """The figures the summary documents print.

        ``payout`` is the part that used to be four hardcoded line kinds in the
        template: it comes from the resolved transfers, so a section whose rules
        pay something else gets it on the paper without anybody editing LaTeX.
        The named figures below it are the rates and totals the document
        narrates around that list.

        ``orders`` is the other half, and it is only on the paper where the
        paper is an **instruction**: in a section whose Geschäftsstelle makes
        the transfers (:attr:`payout_mode`), this document is the only thing
        the person making them ever sees, and until now it carried the covered
        bills and the payout lines and not one account number. Where the
        reviewer makes the transfers they are made from the review screen,
        which shows the accounts and the QR codes, and the document is a
        receipt for what already happened — so ``handoff`` is false, ``orders``
        is empty, and the paper is byte for byte what it was.
        """
        handoff = self.payout_handoff
        orders = self.payment_orders() if handoff else []
        context = {
            "total_bills": self.total_bills,
            "total_bills_theoretic": self.total_bills_theoretic,
            "bills_covered": self.bills_covered,
            "total": self.total,
            "payout": self.payout_lines(),
            "payout_total": sum(
                (line["amount"] for line in self.payout_lines()), cvt_to_decimal(0)
            ),
            "handoff": handoff,
            "orders": orders,
            "orders_total": sum((order["amount"] for order in orders), cvt_to_decimal(0)),
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
                "paid_ljp_contributions": self.paid_ljp_contributions,
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

    def hand_over(self, confirmer=None):
        """Send the office the summary it makes the transfers from.

        Only the handoff mode calls this, and only :meth:`_pay_out` does, right
        before the status would move. The person releasing the statement is
        copied in, which is the same courtesy the review screen's "Beleg
        senden" has always given whoever pressed it.

        Returns whether the mail was accepted for delivery.
        :func:`mailer.mailutils.send` catches its own exceptions and answers
        with a status, so "it did not go" is a value here rather than a
        traceback — and it is the value the status of this statement hangs on.
        """
        cc = [confirmer.email] if confirmer is not None and confirmer.email else []
        return self.send_summary(cc=cc) == SENT

    def send_summary(self, cc=None):
        """
        Sends a summary of the statement to the central office of the association.

        Returns the :mod:`mailer.mailutils` status — ``SENT`` when the message
        was handed to the mail server. Every caller but :meth:`hand_over`
        ignores it, exactly as they did when it returned ``None``: in a section
        that pays from the review screen the mail is a receipt for an act that
        has already happened, and in one whose office pays it *is* the act.
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
        return send_mail(
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
        return f"{self.short_description} ({self.amount}€)"

    def save(self, *args, **kwargs):
        """Save, and keep the statement's materialised payout in step.

        The one field the finance officer may still edit after a statement is
        handed in is ``costs_covered`` — that is what their permission on
        ``BillOnStatementProxy`` is for — and covering a bill changes what is
        owed. So a bill that moves re-freezes its statement's rows, unless the
        statement is already paid out, where nothing may move at all.
        """
        super().save(*args, **kwargs)
        self._refresh_statement()

    def _refresh_statement(self):
        """Re-resolve the statement this bill is on, after the bill moved.

        Called on a save, and on a deletion by :mod:`finance.signals` — on
        *every* deletion, not only one that goes through this instance's
        ``delete``. A queryset delete never calls ``Model.delete``, and a
        statement whose rows a receipt had retired stayed without them once
        the receipt was gone that way: no live approval row, nobody able to
        sign, and nothing wrong with the statement to say why.
        """
        statement = self.statement
        if statement.confirmed:
            return
        if statement.submitted:
            freeze_obligations(statement)
        else:
            materialise(statement)

    def pretty_amount(self):
        return f"{self.amount}€"

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
    settlement_group = models.CharField(
        verbose_name=_("Settlement group"),
        max_length=SETTLEMENT_GROUP_LENGTH,
        blank=True,
        default="",
        help_text=_(
            "The group of bank transfers this booking may share, carried over "
            "from the transfer the section's rules resolved. Bookings are "
            "bundled into one payment only within one group, so an amount that "
            "names its own is transferred separately. Empty means no group."
        ),
    )
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
        return f"T#{self.pk}"

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
