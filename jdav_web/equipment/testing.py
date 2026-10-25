"""Shared fixtures for the material tests."""

from datetime import date

from django.utils import translation
from members.models import Group
from members.models import MALE
from members.models import Member

from .models import Location
from .models import Part
from .models import ProductType
from .models import SetEntry
from .models import Size


class MaterialFixture:
    """A section with two groups, a cupboard, a few members and some material.

    - ``alice`` is in ``jugend``; ``bob`` leads ``jugend``; ``carol`` leads ``hochtour``.
    - ``slings``: four section slings, two in the cupboard, one each with bob and carol.
    - ``crampons``: two crampons of ``hochtour``.
    - ``harness``: one PSA harness of ``jugend``.
    """

    def make_member(self, prename, **kwargs):
        return Member.objects.create(
            prename=prename,
            lastname="Test",
            birth_date=date(1990, 1, 1),
            email="{}@example.com".format(prename.lower()),
            gender=MALE,
            **kwargs,
        )

    def make_part(self, product_type, **kwargs):
        return Part.objects.create(product_type=product_type, **kwargs)

    def setUpMaterial(self):
        # The assertions read the source-language messages, whatever the catalogues say.
        self.enterContext(translation.override("en"))
        self.cupboard = Location.objects.create(name="Griffwerk")
        self.jugend = Group.objects.create(name="Jugend")
        self.hochtour = Group.objects.create(name="Hochtour")
        self.alice = self.make_member("Alice")
        self.alice.group.add(self.jugend)
        self.bob = self.make_member("Bob")
        self.jugend.leiters.add(self.bob)
        self.carol = self.make_member("Carol")
        self.hochtour.leiters.add(self.carol)

        self.sling_type = ProductType.objects.create(name="Bandschlinge 120 cm")
        self.slings = [
            self.make_part(self.sling_type, location=self.cupboard, home_location=self.cupboard),
            self.make_part(self.sling_type, location=self.cupboard, home_location=self.cupboard),
            self.make_part(self.sling_type, holder=self.bob, home_location=self.cupboard),
            self.make_part(self.sling_type, holder=self.carol, home_location=self.cupboard),
        ]
        self.crampon_type = ProductType.objects.create(name="Steigeisen")
        self.crampons = [
            self.make_part(self.crampon_type, group=self.hochtour, location=self.cupboard),
            self.make_part(self.crampon_type, group=self.hochtour, location=self.cupboard),
        ]
        self.harness_type = ProductType.objects.create(
            name="Gurt", manufacturer="Petzl", is_psa=True
        )
        self.harness = self.make_part(
            self.harness_type,
            group=self.jugend,
            psa_id="G1",
            manufactured_on=date(2024, 1, 1),
            location=self.cupboard,
        )

    def setUpSizes(self):
        """``friends``, kept by size: two of size 1, three of size 2 (two to a set) and one of size 3 of ``hochtour``."""
        self.friends_type = ProductType.objects.create(name="Friends")
        self.size1 = Size.objects.create(
            product_type=self.friends_type, name="1", quantity=2, position=1
        )
        self.size2 = Size.objects.create(
            product_type=self.friends_type, name="2", quantity=3, per_set=2, position=2
        )
        self.size3 = Size.objects.create(
            product_type=self.friends_type,
            name="3",
            quantity=1,
            group=self.hochtour,
            position=3,
        )

    def setUpSet(self):
        """``cam_set``, a set of one ``small_cam`` and one ``large_cam``, pieces with IDs.

        There are two small cams of the section, and two large ones: one of the
        section, one of ``hochtour``.
        """
        self.small_type = ProductType.objects.create(name="CAM 0.5")
        self.large_type = ProductType.objects.create(name="CAM 1")
        self.small_cams = [
            self.make_part(self.small_type, psa_id="C05-1", location=self.cupboard),
            self.make_part(self.small_type, psa_id="C05-2", location=self.cupboard),
        ]
        self.large_cams = [
            self.make_part(self.large_type, psa_id="C1-1", location=self.cupboard),
            self.make_part(
                self.large_type, psa_id="C1-2", group=self.hochtour, location=self.cupboard
            ),
        ]
        self.cam_set = ProductType.objects.create(name="Totem Satz")
        self.small_entry = SetEntry.objects.create(
            set_type=self.cam_set, product_type=self.small_type, position=1
        )
        self.large_entry = SetEntry.objects.create(
            set_type=self.cam_set, product_type=self.large_type, position=2
        )
