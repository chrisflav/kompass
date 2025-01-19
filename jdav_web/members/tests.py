from django.contrib.auth import models as authmodels
from django.contrib.admin.sites import AdminSite
from django.contrib.messages import get_messages
from django.contrib.auth.models import User
from django.test import TestCase, Client, RequestFactory
from django.utils import timezone, translation
from django.conf import settings
from django.urls import reverse
from unittest import skip, mock
from .models import Member, Group, PermissionMember, PermissionGroup, Freizeit, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE,\
        MemberNoteList, NewMemberOnList, confirm_mail_by_key, EmergencyContact, MemberWaitingList,\
        DIVERSE, MALE, FEMALE
from .admin import MemberWaitingListAdmin, MemberAdmin, FreizeitAdmin
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
import random
import datetime
from dateutil.relativedelta import relativedelta
import math


def create_custom_user(username, groups, prename, lastname):
    user = User.objects.create_user(
        username=username, password='secret'
    )
    member = Member.objects.create(prename=prename, lastname=lastname, birth_date=timezone.localdate(), email=settings.TEST_MAIL, gender=DIVERSE)
    member.user = user
    member.save()
    user.is_staff = True
    user.save()

    for group in groups:
        g = authmodels.Group.objects.get(name=group)
        user.groups.add(g)
    return user


class BasicMemberTestCase(TestCase):
    def setUp(self):
        self.jl = Group.objects.create(name="Jugendleiter")
        self.alp = Group.objects.create(name="Alpenfuechse")
        self.spiel = Group.objects.create(name="Spielkinder")

        self.fritz = Member.objects.create(prename="Fritz", lastname="Wulter", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=DIVERSE)
        self.fritz.group.add(self.jl)
        self.fritz.group.add(self.alp)
        self.fritz.save()

        self.peter = Member.objects.create(prename="Peter", lastname="Wulter",
                                           birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=MALE)
        self.peter.group.add(self.jl)
        self.peter.group.add(self.alp)
        self.peter.save()

        self.lara = Member.objects.create(prename="Lara", lastname="Wallis", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=DIVERSE)
        self.lara.group.add(self.alp)
        self.lara.save()
        self.fridolin = Member.objects.create(prename="Fridolin", lastname="Spargel", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=MALE)
        self.fridolin.group.add(self.alp)
        self.fridolin.group.add(self.spiel)
        self.fridolin.save()

        self.lise = Member.objects.create(prename="Lise", lastname="Lotte", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=FEMALE)


class MemberTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()

        p1 = PermissionMember.objects.create(member=self.fritz)
        p1.view_members.add(self.lara)
        p1.change_members.add(self.lara)
        p1.view_groups.add(self.spiel)

        self.ja = Group.objects.create(name="Jugendausschuss")
        self.peter = Member.objects.create(prename="Peter", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=MALE)
        self.anna = Member.objects.create(prename="Anna", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=FEMALE)
        self.lisa = Member.objects.create(prename="Lisa", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=DIVERSE)
        self.peter.group.add(self.ja)
        self.anna.group.add(self.ja)
        self.lisa.group.add(self.ja)

        p2 = PermissionGroup.objects.create(group=self.ja)
        p2.list_groups.add(self.ja)

    def test_may(self):
        self.assertTrue(self.fritz.may_view(self.lara))
        self.assertTrue(self.fritz.may_change(self.lara))
        self.assertTrue(self.fritz.may_view(self.fridolin))
        self.assertFalse(self.fritz.may_change(self.fridolin))

        # every member should be able to list, view and change themselves
        for member in Member.objects.all():
            self.assertTrue(member.may_list(member))
            self.assertTrue(member.may_view(member))
            self.assertTrue(member.may_change(member))

        # every member of Jugendausschuss should be able to view every other member of Jugendausschuss
        for member in self.ja.member_set.all():
            for other in self.ja.member_set.all():
                self.assertTrue(member.may_list(other))
                if member != other:
                    self.assertFalse(member.may_view(other))
                    self.assertFalse(member.may_change(other))

    def test_filter_queryset(self):
        # lise may only list herself
        self.assertEqual(set(self.lise.filter_queryset_by_permissions(model=Member)), set([self.lise]))

        for member in Member.objects.all():
            # passing the empty queryset as starting queryset, should give the empty queryset back
            self.assertEqual(member.filter_queryset_by_permissions(Member.objects.none(), model=Member).count(), 0)
            # passing all objects as start queryset should give the same result as not giving any start queryset
            self.assertEqual(set(member.filter_queryset_by_permissions(Member.objects.all(), model=Member)),
                             set(member.filter_queryset_by_permissions(model=Member)))


    def test_compare_filter_queryset_may_list(self):
        # filter_queryset and filtering manually by may_list should be the same
        for member in Member.objects.all():
            s1 = set(member.filter_queryset_by_permissions(model=Member))
            s2 = set(other for other in Member.objects.all() if member.may_list(other))
            self.assertEqual(s1, s2)


class PDFTestCase(TestCase):
    def setUp(self):
        self.ex = Freizeit.objects.create(name='Wild trip', kilometers_traveled=120,
                                          tour_type=GEMEINSCHAFTS_TOUR,
                                          tour_approach=MUSKELKRAFT_ANREISE,
                                          difficulty=1)
        self.note = MemberNoteList.objects.create(title='Cool list')

        for i in range(7):
            m = Member.objects.create(prename='Lise {}'.format(i),
                                      lastname='Walter',
                                      birth_date=timezone.now().date(),
                                      email=settings.TEST_MAIL, gender=FEMALE)
            NewMemberOnList.objects.create(member=m, comments='a' * i, memberlist=self.ex)
            NewMemberOnList.objects.create(member=m, comments='a' * i, memberlist=self.note)

        User.objects.create_superuser(
            username='superuser', password='secret'
        )
        standard = create_custom_user('standard', ['Standard'], 'Paul', 'Wulter')

    def _test_pdf(self, name, model='freizeit', invalid=False, username='superuser'):
        c = Client()
        c.login(username=username, password='secret')

        pk = self.ex.pk if model == 'freizeit' else self.note.pk
        url = reverse('admin:members_%s_action' % model, args=(pk,))
        response = c.post(url, {name: 'hoho'})
        if not invalid:
            self.assertEqual(response.status_code, 200, 'Response code is not 200.')
            self.assertEqual(response.headers['Content-Type'], 'application/pdf', 'Response content type is not pdf.')
        else:
            self.assertEqual(response.status_code, 302, 'Response code is not 302.')

    def test_crisis_intervention_list(self):
        self._test_pdf('crisis_intervention_list')
        self._test_pdf('crisis_intervention_list', username='standard', invalid=True)

    def test_notes_list(self):
        self._test_pdf('notes_list')
        self._test_pdf('notes_list', username='standard', invalid=True)

    def test_sjr_application(self):
        self._test_pdf('sjr_application')
        self._test_pdf('sjr_application', username='standard', invalid=True)

    # TODO: Since generating a seminar report requires more input now, this test rightly
    # fails. Replace this test with one that fills the POST form and generates a pdf.
    @skip("Currently rightly fails, because expected behaviour changed.")
    def test_seminar_report(self):
        self._test_pdf('seminar_report')
        self._test_pdf('seminar_report', username='standard', invalid=True)

    def test_membernote_summary(self):
        self._test_pdf('summary', model='membernotelist')
        self._test_pdf('summary', model='membernotelist', username='standard', invalid=True)

    def test_wrong_action_freizeit(self):
        return self._test_pdf('asdf', invalid=True)

    def test_wrong_action_membernotelist(self):
        return self._test_pdf('asdf', invalid=True, model='membernotelist')


class AdminTestCase(TestCase):
    def setUp(self, model, admin):
        self.factory = RequestFactory()
        self.model = model
        if model is not None and admin is not None:
            self.admin = admin(model, AdminSite())
        superuser = User.objects.create_superuser(
            username='superuser', password='secret'
        )
        standard = create_custom_user('standard', ['Standard'], 'Paul', 'Wulter')
        trainer = create_custom_user('trainer', ['Standard', 'Trainings'], 'Lise', 'Lotte')
        treasurer = create_custom_user('treasurer', ['Standard', 'Finance'], 'Lara', 'Litte')
        materialwarden = create_custom_user('materialwarden', ['Standard', 'Material'], 'Loro', 'Lutte')

        paul = standard.member

        staff = Group.objects.create(name='Jugendleiter')
        cool_kids = Group.objects.create(name='cool kids')
        super_kids = Group.objects.create(name='super kids')

        p1 = PermissionMember.objects.create(member=paul)
        p1.view_groups.add(cool_kids)
        p1.list_groups.add(super_kids)
        p1.list_groups.add(cool_kids)

        for i in range(3):
            m = Member.objects.create(prename='Fritz {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=MALE)
            m.group.add(cool_kids)
            m.save()
        for i in range(7):
            m = Member.objects.create(prename='Lise {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=FEMALE)
            m.group.add(super_kids)
            m.save()
        for i in range(5):
            m = Member.objects.create(prename='Lulla {}'.format(i), lastname='Hulla', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=DIVERSE)
            m.group.add(staff)
            m.save()
        m = Member.objects.create(prename='Peter', lastname='Hulla', birth_date=timezone.now().date(),
                                  email=settings.TEST_MAIL, gender=MALE)
        m.group.add(staff)
        p1.list_members.add(m)

    def _login(self, name):
        c = Client()
        res = c.login(username=name, password='secret')
        # make sure we logged in
        assert res
        return c


class PermissionTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=None, admin=None)

    def test_standard_permissions(self):
        u = User.objects.get(username='standard')
        self.assertTrue(u.has_perm('members.view_member'))

    def test_queryset_standard(self):
        u = User.objects.get(username='standard')
        queryset = u.member.filter_queryset_by_permissions(model=Member)
        super_kids = Group.objects.get(name='super kids')
        super_kid = super_kids.member_set.first()
        self.assertTrue(super_kid in queryset, 'super kid is not in queryset for Paul.')

    def test_queryset_trainer(self):
        u = User.objects.get(username='trainer')
        queryset = u.member.filter_queryset_by_permissions(model=Member)
        self.assertEqual(set(queryset), {u.member}, 'Filtering trainer queryset yields more the trainer.')


class MemberAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=Member, admin=MemberAdmin)
        cool_kids = Group.objects.get(name='cool kids')
        super_kids = Group.objects.get(name='super kids')
        mega_kids = Group.objects.create(name='mega kids')

        for i in range(1):
            m = Member.objects.create(prename='Peter {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=MALE)
            m.group.add(mega_kids)
            m.save()

    def test_changelist(self):
        c = self._login('superuser')

        url = reverse('admin:members_member_changelist')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

    def test_change(self):
        c = self._login('superuser')

        mega_kids = Group.objects.get(name='mega kids')
        mega_kid = mega_kids.member_set.first()
        url = reverse('admin:members_member_change', args=(mega_kid.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # if member does not exist, expect redirect
        url = reverse('admin:members_member_change', args=(71233,))
        response = c.get(url)
        self.assertEqual(response.status_code, 302, 'Response code is not 302.')

    def test_changelist_standard(self):
        c = self._login('standard')

        url = reverse('admin:members_member_changelist')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        results = response.context['results']
        for result in results:
            name_or_link_field = result[1]
            group_field = result[4]
            self.assertFalse('mega kids' in group_field, 'Standard can list a mega kid.')
            if 'cool kids' in group_field:
                self.assertTrue('href' in name_or_link_field)
            elif 'super kids' in group_field:
                self.assertFalse('href' in name_or_link_field)


    def test_changelist_trainer(self):
        c = self._login('trainer')

        url = reverse('admin:members_member_changelist')
        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # trainers can view everyone, so there should be links in every row
        results = response.context['results']
        for result in results:
            name_or_link_field = result[1]
            group_field = result[4]
            self.assertTrue('href' in name_or_link_field)


    def test_changelist_materialwarden(self):
        u = User.objects.get(username='materialwarden')
        c = self._login('materialwarden')

        url = reverse('admin:members_member_changelist')
        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # materialwarden people can list everyone, but only view themselves by default
        results = response.context['results']
        for result in results:
            name_or_link_field = result[1]
            group_field = result[4]
            self.assertFalse('href' in name_or_link_field and str(u.member.pk) not in name_or_link_field)

        # now set member to None
        m = u.member
        m.user = None
        m.save()

        response = c.get(url)
        # should not redirect
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # since materialwarden has no member associated, no one should be viewable
        results = response.context['results']
        for result in results:
            name_or_link_field = result[1]
            group_field = result[4]
            self.assertFalse('href' in name_or_link_field)


    def test_change_standard(self):
        u = User.objects.get(username='standard')
        self.assertTrue(hasattr(u, 'member'))
        c = self._login('standard')

        cool_kids = Group.objects.get(name='cool kids')
        cool_kid = cool_kids.member_set.first()

        self.assertTrue(u.has_perm('members.view_obj_member', cool_kid))
        self.assertFalse(u.has_perm('members.change_obj_member', cool_kid))
        self.assertFalse(u.has_perm('members.delete_obj_member', cool_kid))
        self.assertTrue(hasattr(u, 'member'))
        url = reverse('admin:members_member_change', args=(cool_kid.pk,))
        response = c.get(url, follow=True)

        super_kids = Group.objects.get(name='super kids')
        super_kid = super_kids.member_set.first()
        url = reverse('admin:members_member_change', args=(super_kid.pk,))
        response = c.get(url, follow=True)
        final = response.redirect_chain[-1][0]
        final_target = reverse('admin:members_member_changelist')
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')
        self.assertEqual(final, final_target, 'Did redirect to wrong url.')


class FreizeitTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.ex = Freizeit.objects.create(name='Wild trip', kilometers_traveled=120,
                                          tour_type=GEMEINSCHAFTS_TOUR,
                                          tour_approach=MUSKELKRAFT_ANREISE,
                                          difficulty=1)

    def _setup_test_ljp_participant_count(self, n_yl, n_correct_age, n_too_old):
        for i in range(n_yl):
            # a 50 years old
            m = Member.objects.create(prename='Peter {}'.format(i),
                                      lastname='Wulter',
                                      birth_date=datetime.datetime.today() - relativedelta(years=50),
                                      email=settings.TEST_MAIL,
                                      gender=FEMALE)
            self.ex.jugendleiter.add(m)
        for i in range(n_correct_age):
            # a 10 years old
            m = Member.objects.create(prename='Lise {}'.format(i),
                                      lastname='Walter',
                                      birth_date=datetime.datetime.today() - relativedelta(years=10),
                                      email=settings.TEST_MAIL,
                                      gender=FEMALE)
            NewMemberOnList.objects.create(member=m, comments='a', memberlist=self.ex)
        for i in range(n_too_old):
            # a 27 years old
            m = Member.objects.create(prename='Lise {}'.format(i),
                                      lastname='Walter',
                                      birth_date=datetime.datetime.today() - relativedelta(years=27),
                                      email=settings.TEST_MAIL,
                                      gender=FEMALE)
            NewMemberOnList.objects.create(member=m, comments='a', memberlist=self.ex)

    def _cleanup_excursion(self):
        # delete all members on excursion for clean up
        NewMemberOnList.objects.all().delete()
        self.ex.jugendleiter.all().delete()

    def _test_theoretic_ljp_participant_count_proportion(self, n_yl, n_correct_age, n_too_old):
        self._setup_test_ljp_participant_count(n_yl, n_correct_age, n_too_old)
        self.assertGreaterEqual(self.ex.theoretic_ljp_participant_count, n_yl,
                                'An excursion with {n_yl} youth leaders and {n_correct_age} participants in the correct age range should have at least {n} participants.'.format(n_yl=n_yl, n_correct_age=n_correct_age, n=n_yl + n_correct_age))
        self.assertLessEqual(self.ex.theoretic_ljp_participant_count, n_yl + n_correct_age + n_too_old,
                             'An excursion with a total number of youth leaders and participants of {n} should have not more than {n} participants'.format(n=n_yl + n_correct_age + n_too_old))

        n_parts_only = self.ex.theoretic_ljp_participant_count - n_yl
        self.assertLessEqual(n_parts_only - n_correct_age, 1/5 * n_parts_only,
                             'An excursion with {n_parts_only} non-youth-leaders, of which {n_correct_age} have the correct age, the number of participants violating the age range must not exceed 20% of the total participants, i.e. {d}'.format(n_parts_only=n_parts_only, n_correct_age=n_correct_age, d=1/5 * n_parts_only))

        self.assertEqual(n_parts_only - n_correct_age, min(math.floor(1/5 * n_parts_only), n_too_old),
                         'An excursion with {n_parts_only} non-youth-leaders, of which {n_correct_age} have the correct age, the number of participants violating the age range must be equal to the minimum of {n_too_old} and the smallest integer less than 20% of the total participants, i.e. {d}'.format(n_parts_only=n_parts_only, n_correct_age=n_correct_age, d=math.floor(1/5 * n_parts_only), n_too_old=n_too_old))

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

class FreizeitAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=Freizeit, admin=FreizeitAdmin)
        ex = Freizeit.objects.create(name='Wild trip', kilometers_traveled=120,
                tour_type=GEMEINSCHAFTS_TOUR,
                tour_approach=MUSKELKRAFT_ANREISE,
                difficulty=1)

        for i in range(7):
            m = Member.objects.create(prename='Lise {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL, gender=FEMALE)
            NewMemberOnList.objects.create(member=m, comments='a' * i, memberlist=ex)

    def test_changelist(self):
        c = self._login('superuser')

        url = reverse('admin:members_freizeit_changelist')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

    def test_change(self):
        c = self._login('superuser')

        ex = Freizeit.objects.get(name='Wild trip')
        url = reverse('admin:members_freizeit_change', args=(ex.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # if excursion does not exist, expect redirect
        url = reverse('admin:members_freizeit_change', args=(71233,))
        response = c.get(url)
        self.assertEqual(response.status_code, 302, 'Response code is not 302.')

    def test_add(self):
        c = self._login('standard')

        url = reverse('admin:members_freizeit_add')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

    @skip("The filtering is currently (intentionally) disabled.")
    def test_add_queryset_filter(self):
        """Test if queryset on `jugendleiter` field is properly filtered by permissions."""
        u = User.objects.get(username='standard')
        c = self._login('standard')

        url = reverse('admin:members_freizeit_add')

        request = self.factory.get(url)
        request.user = u

        field = Freizeit._meta.get_field('jugendleiter')
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        self.assertQuerysetEqual(queryset, u.member.filter_queryset_by_permissions(model=Member),
                                 msg='Field queryset does not match filtered queryset from models.',
                                 ordered=False)

        u.member.user = None
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        self.assertQuerysetEqual(queryset, Member.objects.none())

        c = self._login('materialwarden')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        u = User.objects.get(username='materialwarden')

        request.user = u
        field = Freizeit._meta.get_field('jugendleiter')
        queryset = self.admin.formfield_for_manytomany(field, request).queryset
        # material warden can list everyone
        self.assertQuerysetEqual(queryset, Member.objects.all(),
                                 msg='Field queryset does not match all members.',
                                 ordered=False)

        queryset = self.admin.formfield_for_manytomany(field, None).queryset
        self.assertQuerysetEqual(queryset, Member.objects.none())


class MemberWaitingListAdminTestCase(AdminTestCase):
    def setUp(self):
        super().setUp(model=MemberWaitingList, admin=MemberWaitingListAdmin)
        for i in range(10):
            day = random.randint(1, 28)
            month = random.randint(1, 12)
            year = random.randint(1900, timezone.now().year)
            ex = MemberWaitingList.objects.create(prename='Peter {}'.format(i),
                                                  lastname='Puter',
                                                  birth_date=datetime.date(year, month, day),
                                                  email=settings.TEST_MAIL,
                                                  gender=FEMALE)

    def test_age_eq_birth_date_delta(self):
        u = User.objects.get(username='superuser')
        url = reverse('admin:members_memberwaitinglist_changelist')
        request = self.factory.get(url)
        request.user = u
        queryset = self.admin.get_queryset(request)
        today = timezone.now().date()

        for m in queryset:
            self.assertEqual(m.birth_date_delta, m.age(),
                             msg='Queryset based age calculation differs from python based age calculation for birth date {birth_date} compared to {today}.'.format(birth_date=m.birth_date, today=today))


class MailConfirmationTestCase(BasicMemberTestCase):
    def setUp(self):
        super().setUp()
        self.father = EmergencyContact.objects.create(prename='Olaf', lastname='Old',
                email=settings.TEST_MAIL, member=self.fritz)
        self.father.save()

    def test_contact_confirmation(self):
        # request mail confirmation of father
        requested_confirmation = self.father.request_mail_confirmation()
        self.assertTrue(requested_confirmation,
                        msg='Requesting mail confirmation should return true, if rerequest is false.')
        # father's mail should not be confirmed
        self.assertFalse(self.father.confirmed_mail,
                         msg='Mail should not be confirmed after requesting confirmation.')

        key = self.father.confirm_mail_key
        # key should not be empty
        self.assertFalse(key == "", msg='Mail confirmation key should not be blank after requesting confirmation.')

        # now confirm mail by using the generated key
        res = self.father.confirm_mail(key)

        # father's mail should now be confirmed
        self.assertTrue(self.father.confirmed_mail, msg='After confirming by key, the mail should be confirmed.')

    @skip("Currently, emergency contact email addresses are not required to be confirmed.")
    def test_emergency_contact_confirmation(self):
        # request mail confirmation of fritz, should also ask for confirmation of father
        requested_confirmation = self.fritz.request_mail_confirmation()
        self.assertTrue(requested_confirmation,
                        msg='Requesting mail confirmation should return true, if rerequest is false.')

        for em in self.fritz.emergencycontact_set.all():
            # emergency contact mail should not be confirmed
            self.assertFalse(em.confirmed_mail,
                             msg='Mail should not be confirmed after requesting confirmation.')
            key = em.confirm_mail_key
            self.assertFalse(key == "",
                             msg='Mail confirmation key should not be blank after requesting confirmation.')

            # now confirm mail by using the generated key
            res = confirm_mail_by_key(key)

        for em in self.fritz.emergencycontact_set.all():
            self.assertTrue(em.confirmed_mail,
                            msg='Mail of every emergency contact should be confirmed after manually confirming.')
