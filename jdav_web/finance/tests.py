from unittest import skip
from django.test import TestCase
from django.utils import timezone
from django.conf import settings
from .models import Statement, StatementUnSubmitted, StatementSubmitted, Bill, Ledger, Transaction,\
        StatementUnSubmittedManager, StatementSubmittedManager, StatementConfirmedManager,\
        StatementConfirmed, TransactionIssue, StatementManager
from members.models import Member, Group, Freizeit, GEMEINSCHAFTS_TOUR, MUSKELKRAFT_ANREISE, NewMemberOnList,\
        FAHRGEMEINSCHAFT_ANREISE, MALE, FEMALE, DIVERSE

# Create your tests here.
class StatementTestCase(TestCase):
    night_cost = 27
    kilometers_traveled = 512
    participant_count = 10
    staff_count = 5
    allowance_to_count = 3

    def setUp(self):
        self.jl = Group.objects.create(name="Jugendleiter")
        self.fritz = Member.objects.create(prename="Fritz", lastname="Wulter", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=MALE)
        self.fritz.group.add(self.jl)
        self.fritz.save()

        self.personal_account = Ledger.objects.create(name='personal account')

        self.st = Statement.objects.create(short_description='A statement', explanation='Important!', night_cost=0)
        Bill.objects.create(statement=self.st, short_description='food', explanation='i was hungry',
                            amount=67.3, costs_covered=False, paid_by=self.fritz)
        Transaction.objects.create(reference='gift', amount=12.3,
                                   ledger=self.personal_account, member=self.fritz,
                                   statement=self.st)

        self.st2 = Statement.objects.create(short_description='Actual expenses', night_cost=0)
        Bill.objects.create(statement=self.st2, short_description='food', explanation='i was hungry',
                            amount=67.3, costs_covered=True, paid_by=self.fritz)

        ex = Freizeit.objects.create(name='Wild trip', kilometers_traveled=self.kilometers_traveled,
                                     tour_type=GEMEINSCHAFTS_TOUR,
                                     tour_approach=MUSKELKRAFT_ANREISE,
                                     difficulty=1)
        self.st3 = Statement.objects.create(night_cost=self.night_cost, excursion=ex, subsidy_to=self.fritz)
        for i in range(self.participant_count):
            m = Member.objects.create(prename='Fritz {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                      email=settings.TEST_MAIL, gender=MALE)
            mol = NewMemberOnList.objects.create(member=m, memberlist=ex)
            ex.membersonlist.add(mol)
        for i in range(self.staff_count):
            m = Member.objects.create(prename='Fritz {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                      email=settings.TEST_MAIL, gender=MALE)
            Bill.objects.create(statement=self.st3, short_description='food', explanation='i was hungry',
                                amount=42.69, costs_covered=True, paid_by=m)
            m.group.add(self.jl)
            ex.jugendleiter.add(m)
            if i < self.allowance_to_count:
                self.st3.allowance_to.add(m)

        ex = Freizeit.objects.create(name='Wild trip 2', kilometers_traveled=self.kilometers_traveled,
                                     tour_type=GEMEINSCHAFTS_TOUR,
                                     tour_approach=MUSKELKRAFT_ANREISE,
                                     difficulty=2)
        self.st4 = Statement.objects.create(night_cost=self.night_cost, excursion=ex, subsidy_to=self.fritz)
        for i in range(2):
            m = Member.objects.create(prename='Peter {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                      email=settings.TEST_MAIL, gender=DIVERSE)
            mol = NewMemberOnList.objects.create(member=m, memberlist=ex)
            ex.membersonlist.add(mol)

    def test_staff_count(self):
        self.assertEqual(self.st4.admissible_staff_count, 0,
                         'Admissible staff count is not 0, although not enough participants.')
        for i in range(2):
            m = Member.objects.create(prename='Peter {}'.format(i), lastname='Walter', birth_date=timezone.now().date(),
                                      email=settings.TEST_MAIL, gender=DIVERSE)
            mol = NewMemberOnList.objects.create(member=m, memberlist=self.st4.excursion)
            self.st4.excursion.membersonlist.add(mol)
        self.assertEqual(self.st4.admissible_staff_count, 2,
                         'Admissible staff count is not 2, although there are 4 participants.')

    def test_reduce_transactions(self):
        self.st3.generate_transactions()
        self.assertTrue(self.st3.allowance_to_valid, 'Configured `allowance_to` field is invalid.')
        # every youth leader on `st3` paid one bill, the first three receive the allowance
        # and one receives the subsidies
        self.assertEqual(self.st3.transaction_set.count(), self.st3.real_staff_count + self.staff_count + 1,
                         'Transaction count is not twice the staff count.')
        self.st3.reduce_transactions()
        self.assertEqual(self.st3.transaction_set.count(), self.st3.real_staff_count + self.staff_count + 1,
                         'Transaction count after reduction is not the same as before, although no ledgers are configured.')
        for trans in self.st3.transaction_set.all():
            trans.ledger = self.personal_account
            trans.save()
        self.st3.reduce_transactions()
        # the three yls that receive an allowance should only receive one transaction after reducing,
        # the additional one is the one for the subsidies
        self.assertEqual(self.st3.transaction_set.count(), self.staff_count + 1,
                         'Transaction count after setting ledgers and reduction is incorrect.')
        self.st3.reduce_transactions()
        self.assertEqual(self.st3.transaction_set.count(), self.staff_count + 1,
                         'Transaction count did change after reducing a second time.')

    def test_confirm_statement(self):
        self.assertFalse(self.st3.confirm(confirmer=self.fritz), 'Statement was confirmed, although it is not submitted.')
        self.st3.submit(submitter=self.fritz)
        self.assertTrue(self.st3.submitted, 'Statement is not submitted, although it was.')
        self.assertEqual(self.st3.submitted_by, self.fritz,
                         'Statement was not submitted by fritz.')

        self.assertFalse(self.st3.confirm(), 'Statement was confirmed, but is not valid yet.')
        self.st3.generate_transactions()
        for trans in self.st3.transaction_set.all():
            trans.ledger = self.personal_account
            trans.save()
        self.assertEqual(self.st3.validity, Statement.VALID,
                         'Statement is not valid, although it was setup to be so.')
        self.assertTrue(self.st3.confirm(confirmer=self.fritz),
                        'Statement was not confirmed, although it submitted and valid.')
        self.assertEqual(self.st3.confirmed_by, self.fritz, 'Statement not confirmed by fritz.')
        for trans in self.st3.transaction_set.all():
            self.assertTrue(trans.confirmed, 'Transaction on confirmed statement is not confirmed.')
            self.assertEqual(trans.confirmed_by, self.fritz, 'Transaction on confirmed statement is not confirmed by fritz.')

    def test_excursion_statement(self):
        self.assertEqual(self.st3.excursion.staff_count, self.staff_count,
                         'Calculated staff count is not constructed staff count.')
        self.assertEqual(self.st3.excursion.participant_count, self.participant_count,
                         'Calculated participant count is not constructed participant count.')
        self.assertLess(self.st3.admissible_staff_count, self.staff_count,
                        'All staff members are refinanced, although {} is too much for {} participants.'.format(self.staff_count, self.participant_count))
        self.assertFalse(self.st3.transactions_match_expenses,
                         'Transactions match expenses, but currently no one is paid.')
        self.assertGreater(self.st3.total_staff, 0,
                           'There are no costs for the staff, although there are enough participants.')
        self.assertEqual(self.st3.total_nights, 0,
                         'There are costs for the night, although there was no night.')
        self.assertEqual(self.st3.real_night_cost, settings.MAX_NIGHT_COST,
                         'Real night cost is not the max, although the given one is way too high.')
        # changing means of transport changes euro_per_km
        epkm = self.st3.euro_per_km
        self.st3.excursion.tour_approach = FAHRGEMEINSCHAFT_ANREISE
        self.assertNotEqual(epkm, self.st3.euro_per_km, 'Changing means of transport did not change euro per km.')
        self.st3.generate_transactions()
        self.assertTrue(self.st3.transactions_match_expenses,
                        "Transactions don't match expenses after generating them.")
        self.assertGreater(self.st3.total, 0, 'Total is 0.')

    def test_generate_transactions(self):
        # self.st2 has an unpaid bill
        self.assertFalse(self.st2.transactions_match_expenses,
                         'Transactions match expenses, but one bill is not paid.')
        self.st2.generate_transactions()
        # now transactions should match expenses
        self.assertTrue(self.st2.transactions_match_expenses,
                        "Transactions don't match expenses after generating them.")
        # self.st2 is still not valid
        self.assertEqual(self.st2.validity, Statement.MISSING_LEDGER,
                         'Statement is valid, although transaction has no ledger setup.')
        for trans in self.st2.transaction_set.all():
            trans.ledger = self.personal_account
            trans.save()
        self.assertEqual(self.st2.validity, Statement.VALID,
                         'Statement is still invalid, after setting up ledger.')

        # create a new transaction issue by manually changing amount
        t1 = self.st2.transaction_set.all()[0]
        t1.amount = 123
        t1.save()
        self.assertFalse(self.st2.transactions_match_expenses,
                         'Transactions match expenses, but one transaction was tweaked.')

    def test_generate_transactions_not_covered(self):
        bill = self.st2.bill_set.all()[0]
        bill.paid_by = None
        bill.save()
        self.st2.generate_transactions()
        self.assertTrue(self.st2.transactions_match_expenses)

        bill.amount = 0
        bill.paid_by = self.fritz
        bill.save()
        self.assertTrue(self.st2.transactions_match_expenses)

    def test_statement_without_excursion(self):
        # should be all 0, since no excursion is associated
        self.assertEqual(self.st.real_staff_count, 0)
        self.assertEqual(self.st.admissible_staff_count, 0)
        self.assertEqual(self.st.nights_per_yl, 0)
        self.assertEqual(self.st.allowance_per_yl, 0)
        self.assertEqual(self.st.real_per_yl, 0)
        self.assertEqual(self.st.transportation_per_yl, 0)
        self.assertEqual(self.st.euro_per_km, 0)
        self.assertEqual(self.st.total_allowance, 0)
        self.assertEqual(self.st.total_transportation, 0)

    def test_detect_unallowed_gift(self):
        # there is a bill
        self.assertGreater(self.st.total_bills_theoretic, 0, 'Theoretic bill total is 0 (should be > 0).')
        # but it is not covered
        self.assertEqual(self.st.total_bills, 0, 'Real bill total is not 0.')
        self.assertEqual(self.st.total, 0, 'Total is not 0.')
        self.assertGreater(self.st.total_theoretic, 0, 'Total in theorey is 0.')
        self.st.generate_transactions()
        self.assertEqual(self.st.transaction_set.count(), 1, 'Generating transactions did produce new transactions.')
        # but there is a transaction anyway
        self.assertFalse(self.st.transactions_match_expenses,
                         'Transactions match expenses, although an unreasonable gift is paid.')
        # so statement must be invalid
        self.assertFalse(self.st.is_valid(),
                         'Transaction is valid, although an unreasonable gift is paid.')

    @skip('This fails on main, but will be resolved when #112 is merged.')
    def test_allowance_to_valid(self):
        self.assertEqual(self.st3.excursion.participant_count, self.participant_count)
        # st3 should have 3 admissible yls and all of them should receive allowance
        self.assertEqual(self.st3.admissible_staff_count, self.allowance_to_count)
        self.assertEqual(self.st3.allowances_paid, self.allowance_to_count)
        self.assertTrue(self.st3.allowance_to_valid)

        m1 = self.st3.excursion.jugendleiter.all()[0]
        m2 = self.st3.excursion.jugendleiter.all()[self.allowance_to_count]

        # now remove one, so allowance_to should be reduced by one
        self.st3.allowance_to.remove(m1)
        self.assertEqual(self.st3.allowances_paid, self.allowance_to_count - 1)
        # but still valid
        self.assertTrue(self.st3.allowance_to_valid)
        # and theoretical staff costs are now higher than real staff costs
        self.assertLess(self.st3.total_staff, self.st3.theoretical_total_staff)
        self.assertLess(self.st3.real_per_yl, self.st3.total_per_yl)

        # adding a foreign yl adds the number of allowances_paid
        self.st3.allowance_to.add(self.fritz)
        self.assertEqual(self.st3.allowances_paid, self.allowance_to_count)
        # but invalidates `allowance_to`
        self.assertFalse(self.st3.allowance_to_valid)

        # remove the foreign yl and add too many yls
        self.st3.allowance_to.remove(self.fritz)
        self.st3.allowance_to.add(m1, m2)
        self.assertEqual(self.st3.allowances_paid, self.allowance_to_count + 1)
        # should be invalid
        self.assertFalse(self.st3.allowance_to_valid)

        self.st3.generate_transactions()
        for trans in self.st3.transaction_set.all():
            trans.ledger = self.personal_account
            trans.save()
        self.assertEqual(self.st3.validity, Statement.INVALID_ALLOWANCE_TO)

    def test_total_pretty(self):
        self.assertEqual(self.st3.total_pretty(), "{}€".format(self.st3.total))

    def test_template_context(self):
        # with excursion
        self.assertTrue('euro_per_km' in self.st3.template_context())
        # without excursion
        self.assertFalse('euro_per_km' in self.st2.template_context())

    def test_grouped_bills(self):
        bills = self.st2.grouped_bills()
        self.assertTrue('amount' in bills[0])


class LedgerTestCase(TestCase):
    def setUp(self):
        self.personal_account = Ledger.objects.create(name='personal account')

    def test_str(self):
        self.assertTrue(str(self.personal_account), 'personal account')


class ManagerTestCase(TestCase):
    def setUp(self):
        self.st = Statement.objects.create(short_description='A statement',
                                           explanation='Important!',
                                           night_cost=0)
        self.st_submitted = Statement.objects.create(short_description='A statement',
                                                     explanation='Important!',
                                                     night_cost=0,
                                                     submitted=True)
        self.st_confirmed = Statement.objects.create(short_description='A statement',
                                                     explanation='Important!',
                                                     night_cost=0,
                                                     confirmed=True)

    def test_get_queryset(self):
        # TODO: remove this manager, since it is not used
        mgr = StatementManager()
        mgr.model = Statement
        self.assertQuerysetEqual(mgr.get_queryset(), Statement.objects.filter(pk=self.st.pk))

        mgr_unsubmitted = StatementUnSubmittedManager()
        mgr_unsubmitted.model = StatementUnSubmitted
        self.assertQuerysetEqual(mgr_unsubmitted.get_queryset(), Statement.objects.filter(pk=self.st.pk))

        mgr_submitted = StatementSubmittedManager()
        mgr_submitted.model = StatementSubmitted
        self.assertQuerysetEqual(mgr_submitted.get_queryset(), Statement.objects.filter(pk=self.st_submitted.pk))

        mgr_confirmed = StatementConfirmedManager()
        mgr_confirmed.model = StatementConfirmed
        self.assertQuerysetEqual(mgr_confirmed.get_queryset(), Statement.objects.filter(pk=self.st_confirmed.pk))


class TransactionTestCase(TestCase):
    def setUp(self):
        self.st = Statement.objects.create(short_description='A statement',
                                           explanation='Important!',
                                           night_cost=0)
        self.personal_account = Ledger.objects.create(name='personal account')
        self.fritz = Member.objects.create(prename="Fritz", lastname="Wulter", birth_date=timezone.now().date(),
                              email=settings.TEST_MAIL, gender=MALE)
        self.trans = Transaction.objects.create(reference='foobar',
                                                amount=42,
                                                member=self.fritz,
                                                ledger=self.personal_account,
                                                statement=self.st)

    def test_str(self):
        self.assertTrue(str(self.trans.pk) in str(self.trans))

    def test_escape_reference(self):
        self.assertEqual(Transaction.escape_reference('harmless'), 'harmless')
        self.assertEqual(Transaction.escape_reference('äöüÄÖÜß'), 'aeoeueAeOeUess')
        self.assertEqual(Transaction.escape_reference('ha@r!?mless+09'), 'har?mless+09')

    def test_code(self):
        self.trans.amount = 0
        # amount is zero, so empty
        self.assertEqual(self.trans.code(), '')
        self.trans.amount = 42
        # iban is invalid, so empty
        self.assertEqual(self.trans.code(), '')
        # a valid (random) iban
        self.fritz.iban = 'DE89370400440532013000'
        self.assertNotEqual(self.trans.code(), '')


class BillTestCase(TestCase):
    def setUp(self):
        self.st = Statement.objects.create(short_description='A statement',
                                           explanation='Important!',
                                           night_cost=0)
        self.bill = Bill.objects.create(statement=self.st,
                                        short_description='foobar')

    def test_str(self):
        self.assertTrue('€' in str(self.bill))

    def test_pretty_amount(self):
        self.assertTrue('€' in self.bill.pretty_amount())


class TransactionIssueTestCase(TestCase):
    def setUp(self):
        self.issue = TransactionIssue('foo', 42, 26)

    def test_difference(self):
        self.assertEqual(self.issue.difference, 26 - 42)
