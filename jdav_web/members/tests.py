from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.utils import timezone, translation
from django.conf import settings
from django.urls import reverse
from .models import Member, Group, PermissionMember, PermissionGroup, Freizeit, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Migrator:
    def __init__(self, connection=connection):
        self.executor = MigrationExecutor(connection)

    def migrate(self, app_label: str, migration: str):
        target = [(app_label, migration)]
        self.executor.loader.build_graph()
        self.executor.migrate(target)
        self.apps = self.executor.loader.project_state(target).apps


class MemberTestCase(TestCase):
    def setUp(self):
        self.jl = Group.objects.create(name="Jugendleiter")
        self.alp = Group.objects.create(name="Alpenfuechse")
        self.spiel = Group.objects.create(name="Spielkinder")

        self.fritz = Member.objects.create(prename="Fritz", lastname="Wulter", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL)
        self.fritz.group.add(self.jl)
        self.fritz.group.add(self.alp)
        self.fritz.save()
        self.lara = Member.objects.create(prename="Lara", lastname="Wallis", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL)
        self.lara.group.add(self.alp)
        self.lara.save()
        self.fridolin = Member.objects.create(prename="Fridolin", lastname="Spargel", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL)
        self.fridolin.group.add(self.alp)
        self.fridolin.group.add(self.spiel)
        self.fridolin.save()

        self.lise = Member.objects.create(prename="Lise", lastname="Lotte", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL)

        p1 = PermissionMember.objects.create(member=self.fritz)
        p1.view_members.add(self.lara)
        p1.change_members.add(self.lara)
        p1.view_groups.add(self.spiel)

        self.ja = Group.objects.create(name="Jugendausschuss")
        self.peter = Member.objects.create(prename="Peter", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL)
        self.anna = Member.objects.create(prename="Anna", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL)
        self.lisa = Member.objects.create(prename="Lisa", lastname="Keks", birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL)
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

        User.objects.create_superuser(
            username='superuser', password='secret'
        )

    def _test_pdf(self, name, invalid=False):
        c = Client()
        c.login(username='superuser', password='secret')

        url = reverse('admin:members_freizeit_action', args=(self.ex.pk,))
        response = c.post(url, {name: 'hoho'})
        if not invalid:
            self.assertEqual(response.status_code, 200, 'Response code is not 200.')
            self.assertEqual(response.headers['Content-Type'], 'application/pdf', 'Response content type is not pdf.')
        else:
            self.assertEqual(response.status_code, 302, 'Response code is not 302.')

    def test_crisis_intervention_list(self):
        return self._test_pdf('crisis_intervention_list')

    def test_notes_list(self):
        return self._test_pdf('notes_list')

    def test_seminar_report(self):
        return self._test_pdf('seminar_report')

    def test_wrong_action(self):
        return self._test_pdf('asdf', invalid=True)


class MemberAdminTestCase(TestCase):
    def setUp(self):
        User.objects.create_superuser(
            username='superuser', password='secret'
        )
        for i in range(100):
            self.m = Member.objects.create(prename='Fritz {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                           email=settings.TEST_MAIL)


    def _login(self, name):
        c = Client()
        c.login(username=name, password='secret')
        return c

    def test_changelist(self):
        c = self._login('superuser')

        url = reverse('admin:members_member_changelist')
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

    def test_change(self):
        c = self._login('superuser')

        url = reverse('admin:members_member_change', args=(self.m.pk,))
        response = c.get(url)
        self.assertEqual(response.status_code, 200, 'Response code is not 200.')

        # if member does not exist, expect redirect
        url = reverse('admin:members_member_change', args=(71233,))
        response = c.get(url)
        self.assertEqual(response.status_code, 302, 'Response code is not 302.')
