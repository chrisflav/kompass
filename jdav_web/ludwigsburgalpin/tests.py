from http import HTTPStatus

from django.conf import settings
from django.contrib.admin.sites import AdminSite
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .admin import TerminAdmin
from .models import EVENTART
from .models import GRUPPE
from .models import KATEGORIE
from .models import KLASSIFIZIERUNG
from .models import KONDITION
from .models import SAISON
from .models import TECHNIK
from .models import Termin


class BasicTerminTestCase(TestCase):
    TERMIN_NO = 10

    def setUp(self):
        for i in range(BasicTerminTestCase.TERMIN_NO):
            Termin.objects.create(
                title="Foo {}".format(i),
                start_date=timezone.now().date(),
                end_date=timezone.now().date(),
                group=GRUPPE[0][0],
                email=settings.TEST_MAIL,
                category=KATEGORIE[0][0],
                technik=TECHNIK[0][0],
                max_participants=42,
                anforderung_hoehe=10,
            )


class TerminAdminTestCase(BasicTerminTestCase):
    def test_str(self):
        t = Termin.objects.all()[0]
        self.assertEqual(str(t), "{} {}".format(t.title, str(t.group)))

    def test_make_overview(self):
        factory = RequestFactory()
        admin = TerminAdmin(Termin, AdminSite())
        url = reverse("admin:ludwigsburgalpin_termin_changelist")
        request = factory.get(url)

        response = admin.make_overview(request, Termin.objects.all())

        self.assertEqual(
            response["Content-Type"],
            "application/xlsx",
            "The content-type of the generated overview should be an .xlsx file.",
        )


class ViewTestCase(BasicTerminTestCase):
    def test_get_index(self):
        url = reverse("ludwigsburgalpin:index")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_submit_termin(self):
        url = reverse("ludwigsburgalpin:index")
        response = self.client.post(
            url,
            data={
                "title": "My Title",
                "subtitle": "My Subtitle",
                "start_date": "2024-01-01",
                "end_date": "2024-02-01",
                "group": GRUPPE[0][0],
                "category": KATEGORIE[0][0],
                "condition": KONDITION[0][0],
                "technik": TECHNIK[0][0],
                "saison": SAISON[0][0],
                "eventart": EVENTART[0][0],
                "klassifizierung": KLASSIFIZIERUNG[0][0],
                "anforderung_hoehe": 10,
                "anforderung_strecke": 10,
                "anforderung_dauer": 10,
                "max_participants": 100,
            },
        )
        t = Termin.objects.get(title="My Title")
        self.assertEqual(t.group, GRUPPE[0][0])
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, "Termin erfolgreich eingereicht", html=True)

    def test_submit_termin_invalid(self):
        url = reverse("ludwigsburgalpin:index")
        # many required fields are missing
        response = self.client.post(
            url,
            data={
                "title": "My Title",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, "Dieses Feld ist zwingend erforderlich.", html=True)
