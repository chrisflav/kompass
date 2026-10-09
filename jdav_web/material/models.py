from datetime import datetime

from django.db import models
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

# maximum time in years of a material part until being replaced
MAX_TIME_MATERIAL = 5


class MaterialCategory(models.Model):
    """
    Describes one kind of material
    """

    name = models.CharField(max_length=40, verbose_name=_("Name"))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _("Material category")
        verbose_name_plural = _("Material categories")


class MaterialPart(models.Model):
    """
    Represents one physical piece of material. A piece is owned (and stored) by
    at most one member of the association.
    """

    name = models.CharField(_("name"), max_length=30)
    description = models.CharField(_("description"), default="", max_length=140)
    buy_date = models.DateField(_("purchase date"), editable=True)
    lifetime = models.DecimalField(_("lifetime (years)"), decimal_places=0, max_digits=3)
    photo = models.ImageField(_("photo"), upload_to="images", blank=True)
    material_cat = models.ManyToManyField(
        MaterialCategory, default=None, verbose_name=_("Material category")
    )
    owner = models.ForeignKey(
        "members.Member",
        verbose_name=_("owner"),
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        """String representation"""
        return self.name

    def admin_thumbnail(self):
        if self.photo:
            return format_html(
                '<a href="{0}"><img src="{0}" height="60" style="image-orientation: from-image;"></a>'.format(
                    self.photo.url
                )
            )
        else:
            return format_html("<i>kein Bild</i>")

    admin_thumbnail.short_description = _("Thumbnail")

    def not_too_old(self):
        """Returns wether the part should be replaced cause of age"""
        buy_time = timezone.make_aware(datetime.combine(self.buy_date, datetime.min.time()))
        return yearsago(int(self.lifetime)) < buy_time

    not_too_old.admin_order_field = "buy_date"
    not_too_old.boolean = True
    not_too_old.short_description = _("Not too old?")

    class Meta:
        verbose_name = _("material part")
        verbose_name_plural = _("material parts")


def yearsago(years, from_date=None):
    """Function to return the date with a delta of years in the past"""
    if from_date is None:
        from_date = timezone.now()
    try:
        return from_date.replace(year=from_date.year - years)
    except ValueError:
        # 29.02 -> use 28.02
        assert from_date.month == 2 and from_date.day == 29
        return from_date.replace(month=2, day=28, year=from_date.year - years)
