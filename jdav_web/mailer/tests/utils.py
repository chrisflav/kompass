from unittest import skip, mock
from django.test import TestCase
from django.conf import settings
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.utils.translation import gettext as _
from django.core.files.uploadedfile import SimpleUploadedFile
from members.models import Member, Group, DIVERSE, Freizeit, MemberNoteList, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE
from mailer.models import EmailAddress, EmailAddressForm, Message, MessageForm, Attachment
from mailer.mailutils import SENT, NOT_SENT, PARTLY_SENT


class BasicMailerTestCase(TestCase):
    def setUp(self):
        self.mygroup = Group.objects.create(name="My Group")
        self.fritz = Member.objects.create(prename="Fritz", lastname="Wulter", birth_date=timezone.now().date(),
                              email='fritz@foo.com', gender=DIVERSE)
        self.fritz.group.add(self.mygroup)
        self.fritz.save()
        self.fritz.generate_key()

        self.paul = Member.objects.create(prename="Paul", lastname="Wulter", birth_date=timezone.now().date(),
                              email='paul@foo.com', gender=DIVERSE)

        self.em = EmailAddress.objects.create(name='foobar')
        self.em.to_groups.add(self.mygroup)
        self.em.to_members.add(self.paul)
