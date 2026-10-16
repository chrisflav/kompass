"""Where a section's rules and their results are kept.

Four models, and between them they answer the question a statement raises
years later: *under which rules was this settled, and what did they say?*

:class:`RuleSet`
    One immutable version of a section's rules — the whole source closure, its
    hash, its parameters, and when it was in force. A correction to a past
    version is a *new row* that points at the one it supersedes, never an
    update: that is the difference between valid time (``valid_from`` /
    ``valid_to``, when the rules applied) and transaction time
    (``imported_at`` / ``activated_at``, when the system learned of them), and
    an auditor needs both.
:class:`RoleAssignment`
    Who held which section role, with dates. The source of ``ctx.roles``.
:class:`Obligation`
    The resolved transfers, materialised as rows. **These are the
    authoritative record**: the payout screen, the generated transactions, the
    summary PDF and the audit trail read rows, never code. A statement can
    therefore be read without re-evaluating anything, which is what makes it
    legible in eight years when the configuration repository, the evaluator
    and possibly the maintainers are gone.
:class:`ApprovalConstraint`
    What the rules asked for in the way of signatures, frozen beside the
    obligations.

A German club's books fall under the GoBD, which asks for *Unveränderbarkeit*
(no entry altered unnoticed), *Nachvollziehbarkeit* (every transaction
traceable) and a versioned *Verfahrensdokumentation*. A git-versioned
configuration repository is that documentation; these rows are the trace.
"""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from finance.parties import MEMBER
from finance.parties import PARTICIPANTS
from finance.parties import SECTION
from members.models import Member

#: The fields of a :class:`RuleSet` row that may never change once it is
#: saved. Everything else about a version is lifecycle — when it was
#: activated, when it was closed, whether its cases passed.
IMMUTABLE_FIELDS = (
    "name",
    "hash",
    "manifest",
    "sources",
    "revision",
    "engine_version",
    "context_version",
    "params",
    "valid_from",
    "supersedes_id",
)

#: How a party is stored on an :class:`Obligation` (see
#: :mod:`finance.parties` for why the strings live elsewhere).
PARTY_KINDS = [
    (MEMBER, _("Member")),
    (SECTION, _("Section")),
    (PARTICIPANTS, _("Participants")),
]


class ImmutableRuleSet(Exception):
    """Raised on an attempt to change what a stored version says."""


class RuleSetManager(models.Manager):
    def active(self, when=None):
        """The version in force at ``when`` (default: now), or ``None``.

        In force means: activated, its validity has started, and its validity
        has not been closed by a successor. Where two rows could answer, the
        one whose validity started last wins — which is what a correction with
        the same valid range is for.
        """
        moment = timezone.now() if when is None else when
        return (
            self.filter(state=RuleSet.ACTIVE, valid_from__lte=moment)
            .filter(Q(valid_to__isnull=True) | Q(valid_to__gt=moment))
            .order_by("-valid_from", "-imported_at")
            .first()
        )


class RuleSet(models.Model):
    """One immutable version of a section's finance rules.

    The whole source closure lives in :attr:`sources`, and the engine loads a
    version from *there* rather than from the file it was read from. A draft
    bound to last month's version therefore keeps last month's rules even
    after the configuration repository has moved on, and two versions coexist
    in one process without either knowing about the other.
    """

    DRAFT, ACTIVE, RETIRED = 0, 1, 2
    STATE_CHOICES = [
        (DRAFT, _("Draft (not activated)")),
        (ACTIVE, _("Active")),
        (RETIRED, _("Retired")),
    ]

    name = models.CharField(verbose_name=_("Name"), max_length=50)
    hash = models.CharField(verbose_name=_("Hash"), max_length=64, unique=True)
    manifest = models.JSONField(
        verbose_name=_("Manifest"),
        default=dict,
        help_text=_("One SHA-256 per file of the ruleset, keyed by relative path."),
    )
    sources = models.JSONField(
        verbose_name=_("Sources"),
        default=dict,
        help_text=_("The ruleset's whole source closure, keyed by relative path."),
    )
    revision = models.CharField(
        verbose_name=_("Revision"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("The commit the sources were read from, where there is one."),
    )
    engine_version = models.CharField(
        verbose_name=_("Engine version"),
        max_length=200,
        blank=True,
        default="",
        help_text=_("The Kompass and interpreter version the sources were imported into."),
    )
    context_version = models.PositiveIntegerField(verbose_name=_("Context version"), default=1)
    params = models.JSONField(
        verbose_name=_("Parameters"),
        default=dict,
        help_text=_("The section's numbers, as exact decimal strings."),
    )
    state = models.IntegerField(verbose_name=_("State"), choices=STATE_CHOICES, default=DRAFT)
    problems = models.JSONField(
        verbose_name=_("Problems"),
        default=list,
        blank=True,
        help_text=_("Why this version was not activated, where it was not."),
    )
    valid_from = models.DateTimeField(verbose_name=_("Valid from"), default=timezone.now)
    valid_to = models.DateTimeField(verbose_name=_("Valid to"), null=True, blank=True, default=None)
    imported_at = models.DateTimeField(verbose_name=_("Imported on"), auto_now_add=True)
    activated_at = models.DateTimeField(
        verbose_name=_("Activated on"), null=True, blank=True, default=None
    )
    cases_passed_at = models.DateTimeField(
        verbose_name=_("Cases passed on"), null=True, blank=True, default=None
    )
    supersedes = models.ForeignKey(
        "self",
        verbose_name=_("Supersedes"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.PROTECT,
        related_name="superseded_by",
    )

    objects = RuleSetManager()

    class Meta:
        verbose_name = _("Ruleset version")
        verbose_name_plural = _("Ruleset versions")
        ordering = ["-valid_from", "-imported_at"]

    def __str__(self):
        return f"{self.name}@{self.short_hash}"

    @property
    def short_hash(self):
        """The first twelve characters of the hash, which is what people read."""
        return self.hash[:12]

    def save(self, *args, **kwargs):
        """Refuse to change what a stored version says.

        A version is a historical fact: a statement settled under it has to
        stay settled under it. Only the lifecycle fields — state, validity
        end, activation, cases, problems — may move after the first save, and
        a correction to the rules themselves is a new row with
        :attr:`supersedes` set.
        """
        if self.pk is not None:
            stored = RuleSet.objects.filter(pk=self.pk).values(*IMMUTABLE_FIELDS).first()
            if stored is not None:
                changed = [
                    field for field, value in stored.items() if getattr(self, field) != value
                ]
                if changed:
                    raise ImmutableRuleSet(
                        f"{self} is a stored version; {', '.join(changed)} cannot change. "
                        "Import a new version instead."
                    )
        return super().save(*args, **kwargs)

    def snapshot(self):
        """What a statement copies so that it can be settled from itself alone.

        A section's ruleset is kilobytes, so the statement carries the whole
        closure rather than a reference to it.
        """
        return {
            "hash": self.hash,
            "name": self.name,
            "sources": dict(self.sources),
            "params": dict(self.params),
            "engine_version": self.engine_version,
            "context_version": self.context_version,
            "revision": self.revision,
        }

    def retire(self, when=None):
        """Close this version's validity, because a successor took over."""
        self.valid_to = timezone.now() if when is None else when
        self.state = RuleSet.RETIRED
        self.save(update_fields=["valid_to", "state"])

    def activate(self):
        """Put this version in force.

        From now, or from :attr:`valid_from` where that is in the future: a
        staged change is activated once and takes effect on its own date,
        which is why activation and validity are separate fields rather than
        one timestamp.
        """
        self.state = RuleSet.ACTIVE
        self.activated_at = timezone.now()
        self.valid_to = None
        self.save(update_fields=["state", "activated_at", "valid_to"])


class RoleAssignment(models.Model):
    """Who holds which section role, with the dates they held it.

    The rules read these as ``ctx.roles["kassenwart"]`` and may route an
    approval by them. What a role *means* is the section's business; Kompass
    only records who held it and when, so that a statement from 2026 is
    approved by the people who were the treasurer in 2026.
    """

    role = models.CharField(
        verbose_name=_("Role"),
        max_length=50,
        help_text=_("The name the section's rules read this role under, e.g. 'kassenwart'."),
    )
    member = models.ForeignKey(
        Member, verbose_name=_("Member"), on_delete=models.CASCADE, related_name="finance_roles"
    )
    valid_from = models.DateField(verbose_name=_("Valid from"), default=timezone.localdate)
    valid_to = models.DateField(verbose_name=_("Valid to"), null=True, blank=True, default=None)
    comment = models.TextField(verbose_name=_("Comment"), blank=True, default="")

    class Meta:
        verbose_name = _("Role assignment")
        verbose_name_plural = _("Role assignments")
        ordering = ["role", "-valid_from"]

    def __str__(self):
        return f"{self.role}: {self.member}"

    @staticmethod
    def roles_at(when=None):
        """``{role: (member_pk, …)}`` for the assignments in force at ``when``."""
        day = timezone.localdate() if when is None else when
        roles: dict[str, list[int]] = {}
        rows = RoleAssignment.objects.filter(valid_from__lte=day).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gte=day)
        )
        for role, member_id in rows.values_list("role", "member_id"):
            roles.setdefault(role, []).append(member_id)
        return {role: tuple(members) for role, members in roles.items()}


class Obligation(models.Model):
    """One resolved transfer, as a row.

    Written on a draft's every save and frozen when the statement is handed
    in. Amounts are integer cents: a row is read back, canonicalised and
    hashed, and JSON numbers are IEEE-754 doubles, which is not a thing to
    store money in.
    """

    statement = models.ForeignKey(
        "finance.Statement",
        verbose_name=_("Statement"),
        on_delete=models.CASCADE,
        related_name="obligation_set",
    )
    position = models.PositiveIntegerField(
        verbose_name=_("Position"),
        default=0,
        help_text=_("The order the rules produced this transfer in."),
    )
    source_kind = models.CharField(
        verbose_name=_("Owed by"), max_length=20, choices=PARTY_KINDS, default=SECTION
    )
    source_member = models.ForeignKey(
        Member,
        verbose_name=_("Owed by (member)"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="owes_obligations",
    )
    source_name = models.CharField(
        verbose_name=_("Owed by (name)"), max_length=100, blank=True, default=""
    )
    destination_kind = models.CharField(
        verbose_name=_("Owed to"), max_length=20, choices=PARTY_KINDS, default=MEMBER
    )
    destination_member = models.ForeignKey(
        Member,
        verbose_name=_("Owed to (member)"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="receives_obligations",
    )
    destination_name = models.CharField(
        verbose_name=_("Owed to (name)"), max_length=100, blank=True, default=""
    )
    amount_cents = models.BigIntegerField(verbose_name=_("Amount in cents"), default=0)
    category = models.CharField(verbose_name=_("Category"), max_length=50, blank=True, default="")
    label = models.CharField(verbose_name=_("Label"), max_length=200, blank=True, default="")
    explanation = models.TextField(verbose_name=_("Explanation"), blank=True, default="")
    rule_id = models.CharField(verbose_name=_("Rule"), max_length=100, blank=True, default="")
    rule_version = models.CharField(
        verbose_name=_("Rule version"),
        max_length=64,
        blank=True,
        default="",
        help_text=_("The hash of the ruleset version that produced this row."),
    )
    computed_at = models.DateTimeField(verbose_name=_("Computed on"), auto_now=True)
    frozen_at = models.DateTimeField(
        verbose_name=_("Frozen on"),
        null=True,
        blank=True,
        default=None,
        help_text=_(
            "Set when the statement was handed in. A frozen row is never changed: "
            "where the payout had to be resolved again, this row is superseded and "
            "the new one is written beside it."
        ),
    )
    superseded_at = models.DateTimeField(
        verbose_name=_("Superseded on"),
        null=True,
        blank=True,
        default=None,
        help_text=_("Set when a later resolution replaced this row. It is kept, not deleted."),
    )

    class Meta:
        verbose_name = _("Obligation")
        verbose_name_plural = _("Obligations")
        ordering = ["statement_id", "position", "pk"]

    def __str__(self):
        superseded = " (superseded)" if self.superseded_at is not None else ""
        return f"{self.category or self.rule_id}: {self.amount}€{superseded}"

    @property
    def live(self):
        """Whether this row is the current one rather than a superseded one."""
        return self.superseded_at is None

    @property
    def amount(self):
        """The amount as a :class:`~decimal.Decimal` of euros."""
        return (Decimal(self.amount_cents) / 100).quantize(Decimal("0.01"))

    @property
    def source_display(self):
        """Who owes the money, as a person reads it."""
        return self._display(self.source_kind, self.source_member, self.source_name)

    @property
    def destination_display(self):
        """Who receives the money, as a person reads it."""
        return self._display(self.destination_kind, self.destination_member, self.destination_name)

    @staticmethod
    def _display(kind, member, name):
        if kind == MEMBER:
            return member.name if member is not None else name
        return str(dict(PARTY_KINDS)[kind])


class Approval(models.Model):
    """One signature on one statement.

    A signature is on the *statement*, not on a constraint: a person who is
    named by two eligible sets signs once and advances both, because what they
    did was approve the payout (GitLab's rule, and the only one that does not
    ask somebody to click twice for the same decision).
    """

    statement = models.ForeignKey(
        "finance.Statement",
        verbose_name=_("Statement"),
        on_delete=models.CASCADE,
        related_name="approval_set",
    )
    member = models.ForeignKey(
        Member,
        verbose_name=_("Signed by"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="finance_approvals",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name=_("Signed by account"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="finance_approvals",
        help_text=_(
            "The account that signed. Recorded beside the member so that a "
            "signature from an administrator with no member record is still "
            "one signature from one person rather than an anonymous tally."
        ),
    )
    at = models.DateTimeField(verbose_name=_("Signed on"), auto_now_add=True)
    note = models.TextField(verbose_name=_("Note"), blank=True, default="")

    class Meta:
        verbose_name = _("Approval")
        verbose_name_plural = _("Approvals")
        ordering = ["statement_id", "at", "pk"]
        # One signature per signer per statement. Pressing the button twice is
        # one person approving, and a quorum of two means two people: without
        # these, an account with no member record could satisfy a four-eyes
        # rule on its own.
        #
        # Deliberately *unconditional*. The obvious spelling — a condition that
        # skips the null rows — is silently dropped by MariaDB, which does not
        # support partial unique indexes (`models.W036`), so it would have been
        # enforced on the agent's SQLite and on nothing in production. These
        # need no condition: in SQLite, MySQL/MariaDB and PostgreSQL alike a
        # `NULL` never collides with another `NULL` in a unique index, which is
        # exactly the rule wanted here — any number of signatures with no
        # member, at most one per member who has one.
        constraints = [
            models.UniqueConstraint(
                fields=["statement", "member"],
                name="finance_approval_once_per_member",
            ),
            models.UniqueConstraint(
                fields=["statement", "user"],
                name="finance_approval_once_per_account",
            ),
        ]

    def __str__(self):
        return f"{self.member or self.user}: {self.at:%Y-%m-%d}"

    @property
    def signer(self):
        """What identifies the person who signed, for counting purposes.

        A member if the signature could be attributed to one, otherwise the
        account, otherwise the fact that somebody unattributable signed — and
        in that last case every such signature is the *same* key, because a
        tally nobody can name must not add up to a quorum.
        """
        if self.member_id:
            return ("member", self.member_id)
        if self.user_id:
            return ("user", self.user_id)
        return ("unattributable",)


class ApprovalConstraint(models.Model):
    """A signature the rules asked for, frozen beside the obligations.

    Persisted at submission so that the question "who was allowed to sign
    this, at the time" has an answer that does not depend on today's
    permissions or today's rules. Evaluating these — quorum, exclusions,
    who has signed — is the approval engine, which is a later step; this is
    the record it will read.
    """

    statement = models.ForeignKey(
        "finance.Statement",
        verbose_name=_("Statement"),
        on_delete=models.CASCADE,
        related_name="approval_constraint_set",
    )
    position = models.PositiveIntegerField(verbose_name=_("Position"), default=0)
    name = models.CharField(verbose_name=_("Name"), max_length=100)
    description = models.TextField(verbose_name=_("Description"), blank=True, default="")
    applicable = models.BooleanField(verbose_name=_("Applicable"), default=True)
    required = models.PositiveIntegerField(verbose_name=_("Signatures required"), default=1)
    eligible_member_ids = models.JSONField(
        verbose_name=_("Eligible members"),
        default=list,
        blank=True,
        help_text=_("Who the rules named, re-checked against the permission system."),
    )
    excluded = models.JSONField(
        verbose_name=_("Excluded"),
        default=list,
        blank=True,
        help_text=_("Who a forbid or the permission check removed, and which one."),
    )
    satisfied = models.BooleanField(
        verbose_name=_("Satisfied"),
        default=False,
        help_text=_("Whether the signatures this constraint asks for are in."),
    )
    overridden_by = models.ForeignKey(
        Member,
        verbose_name=_("Overridden by"),
        null=True,
        blank=True,
        default=None,
        on_delete=models.SET_NULL,
        related_name="overridden_approval_constraints",
    )
    overridden_at = models.DateTimeField(
        verbose_name=_("Overridden on"), null=True, blank=True, default=None
    )
    override_reason = models.TextField(
        verbose_name=_("Reason for the override"), blank=True, default=""
    )
    error = models.TextField(
        verbose_name=_("Could not be resolved"),
        blank=True,
        default="",
        help_text=_(
            "Why the rules could not say who may sign this. A constraint with "
            "a reason here names nobody and is satisfied by nobody: a broken "
            "rule may not be signed away."
        ),
    )
    rule_version = models.CharField(
        verbose_name=_("Rule version"), max_length=64, blank=True, default=""
    )
    frozen_at = models.DateTimeField(
        verbose_name=_("Frozen on"), null=True, blank=True, default=None
    )

    class Meta:
        verbose_name = _("Approval constraint")
        verbose_name_plural = _("Approval constraints")
        ordering = ["statement_id", "position", "pk"]

    def __str__(self):
        return f"{self.name} ({self.required})"

    @property
    def eligible(self):
        """The members the rules named, as rows."""
        return Member.objects.filter(pk__in=self.eligible_member_ids)

    @property
    def overridden(self):
        """Whether somebody signed this constraint off without the quorum."""
        return self.overridden_at is not None

    def as_row(self):
        """The mapping :mod:`finance.engine.approval` evaluates.

        ``satisfied`` is on it because this row **is** the record: it holds
        the answer that was reached when the statement was signed. Left off,
        it was recomputed as ``signed ∩ eligible`` against the *frozen*
        eligible set — and a treasurer appointed after submission is by
        construction not in that set, so an ordinary mid-flight signature
        made a settled statement report ``approved: true`` beside a step read
        as open and missing a signature, with the row itself saying
        ``satisfied`` all along.

        Which of the two questions a reader of this row is asking is *its*
        business to say: :func:`finance.engine.approval.states` reads this
        field only when it is asked with ``recorded=True``, and the gate — the
        same rows, re-resolved — never asks, because asking the question
        afresh is the whole of what it is for.

        The words a person reads come from the resolved state and never from
        this row directly (:func:`finance.api.approval.state_display`), for
        the same reason: a row rendered beside the gate's answer contradicted
        it.
        """
        return {
            "name": self.name,
            "description": self.description,
            "applicable": self.applicable,
            "required": self.required,
            "satisfied": self.satisfied,
            "eligible": list(self.eligible_member_ids),
            "excluded": list(self.excluded),
            "overridden": self.overridden,
            "overridden_by": self.overridden_by_id,
            "override_reason": self.override_reason,
            "error": self.error,
        }
