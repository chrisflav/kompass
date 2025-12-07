import datetime

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth import models as authmodels
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from mailer.models import EmailAddress
from members.models import DIVERSE
from members.models import FEMALE
from members.models import Group
from members.models import MALE
from members.models import Member
from members.models import NewMemberOnList

INTERNAL_EMAIL = "foobar@{domain}".format(
    domain=settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER[0]
)
REGISTRATION_DATA = {
    "prename": "Peter",
    "lastname": "Wulter",
    "street": "Street 123",
    "plz": "12345 EJ",
    "town": "Town 1",
    "phone_number": "+49 123456",
    "birth_date": "2010-05-17",
    "gender": "2",
    "email": settings.TEST_MAIL,
    "alternative_email": settings.TEST_MAIL,
}
WAITER_DATA = {
    "prename": "Peter",
    "lastname": "Wulter",
    "birth_date": "1999-02-16",
    "gender": "0",
    "email": settings.TEST_MAIL,
    "application_text": "hoho",
}


def create_custom_user(username, groups, prename, lastname):
    user = User.objects.create_user(username=username, password="secret")
    member = Member.objects.create(
        prename=prename,
        lastname=lastname,
        birth_date=timezone.localdate(),
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )
    member.user = user
    member.save()
    user.is_staff = True
    user.save()

    for group in groups:
        g = authmodels.Group.objects.get(name=group)
        user.groups.add(g)
    return user


class BasicMemberTestCase(TestCase):
    """
    Utility base class for setting up a test environment for member-related tests.
    It creates a few groups and members with different attributes.
    """

    def setUp(self):
        self.jl = Group.objects.create(name="Jugendleiter", year_from=0, year_to=0)
        self.alp = Group.objects.create(
            name="Alpenfuechse", year_from=1900, year_to=2000, show_website=True
        )
        self.spiel = Group.objects.create(name="Spielkinder")

        self.fritz = Member.objects.create(
            prename="Fritz",
            lastname="Wulter",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )
        self.fritz.group.add(self.jl)
        self.fritz.group.add(self.alp)
        self.fritz.save()

        em = EmailAddress.objects.create(name="foobar")
        self.alp.contact_email = em
        self.alp.save()

        self.peter = Member.objects.create(
            prename="Peter",
            lastname="Wulter",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
        )
        self.peter.group.add(self.jl)
        self.peter.group.add(self.alp)
        self.peter.save()

        self.lara = Member.objects.create(
            prename="Lara",
            lastname="Wallis",
            birth_date=timezone.now().date(),
            email=INTERNAL_EMAIL,
            gender=DIVERSE,
        )
        self.lara.group.add(self.alp)
        self.lara.save()
        self.fridolin = Member.objects.create(
            prename="Fridolin",
            lastname="Spargel",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
        )
        self.fridolin.group.add(self.alp)
        self.fridolin.group.add(self.spiel)
        self.fridolin.save()

        self.lise = Member.objects.create(
            prename="Lise",
            lastname="Lotte",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        self.alp.leiters.add(self.lise)
        self.alp.save()


def add_memberonlist_by_age(excursion, n_yl, n_correct_age, n_too_old):
    """
    Utility function for setting up a test environment. Adds `n_yl` youth leaders,
    `n_correct_age` members of correct age (i.e. 10 years olds) and
    `n_too_old` members that are too old (i.e. 27 years olds) to `excursion`.
    """
    for i in range(n_yl):
        # a 50 years old
        m = Member.objects.create(
            prename="Peter {}".format(i),
            lastname="Wulter",
            birth_date=datetime.datetime.today() - relativedelta(years=50),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        excursion.jugendleiter.add(m)
    for i in range(n_correct_age):
        # a 10 years old
        m = Member.objects.create(
            prename="Lise {}".format(i),
            lastname="Walter",
            birth_date=datetime.datetime.today() - relativedelta(years=10),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        NewMemberOnList.objects.create(member=m, comments="a", memberlist=excursion)
    for i in range(n_too_old):
        # a 27 years old
        m = Member.objects.create(
            prename="Lise {}".format(i),
            lastname="Walter",
            birth_date=datetime.datetime.today() - relativedelta(years=27),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        NewMemberOnList.objects.create(member=m, comments="a", memberlist=excursion)


def add_memberonlist_by_local(excursion, n_yl, n_b27_local, n_b27_non_local):
    """
    Utility function for setting up a test environment. Adds `n_yl` youth leaders,
    `n_b27_local` local members of correct age and
    `n_b27_non_local` non-local members of correct age to `excursion`.
    """
    for i in range(n_yl):
        m = Member.objects.create(
            prename="Peter {}".format(i),
            lastname="Wulter",
            birth_date=datetime.datetime.today() - relativedelta(years=50),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        excursion.jugendleiter.add(m)
        NewMemberOnList.objects.create(member=m, comments="a", memberlist=excursion)
    for i in range(n_b27_local):
        m = Member.objects.create(
            prename="Lise {}".format(i),
            lastname="Walter",
            birth_date=datetime.datetime.today() - relativedelta(years=10),
            town=settings.SEKTION,
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        NewMemberOnList.objects.create(member=m, comments="a", memberlist=excursion)
    for i in range(n_b27_non_local):
        m = Member.objects.create(
            prename="Lise {}".format(i),
            lastname="Walter",
            birth_date=datetime.datetime.today() - relativedelta(years=10),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        NewMemberOnList.objects.create(member=m, comments="a", memberlist=excursion)


def cleanup_excursion(excursion):
    """
    Utility function for cleaning up a test environment. Deletes all members and
    youth leaders from `excursion`.
    """
    excursion.membersonlist.all().delete()
    excursion.jugendleiter.all().delete()
