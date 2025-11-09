from django.db.models import F, When, IntegerField, Case, Subquery, OuterRef, Count
from datetime import timedelta
from django.utils import timezone
from .constants import *
from .activity import ActivityCategory
from .group import Group
from .member import Member, MemberManager
from .emergency_contact import EmergencyContact
from .member_unconfirmed import MemberUnconfirmedProxy, MemberUnconfirmedManager
from .invitation import InvitationToGroup
from .waiting_list import MemberWaitingList
from .member_on_list import NewMemberOnList
from .excursion import Freizeit
from .member_note_list import MemberNoteList
from .klettertreff import Klettertreff, KlettertreffAttendee
from .registration import RegistrationPassword
from .ljp import LJPProposal, Intervention
from .permission import PermissionMember, PermissionGroup
from .training import TrainingCategory, MemberTraining
from .base import Contact, ContactWithPhoneNumber, Person, gen_key

__all__ = [
    'ActivityCategory',
    'Group',
    'Member', 'MemberManager', 'Contact', 'ContactWithPhoneNumber', 'Person',
    'EmergencyContact', 
    'MemberUnconfirmedProxy', 'MemberUnconfirmedManager',
    'InvitationToGroup',
    'MemberWaitingList',
    'NewMemberOnList',
    'Freizeit',
    'MemberNoteList', 
    'Klettertreff', 'KlettertreffAttendee',
    'RegistrationPassword',
    'LJPProposal', 'Intervention',
    'PermissionMember', 'PermissionGroup',
    'TrainingCategory', 'MemberTraining', 'gen_key',
]


def annotate_activity_score(queryset):
    one_year_ago = timezone.now() - timedelta(days=365)
    queryset = queryset.annotate(
        _jugendleiter_freizeit_score_calc=Subquery(
            Freizeit.objects.filter(jugendleiter=OuterRef('pk'),
                                    date__gte=one_year_ago)
                .values('jugendleiter')
                .annotate(cnt=Count('pk', distinct=True))
                .values('cnt'),
            output_field=IntegerField()
            ),
        # better solution but does not work in production apparently
        #_jugendleiter_freizeit_score=Sum(Case(
        #    When(
        #        freizeit__date__gte=one_year_ago,
        #        then=1),
        #    default=0,
        #    output_field=IntegerField()
        #    ),
        #    distinct=True),
        _jugendleiter_klettertreff_score_calc=Subquery(
            Klettertreff.objects.filter(jugendleiter=OuterRef('pk'),
                                        date__gte=one_year_ago)
                .values('jugendleiter')
                .annotate(cnt=Count('pk', distinct=True))
                .values('cnt'),
            output_field=IntegerField()
            ),
        # better solution but does not work in production apparently
        #_jugendleiter_klettertreff_score=Sum(Case(
        #    When(
        #        klettertreff__date__gte=one_year_ago,
        #        then=1),
        #    default=0,
        #    output_field=IntegerField()
        #    ),
        #    distinct=True),
        _freizeit_score_calc=Subquery(
            Freizeit.objects.filter(membersonlist__member=OuterRef('pk'),
                                    date__gte=one_year_ago)
                .values('membersonlist__member')
                .annotate(cnt=Count('pk', distinct=True))
                .values('cnt'),
            output_field=IntegerField()
            ),
        _klettertreff_score_calc=Subquery(
            KlettertreffAttendee.objects.filter(member=OuterRef('pk'),
                                                klettertreff__date__gte=one_year_ago)
                .values('member')
                .annotate(cnt=Count('pk', distinct=True))
                .values('cnt'),
            output_field=IntegerField()))
    queryset = queryset.annotate(
        _jugendleiter_freizeit_score=Case(
            When(
                _jugendleiter_freizeit_score_calc=None,
                then=0
            ),
            default=F('_jugendleiter_freizeit_score_calc'),
            output_field=IntegerField()),
        _jugendleiter_klettertreff_score=Case(
            When(
                _jugendleiter_klettertreff_score_calc=None,
                then=0
            ),
            default=F('_jugendleiter_klettertreff_score_calc'),
            output_field=IntegerField()),
        _klettertreff_score=Case(
            When(
                _klettertreff_score_calc=None,
                then=0
            ),
            default=F('_klettertreff_score_calc'),
            output_field=IntegerField()),
        _freizeit_score=Case(
            When(
                _freizeit_score_calc=None,
                then=0
            ),
            default=F('_freizeit_score_calc'),
            output_field=IntegerField()))
    queryset = queryset.annotate(
        #_activity_score=F('_jugendleiter_freizeit_score')
        _activity_score=(F('_klettertreff_score') + 3 * F('_freizeit_score')
            + F('_jugendleiter_klettertreff_score') + 3 * F('_jugendleiter_freizeit_score'))
    )
    return queryset

def confirm_mail_by_key(key):
    matching_unconfirmed = MemberUnconfirmedProxy.objects.filter(confirm_mail_key=key) \
                         | MemberUnconfirmedProxy.objects.filter(confirm_alternative_mail_key=key)
    matching_waiter = MemberWaitingList.objects.filter(confirm_mail_key=key)
    matching_emergency_contact = EmergencyContact.objects.filter(confirm_mail_key=key)
    matches = list(matching_unconfirmed) + list(matching_waiter) + list(matching_emergency_contact)
    # if not exactly one match, return None. The case > 1 match should not occur!
    if len(matches) != 1:
        return None
    person = matches[0]
    return person, person.confirm_mail(key)