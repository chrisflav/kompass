from django.test import TestCase
from django.utils import timezone
from mailer.models import EmailAddress
from members.models import DIVERSE
from members.models import Group
from members.models import Member


class BasicMailerTestCase(TestCase):
    def setUp(self):
        self.mygroup = Group.objects.create(name="My Group")
        self.fritz = Member.objects.create(
            prename="Fritz",
            lastname="Wulter",
            birth_date=timezone.now().date(),
            email="fritz@foo.com",
            gender=DIVERSE,
        )
        self.fritz.group.add(self.mygroup)
        self.fritz.save()
        self.fritz.generate_key()

        self.paul = Member.objects.create(
            prename="Paul",
            lastname="Wulter",
            birth_date=timezone.now().date(),
            email="paul@foo.com",
            gender=DIVERSE,
        )

        self.em = EmailAddress.objects.create(name="foobar")
        self.em.to_groups.add(self.mygroup)
        self.em.to_members.add(self.paul)
