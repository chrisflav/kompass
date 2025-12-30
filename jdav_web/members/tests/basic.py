import datetime
import math
import os
import os.path
import random
import tempfile
from http import HTTPStatus
from io import BytesIO
from unittest import mock
from unittest import skip

from dateutil.relativedelta import relativedelta
from django import template
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import AdminSite
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.http import HttpResponseRedirect
from django.test import Client
from django.test import RequestFactory
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from finance.models import Bill
from finance.models import Statement
from mailer.models import EmailAddress
from mailer.models import Message
from members.admin import AgeFilter
from members.admin import FilteredMemberFieldMixin
from members.admin import FreizeitAdmin
from members.admin import GroupAdmin
from members.admin import InvitationToGroupAdmin
from members.admin import InvitedToGroupFilter
from members.admin import KlettertreffAdmin
from members.admin import MemberAdmin
from members.admin import MemberAdminForm
from members.admin import MemberNoteListAdmin
from members.admin import MemberOnListInlineForm
from members.admin import MemberTrainingAdmin
from members.admin import MemberUnconfirmedAdmin
from members.admin import MemberWaitingListAdmin
from members.admin import StatementOnListForm
from members.excel import generate_ljp_vbk
from members.models import ActivityCategory
from members.models import AUSBILDUNGS_TOUR
from members.models import confirm_mail_by_key
from members.models import DIVERSE
from members.models import EmergencyContact
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import FEMALE
from members.models import Freizeit
from members.models import FUEHRUNGS_TOUR
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import InvitationToGroup
from members.models import Klettertreff
from members.models import KlettertreffAttendee
from members.models import LJPProposal
from members.models import MALE
from members.models import Member
from members.models import MemberDocument
from members.models import MemberNoteList
from members.models import MemberTraining
from members.models import MemberUnconfirmedProxy
from members.models import MemberWaitingList
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList
from members.models import OEFFENTLICHE_ANREISE
from members.models import PermissionGroup
from members.models import PermissionMember
from members.models import RegistrationPassword
from members.models import TrainingCategory
from members.models import WEEKDAYS
from members.pdf import fill_pdf_form
from members.pdf import find_template
from members.pdf import media_path
from members.pdf import merge_pdfs
from members.pdf import pdf_add_attachments
from members.pdf import render_docx
from members.pdf import render_tex
from members.pdf import scale_pdf_page_to_a4
from members.pdf import scale_pdf_to_a4
from members.pdf import serve_pdf
from members.tests.utils import add_memberonlist_by_age
from members.tests.utils import add_memberonlist_by_local
from members.tests.utils import BasicMemberTestCase
from members.tests.utils import cleanup_excursion
from members.tests.utils import create_custom_user
from members.tests.utils import INTERNAL_EMAIL
from members.tests.utils import REGISTRATION_DATA
from members.tests.utils import WAITER_DATA
from members.views import render_register_failed
from members.views import render_register_success
from PIL import Image
from pypdf import PageObject
from pypdf import PdfReader
from pypdf import PdfWriter

EMERGENCY_CONTACT_DATA = {
    "emergencycontact_set-TOTAL_FORMS": "1",
    "emergencycontact_set-INITIAL_FORMS": "0",
    "emergencycontact_set-MIN_NUM_FORMS": "1",
    "emergencycontact_set-MAX_NUM_FORMS": "1000",
    "emergencycontact_set-0-prename": "Papa",
    "emergencycontact_set-0-lastname": "Wulter",
    "emergencycontact_set-0-email": settings.TEST_MAIL,
    "emergencycontact_set-0-phone_number": "-49 124125",
    "emergencycontact_set-0-id": "",
    "emergencycontact_set-0-DELETE": "",
    "emergencycontact_set-0-member": "",
}


class MemberTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()

        p1 = PermissionMember.objects.create(member=self.fritz)
        p1.list_members.add(self.lara)
        p1.view_members.add(self.lara)
        p1.change_members.add(self.lara)
        p1.delete_members.add(self.lara)
        p1.list_groups.add(self.spiel)
        p1.view_groups.add(self.spiel)
        p1.change_groups.add(self.spiel)
        p1.delete_groups.add(self.spiel)

        self.ja = Group.objects.create(name="Jugendausschuss")
        self.peter = Member.objects.create(
            prename="Peter",
            lastname="Keks",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
            street="Peters Street 123",
            town="Peters Town",
            plz="3515 AJ",
            phone_number="+49 124125125",
        )
        self.anna = Member.objects.create(
            prename="Anna",
            lastname="Keks",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=FEMALE,
            good_conduct_certificate_presented_date=timezone.now().date(),
        )
        img = SimpleUploadedFile("image.jpg", b"file_content", content_type="image/jpeg")
        pdf = SimpleUploadedFile("form.pdf", b"very sensitive!", content_type="application/pdf")
        self.lisa = Member.objects.create(
            prename="Lisa",
            lastname="Keks",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
            image=img,
            registration_form=pdf,
        )
        self.lisa.confirmed_mail, self.lisa.confirmed_alternative_mail = True, True
        self.peter.group.add(self.ja)
        self.anna.group.add(self.ja)
        self.lisa.group.add(self.ja)

        self.ex = Freizeit.objects.create(
            name="Wild trip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
            date=timezone.localtime(),
        )
        self.ex.jugendleiter.add(self.fritz)
        self.ex.save()

        p2 = PermissionGroup.objects.create(group=self.ja)
        p2.list_members.add(self.lara)
        p2.view_members.add(self.lara)
        p2.change_members.add(self.lara)
        p2.delete_members.add(self.lara)
        p2.list_groups.add(self.ja)
        p2.list_groups.add(self.spiel)
        p2.view_groups.add(self.spiel)
        p2.change_groups.add(self.spiel)
        p2.delete_groups.add(self.spiel)

    def test_may(self):
        self.assertTrue(self.fritz.may_list(self.lara))
        self.assertTrue(self.fritz.may_view(self.lara))
        self.assertTrue(self.fritz.may_change(self.lara))
        self.assertTrue(self.fritz.may_delete(self.lara))
        self.assertTrue(self.fritz.may_list(self.fridolin))
        self.assertTrue(self.fritz.may_view(self.fridolin))
        self.assertTrue(self.fritz.may_change(self.fridolin))
        self.assertTrue(self.fritz.may_delete(self.fridolin))
        self.assertFalse(self.fritz.may_view(self.anna))

        # every member should be able to list, view and change themselves
        for member in Member.objects.all():
            self.assertTrue(member.may_list(member))
            self.assertTrue(member.may_view(member))
            self.assertTrue(member.may_change(member))
            self.assertTrue(member.may_delete(member))

        # every member of Jugendausschuss should be able to view every other member of Jugendausschuss
        for member in self.ja.member_set.all():
            self.assertTrue(member.may_list(self.fridolin))
            self.assertTrue(member.may_view(self.fridolin))
            self.assertTrue(member.may_view(self.lara))
            self.assertTrue(member.may_change(self.lara))
            self.assertTrue(member.may_change(self.fridolin))
            self.assertTrue(member.may_delete(self.lara))
            self.assertTrue(member.may_delete(self.fridolin))
            for other in self.ja.member_set.all():
                self.assertTrue(member.may_list(other))
                if member != other:
                    self.assertFalse(member.may_view(other))
                    self.assertFalse(member.may_change(other))
                    self.assertFalse(member.may_delete(other))

    def test_filter_queryset(self):
        # lise may only list herself
        self.assertEqual(set(self.lise.filter_queryset_by_permissions(model=Member)), {self.lise})

        for member in Member.objects.all():
            # passing the empty queryset as starting queryset, should give the empty queryset back
            self.assertEqual(
                member.filter_queryset_by_permissions(Member.objects.none(), model=Member).count(),
                0,
            )
            # passing all objects as start queryset should give the same result as not giving any start queryset
            self.assertEqual(
                set(member.filter_queryset_by_permissions(Member.objects.all(), model=Member)),
                set(member.filter_queryset_by_permissions(model=Member)),
            )

    def test_filter_members_by_permissions(self):
        qs = Member.objects.all()
        qs_a = self.anna.filter_members_by_permissions(qs, annotate=True)
        # Anna may list Peter, because Peter is also in the Jugendausschuss.
        self.assertIn(self.peter, qs_a)
        # Anna may not view Peter.
        self.assertNotIn(self.peter, qs_a.filter(_viewable=True))

    def test_filter_messages_by_permissions(self):
        good = Message.objects.create(
            subject="Good message", content="This is a test message", created_by=self.fritz
        )
        Message.objects.create(subject="Bad message", content="This is a test message")
        self.assertQuerysetEqual(
            self.fritz.filter_messages_by_permissions(Message.objects.all()), [good], ordered=False
        )

    def test_filter_statements_by_permissions(self):
        st1 = Statement.objects.create(night_cost=42, subsidy_to=None, created_by=self.fritz)
        st2 = Statement.objects.create(night_cost=42, subsidy_to=None, excursion=self.ex)
        Statement.objects.create(night_cost=42, subsidy_to=None)
        qs = Statement.objects.all()
        self.assertQuerysetEqual(
            self.fritz.filter_statements_by_permissions(qs), [st1, st2], ordered=False
        )

    def test_filter_waiters_by_permissions(self):
        waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        MemberWaitingList.objects.create(**WAITER_DATA)
        InvitationToGroup.objects.create(group=self.alp, waiter=waiter)
        qs = MemberWaitingList.objects.all()
        self.assertQuerysetEqual(
            self.lise.filter_waiters_by_permissions(qs), [waiter], ordered=False
        )

    def test_annotate_view_permissions(self):
        qs = Member.objects.all()
        # if the model is not Member, the queryset should not change
        self.assertQuerysetEqual(
            self.fritz.annotate_view_permission(qs, MemberWaitingList), qs, ordered=False
        )

        # Fritz can't view Anna.
        qs_a = self.fritz.annotate_view_permission(qs, Member)
        self.assertNotIn(self.anna, qs_a.filter(_viewable=True))

        # Anna can't view Fritz.
        qs_a = self.anna.annotate_view_permission(qs, Member)
        self.assertNotIn(self.fritz, qs_a.filter(_viewable=True))

    def test_compare_filter_queryset_may_list(self):
        # filter_queryset and filtering manually by may_list should be the same
        for member in Member.objects.all():
            s1 = set(member.filter_queryset_by_permissions(model=Member))
            s2 = {other for other in Member.objects.all() if member.may_list(other)}
            self.assertEqual(s1, s2)

    def test_image_visible(self):
        url = self.lisa.image.url
        c = Client()
        response = c.get("/de" + url)
        self.assertEqual(
            response.status_code, 200, "Members images should be visible without login."
        )

    def test_registration_form_not_visible(self):
        url = self.lisa.registration_form.url
        c = Client()
        response = c.get("/de" + url)
        self.assertEqual(
            response.status_code,
            302,
            "Members registration forms should not be visible without login.",
        )

        User.objects.create_user(username="user", password="secret", is_staff=True)
        res = c.login(username="user", password="secret")
        assert res
        response = c.get("/de" + url)
        self.assertEqual(
            response.status_code,
            200,
            "Members registration forms should be visible after staff login.",
        )

    def test_suggested_username(self):
        self.fritz.prename = "Päter"
        self.fritz.lastname = "Püt er"
        self.assertEqual(self.fritz.suggested_username(), "paeter.puet_er")

    def test_place(self):
        self.assertIn(self.peter.plz, self.peter.place)

    def test_address(self):
        self.assertIn(self.peter.street, self.peter.address)
        self.assertEqual("---", self.lisa.address)

        self.assertIn(self.peter.street, self.peter.address_multiline)
        self.assertIn("\\linebreak", self.peter.address_multiline)
        self.assertEqual("---", self.lisa.address_multiline)

    def test_good_conduct_certificate_valid(self):
        self.assertFalse(self.peter.good_conduct_certificate_valid())
        self.assertTrue(self.anna.good_conduct_certificate_valid())
        delta = datetime.timedelta(days=2 * settings.MAX_AGE_GOOD_CONDUCT_CERTIFICATE_MONTHS * 30)
        self.anna.good_conduct_certificate_presented_date -= delta
        self.assertFalse(self.anna.good_conduct_certificate_valid())

    def test_generate_key(self):
        key = self.peter.generate_key()
        p = Member.objects.get(pk=self.peter.pk)
        self.assertEqual(key, p.unsubscribe_key)

    def test_unsubscribe(self):
        key = self.peter.generate_key()
        self.assertTrue(self.peter.unsubscribe(key))
        self.assertFalse(self.lisa.unsubscribe(key))

        p = Member.objects.get(pk=self.peter.pk)
        self.assertFalse(p.gets_newsletter)

    def test_contact_phone_number(self):
        self.assertEqual(self.peter.phone_number, self.peter.contact_phone_number)
        self.assertEqual("---", self.lisa.contact_phone_number)

    def test_contact_email(self):
        self.assertEqual(self.peter.email, self.peter.contact_email)

    def test_username(self):
        self.assertEqual(self.peter.username, self.peter.suggested_username())
        u = User.objects.create_user(username="user", password="secret", is_staff=True)
        self.peter.user = u
        self.assertEqual(self.peter.username, "user")

    def test_association_email(self):
        self.assertIn(settings.DOMAIN, self.peter.association_email)

    def test_registration_complete(self):
        # this is currently a dummy that always returns True
        self.assertTrue(self.peter.registration_complete())

    def test_unconfirm(self):
        self.assertTrue(self.peter.confirmed)
        self.peter.unconfirm()
        self.assertFalse(self.peter.confirmed)

    def test_generate_upload_registration_form_key(self):
        self.peter.generate_upload_registration_form_key()
        self.assertIsNotNone(self.peter.upload_registration_form_key)

    def test_has_internal_email(self):
        self.peter.email = "foobar"
        self.assertFalse(self.peter.has_internal_email())

    def test_invite_as_user(self):
        # sucess
        self.assertTrue(self.lara.has_internal_email())
        self.lara.user = None
        self.assertTrue(self.lara.invite_as_user())

        # failure: already has user data
        u = User.objects.create_user(username="user", password="secret", is_staff=True)
        self.lara.user = u
        self.assertFalse(self.lara.invite_as_user())

        # failure: no internal email
        self.peter.email = "foobar"
        self.assertFalse(self.peter.invite_as_user())

    def test_birth_date_str(self):
        self.fritz.birth_date = None
        self.assertEqual(self.fritz.birth_date_str, "---")
        date = timezone.now().date()
        self.fritz.birth_date = date
        self.assertEqual(self.fritz.birth_date_str, date.strftime("%d.%m.%Y"))

    def test_gender_str(self):
        self.assertGreater(len(self.fritz.gender_str), 0)

    def test_led_freizeiten(self):
        self.assertGreater(len(self.fritz.led_freizeiten()), 0)

    def test_create_from_registration(self):
        self.lisa.confirmed = False
        # Lisa's registration is ready, no more mail requests needed
        self.assertFalse(self.lisa.create_from_registration(None, self.alp))
        # After creating from registration, Lisa should be unconfirmed.
        self.assertFalse(self.lisa.confirmed)

    def test_validate_registration_form(self):
        self.lisa.confirmed = False
        self.assertIsNotNone(self.lisa.registration_form)
        self.assertIsNone(self.lisa.validate_registration_form())

    def test_send_upload_registration_form_link(self):
        self.assertEqual(self.lisa.upload_registration_form_key, "")
        self.assertIsNone(self.lisa.send_upload_registration_form_link())

    def test_demote_to_waiter(self):
        self.lisa.waitinglist_application_date = timezone.now()
        self.lisa.demote_to_waiter()

    def test_filter_queryset_by_permissions_message(self):
        """Test filtering of Message objects via filter_queryset_by_permissions"""
        message = Message.objects.create(
            subject="Test Message", content="Content", created_by=self.fritz
        )
        queryset = Message.objects.all()
        filtered = self.fritz.filter_queryset_by_permissions(queryset=queryset, model=Message)
        self.assertQuerysetEqual(filtered, [message], ordered=False)


class PDFTestCase(TestCase):
    def setUp(self):
        self.ex = Freizeit.objects.create(
            name="Wild & ‬_törip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.note = MemberNoteList.objects.create(title="Coolß! ‬löst")
        self.cat = ActivityCategory.objects.create(name="Climbing", description="Climbing")
        ActivityCategory.objects.create(name="Walking", description="Climbing")
        self.ex.activity.add(self.cat)
        self.ex.save()

        for i in range(15):
            m = Member.objects.create(
                prename="Liääüuße {}".format(i),
                lastname="Walter&co ‬: _ kg &",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=FEMALE,
            )
            NewMemberOnList.objects.create(member=m, comments="a" * i, memberlist=self.ex)
            NewMemberOnList.objects.create(member=m, comments="a" * i, memberlist=self.note)

    def _assert_file_exists(self, fp):
        self.assertTrue(
            os.path.isfile(media_path(fp)), "{fp} does not exist after generating it.".format(fp=fp)
        )

    def _test_render_tex(self, template, context):
        fp = render_tex("Foo Bar", template, context, save_only=True)
        self._assert_file_exists(fp)
        return fp

    def _test_fill_pdf(self, template, context):
        fp = fill_pdf_form("Foo Bar", template, context, save_only=True)
        self._assert_file_exists(fp)

    def test_invalid_template(self):
        self.assertRaises(template.TemplateDoesNotExist, find_template, "foobar")

    def test_seminar_report(self):
        context = dict(memberlist=self.ex, settings=settings, mode="basic")
        fp = self._test_render_tex("members/seminar_report.tex", context)

        # test serving pdf
        response = serve_pdf(fp)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")
        self.assertEqual(
            response.headers["Content-Type"], "application/pdf", "Response content type is not pdf."
        )

        # test merging
        fp = merge_pdfs("foo", [fp, fp], save_only=True)
        self._assert_file_exists(fp)

    def test_notes_list(self):
        people, skills = self.ex.skill_summary
        context = dict(memberlist=self.ex, people=people, skill=skills, settings=settings)
        self._test_render_tex("members/notes_list.tex", context)

    def test_crisis_intervention_list(self):
        context = dict(memberlist=self.ex, settings=settings)
        self._test_render_tex("members/crisis_intervention_list.tex", context)

    def test_sjr_application(self):
        context = self.ex.sjr_application_fields()
        self._test_fill_pdf("members/sjr_template.pdf", context)

    def test_v32(self):
        context = self.ex.v32_fields()
        self._test_fill_pdf("members/V32-1_Themenorientierte_Bildungsmassnahmen.pdf", context)

    def test_render_docx_save_only(self):
        """Test render_docx with save_only=True"""
        context = dict(memberlist=self.ex, settings=settings, mode="basic")
        fp = render_docx("Test DOCX", "members/seminar_report.tex", context, save_only=True)
        self.assertIsInstance(fp, str)
        self.assertTrue(fp.endswith(".docx"))

    def test_pdf_add_attachments_with_image(self):
        """Test pdf_add_attachments with non-PDF image files"""
        # Create a simple test image
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_file:
            img = Image.new("RGB", (100, 100), color="red")
            img.save(tmp_file.name, "PNG")
            tmp_file.flush()

            # Create a PDF writer and test adding the image
            writer = PdfWriter()
            blank_page = PageObject.create_blank_page(width=595, height=842)
            writer.add_page(blank_page)

            # add image as attachment and verify page count
            pdf_add_attachments(writer, [tmp_file.name])
            self.assertGreater(len(writer.pages), 1)

            # Clean up
            os.unlink(tmp_file.name)

    def test_scale_pdf_page_to_a4(self):
        """Test scale_pdf_page_to_a4 function"""
        # Create a test page with different dimensions
        original_page = PageObject.create_blank_page(width=200, height=300)
        scaled_page = scale_pdf_page_to_a4(original_page)

        # A4 dimensions are 595x842
        self.assertEqual(float(scaled_page.mediabox.width), 595.0)
        self.assertEqual(float(scaled_page.mediabox.height), 842.0)

    def test_scale_pdf_to_a4(self):
        """Test scale_pdf_to_a4 function"""
        # Create a simple PDF with multiple pages of different sizes
        original_pdf = PdfWriter()
        original_pdf.add_page(PageObject.create_blank_page(width=200, height=300))
        original_pdf.add_page(PageObject.create_blank_page(width=400, height=600))

        # Write to BytesIO to create a readable PDF
        pdf_io = BytesIO()
        original_pdf.write(pdf_io)
        pdf_io.seek(0)

        # Read it back and scale
        pdf_reader = PdfReader(pdf_io)
        scaled_pdf = scale_pdf_to_a4(pdf_reader)

        # All pages should be A4 size (595x842)
        for page in scaled_pdf.pages:
            self.assertEqual(float(page.mediabox.width), 595.0)
            self.assertEqual(float(page.mediabox.height), 842.0)

    def test_merge_pdfs_serve(self):
        """Test merge_pdfs with save_only=False"""
        # First create two PDF files to merge
        context = dict(memberlist=self.ex, settings=settings, mode="basic")
        fp1 = render_tex("Test PDF 1", "members/seminar_report.tex", context, save_only=True)
        fp2 = render_tex("Test PDF 2", "members/seminar_report.tex", context, save_only=True)

        # Test merge with save_only=False (should return HttpResponse)
        response = merge_pdfs("Merged PDF", [fp1, fp2], save_only=False)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")


class AdminTestCase(TestCase):
    def setUp(self, model, admin):
        self.factory = RequestFactory()
        self.model = model
        if model is not None and admin is not None:
            self.admin = admin(model, AdminSite())
        User.objects.create_superuser(username="superuser", password="secret")
        standard = create_custom_user("standard", ["Standard"], "Paul", "Wulter")
        create_custom_user("trainer", ["Standard", "Trainings"], "Lise", "Lotte")
        create_custom_user("treasurer", ["Standard", "Finance"], "Lara", "Litte")
        create_custom_user("materialwarden", ["Standard", "Material"], "Loro", "Lutte")
        create_custom_user("waitinglistmanager", ["Standard", "Waitinglist"], "Liri", "Litti")

        paul = standard.member

        self.em = EmailAddress.objects.create(name="foobar")
        self.staff = Group.objects.create(name="Jugendleiter", contact_email=self.em)
        cool_kids = Group.objects.create(name="cool kids", show_website=True)
        super_kids = Group.objects.create(name="super kids")

        p1 = PermissionMember.objects.create(member=paul)
        p1.view_groups.add(cool_kids)
        p1.list_groups.add(super_kids)
        p1.list_groups.add(cool_kids)

        for i in range(3):
            m = Member.objects.create(
                prename="Fritz {}".format(i),
                lastname="Walter",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=MALE,
            )
            m.group.add(cool_kids)
            m.save()
        for i in range(7):
            m = Member.objects.create(
                prename="Lise {}".format(i),
                lastname="Walter",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=FEMALE,
            )
            m.group.add(super_kids)
            m.save()
        for i in range(5):
            m = Member.objects.create(
                prename="Lulla {}".format(i),
                lastname="Hulla",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=DIVERSE,
            )
            m.group.add(self.staff)
            m.save()
        m = Member.objects.create(
            prename="Peter",
            lastname="Hulla",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
        )
        m.group.add(self.staff)
        p1.list_members.add(m)

    def _login(self, name):
        c = Client()
        res = c.login(username=name, password="secret")
        # make sure we logged in
        assert res
        return c


class PermissionTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=None, admin=None)

    def test_standard_permissions(self):
        u = User.objects.get(username="standard")
        self.assertTrue(u.has_perm("members.view_member"))
        self.assertTrue(u.has_perm("members.view_memberwaitinglist"))
        self.assertFalse(u.has_perm("members.view_memberwaitinglist_global"))

    def test_queryset_standard(self):
        u = User.objects.get(username="standard")
        queryset = u.member.filter_queryset_by_permissions(model=Member)
        super_kids = Group.objects.get(name="super kids")
        super_kid = super_kids.member_set.first()
        self.assertTrue(super_kid in queryset, "super kid is not in queryset for Paul.")

    def test_queryset_trainer(self):
        u = User.objects.get(username="trainer")
        queryset = u.member.filter_queryset_by_permissions(model=Member)
        self.assertEqual(
            set(queryset), {u.member}, "Filtering trainer queryset yields more the trainer."
        )


class MemberAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=Member, admin=MemberAdmin)
        cool_kids = Group.objects.get(name="cool kids")
        Group.objects.get(name="super kids")
        mega_kids = Group.objects.create(name="mega kids")

        for i in range(1):
            m = Member.objects.create(
                prename="Peter {}".format(i),
                lastname="Walter",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=MALE,
            )
            m.group.add(mega_kids)
            m.save()
        self.fritz = cool_kids.member_set.first()
        self.peter = mega_kids.member_set.first()

    def test_changelist(self):
        c = self._login("superuser")

        url = reverse("admin:members_member_changelist")
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

    def test_change(self):
        c = self._login("superuser")

        mega_kids = Group.objects.get(name="mega kids")
        mega_kid = mega_kids.member_set.first()
        url = reverse("admin:members_member_change", args=(mega_kid.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        # if member does not exist, expect redirect
        url = reverse("admin:members_member_change", args=(71233,))
        response = c.get(url)
        self.assertEqual(response.status_code, 302, "Response code is not 302.")

    def test_changelist_standard(self):
        c = self._login("standard")

        url = reverse("admin:members_member_changelist")
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        results = response.context["results"]
        for result in results:
            name_or_link_field = result[1]
            group_field = result[4]
            self.assertFalse("mega kids" in group_field, "Standard can list a mega kid.")
            if "cool kids" in group_field:
                self.assertTrue("href" in name_or_link_field)
            elif "super kids" in group_field:
                self.assertFalse("href" in name_or_link_field)

    def test_changelist_trainer(self):
        c = self._login("trainer")

        url = reverse("admin:members_member_changelist")
        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        # trainers can view everyone, so there should be links in every row
        results = response.context["results"]
        for result in results:
            name_or_link_field = result[1]
            self.assertTrue("href" in name_or_link_field)

    def test_changelist_materialwarden(self):
        u = User.objects.get(username="materialwarden")
        c = self._login("materialwarden")

        url = reverse("admin:members_member_changelist")
        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        # materialwarden people can list everyone, but only view themselves by default
        results = response.context["results"]
        for result in results:
            name_or_link_field = result[1]
            self.assertFalse(
                "href" in name_or_link_field and str(u.member.pk) not in name_or_link_field
            )

        # now set member to None
        m = u.member
        m.user = None
        m.save()

        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        # since materialwarden has no member associated, no one should be viewable
        results = response.context["results"]
        for result in results:
            name_or_link_field = result[1]
            self.assertFalse("href" in name_or_link_field)

    def test_change_standard(self):
        u = User.objects.get(username="standard")
        self.assertTrue(hasattr(u, "member"))
        c = self._login("standard")

        cool_kids = Group.objects.get(name="cool kids")
        cool_kid = cool_kids.member_set.first()

        self.assertTrue(u.has_perm("members.view_obj_member", cool_kid))
        self.assertFalse(u.has_perm("members.change_obj_member", cool_kid))
        self.assertFalse(u.has_perm("members.delete_obj_member", cool_kid))
        self.assertTrue(hasattr(u, "member"))
        url = reverse("admin:members_member_change", args=(cool_kid.pk,))
        response = c.get(url, follow=True)

        super_kids = Group.objects.get(name="super kids")
        super_kid = super_kids.member_set.first()
        url = reverse("admin:members_member_change", args=(super_kid.pk,))
        response = c.get(url, follow=True)
        final = response.redirect_chain[-1][0]
        final_target = reverse("admin:members_member_changelist")
        self.assertEqual(response.status_code, 200, "Response code is not 200.")
        self.assertEqual(final, final_target, "Did redirect to wrong url.")

    def test_invite_as_user_view(self):
        # insufficient permissions
        c = self._login("standard")
        url = reverse("admin:members_member_inviteasuser", args=(self.fritz.pk,))
        response = c.post(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Permission denied."))

        c = self._login("superuser")

        # expect: user does not exist
        response = c.post(reverse("admin:members_member_inviteasuser", args=(12345,)), follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Member not found."))

        # expect: user is found, but email address is not internal
        response = c.post(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertFalse(self.fritz.has_internal_email())
        self.assertContains(
            response,
            _("The configured email address for %(name)s is not an internal one.")
            % {"name": str(self.fritz)},
        )

        # update email to allowed email domain
        self.fritz.email = INTERNAL_EMAIL
        self.fritz.save()
        response = c.post(url)
        # expect: user is found and confirmation page is shown
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Invite"))

        # expect: user is invited
        response = c.post(url, data={"apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        # expect: user already has a pending invitation
        response = c.post(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _("{name} already has a pending invitation as user.".format(name=str(self.fritz))),
        )

        # set user
        u = User.objects.create(username="fritzuser", password="secret")
        self.fritz.user = u
        self.fritz.save()

        # expect: user already has an account
        response = c.post(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("%(name)s already has login data.") % {"name": str(self.fritz)}
        )

    def test_invite_as_user_action_insufficient_permission(self):
        url = reverse("admin:members_member_changelist")

        # expect: confirmation view
        c = self._login("trainer")
        response = c.post(
            url,
            data={"action": "invite_as_user_action", "_selected_action": [self.fritz.pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertNotContains(response, _("Invite"))

    def test_invite_as_user_action(self):
        url = reverse("admin:members_member_changelist")

        # expect: confirmation view
        c = self._login("superuser")
        response = c.post(
            url,
            data={"action": "invite_as_user_action", "_selected_action": [self.fritz.pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Invite"))

        # confirm invite, expect: partial success
        response = c.post(
            url,
            data={
                "action": "invite_as_user_action",
                "_selected_action": [self.fritz.pk],
                "apply": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("Some members have been invited, others could not be invited.")
        )

        # confirm invite, expect: success
        self.peter.email = INTERNAL_EMAIL
        self.peter.save()
        self.fritz.email = INTERNAL_EMAIL
        self.fritz.save()
        response = c.post(
            url,
            data={
                "action": "invite_as_user_action",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "apply": True,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Successfully invited selected members to join as users."))

    def test_send_mail_to(self):
        # this is not connected to an action currently
        qs = Member.objects.all()
        response = self.admin.send_mail_to(None, qs)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_request_echo(self):
        self.peter.gets_newsletter = False
        self.peter.save()

        url = reverse("admin:members_member_changelist")

        # expect: success
        c = self._login("superuser")
        response = c.post(
            url,
            data={"action": "request_echo", "_selected_action": [self.fritz.pk, self.peter.pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_request_echo_fail_on_missing_birthdate(self):
        self.peter.birth_date = None
        self.peter.save()

        c = self._login("superuser")
        url = reverse("admin:members_member_changelist")
        response = c.post(
            url,
            data={"action": "request_echo", "_selected_action": [self.peter.pk]},
            follow=True,
        )

        self.assertContains(
            response,
            _(
                "Member {name} doesn't have a birthdate set, which is mandatory for echo requests"
            ).format(name=self.peter.name),
        )

    def test_request_echo_view(self):
        # expect: successful echo request
        c = self._login("superuser")
        url = reverse("admin:members_member_requestecho", args=(self.fritz.pk,))
        self.fritz.gets_newsletter = False
        self.fritz.save()
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)

        url = reverse("admin:members_member_requestecho", args=(self.peter.pk,))
        self.peter.gets_newsletter = True
        self.peter.save()
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)

        url = reverse("admin:members_member_requestecho", args=(12345,))
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_request_echo_view_fail_on_missing_birthdate(self):
        self.peter.birth_date = None
        self.peter.save()

        c = self._login("superuser")
        url = reverse("admin:members_member_requestecho", args=(self.peter.pk,))
        response = c.get(url, follow=True)

        self.assertContains(
            response,
            _(
                "Member {name} doesn't have a birthdate set, which is mandatory for echo requests"
            ).format(name=self.peter.name),
        )

    def test_activity_score(self):
        # manually set activity score
        for i in range(5):
            self.fritz._activity_score = i * 10 - 1
            self.assertTrue("img" in self.admin.activity_score(self.fritz))

    def test_unconfirm(self):
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        response = c.post(
            url, data={"action": "unconfirm", "_selected_action": [self.fritz.pk]}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.fritz.refresh_from_db()
        self.assertFalse(self.fritz.confirmed)

    def test_create_object_from_initial_view(self):
        """Test the initial view of create_object_from action."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action to get to the create_object_from view
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, self.fritz.name)
        self.assertContains(response, self.peter.name)

    def test_create_object_from_create_message(self):
        """Test creating a new Message from selected members."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'create' and choice='Message'
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "create": "create",
                "choice": "Message",
            },
        )
        # Should redirect to Message add view with members parameter
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertIn(reverse("admin:mailer_message_add"), response.url)
        self.assertIn("members=", response.url)

    def test_create_object_from_create_excursion(self):
        """Test creating a new Excursion from selected members."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'create' and choice='Excursion'
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "create": "create",
                "choice": "Excursion",
            },
        )
        # Should redirect to Freizeit add view with members parameter
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertIn("members/freizeit/add/", response.url)
        self.assertIn("members=", response.url)

    def test_create_object_from_create_membernotelist(self):
        """Test creating a new MemberNoteList from selected members."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'create' and choice='MemberNoteList'
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "create": "create",
                "choice": "MemberNoteList",
            },
        )
        # Should redirect to MemberNoteList add view with members parameter
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertIn("members/membernotelist/add/", response.url)
        self.assertIn("members=", response.url)

    def test_create_object_from_add_to_existing_message(self):
        """Test adding members to an existing Message."""
        # Create a test message
        message = Message.objects.create(subject="Test Message", content="Test content")
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'add_to_selected' and existing message
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "add_to_selected": "add_to_selected",
                "choice": "Message",
                "existing_entry": message.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check that members were added to the message
        message.refresh_from_db()
        self.assertEqual(message.to_members.count(), 2)
        self.assertIn(self.fritz, message.to_members.all())
        self.assertIn(self.peter, message.to_members.all())

    def test_create_object_from_add_to_existing_excursion(self):
        """Test adding members to an existing Excursion."""
        # Create a test excursion
        excursion = Freizeit.objects.create(
            name="Test Excursion",
            date=timezone.now(),
            end=timezone.now() + timezone.timedelta(days=1),
            kilometers_traveled=100,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'add_to_selected' and existing excursion
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "add_to_selected": "add_to_selected",
                "choice": "Excursion",
                "existing_entry": excursion.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check that members were added to the excursion
        self.assertEqual(excursion.membersonlist.count(), 2)

    def test_create_object_from_add_to_existing_membernotelist(self):
        """Test adding members to an existing MemberNoteList."""
        # Create a test note list
        note_list = MemberNoteList.objects.create(
            title="Test Note List", date=timezone.now().date()
        )
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'add_to_selected' and existing note list
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk, self.peter.pk],
                "add_to_selected": "add_to_selected",
                "choice": "MemberNoteList",
                "existing_entry": note_list.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # Check that members were added to the note list
        self.assertEqual(note_list.membersonlist.count(), 2)

    def test_create_object_from_add_to_nonexistent_message(self):
        """Test error handling when adding to non-existent message."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with non-existent message ID
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk],
                "add_to_selected": "add_to_selected",
                "choice": "Message",
                "existing_entry": 99999,
            },
            follow=True,
        )
        # Should redirect back to changelist
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("members/member/", response.request["PATH_INFO"])

    def test_create_object_from_add_to_nonexistent_excursion(self):
        """Test error handling when adding to non-existent excursion."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with non-existent excursion ID
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk],
                "add_to_selected": "add_to_selected",
                "choice": "Excursion",
                "existing_entry": 99999,
            },
            follow=True,
        )
        # Should redirect back to changelist
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("members/member/", response.request["PATH_INFO"])

    def test_create_object_from_add_to_nonexistent_membernotelist(self):
        """Test error handling when adding to non-existent note list."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with non-existent note list ID
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk],
                "add_to_selected": "add_to_selected",
                "choice": "MemberNoteList",
                "existing_entry": 99999,
            },
            follow=True,
        )
        # Should redirect back to changelist
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("members/member/", response.request["PATH_INFO"])

    def test_create_object_from_with_no_choice(self):
        """Test clicking create button without selecting a choice."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'create' but no choice
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk],
                "create": "create",
            },
        )
        # Should show the form again (no redirect)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("allowed_choices", response.context)

    def test_create_object_from_add_without_entry_id(self):
        """Test clicking add_to_selected button without selecting an existing entry."""
        url = reverse("admin:members_member_changelist")
        c = self._login("superuser")
        # Submit the action with 'add_to_selected' but no entry_id
        response = c.post(
            url,
            data={
                "action": "create_object_from",
                "_selected_action": [self.fritz.pk],
                "add_to_selected": "add_to_selected",
                "choice": "Message",
            },
            follow=True,
        )
        # Should redirect back to changelist
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertIn("members/member/", response.request["PATH_INFO"])


class FreizeitTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        # this excursion is used for the counting tests
        self.ex = Freizeit.objects.create(
            name="Wild trip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
            date=timezone.localtime(),
        )
        # this excursion is used in the other tests
        self.ex2 = Freizeit.objects.create(
            name="Wild trip 2",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
            date=timezone.localtime(),
        )
        self.ex2.jugendleiter.add(self.fritz)
        self.st = Statement.objects.create(excursion=self.ex2, night_cost=42, subsidy_to=None)
        self.ex2.save()
        # this excursion is used in the other tests
        self.ex3 = Freizeit.objects.create(
            name="Wild trip 3",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
            date=timezone.localtime(),
        )

    def _setup_test_sjr_application_numbers(self, n_yl, n_b27_local, n_b27_non_local):
        add_memberonlist_by_local(self.ex, n_yl, n_b27_local, n_b27_non_local)

    def _setup_test_ljp_participant_count(self, n_yl, n_correct_age, n_too_old):
        add_memberonlist_by_age(self.ex, n_yl, n_correct_age, n_too_old)

    def _cleanup_excursion(self):
        cleanup_excursion(self.ex)

    def _test_theoretic_ljp_participant_count_proportion(self, n_yl, n_correct_age, n_too_old):
        self._setup_test_ljp_participant_count(n_yl, n_correct_age, n_too_old)
        self.assertGreaterEqual(
            self.ex.theoretic_ljp_participant_count,
            n_yl,
            "An excursion with {n_yl} youth leaders and {n_correct_age} participants in the correct age range should have at least {n} participants.".format(
                n_yl=n_yl, n_correct_age=n_correct_age, n=n_yl + n_correct_age
            ),
        )
        self.assertLessEqual(
            self.ex.theoretic_ljp_participant_count,
            n_yl + n_correct_age + n_too_old,
            "An excursion with a total number of youth leaders and participants of {n} should have not more than {n} participants".format(
                n=n_yl + n_correct_age + n_too_old
            ),
        )

        n_parts_only = self.ex.theoretic_ljp_participant_count - n_yl
        self.assertLessEqual(
            n_parts_only - n_correct_age,
            1 / 5 * n_parts_only,
            "An excursion with {n_parts_only} non-youth-leaders, of which {n_correct_age} have the correct age, the number of participants violating the age range must not exceed 20% of the total participants, i.e. {d}".format(
                n_parts_only=n_parts_only, n_correct_age=n_correct_age, d=1 / 5 * n_parts_only
            ),
        )

        self.assertEqual(
            n_parts_only - n_correct_age,
            min(math.floor(1 / 5 * n_parts_only), n_too_old),
            "An excursion with {n_parts_only} non-youth-leaders, of which {n_correct_age} have the correct age, the number of participants violating the age range must be equal to the minimum of {n_too_old} and the smallest integer less than 20% of the total participants, i.e. {d}".format(
                n_parts_only=n_parts_only,
                n_correct_age=n_correct_age,
                d=math.floor(1 / 5 * n_parts_only),
                n_too_old=n_too_old,
            ),
        )

        # cleanup
        self._cleanup_excursion()

    def _test_ljp_participant_count_proportion(self, n_yl, n_correct_age, n_too_old):
        self._setup_test_ljp_participant_count(n_yl, n_correct_age, n_too_old)
        if n_yl + n_correct_age + n_too_old < 5:
            self.assertEqual(self.ex.ljp_participant_count, 0)
        else:
            self.assertEqual(self.ex.ljp_participant_count, self.ex.theoretic_ljp_participant_count)

        # cleanup
        self._cleanup_excursion()

    def test_theoretic_ljp_participant_count(self):
        self._test_theoretic_ljp_participant_count_proportion(2, 0, 0)
        for i in range(10):
            self._test_theoretic_ljp_participant_count_proportion(2, 10 - i, i)

    def test_ljp_participant_count(self):
        self._test_ljp_participant_count_proportion(2, 1, 1)
        self._test_ljp_participant_count_proportion(2, 5, 1)

    def _test_sjr_application_numbers(self, n_yl, n_b27_local, n_b27_non_local):
        self._setup_test_sjr_application_numbers(n_yl, n_b27_local, n_b27_non_local)
        numbers = self.ex.sjr_application_numbers()

        self.assertEqual(numbers["b27_local"], n_b27_local)
        self.assertEqual(numbers["b27_non_local"], n_b27_non_local)
        self.assertEqual(numbers["staff"], n_yl)
        self.assertLessEqual(numbers["relevant_b27"], n_b27_local + n_b27_non_local)
        self.assertLessEqual(numbers["relevant_b27"] - n_b27_local, 1 / 3 * numbers["relevant_b27"])
        self.assertLessEqual(numbers["subsidizable"] - numbers["relevant_b27"], n_yl)
        self.assertLessEqual(
            numbers["subsidizable"] - numbers["relevant_b27"], numbers["relevant_b27"] / 7 + 1
        )

        # cleanup
        self._cleanup_excursion()

    def test_sjr_application_numbers(self):
        self._test_sjr_application_numbers(0, 10, 0)
        for i in range(10):
            self._test_sjr_application_numbers(10, 10 - i, i)

    def test_notify_leaders_crisis_intervention_list(self):
        self.ex2.notification_crisis_intervention_list_sent = False
        self.ex2.notify_leaders_crisis_intervention_list()
        self.assertTrue(self.ex2.notification_crisis_intervention_list_sent)
        self.ex2.notify_leaders_crisis_intervention_list(sending_time=timezone.now())

    def test_send_crisis_intervention_list(self):
        self.ex2.crisis_intervention_list_sent = False
        self.ex2.send_crisis_intervention_list()
        self.assertTrue(self.ex2.crisis_intervention_list_sent)

    def test_filter_queryset_by_permissions(self):
        qs = Freizeit.filter_queryset_by_permissions(self.fritz)
        self.assertIn(self.ex2, qs)

    def test_v32_fields(self):
        self.assertIn("Textfeld 61", self.ex2.v32_fields().keys())

    def test_no_statement(self):
        self.assertEqual(self.ex.total_relative_costs, 0)
        self.assertEqual(self.ex.payable_ljp_contributions, 0)
        self.assertEqual(self.ex.potential_ljp_contributions, 0)

    def test_no_ljpproposal(self):
        self.assertEqual(self.ex2.total_intervention_hours, 0)
        self.assertEqual(self.ex2.seminar_time_per_day, [])

    def test_relative_costs(self):
        # after deducting contributions, the total costs should still be non-negative
        self.assertGreaterEqual(self.ex2.total_relative_costs, 0)

    def test_payable_ljp_contributions(self):
        self.assertGreaterEqual(self.ex2.payable_ljp_contributions, 0)
        self.st.ljp_to = self.fritz
        self.assertGreaterEqual(self.ex2.payable_ljp_contributions, 0)

    def test_get_tour_type(self):
        self.ex2.tour_type = GEMEINSCHAFTS_TOUR
        self.assertEqual(self.ex2.get_tour_type(), "Gemeinschaftstour")
        self.ex2.tour_type = FUEHRUNGS_TOUR
        self.assertEqual(self.ex2.get_tour_type(), "Führungstour")
        self.ex2.tour_type = AUSBILDUNGS_TOUR
        self.assertEqual(self.ex2.get_tour_type(), "Ausbildung")

    def test_get_tour_approach(self):
        self.ex2.tour_approach = MUSKELKRAFT_ANREISE
        self.assertEqual(self.ex2.get_tour_approach(), "Muskelkraft")
        self.ex2.tour_approach = OEFFENTLICHE_ANREISE
        self.assertEqual(self.ex2.get_tour_approach(), "ÖPNV")
        self.ex2.tour_approach = FAHRGEMEINSCHAFT_ANREISE
        self.assertEqual(self.ex2.get_tour_approach(), "Fahrgemeinschaften")

    def test_duration(self):
        self.assertGreaterEqual(self.ex.duration, 0)

        # less than 6 hours
        self.ex.date = timezone.datetime(2000, 1, 1, 8, 0, 0)
        self.ex.end = timezone.datetime(2000, 1, 1, 10, 0, 0)
        self.assertEqual(self.ex.duration, 0.5)

        # at least 6 hours
        self.ex.date = timezone.datetime(2000, 1, 1, 8, 0, 0)
        self.ex.end = timezone.datetime(2000, 1, 1, 14, 0, 0)
        self.assertEqual(self.ex.duration, 1)

        # one full day and two extra days on beginning and end
        self.ex.date = timezone.datetime(2000, 1, 1, 8, 0, 0)
        self.ex.end = timezone.datetime(2000, 1, 3, 14, 0, 0)
        self.assertEqual(self.ex.duration, 3)

        # one full day and two half days on beginning and end
        self.ex.date = timezone.datetime(2000, 1, 1, 16, 0, 0)
        self.ex.end = timezone.datetime(2000, 1, 3, 8, 0, 0)
        self.assertEqual(self.ex.duration, 2)

    def test_duration_midday_midday(self):
        self.ex.date = timezone.datetime(2000, 1, 1, 12, 0, 0)
        self.ex.end = timezone.datetime(2000, 1, 1, 12, 0, 0)
        self.assertEqual(self.ex.duration, 0.5)

    def test_generate_ljp_vbk_no_proposal_raises_error(self):
        """Test generate_ljp_vbk raises ValueError when excursion has no LJP proposal"""
        with self.assertRaises(ValueError) as cm:
            generate_ljp_vbk(self.ex)
        self.assertIn("Excursion has no LJP proposal", str(cm.exception))

    def test_filter_queryset_date_next_n_hours(self):
        self.ex.date = timezone.now() + timezone.timedelta(hours=12)
        self.ex.save()
        self.ex2.date = timezone.now() + timezone.timedelta(hours=36)
        self.ex2.save()
        self.ex3.date = timezone.now() - timezone.timedelta(hours=1)
        self.ex3.save()
        qs = Freizeit.filter_queryset_date_next_n_hours(24)
        self.assertIn(self.ex, qs)
        self.assertNotIn(self.ex2, qs)
        self.assertNotIn(self.ex3, qs)

    def test_querysets_crisis_intervention_list(self):
        self.ex.date = timezone.now() + timezone.timedelta(hours=12)
        self.ex.crisis_intervention_list_sent = False
        self.ex.save()
        self.ex2.date = timezone.now() + timezone.timedelta(hours=36)
        self.ex2.notification_crisis_intervention_list_sent = False
        self.ex2.save()
        self.ex3.notification_crisis_intervention_list_sent = True
        self.ex3.save()
        to_send = Freizeit.to_send_crisis_intervention_list()
        to_notify = Freizeit.to_notify_crisis_intervention_list()
        self.assertIn(self.ex, to_send)
        self.assertNotIn(self.ex2, to_send)
        self.assertNotIn(self.ex3, to_send)
        self.assertIn(self.ex2, to_notify)

    def test_get_dropdown_display(self):
        """Test get_dropdown_display formats name and date correctly."""
        display = self.ex.get_dropdown_display()
        self.assertIn("Wild trip", display)
        self.assertIn("-", display)
        self.assertRegex(display, r"\d{2}\.\d{2}\.\d{4}")

    def test_filter_queryset_by_change_permissions_without_member_attribute(self):
        """Test filter_queryset when user has no member attribute."""
        user = User.objects.create_user(username="no_member", password="secret")
        queryset = Freizeit.filter_queryset_by_change_permissions(user)
        self.assertEqual(queryset.count(), 0)

    def test_filter_queryset_by_change_permissions_with_limited_permissions(self):
        """Test filter_queryset when user has member but limited permissions."""
        user = User.objects.create_user(username="limited_user", password="secret")
        member = Member.objects.create(
            prename="Limited",
            lastname="User",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=DIVERSE,
        )
        member.user = user
        member.save()
        queryset = Freizeit.filter_queryset_by_change_permissions(user)
        self.assertIsNotNone(queryset)


class PDFActionMixin:
    def _test_pdf(
        self, name, pk, model="freizeit", invalid=False, username="superuser", post_data=None
    ):
        c = Client()
        c.login(username=username, password="secret")

        url = reverse("admin:members_%s_action" % model, args=(pk,))
        if not post_data:
            post_data = {name: "hoho"}
        response = c.post(url, post_data)
        if not invalid:
            self.assertEqual(response.status_code, 200, "Response code is not 200.")
            self.assertEqual(
                response.headers["Content-Type"],
                "application/pdf",
                "Response content type is not pdf.",
            )
        else:
            self.assertEqual(response.status_code, 302, "Response code is not 302.")


class FreizeitAdminTestCase(AdminTestCase, PDFActionMixin):
    def setUp(self):
        super().setUp(model=Freizeit, admin=FreizeitAdmin)
        self.ex = Freizeit.objects.create(
            name="Wild trip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.yl1 = Member.objects.create(
            prename="Lose",
            lastname="Walter",
            birth_date=timezone.now().date() - relativedelta(years=15),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        self.yl2 = Member.objects.create(
            prename="Lose",
            lastname="Walter",
            birth_date=timezone.now().date() - relativedelta(years=15),
            email=settings.TEST_MAIL,
            gender=FEMALE,
        )
        self.ex.jugendleiter.add(self.yl1)
        self.ex.jugendleiter.add(self.yl2)

        for i in range(7):
            m = Member.objects.create(
                prename="Lise {}".format(i),
                lastname="Walter",
                birth_date=timezone.now().date() - relativedelta(years=15),
                email=settings.TEST_MAIL,
                gender=FEMALE,
            )
            NewMemberOnList.objects.create(member=m, comments="a" * i, memberlist=self.ex)

        fr = Member.objects.create(
            prename="Peter",
            lastname="Wulter",
            birth_date=datetime.date(1900, 1, 1),
            email=settings.TEST_MAIL,
            gender=MALE,
        )
        self.st = Statement.objects.create(night_cost=11, subsidy_to=fr)
        file = SimpleUploadedFile("proof.pdf", b"file_content", content_type="application/pdf")
        self.bill = Bill.objects.create(
            statement=self.st,
            short_description="bla",
            explanation="bli",
            amount=42.69,
            costs_covered=True,
            paid_by=fr,
            proof=file,
        )
        self.ex2 = Freizeit.objects.create(
            name="Wild trip 2",
            kilometers_traveled=0,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.ljpproposal = LJPProposal.objects.create(
            title="My seminar",
            category=LJPProposal.LJP_STAFF_TRAINING,
            goal=LJPProposal.LJP_ENVIRONMENT,
            goal_strategy="my strategy",
            not_bw_reason=LJPProposal.NOT_BW_ROOMS,
            excursion=self.ex2,
        )
        self.st_ljp = Statement.objects.create(
            night_cost=11, subsidy_to=fr, ljp_to=fr, excursion=self.ex2
        )
        self.bill_no_proof = Bill.objects.create(
            statement=self.st_ljp,
            short_description="bla",
            explanation="bli",
            amount=42.69,
            costs_covered=True,
            paid_by=fr,
        )

    def test_changelist(self):
        c = self._login("superuser")

        url = reverse("admin:members_freizeit_changelist")
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

    def test_change(self):
        c = self._login("superuser")

        ex = Freizeit.objects.get(name="Wild trip")
        url = reverse("admin:members_freizeit_change", args=(ex.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        # if excursion does not exist, expect redirect
        url = reverse("admin:members_freizeit_change", args=(71233,))
        response = c.get(url)
        self.assertEqual(response.status_code, 302, "Response code is not 302.")

    def test_add(self):
        c = self._login("standard")

        url = reverse("admin:members_freizeit_add")
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

    @skip("The filtering is currently (intentionally) disabled.")
    def test_add_queryset_filter(self):  # pragma: no cover
        """Test if queryset on `jugendleiter` field is properly filtered by permissions."""
        u = User.objects.get(username="standard")
        c = self._login("standard")

        url = reverse("admin:members_freizeit_add")

        request = self.factory.get(url)
        request.user = u

        field = Freizeit._meta.get_field("jugendleiter")
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        self.assertQuerysetEqual(
            queryset,
            u.member.filter_queryset_by_permissions(model=Member),
            msg="Field queryset does not match filtered queryset from models.",
            ordered=False,
        )

        u.member.user = None
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        self.assertQuerysetEqual(queryset, Member.objects.none())

        c = self._login("materialwarden")
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

        u = User.objects.get(username="materialwarden")

        request.user = u
        field = Freizeit._meta.get_field("jugendleiter")
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        # material warden can list everyone
        self.assertQuerysetEqual(
            queryset,
            Member.objects.all(),
            msg="Field queryset does not match all members.",
            ordered=False,
        )

        queryset = self.admin.formfield_for_manytomany(field, None).queryset
        self.assertQuerysetEqual(queryset, Member.objects.none())

    @mock.patch("members.pdf.render_tex")
    def test_seminar_report_post(self, mocked_fun):
        c = self._login("standard")
        url = reverse("admin:members_freizeit_action", args=(self.ex.pk,))
        response = c.post(url, data={"seminar_report": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        c = self._login("superuser")
        url = reverse("admin:members_freizeit_action", args=(self.ex.pk,))
        response = c.post(url, data={"seminar_report": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _("This excursion does not have a LJP proposal. Please add one and try again."),
        )

        url = reverse("admin:members_freizeit_action", args=(self.ex2.pk,))
        response = c.post(url, data={"seminar_report": "", "apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("A seminar report consists of multiple components:"))

    def test_invalid_download(self):
        url = reverse("admin:members_freizeit_download_ljp_vbk", args=(self.ex.pk,))
        c = self._login("standard")
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _("You are not allowed to view all members on excursion %(name)s.")
            % {"name": self.ex.name},
        )

        c = self._login("superuser")
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _("This excursion does not have a LJP proposal. Please add one and try again."),
        )

        url = reverse("admin:members_freizeit_download_ljp_vbk", args=(123456789,))
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Excursion not found."))

    def test_download_seminar_vbk(self):
        url = reverse("admin:members_freizeit_download_ljp_vbk", args=(self.ex2.pk,))
        c = self._login("superuser")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_download_seminar_report_docx(self):
        url = reverse("admin:members_freizeit_download_ljp_report_docx", args=(self.ex2.pk,))
        c = self._login("superuser")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_download_seminar_report_costs_and_participants(self):
        url = reverse("admin:members_freizeit_download_ljp_costs_participants", args=(self.ex2.pk,))
        c = self._login("superuser")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    @mock.patch("members.pdf.fill_pdf_form")
    def test_sjr_application_post(self, mocked_fun):
        url = reverse("admin:members_freizeit_action", args=(self.ex.pk,))
        c = self._login("standard")
        response = c.post(url, data={"sjr_application": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        c = self._login("superuser")
        response = c.post(url, data={"sjr_application": ""})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("Here you can generate an allowance application for the SJR.")
        )

        response = c.post(url, data={"sjr_application": "", "apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Please select an invoice."))

        self.st.excursion = self.ex
        self.st.save()
        response = c.post(url, data={"sjr_application": "", "apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Please select an invoice."))

        response = c.post(
            url,
            data={
                "sjr_application": "",
                "apply": "",
                "invoice": self.bill.proof.path,
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_crisis_intervention_list_post(self):
        self._test_pdf("crisis_intervention_list", self.ex.pk)
        self._test_pdf("crisis_intervention_list", self.ex.pk, username="standard", invalid=True)

    def test_notes_list_post(self):
        self._test_pdf("notes_list", self.ex.pk)
        self._test_pdf("notes_list", self.ex.pk, username="standard", invalid=True)

    def test_wrong_action_freizeit(self):
        return self._test_pdf("asdf", self.ex.pk, invalid=True)

    def test_finance_overview_no_statement_post(self):
        url = reverse("admin:members_freizeit_action", args=(self.ex.pk,))
        c = self._login("superuser")
        # no statement yields redirect
        response = c.post(url, data={"finance_overview": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("No statement found. Please add a statement and then retry.")
        )

    def test_finance_overview_invalid_post(self):
        url = reverse("admin:members_freizeit_action", args=(self.ex2.pk,))
        c = self._login("superuser")

        # bill with missing proof
        response = c.post(url, data={"finance_overview": "", "apply": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "The excursion is configured to claim LJP contributions. In that case, for all bills, a proof must be uploaded. Please correct this and try again."
            ),
        )

        # invalidate allowance_to
        self.st_ljp.allowance_to.add(self.yl1)

        response = c.post(url, data={"finance_overview": "", "apply": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "The configured recipients of the allowance don't match the regulations. Please correct this and try again."
            ),
        )

    def test_finance_overview_post(self):
        url = reverse("admin:members_freizeit_action", args=(self.ex.pk,))
        c = self._login("superuser")
        # set statement
        self.st.excursion = self.ex
        self.st.save()
        # render overview
        response = c.post(url, data={"finance_overview": ""})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("This is the estimated cost and contribution summary:"))
        # submit fails because allowance_to is wrong
        response = c.post(url, data={"finance_overview": "", "apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        # submit succeeds after fixing allowance_to
        self.st.allowance_to.add(self.yl1)
        self.st.allowance_to.add(self.yl2)
        response = c.post(url, data={"finance_overview": "", "apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_save_model_with_statement(self):
        user_with_member = User.objects.get(username="standard")
        self.ex.statement = self.st
        request = self.factory.post("/")
        request.user = user_with_member
        form = mock.MagicMock()
        with mock.patch("members.admin.super") as mock_super:
            mock_super.return_value.save_model.return_value = None
            self.admin.save_model(request, self.ex, form, change=False)
        self.st.refresh_from_db()
        self.assertEqual(self.st.created_by, user_with_member.member)

    def test_memberonlist_inline_get_formset_with_members_param(self):
        """Test MemberOnListInline.get_formset with members query parameter."""
        c = self._login("superuser")
        url = reverse("admin:members_freizeit_add")
        member_ids = [self.yl1.pk, self.yl2.pk]
        import json

        members_json = json.dumps(member_ids)
        response = c.get(f"{url}?members={members_json}")
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_memberonlist_inline_get_formset_with_invalid_json(self):
        """Test MemberOnListInline.get_formset with invalid JSON in members parameter."""
        c = self._login("superuser")
        url = reverse("admin:members_freizeit_add")
        response = c.get(f"{url}?members=invalid-json")
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_memberonlist_inline_get_formset_with_non_list_json(self):
        """Test MemberOnListInline.get_formset with non-list JSON in members parameter."""
        c = self._login("superuser")
        url = reverse("admin:members_freizeit_add")
        import json

        members_json = json.dumps({"not": "a list"})
        response = c.get(f"{url}?members={members_json}")
        self.assertEqual(response.status_code, HTTPStatus.OK)


class MemberNoteListAdminTestCase(AdminTestCase, PDFActionMixin):
    def setUp(self):
        super().setUp(model=MemberNoteList, admin=MemberNoteListAdmin)
        self.note = MemberNoteList.objects.create(title="Cool list")

        for i in range(7):
            m = Member.objects.create(
                prename="Lise {}".format(i),
                lastname="Walter",
                birth_date=timezone.now().date(),
                email=settings.TEST_MAIL,
                gender=FEMALE,
            )
            NewMemberOnList.objects.create(member=m, comments="a" * i, memberlist=self.note)

    def test_str(self):
        self.assertEqual(str(self.note), "Cool list")

    def test_membernote_summary(self):
        self._test_pdf("summary", self.note.pk, model="membernotelist")
        self._test_pdf(
            "summary", self.note.pk, model="membernotelist", username="standard", invalid=True
        )

    def test_wrong_action_membernotelist(self):
        return self._test_pdf("asdf", self.note.pk, invalid=True, model="membernotelist")

    def test_change(self):
        c = self._login("superuser")

        url = reverse("admin:members_membernotelist_change", args=(self.note.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, "Response code is not 200.")

    def test_get_dropdown_display_with_date(self):
        """Test get_dropdown_display when note list has a date."""
        note_with_date = MemberNoteList.objects.create(
            title="Test Note", date=timezone.now().date()
        )
        display = note_with_date.get_dropdown_display()
        self.assertIn("Test Note", display)
        self.assertIn("-", display)
        # Should contain formatted date
        self.assertRegex(display, r"\d{2}\.\d{2}\.\d{4}")

    def test_get_dropdown_display_without_date(self):
        """Test get_dropdown_display when note list has no date."""
        note_without_date = MemberNoteList.objects.create(title="No Date Note", date=None)
        display = note_without_date.get_dropdown_display()
        self.assertEqual(display, "No Date Note")

    def test_filter_queryset_by_change_permissions_without_permission(self):
        """Test filtering queryset when user lacks change permission."""
        # Standard user doesn't have change_membernotelist permission
        user = User.objects.get(username="standard")
        queryset = MemberNoteList.filter_queryset_by_change_permissions(user)
        # Should return empty queryset
        self.assertEqual(queryset.count(), 0)


class MemberOnListInlineFormTestCase(TestCase):
    def test_has_changed_with_prefilled(self):
        """Test that has_changed on member field works correctly when prefilled=True."""
        # Create a test member
        member = Member.objects.create(
            prename="Test",
            lastname="User",
            birth_date=timezone.now().date(),
            email=settings.TEST_MAIL,
            gender=MALE,
        )

        form = MemberOnListInlineForm(prefilled=True)

        # Test that has_changed returns True for non-empty data
        self.assertTrue(form.fields["member"].has_changed(None, str(member.pk)))
        # Test that has_changed returns False for empty string
        self.assertFalse(form.fields["member"].has_changed(None, ""))


class MemberWaitingListAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=MemberWaitingList, admin=MemberWaitingListAdmin)
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        for i in range(10):
            day = random.randint(1, 28)
            month = random.randint(1, 12)
            year = random.randint(1900, timezone.now().year - 1)
            MemberWaitingList.objects.create(
                prename="Peter {}".format(i),
                lastname="Puter",
                birth_date=datetime.date(year, month, day),
                email=settings.TEST_MAIL,
                gender=FEMALE,
            )

    def _request(self):
        u = User.objects.get(username="superuser")
        url = reverse("admin:members_memberwaitinglist_changelist")
        request = self.factory.get(url)
        request.user = u
        return request

    def test_has_view_permission(self):
        request = self.factory.get("/")
        request.user = User.objects.get(username="standard")
        self.assertTrue(self.admin.has_view_permission(request))
        self.assertFalse(self.admin.has_view_permission(request, self.waiter))

    def test_changelist(self):
        c = self._login("standard")
        url = reverse("admin:members_memberwaitinglist_changelist")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

        c = self._login("waitinglistmanager")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_age_eq_birth_date_delta(self):
        queryset = self.admin.get_queryset(self._request())
        today = timezone.now().date()

        for m in queryset:
            self.assertEqual(
                m.birth_date_delta,
                m.age(),
                msg="Queryset based age calculation differs from python based age calculation for birth date {birth_date} compared to {today}.".format(
                    birth_date=m.birth_date, today=today
                ),
            )

    def test_invite_view_invalid(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberwaitinglist_invite", args=(12312,))

        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("A waiter with this ID does not exist."))

    def test_invite_view_post(self):
        c = self._login("standard")
        url = reverse("admin:members_memberwaitinglist_invite", args=(self.waiter.pk,))

        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

        response = c.post(url, data={"apply": "", "group": 424242})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        self.staff.contact_email = None
        self.staff.save()

        response = c.post(url, data={"apply": "", "group": self.staff.pk})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        self.staff.contact_email = self.em
        self.staff.save()

        response = c.post(url, data={"apply": "", "group": self.staff.pk})
        self.assertEqual(response.status_code, HTTPStatus.OK)

        response = c.post(url, data={"send": "", "group": self.staff.pk})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        response = c.post(url, data={"send": "", "group": self.staff.pk, "text_template": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_ask_for_registration_action(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberwaitinglist_changelist")
        qs = MemberWaitingList.objects.all()
        response = c.post(
            url,
            data={
                "action": "ask_for_registration_action",
                "_selected_action": [qs[0].pk],
                "send": "",
                "text_template": "",
                "group": self.staff.pk,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_age(self):
        req = self._request()
        queryset = self.admin.get_queryset(req)
        w = queryset[0]
        self.assertEqual(self.admin.age(w), w.age())

    def test_ask_for_wait_confirmation(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberwaitinglist_changelist")
        qs = MemberWaitingList.objects.all()
        response = c.post(
            url,
            data={"action": "ask_for_wait_confirmation", "_selected_action": [q.pk for q in qs]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_request_mail_confirmation(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberwaitinglist_changelist")
        qs = MemberWaitingList.objects.all()

        response = c.post(
            url,
            data={"action": "request_mail_confirmation", "_selected_action": [q.pk for q in qs]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

        response = c.post(
            url,
            data={
                "action": "request_required_mail_confirmation",
                "_selected_action": [q.pk for q in qs],
            },
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_response_change_invite(self):
        request = self.factory.post("/", {"_invite": True})
        request.user = User.objects.get(username="superuser")
        with mock.patch("members.admin.super") as mock_super:
            mock_super.return_value.response_change.return_value = HttpResponse()
            response = self.admin.response_change(request, self.waiter)
        self.assertIsInstance(response, HttpResponseRedirect)

    def test_response_change_no_invite(self):
        request = self.factory.post("/", {})
        request.user = User.objects.get(username="superuser")
        expected_response = HttpResponse()
        with mock.patch("members.admin.super") as mock_super:
            mock_super.return_value.response_change.return_value = expected_response
            response = self.admin.response_change(request, self.waiter)
        self.assertEqual(response, expected_response)


class MemberUnconfirmedAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=MemberUnconfirmedProxy, admin=MemberUnconfirmedAdmin)
        self.reg = MemberUnconfirmedProxy.objects.create(**REGISTRATION_DATA, confirmed=False)
        for i in range(10):
            MemberUnconfirmedProxy.objects.create(**REGISTRATION_DATA, confirmed=False)

    def test_get_queryset(self):
        request = self.factory.get("/")
        request.user = User.objects.get(username="superuser")
        qs = self.admin.get_queryset(request)
        self.assertQuerysetEqual(qs, MemberUnconfirmedProxy.objects.all(), ordered=False)

        request.user = User.objects.create(username="test", password="secret")
        qs = self.admin.get_queryset(request)
        self.assertQuerysetEqual(qs, MemberUnconfirmedProxy.objects.none(), ordered=False)

        request.user = User.objects.get(username="standard")
        qs = self.admin.get_queryset(request)
        self.assertQuerysetEqual(qs, MemberUnconfirmedProxy.objects.none(), ordered=False)

    def test_request_registration_form_invalid(self):
        c = self._login("standard")
        url = reverse("admin:members_memberunconfirmedproxy_request_registration_form", args=(124,))
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_request_registration_form_insufficient_permission(self):
        c = self._login("standard")
        url = reverse(
            "admin:members_memberunconfirmedproxy_request_registration_form", args=(self.reg.pk,)
        )
        response = c.get(url, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Insufficient permissions."))

    def test_request_registration_form(self):
        c = self._login("superuser")
        url = reverse(
            "admin:members_memberunconfirmedproxy_request_registration_form", args=(self.reg.pk,)
        )
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Request registration form"))

        response = c.post(url, data={"apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_demote_to_waiter(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_demote", args=(self.reg.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Demote member to waiter"))

        response = c.post(url, data={"apply": ""})
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_demote_to_waiter_action(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        qs = MemberUnconfirmedProxy.objects.all()
        response = c.post(
            url,
            data={"action": "demote_to_waiter_action", "_selected_action": [qs[0].pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        response = c.post(
            url,
            data={"action": "demote_to_waiter_action", "_selected_action": [qs[0].pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_confirm(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        response = c.post(
            url, data={"action": "confirm", "_selected_action": [self.reg.pk]}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.reg.confirmed_mail = True
        self.reg.confirmed_alternative_mail = True
        self.reg.save()
        response = c.post(
            url, data={"action": "confirm", "_selected_action": [self.reg.pk]}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_confirm_multiple(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        qs = MemberUnconfirmedProxy.objects.all()
        response = c.post(
            url, data={"action": "confirm", "_selected_action": [q.pk for q in qs]}, follow=True
        )
        self.assertContains(
            response,
            _("Failed to confirm some registrations because of unconfirmed email addresses."),
        )

        for q in qs:
            q.confirmed_mail = True
            q.confirmed_alternative_mail = True
            q.save()
        response = c.post(
            url, data={"action": "confirm", "_selected_action": [q.pk for q in qs]}, follow=True
        )
        self.assertContains(response, _("Successfully confirmed multiple registrations."))

    def test_request_mail_confirmation(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        qs = MemberUnconfirmedProxy.objects.all()
        response = c.post(
            url,
            data={"action": "request_mail_confirmation", "_selected_action": [qs[0].pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("Successfully requested mail confirmation from selected registrations.")
        )

    def test_request_required_mail_confirmation(self):
        c = self._login("superuser")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        qs = MemberUnconfirmedProxy.objects.all()
        response = c.post(
            url,
            data={"action": "request_required_mail_confirmation", "_selected_action": [qs[0].pk]},
            follow=True,
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _("Successfully re-requested missing mail confirmations from selected registrations."),
        )

    def test_changelist(self):
        c = self._login("standard")
        url = reverse("admin:members_memberunconfirmedproxy_changelist")
        response = c.get(url)
        # By default, standard users may access the member unconfirmed listing (but only view
        # the relevant registrations)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_response_change_confirm(self):
        request = self.factory.post("/", {"_confirm": True})
        request.user = User.objects.get(username="superuser")
        request._messages = mock.MagicMock()

        # Test successful confirm
        self.reg.confirmed_mail = True
        self.reg.confirmed_alternative_mail = True
        self.reg.save()
        with mock.patch.object(self.reg, "confirm", return_value=True):
            self.admin.response_change(request, self.reg)

        # Test failed confirm
        with mock.patch.object(self.reg, "confirm", return_value=False):
            self.admin.response_change(request, self.reg)


class MailConfirmationTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.father = EmergencyContact.objects.create(
            prename="Olaf", lastname="Old", email=settings.TEST_MAIL, member=self.fritz
        )
        self.father.save()
        self.reg = MemberUnconfirmedProxy.objects.create(**REGISTRATION_DATA, confirmed=False)
        self.reg.group.add(self.alp)
        file = SimpleUploadedFile("form.pdf", b"file_content", content_type="application/pdf")
        self.reg.registration_form = file
        self.reg.save()

    def test_request_mail_confirmation(self):
        self.reg.confirmed_mail = True
        self.reg.confirmed_alternative_mail = True
        self.assertFalse(self.reg.request_mail_confirmation(rerequest=False))

    def test_confirm_mail_memberunconfirmed(self):
        requested = self.reg.request_mail_confirmation()
        self.assertTrue(requested)
        self.assertIsNone(self.reg.confirm_mail("foobar"))
        self.assertTrue(self.reg.confirm_mail(self.reg.confirm_mail_key))
        self.assertTrue(self.reg.confirm_mail(self.reg.confirm_alternative_mail_key))
        self.assertTrue(self.reg.registration_ready())

    def test_contact_confirmation(self):
        # request mail confirmation of father
        requested_confirmation = self.father.request_mail_confirmation()
        self.assertTrue(
            requested_confirmation,
            msg="Requesting mail confirmation should return true, if rerequest is false.",
        )
        # father's mail should not be confirmed
        self.assertFalse(
            self.father.confirmed_mail,
            msg="Mail should not be confirmed after requesting confirmation.",
        )

        key = self.father.confirm_mail_key
        # key should not be empty
        self.assertFalse(
            key == "",
            msg="Mail confirmation key should not be blank after requesting confirmation.",
        )

        # now confirm mail by using the generated key
        self.father.confirm_mail(key)

        # father's mail should now be confirmed
        self.assertTrue(
            self.father.confirmed_mail, msg="After confirming by key, the mail should be confirmed."
        )

    @skip("Currently, emergency contact email addresses are not required to be confirmed.")
    def test_emergency_contact_confirmation(self):  # pragma: no cover
        # request mail confirmation of fritz, should also ask for confirmation of father
        requested_confirmation = self.fritz.request_mail_confirmation()
        self.assertTrue(
            requested_confirmation,
            msg="Requesting mail confirmation should return true, if rerequest is false.",
        )

        for em in self.fritz.emergencycontact_set.all():
            # emergency contact mail should not be confirmed
            self.assertFalse(
                em.confirmed_mail, msg="Mail should not be confirmed after requesting confirmation."
            )
            key = em.confirm_mail_key
            self.assertFalse(
                key == "",
                msg="Mail confirmation key should not be blank after requesting confirmation.",
            )

            # now confirm mail by using the generated key
            confirm_mail_by_key(key)

        for em in self.fritz.emergencycontact_set.all():
            self.assertTrue(
                em.confirmed_mail,
                msg="Mail of every emergency contact should be confirmed after manually confirming.",
            )

    def test_request_mail_confirmation_skips_empty_email(self):
        """Ensure request_mail_confirmation continues when email field is empty."""
        # set emergency contact email to empty -> should be skipped
        self.father.email = ""
        self.father.save()
        requested = self.father.request_mail_confirmation()
        self.assertFalse(requested)
        # no key should have been generated
        self.assertEqual(getattr(self.father, "confirm_mail_key", ""), "")


class RegisterWaitingListViewTestCase(BasicMemberTestCase):
    def test_register_waiting_list_get(self):
        url = reverse("members:register_waiting_list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_waiting_list_post(self):
        url = reverse("members:register_waiting_list")
        response = self.client.post(url, data=dict(WAITER_DATA, save=""))
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Your registration for the waiting list was successful."))

    def test_register_waiting_list_post_invalid(self):
        url = reverse("members:register_waiting_list")
        response = self.client.post(
            url,
            data={
                "save": "",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("This field is required."))

        # this is required to bump the test coverage, but this is probably dead code
        response = self.client.post(url, data={})
        self.assertEqual(response.status_code, HTTPStatus.OK)


class RegisterViewTestCase(BasicMemberTestCase):
    REGISTRATION_PASSWORD = "foobar"

    def setUp(self):
        super().setUp()
        self.factory = RequestFactory()
        RegistrationPassword.objects.create(
            group=self.alp, password=RegisterViewTestCase.REGISTRATION_PASSWORD
        )

    def test_register_password_get(self):
        url = reverse("members:register")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_password_post(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data={
                "password": RegisterViewTestCase.REGISTRATION_PASSWORD,
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_password_post_save(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                **EMERGENCY_CONTACT_DATA,
                password=RegisterViewTestCase.REGISTRATION_PASSWORD,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        reg = MemberUnconfirmedProxy.objects.get(prename="Peter", lastname="Wulter", town="Town 1")
        self.assertEqual(reg.street, "Street 123")

    def test_register_password_post_incomplete(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data={
                "password": RegisterViewTestCase.REGISTRATION_PASSWORD,
                "save": "",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_password_post_missing_emergency_contact(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                password=RegisterViewTestCase.REGISTRATION_PASSWORD,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_password_post_invalid(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data={
                "password": RegisterViewTestCase.REGISTRATION_PASSWORD + "_",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("The entered password is wrong."))

    def test_register_no_group(self):
        # Test when group is None, render_register_failed is called with reason
        url = reverse("members:register")
        response = self.client.post(
            url,
            data={
                "password": "",
                "waiter_key": "",
                "save": "",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Registration failed"))

    def test_render_register_success(self):
        # Test render_register_success return statement
        response = render_register_success(
            self.factory.get("/"), "Test Group", "Test Member", False
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_render_register_failed_with_reason(self):
        # Test render_register_failed with reason to cover context assignment
        response = render_register_failed(self.factory.get("/"), "Test reason")
        self.assertEqual(response.status_code, HTTPStatus.OK)


class UploadRegistrationFormViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.reg = MemberUnconfirmedProxy.objects.create(**REGISTRATION_DATA)
        self.reg.create_from_registration(None, self.alp)

    def test_upload_registration_form_get(self):
        url = self.reg.get_upload_registration_form_link()
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "If you are not an adult yet, please let someone responsible for you sign the agreement."
            ),
        )

    def test_upload_registration_form_get_invalid(self):
        url = reverse("members:upload_registration_form")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )

        url = reverse("members:upload_registration_form") + "?key=foobar"
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )

    def test_upload_registration_form_post_no_key(self):
        url = reverse("members:upload_registration_form")
        # no key
        response = self.client.post(url, data={})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )
        # invalid key
        response = self.client.post(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )

    def test_upload_registration_form_post_incomplete(self):
        url = reverse("members:upload_registration_form")
        response = self.client.post(
            url,
            data={
                "key": self.reg.upload_registration_form_key,
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("This field is required."))

    def test_upload_registration_form_post(self):
        url = reverse("members:upload_registration_form")
        file = SimpleUploadedFile("form.pdf", b"file_content", content_type="application/pdf")
        response = self.client.post(
            url,
            data={
                "key": self.reg.upload_registration_form_key,
                "registration_form": file,
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Our team will process your registration shortly."))

    def test_upload_registration_form_validation_error(self):
        # Test ValueError exception handling during form validation
        url = reverse("members:upload_registration_form")
        file = SimpleUploadedFile("form.pdf", b"file_content", content_type="application/pdf")
        with mock.patch.object(Member, "validate_registration_form") as mock_validate:
            mock_validate.side_effect = ValueError("Test validation error")
            response = self.client.post(
                url,
                data={
                    "key": self.reg.upload_registration_form_key,
                    "registration_form": file,
                },
            )
            self.assertEqual(response.status_code, HTTPStatus.OK)
            # Should stay on upload form page due to error
            self.assertContains(
                response,
                _(
                    "If you are not an adult yet, please let someone responsible for you sign the agreement."
                ),
            )


class DownloadRegistrationFormViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.reg = MemberUnconfirmedProxy.objects.create(**REGISTRATION_DATA)
        self.reg.create_from_registration(None, self.alp)

    def test_download_registration_form_get_invalid(self):
        url = reverse("members:download_registration_form")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # this is how it is implemented, but it is questionable if this is the correct behaviour
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )

        response = self.client.get(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        # this is how it is implemented, but it is questionable if this is the correct behaviour
        self.assertContains(
            response, _("The supplied key for uploading a registration form is invalid.")
        )

    def test_download_registration_form_get(self):
        url = reverse("members:download_registration_form")
        response = self.client.get(url, data={"key": self.reg.upload_registration_form_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertEqual(response.headers["Content-Type"], "application/pdf")


class RegistrationFromWaiterViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.invite_to_group(self.alp)
        self.invitation = InvitationToGroup.objects.get(group=self.alp, waiter=self.waiter)

    def test_register_post_waiter_key_invalid(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data={
                "waiter_key": "foobar",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Something went wrong while processing your registration."))

    def test_register_post(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                **EMERGENCY_CONTACT_DATA,
                waiter_key=self.invitation.key,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

    def test_register_post_invalid(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                waiter_key=self.invitation.key,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_register_post_no_save(self):
        url = reverse("members:register")
        response = self.client.post(
            url,
            data=dict(
                waiter_key=self.invitation.key,
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)


class InvitationToGroupViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.invite_to_group(self.alp)
        self.invitation = InvitationToGroup.objects.get(group=self.alp, waiter=self.waiter)

    def _assert_reject_invalid(self, response):
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("This invitation is invalid or expired."))

    def test_accept_get_no_key(self):
        url = reverse("members:registration")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_accept_get_invalid(self):
        url = reverse("members:registration")
        response = self.client.get(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("invalid"))

        url = reverse("members:registration")
        self.invitation.rejected = True
        self.invitation.save()
        response = self.client.get(url, data={"key": self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("expired"))

    def test_accept_get(self):
        url = reverse("members:registration")
        response = self.client.get(url, data={"key": self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_reject_get(self):
        url = reverse("members:reject_invitation")
        response = self.client.get(url, data={"key": self.invitation.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_reject_get_invalid(self):
        url = reverse("members:reject_invitation")
        response = self.client.get(url, data={"key": "foobar"})
        self._assert_reject_invalid(response)

        self.invitation.rejected = True
        self.invitation.save()
        response = self.client.get(url, data={"key": self.invitation.key})
        self._assert_reject_invalid(response)

    def test_reject_post_invalid(self):
        url = reverse("members:reject_invitation")
        response = self.client.post(url)
        self._assert_reject_invalid(response)
        response = self.client.post(url, data={"key": "foobar"})
        self._assert_reject_invalid(response)
        response = self.client.post(url, data={"key": self.invitation.key})
        self._assert_reject_invalid(response)

    def test_reject_post_reject(self):
        url = reverse("members:reject_invitation")
        response = self.client.post(
            url,
            data={
                "key": self.invitation.key,
                "reject_invitation": "",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_reject_post_leave(self):
        url = reverse("members:reject_invitation")
        response = self.client.post(
            url,
            data={
                "key": self.invitation.key,
                "leave_waitinglist": "",
            },
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)


class InvitationToGroupTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.invite_to_group(self.alp)
        self.invitation = InvitationToGroup.objects.get(group=self.alp, waiter=self.waiter)
        self.invitation.created_by = self.fritz

    def test_status(self):
        self.assertEqual(self.invitation.status(), _("Undecided"))
        # expire the invitation
        self.invitation.date = (timezone.now() - timezone.timedelta(days=100)).date()
        self.assertTrue(self.invitation.is_expired())
        self.assertEqual(self.invitation.status(), _("Expired"))
        # reject the invitation
        self.invitation.reject()
        self.assertEqual(self.invitation.status(), _("Rejected"))

    def test_confirm(self):
        self.invitation.confirm()
        self.assertFalse(self.invitation.rejected)

    def test_notify_left_waitinglist(self):
        self.invitation.notify_left_waitinglist()


class MemberWaitingListTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.invite_to_group(self.alp)
        self.invitation = InvitationToGroup.objects.get(group=self.alp, waiter=self.waiter)

    def test_latest_group_invitation(self):
        self.assertGreater(len(self.waiter.latest_group_invitation()), 1)

    def test_may_register(self):
        self.assertTrue(self.waiter.may_register(self.invitation.key))

    def test_may_register_invalid(self):
        self.assertFalse(self.waiter.may_register("foobar"))

    def test_waiting_confirmation_needed(self):
        self.assertFalse(self.waiter.waiting_confirmation_needed)

    def test_confirm_waiting_invalid(self):
        self.assertEqual(
            self.waiter.confirm_waiting("foobar"), MemberWaitingList.WAITING_CONFIRMATION_INVALID
        )


class ConfirmWaitingViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.ask_for_wait_confirmation()
        self.key = self.waiter.generate_wait_confirmation_key()

    def test_get_no_key(self):
        url = reverse("members:confirm_waiting")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        url = reverse("members:confirm_waiting")
        response = self.client.get(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("The supplied link is invalid."))

    def test_get(self):
        url = reverse("members:confirm_waiting")
        response = self.client.get(url, data={"key": self.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Waiting confirmed"))

        # modify the POST data, otherwise the request is cached
        response = self.client.get(url, data={"key": self.key, "foo": "bar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Waiting confirmed"))
        waiter = MemberWaitingList.objects.get(pk=self.waiter.pk)
        self.assertEqual(waiter.leave_key, "")

    def test_get_expired(self):
        # waiter has a pending confirmation request
        self.assertEqual(self.waiter.waiting_confirmed(), None)

        url = reverse("members:confirm_waiting")
        self.waiter.wait_confirmation_key_expire = timezone.now() - timezone.timedelta(days=10)
        self.waiter.save()
        # waiter has pending confirmation request, but request has expired
        self.assertEqual(self.waiter.waiting_confirmed(), False)
        response = self.client.get(url, data={"key": self.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("rejoin the waiting list"))

    def test_get_leave(self):
        url = reverse("members:leave_waitinglist")
        response = self.client.get(url, data={"key": self.waiter.leave_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Leave waitinglist"))

        # modify the POST data, otherwise the request is cached
        response = self.client.post(
            url, data={"key": self.waiter.leave_key, "leave_waitinglist": "bar"}
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Left waitinglist"))
        self.assertRaises(
            MemberWaitingList.DoesNotExist, MemberWaitingList.objects.get, pk=self.waiter.pk
        )

    def test_leave_invalid(self):
        url = reverse("members:leave_waitinglist")
        # get, wrong key
        response = self.client.get(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        # post, wrong key
        response = self.client.post(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        # post, no key
        response = self.client.post(url)
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)
        # post, no sanity flag
        response = self.client.post(url, data={"key": self.waiter.leave_key})
        self.assertEqual(response.status_code, HTTPStatus.NOT_FOUND)

    def test_confirm_waiting_invalid_status(self):
        # Test invalid status handling in confirm_waiting
        url = reverse("members:confirm_waiting")
        with mock.patch.object(MemberWaitingList, "confirm_waiting") as mock_confirm:
            mock_confirm.return_value = 999  # Invalid status
            response = self.client.get(url, data={"key": self.key})
            self.assertEqual(response.status_code, HTTPStatus.OK)
            self.assertContains(response, _("The supplied link is invalid."))


class MailConfirmationViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.request_mail_confirmation()

    def test_get_invalid(self):
        url = reverse("members:confirm_mail")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        url = reverse("members:confirm_mail")
        response = self.client.get(url, data={"key": "foobar"})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Mail confirmation failed"))

    def test_get(self):
        url = reverse("members:confirm_mail")
        response = self.client.get(url, {"key": self.waiter.confirm_mail_key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Mail confirmed"))


class EchoViewTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.key = self.fritz.generate_echo_key()
        file = SimpleUploadedFile("form.pdf", b"file_content", content_type="application/pdf")
        self.fritz.registration_form = file
        self.fritz.save()

    def _assert_failed(self, response):
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Echo failed"))

    def test_get_invalid(self):
        url = reverse("members:echo")
        response = self.client.get(url)
        self.assertEqual(response.status_code, HTTPStatus.FOUND)

        url = reverse("members:echo")
        response = self.client.get(url, data={"key": "foobar"})
        self._assert_failed(response)

    def test_get(self):
        url = reverse("members:echo")
        response = self.client.get(url, data={"key": self.key})
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "Thanks for echoing back. Please enter the password, which you can find in the email we sent you.\n"
            ),
        )

    def test_post_invalid(self):
        url = reverse("members:echo")
        # no key
        response = self.client.post(url)
        self._assert_failed(response)
        # wrong key
        response = self.client.post(
            url, data={"key": "foobar", "password": self.fritz.echo_password}
        )
        self._assert_failed(response)
        # wrong password
        response = self.client.post(url, data={"key": self.key, "password": "foobar"})
        self.assertContains(response, _("The entered password is wrong."))
        # expired key
        self.fritz.echo_expire = timezone.now() - timezone.timedelta(
            days=settings.ECHO_GRACE_PERIOD
        )
        self.fritz.save()
        response = self.client.post(
            url, data={"key": self.key, "password": self.fritz.echo_password}
        )
        self._assert_failed(response)

    def test_post(self):
        url = reverse("members:echo")
        response = self.client.post(
            url, data={"key": self.key, "password": self.fritz.echo_password}
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "Here is your current data. Please check if it is up to date and change accordingly."
            ),
        )

    def test_post_save(self):
        url = reverse("members:echo")
        # provide data, but no emergency contacts
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                key=self.key,
                password=self.fritz.echo_password,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(
            response,
            _(
                "Here is your current data. Please check if it is up to date and change accordingly."
            ),
        )

        # provide everything correctly
        url = reverse("members:echo")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                **EMERGENCY_CONTACT_DATA,
                key=self.key,
                password=self.fritz.echo_password,
                save="",
            ),
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertContains(response, _("Your data was successfully updated."))

    def test_post_save_without_registration_form(self):
        # Clear registration form to test member without registration_form case
        self.fritz.registration_form = None
        self.fritz.save()
        url = reverse("members:echo")
        response = self.client.post(
            url,
            data=dict(
                REGISTRATION_DATA,
                **EMERGENCY_CONTACT_DATA,
                key=self.key,
                password=self.fritz.echo_password,
                save="",
            ),
        )
        # Should redirect to upload registration form
        self.assertEqual(response.status_code, HTTPStatus.FOUND)
        self.assertIn("upload", response.url)


class MemberAdminFormTestCase(TestCase):
    def test_clean_iban(self):
        form_data = dict(REGISTRATION_DATA, iban="foobar")
        form = MemberAdminForm(data=form_data)
        self.assertTrue("IBAN" in str(form.errors))

        form_data = dict(REGISTRATION_DATA, iban="DE89370400440532013000")
        form = MemberAdminForm(data=form_data)
        self.assertFalse("IBAN" in str(form.errors))


class StatementOnListFormTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.ex = Freizeit.objects.create(
            name="Wild trip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.ex.jugendleiter.add(self.fritz)
        self.ex.save()
        self.st = Statement.objects.create(excursion=self.ex, night_cost=42, subsidy_to=None)
        self.st.allowance_to.add(self.fritz)
        self.st.save()

    def test_clean(self):
        form = StatementOnListForm(parent_obj=self.ex, instance=self.st)
        # should not raise any error
        form.cleaned_data = {"excursion": self.ex, "allowance_to": None}
        form.clean()

        # should raise Validation error because too many allowance_to are listed
        form.cleaned_data = {
            "excursion": self.ex,
            "allowance_to": Member.objects.filter(pk=self.fritz.pk),
        }
        self.assertGreater(1, self.ex.approved_staff_count)
        self.assertRaises(ValidationError, form.clean)


class KlettertreffAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=Klettertreff, admin=KlettertreffAdmin)

        cool_kids = Group.objects.get(name="cool kids")
        for i in range(10):
            Klettertreff.objects.create(location="foo", topic="bar", group=cool_kids)

    def test_change(self):
        kl = Klettertreff.objects.first()
        url = reverse("admin:members_klettertreff_change", args=(kl.pk,))
        c = self._login("superuser")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_overview(self):
        qs = Klettertreff.objects.all()
        url = reverse("admin:members_klettertreff_changelist")

        # expect: success
        c = self._login("superuser")
        response = c.post(
            url, data={"action": "overview", "_selected_action": [kl.pk for kl in qs]}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_overview_filtered(self):
        qs = Klettertreff.objects.all()
        cool_kids = Group.objects.get(name="cool kids")
        url = reverse("admin:members_klettertreff_changelist") + f"?group__id__exact={cool_kids.pk}"

        # expect: success and filtered by group
        c = self._login("superuser")
        response = c.post(
            url, data={"action": "overview", "_selected_action": [kl.pk for kl in qs]}, follow=True
        )
        self.assertEqual(response.status_code, HTTPStatus.OK)
        self.assertNotContains(response, "Lise")


class GroupAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=Group, admin=GroupAdmin)

    def test_change(self):
        g = Group.objects.first()
        url = reverse("admin:members_group_change", args=(g.pk,))
        c = self._login("superuser")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_group_overview(self):
        url = reverse("admin:members_group_action")
        c = self._login("standard")
        response = c.post(url, data={"group_overview": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

        c = self._login("superuser")
        response = c.post(url, data={"group_overview": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_group_checklist(self):
        url = reverse("admin:members_group_action")
        c = self._login("standard")
        response = c.post(url, data={"group_checklist": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.FORBIDDEN)

        c = self._login("superuser")
        response = c.post(url, data={"group_checklist": ""}, follow=True)
        self.assertEqual(response.status_code, HTTPStatus.OK)


class FilteredMemberFieldMixinTestCase(AdminTestCase):
    def setUp(self):
        class CustomGroupAdmin(FilteredMemberFieldMixin, admin.ModelAdmin):
            pass

        class CustomMemberAdmin(FilteredMemberFieldMixin, admin.ModelAdmin):
            pass

        class CustomKlettertreffAttendeeAdmin(FilteredMemberFieldMixin, admin.ModelAdmin):
            pass

        self.custom_gr_admin = CustomGroupAdmin(Group, AdminSite())
        self.custom_member_admin = CustomMemberAdmin(Member, AdminSite())
        self.custom_kla_admin = CustomKlettertreffAttendeeAdmin(KlettertreffAttendee, AdminSite())
        super().setUp(model=Group, admin=CustomGroupAdmin)
        User.objects.create_user(username="foobar", password="secret")

    def test_invalid_manytomany(self):
        # filtering a db_field with related model != Member should return the db_field unchanged
        url = reverse("admin:members_memberwaitinglist_changelist")
        request = self.factory.get(url)
        request.user = User.objects.get(username="superuser")
        db_field = Member._meta.get_field("group")
        member_admin = MemberAdmin(Member, AdminSite())
        self.assertQuerysetEqual(
            self.custom_member_admin.formfield_for_manytomany(db_field, request).queryset,
            member_admin.formfield_for_manytomany(db_field, request).queryset,
            ordered=False,
        )

    def test_invalid_foreignkey(self):
        # filtering a db_field with related model != Member should return the db_field unchanged
        url = reverse("admin:members_memberwaitinglist_changelist")
        request = self.factory.get(url)
        request.user = User.objects.get(username="superuser")
        db_field = Group._meta.get_field("contact_email")
        gr_admin = GroupAdmin(Group, AdminSite())
        self.assertQuerysetEqual(
            self.admin.formfield_for_foreignkey(db_field, request).queryset,
            gr_admin.formfield_for_foreignkey(db_field, request).queryset,
        )

    def test_filter_manytomany(self):
        url = reverse("admin:members_memberwaitinglist_changelist")
        request = self.factory.get(url)

        # if user has `members.list_global_member`, the filter returns all fields
        request.user = User.objects.get(username="superuser")
        field = self.admin.formfield_for_manytomany(Group._meta.get_field("leiters"), request)
        self.assertQuerysetEqual(field.queryset, Member.objects.all(), ordered=False)

        # if not, it is filtered by permissions
        u = User.objects.get(username="standard")
        request.user = u
        field = self.admin.formfield_for_manytomany(Group._meta.get_field("leiters"), request)
        self.assertQuerysetEqual(
            field.queryset, u.member.filter_queryset_by_permissions(model=Member), ordered=False
        )

        # if no request is passed, no members are shown
        field = self.admin.formfield_for_manytomany(Group._meta.get_field("leiters"), None)
        self.assertQuerysetEqual(field.queryset, Member.objects.none())

        # if user has no associated member and does not have the special permission,
        # the filter returns nothing
        request.user = User.objects.get(username="foobar")
        field = self.admin.formfield_for_manytomany(Group._meta.get_field("leiters"), request)
        self.assertQuerysetEqual(field.queryset, Member.objects.none(), ordered=False)

    def test_filter_foreignkey(self):
        url = reverse("admin:members_memberwaitinglist_changelist")
        request = self.factory.get(url)

        # if user has `members.list_global_member`, the filter returns all fields
        request.user = User.objects.get(username="superuser")
        field = self.admin.formfield_for_foreignkey(
            KlettertreffAttendee._meta.get_field("member"), request
        )
        self.assertQuerysetEqual(field.queryset, Member.objects.all(), ordered=False)

        # if not, it is filtered by permissions
        u = User.objects.get(username="standard")
        request.user = u
        field = self.admin.formfield_for_foreignkey(
            KlettertreffAttendee._meta.get_field("member"), request
        )
        self.assertQuerysetEqual(
            field.queryset, u.member.filter_queryset_by_permissions(model=Member), ordered=False
        )

        # if no request is passed, no members are shown
        field = self.admin.formfield_for_foreignkey(
            KlettertreffAttendee._meta.get_field("member"), None
        )
        self.assertQuerysetEqual(field.queryset, Member.objects.none())

        # if user has no associated member and does not have the special permission,
        # the filter returns nothing
        request.user = User.objects.get(username="foobar")
        field = self.admin.formfield_for_foreignkey(
            KlettertreffAttendee._meta.get_field("member"), request
        )
        self.assertQuerysetEqual(field.queryset, Member.objects.none(), ordered=False)


class ActivityCategoryTestCase(TestCase):
    def setUp(self):
        self.cat = ActivityCategory.objects.create(
            name="crazy climbing", ljp_category="Klettern", description="foobar"
        )

    def test_str(self):
        self.assertEqual(str(self.cat), "crazy climbing")


class GroupTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.alp.show_website = True
        self.alp.weekday = 3
        self.alp.start_time = datetime.time(15, 0)
        self.alp.end_time = datetime.time(17, 0)
        self.alp.save()

    def test_str(self):
        self.assertEqual(str(self.alp), self.alp.name)

    def test_has_time_info(self):
        self.assertTrue(self.alp.has_time_info())
        self.assertFalse(self.spiel.has_time_info())

    def test_has_age_info(self):
        self.assertTrue(self.alp.has_age_info())
        self.assertFalse(self.jl.has_age_info())

    def test_get_age_info(self):
        self.assertGreater(len(self.alp.get_age_info()), 0)
        self.assertEqual(self.jl.get_age_info(), "")

    def test_get_invitation_text_template(self):
        alp_text = self.alp.get_invitation_text_template()
        spiel_text = self.spiel.get_invitation_text_template()
        url = reverse("startpage:gruppe_detail", args=[self.alp.name])
        self.assertIn(url, alp_text)

        url = reverse("startpage:gruppe_detail", args=[self.spiel.name])
        self.assertNotIn(url, spiel_text)

        self.assertIn(str(WEEKDAYS[self.alp.weekday][1]), alp_text)

        # check that method does not crash if no age info exists
        self.assertGreater(len(self.jl.get_invitation_text_template()), 0)


class NewMemberOnListTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.ex = Freizeit.objects.create(
            name="Wild trip",
            kilometers_traveled=120,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=MUSKELKRAFT_ANREISE,
            difficulty=1,
        )
        self.cat = ActivityCategory.objects.create(
            name="crazy climbing", ljp_category="Klettern", description="foobar"
        )
        self.ex.activity.add(self.cat)
        self.ex.save()
        self.mol = NewMemberOnList.objects.create(memberlist=self.ex, member=self.fritz)

    def test_skills(self):
        self.assertGreater(len(self.mol.skills), 0)

    def test_qualities_tex(self):
        self.assertGreater(len(self.mol.qualities_tex), 0)


class TrainingCategoryTestCase(TestCase):
    def setUp(self):
        self.cat = TrainingCategory.objects.create(name="school", permission_needed=True)

    def test_str(self):
        self.assertEqual(str(self.cat), "school")


class MemberTrainingTestCase(TestCase):
    def setUp(self):
        self.member_training = MemberTraining.objects.create(
            member=Member.objects.create(**REGISTRATION_DATA),
            category=TrainingCategory.objects.create(name="Test Training", permission_needed=False),
            date=timezone.now().date(),
        )
        self.member_training_no_date = MemberTraining.objects.create(
            member=Member.objects.create(**REGISTRATION_DATA),
            category=TrainingCategory.objects.create(name="Test Training", permission_needed=False),
            date=None,
        )

    def test_str(self):
        self.assertIn(self.member_training.date.strftime("%d.%m.%Y"), str(self.member_training))
        self.assertIn(str(_("(no date)")), str(self.member_training_no_date))


class MemberTrainingAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=MemberTraining, admin=MemberTrainingAdmin)
        self.member_training = MemberTraining.objects.create(
            member=Member.objects.create(**REGISTRATION_DATA),
            category=TrainingCategory.objects.create(name="Test Training", permission_needed=False),
            date=timezone.now().date(),
        )
        self.activity = ActivityCategory.objects.create(
            name="Test Activity", ljp_category="Sonstiges", description="Test"
        )
        self.member_training.activity.add(self.activity)

    def test_changelist(self):
        c = self._login("superuser")
        url = reverse("admin:members_membertraining_changelist")
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)

    def test_change(self):
        c = self._login("superuser")
        url = reverse("admin:members_membertraining_change", args=(self.member_training.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, HTTPStatus.OK)


class PermissionMemberGroupTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.gp = PermissionGroup.objects.create(group=self.alp)
        self.gm = PermissionMember.objects.create(member=self.fritz)

    def test_str(self):
        self.assertEqual(str(self.gp), _("Group permissions"))
        self.assertEqual(str(self.gm), _("Permissions"))


class LJPProposalTestCase(TestCase):
    def setUp(self):
        self.proposal = LJPProposal.objects.create(title="Foo")

    def test_str(self):
        self.assertEqual(str(self.proposal), "Foo")


class KlettertreffTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.kt = Klettertreff.objects.create(location="foo", topic="bar", group=self.alp)
        self.kt.jugendleiter.add(self.fritz)
        self.kt.save()
        self.attendee = KlettertreffAttendee.objects.create(klettertreff=self.kt, member=self.peter)

    def test_str_attendee(self):
        self.assertEqual(str(self.attendee), str(self.peter))

    def test_get_jugendleiter(self):
        self.assertIn(self.kt.get_jugendleiter(), self.fritz.name)

    def test_has_jugendleiter(self):
        self.assertFalse(self.kt.has_jugendleiter(self.peter))
        self.assertTrue(self.kt.has_jugendleiter(self.fritz))

    def test_has_attendee(self):
        self.assertTrue(self.kt.has_attendee(self.peter))
        self.assertFalse(self.kt.has_attendee(self.fritz))


class EmergencyContactTestCase(TestCase):
    def setUp(self):
        self.member = Member.objects.create(**REGISTRATION_DATA)
        self.emergency_contact = EmergencyContact.objects.create(member=self.member)

    def test_str(self):
        self.assertEqual(str(self.emergency_contact), str(self.member))


class MemberDocumentTestCase(TestCase):
    def setUp(self):
        self.member = Member.objects.create(**REGISTRATION_DATA)
        self.document = MemberDocument.objects.create(member=self.member)

    def test_str_with_file(self):
        # Simulate a file name
        self.document.f.name = "member_documents/test_medical_form.pdf"
        self.assertEqual(str(self.document), "test_medical_form.pdf")

    def test_str_without_file(self):
        self.assertEqual(str(self.document), _("Empty"))


class InvitationToGroupAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=InvitationToGroup, admin=InvitationToGroupAdmin)

    def test_has_add_permission(self):
        self.assertFalse(self.admin.has_add_permission(None))


class MemberWaitingListFilterTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=MemberWaitingList, admin=MemberWaitingListAdmin)
        self.waiter = MemberWaitingList.objects.create(**WAITER_DATA)
        self.waiter.invite_to_group(self.staff)


class AgeFilterTestCase(MemberWaitingListFilterTestCase):
    def test_queryset_no_value(self):
        fil = AgeFilter(None, {}, MemberWaitingList, self.admin)
        qs = MemberWaitingList.objects.all()
        self.assertQuerysetEqual(fil.queryset(None, qs), qs, ordered=False)

    def test_queryset(self):
        fil = AgeFilter(None, {"age": 12}, MemberWaitingList, self.admin)
        request = self.factory.get("/")
        request.user = User.objects.get(username="superuser")
        qs = self.admin.get_queryset(request)
        self.assertQuerysetEqual(
            fil.queryset(request, qs), qs.filter(birth_date_delta=12), ordered=False
        )


class InvitedToGroupFilterTestCase(MemberWaitingListFilterTestCase):
    def test_queryset_no_value(self):
        fil = InvitedToGroupFilter(None, {}, MemberWaitingList, self.admin)
        qs = MemberWaitingList.objects.all()
        self.assertQuerysetEqual(fil.queryset(None, qs), qs, ordered=False)

    def test_queryset(self):
        fil = InvitedToGroupFilter(
            None, {"pending_group_invitation": self.staff.pk}, MemberWaitingList, self.admin
        )
        request = self.factory.get("/")
        request.user = User.objects.get(username="superuser")
        qs = self.admin.get_queryset(request)
        self.assertQuerysetEqual(fil.queryset(request, qs).distinct(), [self.waiter], ordered=False)
