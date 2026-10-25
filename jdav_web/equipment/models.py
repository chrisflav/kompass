"""Material: what a piece is, where it is, and where it should be.

Three timelines are kept apart:

- what a piece *is*: its ``ProductType`` and its ``Inspection`` history;
- where it *is*: its ``holder`` (a member) or ``location``, with every change
  recorded as an append-only ``CustodyEvent``;
- where it *should be*: the ``Reservation`` its allocation belongs to.

Holding a piece never blocks it. Only a reservation, or a loan with a due
date, does.
"""

from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Tag(models.Model):
    """A tag such as "Hochtour" or "Höhle". A product type may carry several."""

    name = models.CharField(max_length=40, verbose_name=_("Name"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")


class Location(models.Model):
    """A place where material is stored, such as a material cupboard."""

    name = models.CharField(_("name"), max_length=60)
    address = models.CharField(_("address"), max_length=200, blank=True, default="")
    opening_hours = models.TextField(_("opening hours"), blank=True, default="")

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("location")
        verbose_name_plural = _("locations")
        ordering = ["name"]


class ProductType(models.Model):
    """One kind of material, such as "Petzl Spirit Express 12 cm".

    Reservations, availability and the catalogue count per type. A type may
    instead be a *set* of other types (see ``SetEntry``): it then has no pieces
    or sizes of its own, and what is free of it is what is free of its members.
    """

    name = models.CharField(_("name"), max_length=100)
    manufacturer = models.CharField(_("manufacturer"), max_length=100, blank=True, default="")
    product_group = models.CharField(_("product group"), max_length=60, blank=True, default="")
    description = models.TextField(_("description"), blank=True, default="")
    is_psa = models.BooleanField(_("personal protective equipment"), default=False)
    photo = models.ImageField(_("photo"), upload_to="equipment/photos", blank=True)
    article_number = models.CharField(_("article number"), max_length=60, blank=True, default="")
    manual = models.FileField(_("manual"), upload_to="equipment/manuals", blank=True)
    usage_years = models.PositiveIntegerField(_("usage period (years)"), null=True, blank=True)
    inspection_interval_days = models.PositiveIntegerField(
        _("inspection interval (days)"), default=365
    )
    daily_rate = models.DecimalField(
        _("daily rental rate"), max_digits=8, decimal_places=2, null=True, blank=True
    )
    tags = models.ManyToManyField(Tag, blank=True, verbose_name=_("tags"))

    def __str__(self):
        if self.manufacturer:
            return "{} {}".format(self.manufacturer, self.name)
        return self.name

    @property
    def is_set(self):
        return self.set_entries.exists()

    class Meta:
        verbose_name = _("product type")
        verbose_name_plural = _("product types")
        ordering = ["name"]


class Part(models.Model):
    """One physical piece of material.

    A piece may be assembled from other pieces (a quickdraw from a sling and two
    carabiners): the parts point at it through ``parent``. Lending, returning and
    custody act on the top-level piece and carry its parts along.
    """

    ACTIVE, INSPECTION_DUE, RETIRED = "active", "inspection_due", "retired"
    STATUS_CHOICES = [
        (ACTIVE, _("active")),
        (INSPECTION_DUE, _("inspection due")),
        (RETIRED, _("retired")),
    ]

    product_type = models.ForeignKey(
        ProductType,
        verbose_name=_("product type"),
        related_name="parts",
        on_delete=models.PROTECT,
    )
    group = models.ForeignKey(
        "members.Group",
        verbose_name=_("owner group"),
        help_text=_("Empty means the material belongs to the whole section."),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="material_parts",
    )
    psa_id = models.CharField(_("PSA ID"), max_length=40, null=True, blank=True, unique=True)
    serial_number = models.CharField(_("serial number"), max_length=60, blank=True, default="")
    manufactured_on = models.DateField(_("manufacturing date"), null=True, blank=True)
    buy_date = models.DateField(_("purchase date"), null=True, blank=True)
    note = models.CharField(_("note"), max_length=200, blank=True, default="")
    photo = models.ImageField(_("photo"), upload_to="equipment/photos", blank=True)
    parent = models.ForeignKey(
        "self",
        verbose_name=_("assembled into"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="components",
    )
    home_location = models.ForeignKey(
        Location,
        verbose_name=_("home location"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="home_parts",
    )
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    retired_on = models.DateField(_("retired on"), null=True, blank=True)
    # The current custody, cached from the latest CustodyEvent. Written only by
    # ``equipment.services``; a piece is with a member, at a location, or neither.
    holder = models.ForeignKey(
        "members.Member",
        verbose_name=_("holder"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="held_material",
    )
    location = models.ForeignKey(
        Location,
        verbose_name=_("location"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="parts",
    )
    #: The last day the holder was asked to hand the piece in for its inspection.
    #: Cleared when the piece is inspected or changes hands.
    inspection_reminder_sent = models.DateField(null=True, blank=True)

    def __str__(self):
        label = self.psa_id or self.serial_number or "#{}".format(self.pk)
        return "{} ({})".format(self.product_type, label)

    def clean(self):
        is_psa = self.product_type_id is not None and self.product_type.is_psa
        errors = {}
        if is_psa and not self.psa_id:
            errors["psa_id"] = _("A PSA ID is required for personal protective equipment.")
        if is_psa and not self.manufactured_on:
            errors["manufactured_on"] = _(
                "A manufacturing date is required for personal protective equipment."
            )
        if self.parent_id is not None and self.parent_id == self.pk:
            errors["parent"] = _("A piece cannot be assembled into itself.")
        # A set may keep retired pieces from before it became one, but gets no new ones.
        if self.pk is None and self.product_type_id is not None and self.product_type.is_set:
            errors["product_type"] = _("A set has no pieces of its own.")
        if errors:
            raise ValidationError(errors)

    @property
    def top_level(self):
        """The piece that is lent: the outermost assembly this piece belongs to."""
        piece, seen = self, {self.pk}
        while piece.parent_id is not None and piece.parent_id not in seen:
            seen.add(piece.parent_id)
            piece = piece.parent
        return piece

    def last_inspection(self):
        return self.inspections.order_by("-date", "-pk").first()

    def next_inspection_due(self, inspections=None):
        """The date the next inspection is due, or None for non-PSA material.

        ``inspections``, if given, are the piece's inspections, so a list need not
        ask for them once per piece.
        """
        if not self.product_type.is_psa:
            return None
        if inspections is None:
            last = self.inspections.filter(result=Inspection.OK).order_by("-date").first()
        else:
            passed = [i for i in inspections if i.result == Inspection.OK]
            last = max(passed, key=lambda i: i.date) if passed else None
        start = last.date if last else self.manufactured_on or self.buy_date
        if start is None:
            return None
        return start + timedelta(days=self.product_type.inspection_interval_days)

    def past_usage_period(self, today=None):
        """Whether the piece has outlived its type's usage period."""
        years = self.product_type.usage_years
        start = self.manufactured_on or self.buy_date
        if not years or start is None:
            return False
        today = today or timezone.localdate()
        try:
            end = start.replace(year=start.year + years)
        except ValueError:
            # 29 February plus a number of years that is not a leap year.
            end = start.replace(year=start.year + years, day=28)
        return end <= today

    class Meta:
        verbose_name = _("material part")
        verbose_name_plural = _("material parts")
        ordering = ["product_type__name", "psa_id", "pk"]
        permissions = [
            ("manage_inventory", _("Can manage the material inventory and inspections")),
            ("manage_lending", _("Can lend and reserve material on behalf of others")),
        ]


class Size(models.Model):
    """One size of a type kept as a counted stock, such as size 2 of the Friends.

    Pieces of a size carry no ID of their own: the stock is a number, and a
    reservation or loan takes some of it. One *set* of the type holds
    ``per_set`` of each of its sizes, so "a set of Friends" is one of each size.
    """

    product_type = models.ForeignKey(
        ProductType,
        verbose_name=_("product type"),
        related_name="sizes",
        on_delete=models.CASCADE,
    )
    name = models.CharField(_("name"), max_length=40)
    quantity = models.PositiveIntegerField(_("stock"), default=0)
    per_set = models.PositiveIntegerField(_("per set"), default=1)
    group = models.ForeignKey(
        "members.Group",
        verbose_name=_("owner group"),
        help_text=_("Empty means the material belongs to the whole section."),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="material_sizes",
    )
    location = models.ForeignKey(
        Location,
        verbose_name=_("location"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sizes",
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    def __str__(self):
        return "{} {}".format(self.product_type, self.name)

    def clean(self):
        if self.product_type_id is None:
            return
        if self.product_type.is_set:
            raise ValidationError({"product_type": _("A set has no sizes of its own.")})
        # A set is reserved as pieces of its types; counted sizes cannot serve that.
        if self.product_type.in_sets.exists():
            raise ValidationError(
                {"product_type": _("A type in a set is kept as pieces, not by size.")}
            )

    class Meta:
        verbose_name = _("size")
        verbose_name_plural = _("sizes")
        ordering = ["product_type__name", "position", "pk"]


class SetEntry(models.Model):
    """One member type of a set type, such as the 0.5 cam of a set of seven cams.

    A set is made of pieces with IDs of their own, each type also lent on its
    own. One set holds ``per_set`` pieces of each member type, and a set is free
    as often as each of its members has that many free. Reserving a set reserves
    its pieces: a set type has no pieces or sizes of its own, and sets are not
    nested.
    """

    set_type = models.ForeignKey(
        ProductType,
        verbose_name=_("set"),
        related_name="set_entries",
        on_delete=models.CASCADE,
    )
    product_type = models.ForeignKey(
        ProductType,
        verbose_name=_("product type"),
        related_name="in_sets",
        on_delete=models.PROTECT,
    )
    per_set = models.PositiveIntegerField(
        _("per set"), default=1, validators=[MinValueValidator(1)]
    )
    position = models.PositiveIntegerField(_("position"), default=0)

    def __str__(self):
        return "{} × {}".format(self.per_set, self.product_type)

    def clean(self):
        if self.set_type_id is None or self.product_type_id is None:
            return
        if self.set_type_id == self.product_type_id:
            raise ValidationError({"product_type": _("A set cannot contain itself.")})
        if self.product_type.is_set:
            raise ValidationError({"product_type": _("A set cannot contain another set.")})
        if self.product_type.sizes.exists():
            raise ValidationError(
                {"product_type": _("A type in a set is kept as pieces, not by size.")}
            )
        if self.set_type.in_sets.exists():
            raise ValidationError(
                {"set_type": _("A type that belongs to a set cannot be a set itself.")}
            )
        # Retired pieces are out of the stock: they do not keep a type from becoming a set.
        pieces = self.set_type.parts.exclude(status=Part.RETIRED)
        if pieces.exists() or self.set_type.sizes.exists():
            raise ValidationError(
                {"set_type": _("A type with pieces or sizes of its own cannot be a set.")}
            )

    class Meta:
        verbose_name = _("set entry")
        verbose_name_plural = _("set entries")
        ordering = ["position", "pk"]
        unique_together = [("set_type", "product_type")]


class CustodyEventQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError(_("The custody history cannot be changed."))

    def delete(self):
        raise ValidationError(_("The custody history cannot be changed."))


class CustodyEvent(models.Model):
    """One change of who has a piece or where it is. Append-only."""

    CHECKOUT, RETURN, TRANSFER, ASSEMBLE, RETIRE = (
        "checkout",
        "return",
        "transfer",
        "assemble",
        "retire",
    )
    KIND_CHOICES = [
        (CHECKOUT, _("checkout")),
        (RETURN, _("return")),
        (TRANSFER, _("transfer")),
        (ASSEMBLE, _("assemble")),
        (RETIRE, _("retire")),
    ]

    part = models.ForeignKey(
        Part, verbose_name=_("part"), related_name="custody", on_delete=models.CASCADE
    )
    kind = models.CharField(_("kind"), max_length=20, choices=KIND_CHOICES)
    at = models.DateTimeField(_("at"), default=timezone.now)
    from_member = models.ForeignKey(
        "members.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    from_location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_member = models.ForeignKey(
        "members.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    to_location = models.ForeignKey(
        Location, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    by = models.ForeignKey(
        "members.Member",
        verbose_name=_("recorded by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    loan = models.ForeignKey(
        "Loan", null=True, blank=True, on_delete=models.SET_NULL, related_name="custody_events"
    )

    objects = CustodyEventQuerySet.as_manager()

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise ValidationError(_("The custody history cannot be changed."))
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError(_("The custody history cannot be changed."))

    def __str__(self):
        return "{} {} {}".format(self.at.date(), self.get_kind_display(), self.part)

    class Meta:
        verbose_name = _("custody event")
        verbose_name_plural = _("custody events")
        ordering = ["-at", "-pk"]


class Reservation(models.Model):
    """A claim on material for a period, from the first to the last day inclusive."""

    REQUESTED, CONFIRMED, DECLINED, CANCELLED, FULFILLED = (
        "requested",
        "confirmed",
        "declined",
        "cancelled",
        "fulfilled",
    )
    STATUS_CHOICES = [
        (REQUESTED, _("requested")),
        (CONFIRMED, _("confirmed")),
        (DECLINED, _("declined")),
        (CANCELLED, _("cancelled")),
        (FULFILLED, _("picked up")),
    ]
    #: The states in which a reservation blocks its pieces.
    BLOCKING = (REQUESTED, CONFIRMED)

    borrower = models.ForeignKey(
        "members.Member",
        verbose_name=_("borrower"),
        related_name="material_reservations",
        on_delete=models.CASCADE,
    )
    start = models.DateField(_("start"))
    end = models.DateField(_("end"))
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES)
    note = models.CharField(_("note"), max_length=300, blank=True, default="")
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    created_by = models.ForeignKey(
        "members.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    parts = models.ManyToManyField(
        Part, through="ReservedPart", related_name="reservations", verbose_name=_("parts")
    )
    #: The last day the holders of its pieces were asked to bring them back.
    last_holder_notice = models.DateField(null=True, blank=True)

    def __str__(self):
        return "{} {}–{}".format(self.borrower, self.start, self.end)

    @property
    def is_blocking(self):
        return self.status in self.BLOCKING

    class Meta:
        verbose_name = _("reservation")
        verbose_name_plural = _("reservations")
        ordering = ["start", "pk"]
        constraints = [
            models.CheckConstraint(
                condition=Q(end__gte=models.F("start")),
                name="equipment_reservation_end_after_start",
            )
        ]


class ReservedPart(models.Model):
    """A piece allocated to a reservation."""

    reservation = models.ForeignKey(Reservation, on_delete=models.CASCADE)
    part = models.ForeignKey(Part, on_delete=models.CASCADE)
    #: Whether the borrower asked for this very piece. An unpinned allocation may
    #: be moved to another piece of the same type.
    pinned = models.BooleanField(default=False)

    class Meta:
        unique_together = [("reservation", "part")]


class ReservedSize(models.Model):
    """A number of pieces of one size taken by a reservation."""

    reservation = models.ForeignKey(
        Reservation, related_name="reserved_sizes", on_delete=models.CASCADE
    )
    size = models.ForeignKey(Size, related_name="reservations", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(_("quantity"))

    class Meta:
        unique_together = [("reservation", "size")]
        ordering = ["size__position", "size__pk"]


class Approval(models.Model):
    """The decision of one owner group on a reservation of its material."""

    reservation = models.ForeignKey(Reservation, related_name="approvals", on_delete=models.CASCADE)
    group = models.ForeignKey("members.Group", on_delete=models.CASCADE, related_name="+")
    approved = models.BooleanField(_("approved"), null=True)
    decided_by = models.ForeignKey(
        "members.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(_("comment"), max_length=300, blank=True, default="")

    class Meta:
        verbose_name = _("approval")
        verbose_name_plural = _("approvals")
        unique_together = [("reservation", "group")]


class Loan(models.Model):
    """Pieces handed to a borrower, with the day they are due back."""

    #: Empty once the borrower's member record is deleted: the loan stays on
    #: record, and its pieces stay blocked until they are returned.
    borrower = models.ForeignKey(
        "members.Member",
        verbose_name=_("borrower"),
        related_name="material_loans",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    reservation = models.ForeignKey(
        Reservation, null=True, blank=True, on_delete=models.SET_NULL, related_name="loans"
    )
    out_at = models.DateTimeField(_("handed out at"), default=timezone.now)
    due = models.DateField(_("due"))
    created_by = models.ForeignKey(
        "members.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    #: The last day the borrower was reminded to bring the pieces back.
    last_reminder = models.DateField(null=True, blank=True)

    @property
    def borrower_name(self):
        """The borrower's name, or a placeholder once the member is deleted."""
        if self.borrower is None:
            return _("a deleted member")
        return self.borrower.name

    def __str__(self):
        return "{} {}".format(self.borrower_name, timezone.localdate(self.out_at))

    @property
    def is_open(self):
        return (
            self.lines.filter(returned_at__isnull=True).exists()
            or self.lent_sizes.filter(returned_at__isnull=True).exists()
        )

    class Meta:
        verbose_name = _("loan")
        verbose_name_plural = _("loans")
        ordering = ["-out_at", "-pk"]


class LoanLine(models.Model):
    """One piece of a loan, returned independently of the others."""

    loan = models.ForeignKey(Loan, related_name="lines", on_delete=models.CASCADE)
    part = models.ForeignKey(Part, related_name="loan_lines", on_delete=models.CASCADE)
    returned_at = models.DateTimeField(_("returned at"), null=True, blank=True)

    class Meta:
        ordering = ["pk"]


class LentSize(models.Model):
    """A number of pieces of one size handed out on a loan, returned bit by bit."""

    loan = models.ForeignKey(Loan, related_name="lent_sizes", on_delete=models.CASCADE)
    size = models.ForeignKey(Size, related_name="loans", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(_("quantity"))
    returned = models.PositiveIntegerField(_("returned"), default=0)
    #: Set once every piece of the line is back.
    returned_at = models.DateTimeField(_("returned at"), null=True, blank=True)

    @property
    def outstanding(self):
        return self.quantity - self.returned

    class Meta:
        ordering = ["size__position", "size__pk"]


class Inspection(models.Model):
    """A check of a piece, as personal protective equipment requires."""

    OK, RETIRED = "ok", "retired"
    RESULT_CHOICES = [(OK, _("ok")), (RETIRED, _("retired"))]

    part = models.ForeignKey(Part, related_name="inspections", on_delete=models.CASCADE)
    date = models.DateField(_("date"), default=timezone.localdate)
    inspector = models.ForeignKey(
        "members.Member",
        verbose_name=_("inspector"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    result = models.CharField(_("result"), max_length=10, choices=RESULT_CHOICES)
    comment = models.TextField(_("comment"), blank=True, default="")
    photo = models.ImageField(_("photo"), upload_to="equipment/inspections", blank=True)

    def __str__(self):
        return "{} {}".format(self.date, self.get_result_display())

    class Meta:
        verbose_name = _("inspection")
        verbose_name_plural = _("inspections")
        ordering = ["-date", "-pk"]


class Deficit(models.Model):
    """A wish for more or other material, worked through by the Materialwarte."""

    OPEN, ORDERED, DISMISSED = "open", "ordered", "dismissed"
    STATUS_CHOICES = [(OPEN, _("open")), (ORDERED, _("ordered")), (DISMISSED, _("dismissed"))]

    product_type = models.ForeignKey(
        ProductType,
        verbose_name=_("product type"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="deficits",
    )
    text = models.CharField(_("what is missing"), max_length=200, blank=True, default="")
    wanted_from = models.DateField(_("wanted from"), null=True, blank=True)
    wanted_to = models.DateField(_("wanted until"), null=True, blank=True)
    comment = models.TextField(_("comment"), blank=True, default="")
    reported_by = models.ForeignKey(
        "members.Member",
        verbose_name=_("reported by"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    created_at = models.DateTimeField(_("reported at"), auto_now_add=True)
    status = models.CharField(_("status"), max_length=20, choices=STATUS_CHOICES, default=OPEN)

    def __str__(self):
        return str(self.product_type or self.text)

    def clean(self):
        if self.wanted_from and self.wanted_to and self.wanted_to < self.wanted_from:
            raise ValidationError({"wanted_to": _("The end of the period lies before its start.")})

    class Meta:
        verbose_name = _("deficit")
        verbose_name_plural = _("deficits")
        ordering = ["-created_at", "-pk"]
