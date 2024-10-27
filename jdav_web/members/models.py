from datetime import datetime, timedelta
import uuid
import pytz
import re
import csv
from django.db import models
from django.db.models import TextField, ManyToManyField, ForeignKey, Count,\
    Sum, Case, Q, F, When, Value, IntegerField, Subquery, OuterRef
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.urls import reverse
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from utils import RestrictedFileField
import os
from mailer.mailutils import send as send_mail, get_mail_confirmation_link,\
    prepend_base_url, get_registration_link, get_wait_confirmation_link
from django.contrib.auth.models import User
from django.conf import settings
from django.core.validators import MinValueValidator

from .rules import may_view, may_change, may_delete, is_own_training, is_oneself, is_leader, is_leader_of_excursion
import rules
from contrib.models import CommonModel
from contrib.rules import memberize_user, has_global_perm

from dateutil.relativedelta import relativedelta

def generate_random_key():
    return uuid.uuid4().hex


GEMEINSCHAFTS_TOUR = MUSKELKRAFT_ANREISE = MALE = 0
FUEHRUNGS_TOUR = OEFFENTLICHE_ANREISE = FEMALE = 1
AUSBILDUNGS_TOUR = FAHRGEMEINSCHAFT_ANREISE = DIVERSE = 2

WEEKDAYS = (
    (0, _('Monday')),
    (1, _('Tuesday')),
    (2, _('Wednesday')),
    (3, _('Thursday')),
    (4, _('Friday')),
    (5, _('Saturday')),
    (6, _('Sunday')),
)


class ActivityCategory(models.Model):
    """
    Describes one kind of activity
    """
    name = models.CharField(max_length=20, verbose_name=_('Name'))
    description = models.TextField(_('Description'))

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = _('Activity')
        verbose_name_plural = _('Activities')


class Group(models.Model):
    """
    Represents one group of the association
    e.g: J1, J2, Jugendleiter, etc.
    """
    name = models.CharField(max_length=50, verbose_name=_('name'))  # e.g: J1
    description = models.TextField(verbose_name=_('description'), default='', blank=True)
    show_website = models.BooleanField(verbose_name=_('show on website'), default=False)
    year_from = models.IntegerField(verbose_name=_('lowest year'), default=2010)
    year_to = models.IntegerField(verbose_name=_('highest year'), default=2011)
    leiters = models.ManyToManyField('members.Member', verbose_name=_('youth leaders'),
                                     related_name='leited_groups', blank=True)
    weekday = models.IntegerField(choices=WEEKDAYS, null=True, blank=True)
    start_time = models.TimeField(verbose_name=_('Starting time'), null=True, blank=True)
    end_time = models.TimeField(verbose_name=_('Ending time'), null=True, blank=True)

    def __str__(self):
        """String representation"""
        return self.name

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')


class MemberManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=True)


class Contact(CommonModel):
    """
    Represents an abstract person with only absolutely necessary contact information.
    """
    prename = models.CharField(max_length=20, verbose_name=_('prename'))
    lastname = models.CharField(max_length=20, verbose_name=_('last name'))

    email = models.EmailField(max_length=100, default="")
    confirmed_mail = models.BooleanField(default=False, verbose_name=_('Email confirmed'))
    confirm_mail_key = models.CharField(max_length=32, default="")

    class Meta(CommonModel.Meta):
        abstract = True

    def __str__(self):
        """String representation"""
        return self.name

    @property
    def name(self):
        """Returning whole name (prename + lastname)"""
        return "{0} {1}".format(self.prename, self.lastname)

    @property
    def email_fields(self):
        """Returns all tuples of emails and confirmation data related to this contact.
        By default, this is only the principal email field, but extending classes can add
        more email fields and then override this method."""
        return [('email', 'confirmed_mail', 'confirm_mail_key')]

    def request_mail_confirmation(self, rerequest=True):
        """Request mail confirmation for every mail field. If `rerequest` is false, then only
        confirmation is requested for currently unconfirmed emails.

        Returns true if any mail confirmation was requested, false otherwise."""
        requested_confirmation = False
        for email_fd, confirmed_email_fd, confirm_mail_key_fd in self.email_fields:
            if getattr(self, confirmed_email_fd) and not rerequest:
                continue
            requested_confirmation = True
            setattr(self, confirmed_email_fd, False)
            confirm_mail_key = uuid.uuid4().hex
            setattr(self, confirm_mail_key_fd, confirm_mail_key)
            send_mail(_('Email confirmation needed'),
                      settings.CONFIRM_MAIL_TEXT.format(name=self.prename,
                                                        link=get_mail_confirmation_link(confirm_mail_key),
                                                        whattoconfirm='deiner Emailadresse'),
                      settings.DEFAULT_SENDING_MAIL,
                      getattr(self, email_fd))
        self.save()
        return requested_confirmation

    def confirm_mail(self, key):
        for email_fd, confirmed_email_fd, confirm_mail_key_fd in self.email_fields:
            if getattr(self, confirm_mail_key_fd) == key:
                setattr(self, confirmed_email_fd, True)
                setattr(self, confirm_mail_key_fd, "")
                self.save()
                return getattr(self, email_fd)
        return None

    def send_mail(self, subject, content):
        send_mail(subject, content, settings.DEFAULT_SENDING_MAIL,
            [getattr(self, email_fd) for email_fd, _, _ in self.email_fields])


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


class ContactWithPhoneNumber(Contact):
    """
    A contact with a phone number.
    """
    phone_number = models.CharField(max_length=100, verbose_name=_('phone number'))

    class Meta(CommonModel.Meta):
        abstract = True


class Person(Contact):
    """
    Represents an abstract person. Not necessarily a member of any group.
    """
    birth_date = models.DateField(_('birth date'), null=True, blank=True)  # to determine the age
    gender_choices = ((MALE, 'Männlich'),
                      (FEMALE, 'Weiblich'),
                      (DIVERSE, 'Divers'))
    gender = models.IntegerField(choices=gender_choices,
                                 default=DIVERSE,
                                 verbose_name=_('Gender'))
    comments = models.TextField(_('comments'), default='', blank=True)

    class Meta(CommonModel.Meta):
        abstract = True

    @property
    def age(self):
        """Age of member"""
        return relativedelta(datetime.today(), self.birth_date).years

    @property
    def birth_date_str(self):
        if self.birth_date is None:
            return "---"
        return self.birth_date.strftime("%d.%m.%Y")


class Member(Person):
    """
    Represents a member of the association
    Might be a member of different groups: e.g. J1, J2, Jugendleiter, etc.
    """
    alternative_email = models.EmailField(max_length=100, default=None, blank=True, null=True)
    confirmed_alternative_mail = models.BooleanField(default=True,
        verbose_name=_('Alternative email confirmed'))
    confirm_alternative_mail_key = models.CharField(max_length=32, default="")

    phone_number = models.CharField(max_length=100, verbose_name=_('phone number'))
    street = models.CharField(max_length=30, verbose_name=_('street and house number'), default='', blank=True)
    plz = models.CharField(max_length=10, verbose_name=_('Postcode'),
                           default='', blank=True)
    town = models.CharField(max_length=30, verbose_name=_('town'), default='', blank=True)
    address_extra = models.CharField(max_length=100, verbose_name=_('Address extra'), default='', blank=True)
    country = models.CharField(max_length=30, verbose_name=_('Country'), default='', blank=True)

    good_conduct_certificate_presentation_needed = models.BooleanField(_('Good conduct certificate presentation needed'), default=False)
    good_conduct_certificate_presented_date = models.DateField(_('Good conduct certificate presented on'), default=None, blank=True, null=True)
    join_date = models.DateField(_('Joined on'), default=None, blank=True, null=True)
    leave_date = models.DateField(_('Left on'), default=None, blank=True, null=True)
    has_key = models.BooleanField(_('Has key'), default=False)
    has_free_ticket_gym = models.BooleanField(_('Has a free ticket for the climbing gym'), default=False)
    dav_badge_no = models.CharField(max_length=20, verbose_name=_('DAV badge number'), default='', blank=True)
    swimming_badge = models.BooleanField(verbose_name=_('Knows how to swim'), default=False)
    climbing_badge = models.CharField(max_length=100, verbose_name=_('Climbing badge'), default='', blank=True)
    alpine_experience = models.TextField(verbose_name=_('Alpine experience'), default='', blank=True)
    allergies = models.CharField(max_length=100, verbose_name=_('Allergies'), default='', blank=True)
    medication = models.CharField(max_length=100, verbose_name=_('Medication'), default='', blank=True)
    tetanus_vaccination = models.CharField(max_length=50, verbose_name=_('Tetanus vaccination'), default='', blank=True)
    photos_may_be_taken = models.BooleanField(verbose_name=_('Photos may be taken'), default=False)
    legal_guardians = models.CharField(max_length=100, verbose_name=_('Legal guardians'), default='', blank=True)

    group = models.ManyToManyField(Group, verbose_name=_('group'))

    iban = models.CharField(max_length=30, blank=True, verbose_name='IBAN')

    gets_newsletter = models.BooleanField(_('receives newsletter'),
                                          default=True)
    unsubscribe_key = models.CharField(max_length=32, default="")
    unsubscribe_expire = models.DateTimeField(default=timezone.now)
    created = models.DateField(auto_now=True, verbose_name=_('created'))
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    registration_form = RestrictedFileField(verbose_name=_('registration form'),
                                            upload_to='registration_forms',
                                            blank=True,
                                            max_upload_size=5242880,
                                            content_types=['application/pdf',
                                                           'image/jpeg',
                                                           'image/png',
                                                           'image/gif'])
    image = RestrictedFileField(verbose_name=_('image'),
                                upload_to='people',
                                blank=True,
                                max_upload_size=5242880,
                                content_types=['image/jpeg',
                                               'image/png',
                                               'image/gif'])
    echo_key = models.CharField(max_length=32, default="")
    echo_expire = models.DateTimeField(default=timezone.now)
    echoed = models.BooleanField(default=True, verbose_name=_('Echoed'))
    confirmed = models.BooleanField(default=True, verbose_name=_('Confirmed'))
    user = models.OneToOneField(User, blank=True, null=True, on_delete=models.SET_NULL)

    objects = MemberManager()

    @property
    def email_fields(self):
        return [('email', 'confirmed_mail', 'confirm_mail_key'),
                ('alternative_email', 'confirmed_alternative_mail', 'confirm_alternative_mail_key')]

    @property
    def place(self):
        """Returning the whole place (plz + town)"""
        return "{0} {1}".format(self.plz, self.town)

    @property
    def address(self):
        """Returning the whole address"""
        if not self.street and not self.town and not self.plz:
            return "---"
        else:
            return "{0}, {1}".format(self.street, self.place)

    def good_conduct_certificate_valid(self):
        """Returns if a good conduct certificate is still valid, depending on the last presentation."""
        if not self.good_conduct_certificate_presented_date:
            return False
        delta = datetime.now().date() - self.good_conduct_certificate_presented_date
        return delta.days // 30 <= settings.MAX_AGE_GOOD_CONDUCT_CERTIFICATE_MONTHS
    good_conduct_certificate_valid.boolean = True
    good_conduct_certificate_valid.short_description = _('Good conduct certificate valid')

    def generate_key(self):
        self.unsubscribe_key = uuid.uuid4().hex
        self.unsubscribe_expire = timezone.now() + timezone.timedelta(days=1)
        self.save()
        return self.unsubscribe_key

    def generate_echo_key(self):
        self.echo_key = uuid.uuid4().hex
        self.echo_expire = timezone.now() + timezone.timedelta(days=30)
        self.echoed = False
        self.save()
        return self.echo_key

    def confirm(self):
        if not self.confirmed_mail or not self.confirmed_alternative_mail:
            return False
        self.confirmed = True
        self.save()
        return True

    def unsubscribe(self, key):
        if self.unsubscribe_key == key and timezone.now() <\
                self.unsubscribe_expire:
            for member in Member.objects.filter(email=self.email):
                member.gets_newsletter = False
                member.save()
            self.unsubscribe_key, self.unsubscribe_expire = "", timezone.now()
            return True
        else:
            return False

    def may_echo(self, key):
        return self.echo_key == key and timezone.now() < self.echo_expire

    @property
    def echo_password(self):
        return self.birth_date.strftime(settings.ECHO_PASSWORD_BIRTHDATE_FORMAT)

    @property
    def contact_phone_number(self):
        """Synonym for phone number field."""
        if self.phone_number:
            return str(self.phone_number)
        else:
            return "---"

    @property
    def contact_email(self):
        """A synonym for the email field."""
        return self.email

    @property
    def association_email(self):
        """Returning the association email of the member"""
        raw = "{0}.{1}@{2}".format(self.prename.lower(), self.lastname.lower(), settings.DOMAIN)
        return raw.replace('ö', 'oe').replace('ä', 'ae').replace('ü', 'ue')

    def registration_complete(self):
        """Check if all necessary fields are set."""
        # TODO: implement a proper predicate here
        return True
    registration_complete.boolean = True
    registration_complete.short_description = _('Registration complete')

    def get_group(self):
        """Returns a string of groups in which the member is."""
        groupstring = ''.join(g.name + ',\n' for g in self.group.all())
        groupstring = groupstring[:-2]
        return groupstring
    get_group.short_description = _('Group')

    class Meta(CommonModel.Meta):
        verbose_name = _('member')
        verbose_name_plural = _('members')
        permissions = (
            ('may_see_qualities', 'Is allowed to see the quality overview'),
            ('may_set_auth_user', 'Is allowed to set auth user member connections.'),
            ('change_member_group', 'Can change the group field'),
        )
        rules_permissions = {
            'members': rules.always_allow,
            'add_obj': has_global_perm('members.add_global_member'),
            'view_obj': may_view | has_global_perm('members.view_global_member'),
            'change_obj': may_change | has_global_perm('members.change_global_member'),
            'delete_obj': may_delete | has_global_perm('members.delete_global_member'),
        }

    def get_skills(self):
        # get skills by summing up all the activities taken part in
        skills = {}
        for kind in ActivityCategory.objects.all():
            lists = Freizeit.objects.filter(activity=kind,
                                            membersonlist__member=self)
            skills[kind.name] = sum([l.difficulty * 3 for l in lists
                                     if l.date < timezone.now()])
        return skills

    def get_activities(self):
        # get activity overview
        return Freizeit.objects.filter(membersonlist__member=self)

    def create_from_registration(self, waiter, group):
        """Given a member, a corresponding waiting-list object and a group, this completes
        the registration and requests email confirmations if necessary.
        Returns if any mail confirmation requests have been sent out."""
        self.group.add(group)
        self.confirmed = False
        if waiter:
            if self.email == waiter.email:
                self.confirmed_mail = waiter.confirmed_mail
                self.confirm_mail_key = waiter.confirm_mail_key
        if self.alternative_email:
            self.confirmed_alternative_mail = False
        self.save()

        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()
        if waiter:
            waiter.delete()
        return self.request_mail_confirmation(rerequest=False)

    def registration_ready(self):
        """Returns if the member is currently unconfirmed and all email addresses
        are confirmed."""
        return not self.confirmed and self.confirmed_alternative_mail and self.confirmed_mail and\
            all([emc.confirmed_mail for emc in self.emergencycontact_set.all()])

    def request_mail_confirmation(self, rerequest=False):
        ret = super().request_mail_confirmation(rerequest)
        rets = [emc.request_mail_confirmation(rerequest) for emc in self.emergencycontact_set.all()]
        return ret or any(rets)

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()
        return ret

    def notify_jugendleiters_about_confirmed_mail(self):
        group = ", ".join([g.name for g in self.group.all()])
        # notify jugendleiters of group of registration
        jls = [jl for group in self.group.all() for jl in group.leiters.all()]
        for jl in jls:
            link = prepend_base_url(reverse('admin:members_memberunconfirmedproxy_change',
                                            args=[str(self.id)]))
            send_mail(_('New unconfirmed registration for group %(group)s') % {'group': group},
                      settings.NEW_UNCONFIRMED_REGISTRATION.format(name=jl.prename,
                                                                   group=group,
                                                                   link=link),
                      settings.DEFAULT_SENDING_MAIL,
                      jl.email)

    def filter_queryset_by_permissions(self, queryset=None, annotate=False, model=None):
        name = model._meta.object_name
        if queryset is None:
            queryset = Member.objects.all()

        if name == "Message":
            return self.filter_messages_by_permissions(queryset, annotate)
        elif name == "Member":
            return self.filter_members_by_permissions(queryset, annotate)
        elif name == "StatementUnSubmitted":
            return self.filter_statements_by_permissions(queryset, annotate)
        elif name == "Freizeit":
            return self.filter_excursions_by_permissions(queryset, annotate)
        elif name == "LJPProposal":
            return queryset
        elif name == "MemberTraining":
            return queryset
        elif name == "NewMemberOnList":
            return queryset
        elif name == "Statement":
            return queryset
        elif name == "BillOnExcursionProxy":
            return queryset
        elif name == "Intervention":
            return queryset
        elif name == "BillOnStatementProxy":
            return queryset
        elif name == "Attachment":
            return queryset
        elif name == "Group":
            return queryset
        elif name == "EmergencyContact":
            return queryset
        else:
            raise ValueError(name)

    def filter_members_by_permissions(self, queryset, annotate=False):
        #mems = Member.objects.all().prefetch_related('group')

        #list_pks = [ m.pk for m in mems if self.may_list(m) ]
        #view_pks = [ m.pk for m in mems if self.may_view(m) ]

        ## every member may list themself
        pks = [self.pk]
        view_pks = [self.pk]


        if hasattr(self, 'permissions'):
            pks += [ m.pk for m in self.permissions.list_members.all() ]
            view_pks += [ m.pk for m in self.permissions.view_members.all() ]

            for group in self.permissions.list_groups.all():
                pks += [ m.pk for m in group.member_set.all() ]

            for group in self.permissions.view_groups.all():
                view_pks += [ m.pk for m in group.member_set.all() ]

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                pks += [ m.pk for m in group.permissions.list_members.all() ]
                view_pks += [ m.pk for m in group.permissions.view_members.all() ]

                for gr in group.permissions.list_groups.all():
                    pks += [ m.pk for m in gr.member_set.all()]

                for gr in group.permissions.view_groups.all():
                    view_pks += [ m.pk for m in gr.member_set.all()]

        filtered = queryset.filter(pk__in=pks)
        if not annotate:
            return filtered

        return filtered.annotate(_viewable=Case(When(pk__in=view_pks, then=Value(True)), default=Value(False), output_field=models.BooleanField()))

    def annotate_view_permission(self, queryset, model):
        name = model._meta.object_name
        if name != 'Member':
            return queryset
        view_pks = [self.pk]

        if hasattr(self, 'permissions'):
            view_pks += [ m.pk for m in self.permissions.view_members.all() ]

            for group in self.permissions.view_groups.all():
                view_pks += [ m.pk for m in group.member_set.all() ]

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                view_pks += [ m.pk for m in group.permissions.view_members.all() ]

                for gr in group.permissions.view_groups.all():
                    view_pks += [ m.pk for m in gr.member_set.all()]

        return queryset.annotate(_viewable=Case(When(pk__in=view_pks, then=Value(True)), default=Value(False), output_field=models.BooleanField()))


    def filter_messages_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        return queryset.filter(created_by=self)

    def filter_statements_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        return queryset.filter(Q(created_by=self) | Q(excursion__jugendleiter=self))

    def filter_excursions_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        groups = self.leited_groups.all()
        # one may view all excursions by leited groups and leited excursions
        queryset = queryset.filter(Q(groups__in=groups) | Q(jugendleiter=self)).distinct()
        return queryset

    def may_list(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, 'permissions'):
            if other in self.permissions.list_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.list_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                if other in group.permissions.list_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.list_groups.all()]):
                    return True

        return False

    def may_view(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, 'permissions'):
            if other in self.permissions.view_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.view_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                if other in group.permissions.view_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.view_groups.all()]):
                    return True

        return False

    def may_change(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, 'permissions'):
            if other in self.permissions.change_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.change_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                if other in group.permissions.change_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.change_groups.all()]):
                    return True

        return False

    def may_delete(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, 'permissions'):
            if other in self.permissions.delete_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.delete_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, 'permissions'):
                if other in group.permissions.delete_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.delete_groups.all()]):
                    return True

        return False


class EmergencyContact(ContactWithPhoneNumber):
    """
    Emergency contact of a member
    """
    member = models.ForeignKey(Member, verbose_name=_('Member'), on_delete=models.CASCADE)

    def __str__(self):
        return str(self.member)

    class Meta(CommonModel.Meta):
        verbose_name = _('Emergency contact')
        verbose_name_plural = _('Emergency contacts')
        rules_permissions = {
            'add_obj': may_change | has_global_perm('members.change_global_member'),
            'view_obj': may_view | has_global_perm('members.view_global_member'),
            'change_obj': may_change | has_global_perm('members.change_global_member'),
            'delete_obj': may_delete | has_global_perm('members.delete_global_member'),
        }


class MemberUnconfirmedManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=False)


class MemberUnconfirmedProxy(Member):
    """Proxy to show unconfirmed members seperately in admin"""
    objects = MemberUnconfirmedManager()

    class Meta:
        proxy = True
        verbose_name = _('Unconfirmed registration')
        verbose_name_plural = _('Unconfirmed registrations')
        permissions = (('may_manage_all_registrations', 'Can view and manage all unconfirmed registrations.'),)

    def __str__(self):
        """String representation"""
        return self.name


class MemberWaitingList(Person):
    """A participant on the waiting list"""

    WAITING_CONFIRMATION_SUCCESS = 0
    WAITING_CONFIRMATION_INVALID = 1
    WAITING_CONFIRMATION_EXPIRED = 1
    WAITING_CONFIRMED = 2

    application_text = models.TextField(_('Do you want to tell us something else?'), default='', blank=True)
    application_date = models.DateTimeField(verbose_name=_('application date'), auto_now=True)

    last_wait_confirmation = models.DateField(auto_now=True, verbose_name=_('Last wait confirmation'))
    wait_confirmation_key = models.CharField(max_length=32, default="")
    wait_confirmation_key_expire = models.DateTimeField(default=timezone.now)

    registration_key = models.CharField(max_length=32, default="")
    registration_expire = models.DateTimeField(default=timezone.now)

    invited_for_group = models.ForeignKey(Group,
                                          null=True,
                                          blank=True,
                                          default=None,
                                          verbose_name=_('Invited for group'),
                                          on_delete=models.SET_NULL)
    class Meta(CommonModel.Meta):
        verbose_name = _('Waiter')
        verbose_name_plural = _('Waiters')
        permissions = (('may_manage_waiting_list', 'Can view and manage the waiting list.'),)
        rules_permissions = {
            'add_obj': has_global_perm('members.add_global_memberwaitinglist'),
            'view_obj': has_global_perm('members.view_global_memberwaitinglist'),
            'change_obj': has_global_perm('members.change_global_memberwaitinglist'),
            'delete_obj': has_global_perm('members.delete_global_memberwaitinglist'),
        }

    @property
    def waiting_confirmation_needed(self):
        """Returns if person should be asked to confirm waiting status."""
        return wait_confirmation_key is None \
            and last_wait_confirmation < timezone.now() - timezone.timedelta(days=90)

    def waiting_confirmed(self):
        """Returns if the persons waiting status is considered to be confirmed."""
        cutoff = timezone.now() \
            - timezone.timedelta(days=  settings.GRACE_PERIOD_WAITING_CONFIRMATION \
                                      + settings.WAITING_CONFIRMATION_FREQUENCY)
        return self.last_wait_confirmation > cutoff.date()
    waiting_confirmed.admin_order_field = 'last_wait_confirmation'
    waiting_confirmed.boolean = True
    waiting_confirmed.short_description = _('Waiting status confirmed')

    def ask_for_wait_confirmation(self):
        """Sends an email to the person asking them to confirm their intention to wait."""
        self.send_mail(_('Waiting confirmation needed'),
                       settings.WAIT_CONFIRMATION_TEXT.format(name=self.prename,
                                                              link=get_wait_confirmation_link(self)))

    def confirm_waiting(self, key):
        # if a wrong key is supplied, we return invalid
        if not self.wait_confirmation_key == key:
            return self.WAITING_CONFIRMATION_INVALID

        # if the current wait confirmation key is not expired, return sucess
        if timezone.now() < self.wait_confirmation_key_expire:
            self.last_wait_confirmation = timezone.now()
            self.wait_confirmation_key_expire = timezone.now()
            self.save()
            return self.WAITING_CONFIRMATION_SUCCESS

        # if the waiting is already confirmed, return success
        # this might happen if both parents and member mail are used for communication
        if self.waiting_confirmed():
            return self.WAITING_CONFIRMED

        # otherwise the link is too old and the person was not confirmed in time
        return self.WAITING_CONFIRMATION_EXPIRED

    def generate_wait_confirmation_key(self):
        self.wait_confirmation_key = uuid.uuid4().hex
        self.wait_confirmation_key_expire = timezone.now() \
            + timezone.timedelta(days=settings.GRACE_PERIOD_WAITING_CONFIRMATION)
        self.save()
        return self.wait_confirmation_key

    def generate_registration_key(self):
        self.registration_key = uuid.uuid4().hex
        self.registration_expire = timezone.now() + timezone.timedelta(days=30)
        self.save()
        return self.registration_key

    def may_register(self, key):
        return self.registration_key == key and timezone.now() < self.registration_expire

    def invite_to_group(self, group):
        if group.show_website:
            group_link = '({url}) '.format(url=prepend_base_url(reverse('startpage:gruppe_detail', args=[group.name])))
        else:
            group_link = ''
        # TODO: inform the user that the group has no configured weekday, start_time or end_time
        weekday = WEEKDAYS[group.weekday][1] if group.weekday != None else WEEKDAYS[0][1]
        start_time = group.start_time.strftime('%H:%M') if group.start_time != None else "14:00"
        end_time = group.end_time.strftime('%H:%M') if group.end_time != None else "16:00"
        self.send_mail(_("Invitation to trial group meeting"),
            settings.INVITE_TEXT.format(name=self.prename,
            weekday=weekday,
            start_time=start_time,
            end_time=end_time,
            group_name=group.name,
            group_link=group_link,
            link=get_registration_link(self)))


class NewMemberOnList(CommonModel):
    """
    Connects members to a list of members.
    """
    member = models.ForeignKey(Member, verbose_name=_('Member'), on_delete=models.CASCADE)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE,
                                     default=ContentType('members', 'Freizeit').pk)
    object_id = models.PositiveIntegerField()
    memberlist = GenericForeignKey('content_type', 'object_id')
    comments = models.TextField(_('Comment'), default='', blank=True)

    def __str__(self):
        return str(self.member)

    class Meta(CommonModel.Meta):
        verbose_name = _('Member')
        verbose_name_plural = _('Members')
        rules_permissions = {
            'add_obj': is_leader,
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader,
            'delete_obj': is_leader,
        }

    @property
    def comments_tex(self):
        raw = ". ".join(c for c in (self.member.comments, self.comments) if c).replace("..", ".")
        if not raw:
            return "---"
        else:
            return raw

    @property
    def skills(self):
        activities = [a.name for a in memberlist.activity.all()]
        return {k: v for k, v in self.member.get_skills().items() if k in activities}

    @property
    def qualities_tex(self):
        qualities = []
        for activity, value in self.skills:
            qualities.append("\\textit{%s:} %s" % (activity, value))
        return ", ".join(qualities)


class Freizeit(CommonModel):
    """Lets the user create a 'Freizeit' and generate a members overview in pdf format. """

    name = models.CharField(verbose_name=_('Activity'), default='',
                            max_length=50)
    place = models.CharField(verbose_name=_('Place'), default='', max_length=50)
    destination = models.CharField(verbose_name=_('Destination (optional)'),
                                   default='', max_length=50, blank=True)
    date = models.DateTimeField(default=timezone.now, verbose_name=_('Begin'))
    end = models.DateTimeField(verbose_name=_('End (optional)'), default=timezone.now)
    # comment = models.TextField(_('Comments'), default='', blank=True)
    groups = models.ManyToManyField(Group, verbose_name=_('Groups'))
    jugendleiter = models.ManyToManyField(Member)
    tour_type_choices = ((GEMEINSCHAFTS_TOUR, 'Gemeinschaftstour'),
                         (FUEHRUNGS_TOUR, 'Führungstour'),
                         (AUSBILDUNGS_TOUR, 'Ausbildung'))
    # verbose_name is overriden by form, label is set in admin.py
    tour_type = models.IntegerField(choices=tour_type_choices)
    tour_approach_choices = ((MUSKELKRAFT_ANREISE, 'Muskelkraft'),
                             (OEFFENTLICHE_ANREISE, 'ÖPNV'),
                             (FAHRGEMEINSCHAFT_ANREISE, 'Fahrgemeinschaften'))
    tour_approach = models.IntegerField(choices=tour_approach_choices,
                                        default=MUSKELKRAFT_ANREISE,
                                        verbose_name=_('Means of transportation'))
    kilometers_traveled = models.IntegerField(verbose_name=_('Kilometers traveled'),
                                              validators=[MinValueValidator(0)])
    activity = models.ManyToManyField(ActivityCategory, default=None,
                                      verbose_name=_('Categories'))
    difficulty_choices = [(1, _('easy')), (2, _('medium')), (3, _('hard'))]
    # verbose_name is overriden by form, label is set in admin.py
    difficulty = models.IntegerField(choices=difficulty_choices)
    membersonlist = GenericRelation(NewMemberOnList)

    def __str__(self):
        """String represenation"""
        return self.name

    class Meta(CommonModel.Meta):
        verbose_name = "Freizeit"
        verbose_name_plural = "Freizeiten"
        rules_permissions = {
            'add_obj': has_global_perm('members.add_global_freizeit'),
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader | has_global_perm('members.change_global_freizeit'),
            'delete_obj': is_leader | has_global_perm('members.delete_global_freizeit'),
        }

    def get_tour_type(self):
        if self.tour_type == FUEHRUNGS_TOUR:
            return "Führungstour"
        elif self.tour_type == AUSBILDUNGS_TOUR:
            return "Ausbildung"
        else:
            return "Gemeinschaftstour"

    def get_tour_approach(self):
        if self.tour_approach == MUSKELKRAFT_ANREISE:
            return "Muskelkraft"
        elif self.tour_approach == OEFFENTLICHE_ANREISE:
            return "ÖPNV"
        else:
            return "Fahrgemeinschaften"

    def get_absolute_url(self):
        return reverse('admin:members_freizeit_change', args=[str(self.id)])

    @property
    def night_count(self):
        # convert to date first, since we might start at 11pm and end at 1am, which is one night
        return (self.end.date() - self.date.date()).days

    @property
    def duration(self):
        # number of nights is number of full days + 1
        full_days = self.night_count - 1
        extra_days = 0

        if self.date.hour <= 12:
            extra_days += 1.0
        else:
            extra_days += 0.5

        if self.end.hour >= 12:
            extra_days += 1.0
        else:
            extra_days += 0.5

        return full_days + extra_days

    @property
    def staff_count(self):
        return self.jugendleiter.count()

    @property
    def participant_count(self):
        ps = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        return len(ps - jls)

    @property
    def time_period_str(self):
        time_period = self.date.strftime('%d.%m.%Y')
        if self.end != self.date:
            time_period += " - " + self.end.strftime('%d.%m.%Y')
        return time_period

    @property
    def groups_str(self):
        return ', '.join(g.name for g in self.groups.all())

    @property
    def staff_str(self):
        return ', '.join(yl.name for yl in self.jugendleiter.all())

    @property
    def skill_summary(self):
        activities = [a.name for a in self.activity.all()]
        skills = {a: [] for a in activities}
        people = []
        for memberonlist in self.membersonlist.all():
            m = memberonlist.member
            qualities = []
            for activity, value in m.get_skills().items():
                if activity not in activities:
                    continue
                skills[activity].append(value)
                qualities.append("\\textit{%s:} %s" % (activity, value))
            people.append(dict(name=m.name, qualities=", ".join(qualities), comments=memberonlist.comments_tex))

        sks = []
        for activity in activities:
            skill_avg = 0 if len(skills[activity]) == 0 else\
                sum(skills[activity]) / len(skills[activity])
            skill_min = 0 if len(skills[activity]) == 0 else\
                min(skills[activity])
            skill_max = 0 if len(skills[activity]) == 0 else\
                max(skills[activity])
            sks.append(dict(name=activity, skill_avg=skill_avg, skill_min=skill_min, skill_max=skill_max))
        return (people, sks)

    def sjr_application_fields(self):
        members = set(map(lambda x: x.member, self.membersonlist.distinct()))
        total = len(members)
        total_b27_local = len([m for m in members
                               if m.age <= 27 and settings.SEKTION in m.town])
        total_b27_non_local = len([m for m in members
                                   if m.age <= 27 and not settings.SEKTION in m.town])
        jls = self.jugendleiter.distinct()
        title = self.ljpproposal.title if hasattr(self, 'ljpproposal') else self.name
        base = {'Haushaltsjahr': str(datetime.now().year),
                'Art / Thema / Titel': title,
                'Ort': self.place,
                'Datum von': self.date.strftime('%d.%m.%Y'),
                'Datum bis': self.end.strftime('%d.%m.%Y'),
                'Dauer': str(self.duration).replace('.', ','),
                'Teilnehmenden gesamt': str(total),
                'bis 27 aus HD': str(total_b27_local),
                'bis 27 nicht aus HD': str(total_b27_non_local),
                'Verpflegungstage': str(self.duration * self.participant_count).replace('.', ','),
                'Betreuer/in': str(len(jls)),
                'Ort, Datum': '{p}, {d}'.format(p=settings.SEKTION, d=datetime.now().strftime('%d.%m.%Y'))}
        print(members)
        for i, m in enumerate(members):
            suffix = str(' {}'.format(i + 1))
            # indexing starts at zero, but the listing in the pdf starts at 1
            if i + 1 == 1:
                suffix = ''
            elif i + 1 == 12:
                suffix = '12'
            base['Vor- und Nachname' + suffix] = m.name
            base['Anschrift' + suffix] = m.address
            base['Alter' + suffix] = str(m.age)
            base['Status' + suffix] = str(2)
        return base

    @staticmethod
    def filter_queryset_by_permissions(member, queryset=None):
        if queryset is None:
            queryset = Freizeit.objects.all()

        groups = member.leited_groups.all()
        # one may view all leited groups and oneself
        queryset = queryset.filter(Q(groups__in=groups) | Q(jugendleiter__pk=member.pk)).distinct()
        return queryset


class MemberNoteList(models.Model):
    """
    A member list with a title and a bunch of members to take some notes.
    """
    title = models.CharField(verbose_name=_('Title'), default='', max_length=50)
    date = models.DateField(default=datetime.today, verbose_name=_('Date'), null=True, blank=True)
    membersonlist = GenericRelation(NewMemberOnList)

    def __str__(self):
        """String represenation"""
        return self.title

    class Meta:
        verbose_name = "Notizliste"
        verbose_name_plural = "Notizlisten"


class Klettertreff(models.Model):
    """ This model represents a Klettertreff event.

    A Klettertreff can take a date, location, Jugendleiter, attending members
    as input.
    """
    date = models.DateField(_('Date'), default=datetime.today)
    location = models.CharField(_('Location'), default='', max_length=60)
    topic = models.CharField(_('Topic'), default='', max_length=60)
    jugendleiter = models.ManyToManyField(Member)
    group = models.ForeignKey(Group, default='', verbose_name=_('Group'), on_delete=models.CASCADE)

    def __str__(self):
        return self.location + ' ' + self.date.strftime('%d.%m.%Y')

    def get_jugendleiter(self):
        jl_string = ', '.join(j.name for j in self.jugendleiter.all())
        return jl_string

    def has_attendee(self, member):
        queryset = KlettertreffAttendee.objects.filter(
                member__id__contains=member.id,
                klettertreff__id__contains=self.id)
        if queryset:
            return True
        return False

    def has_jugendleiter(self, jugendleiter):
        if jugendleiter in self.jugendleiter.all():
            return True
        return False

    get_jugendleiter.short_description = _('Jugendleiter')

    class Meta:
        verbose_name = _('Klettertreff')
        verbose_name_plural = _('Klettertreffs')


class KlettertreffAttendee(models.Model):
    """Connects members to Klettertreffs."""
    member = models.ForeignKey(Member, verbose_name=_('Member'), on_delete=models.CASCADE)
    klettertreff = models.ForeignKey(Klettertreff, on_delete=models.CASCADE)

    def __str__(self):
        return str(self.member)

    class Meta:
        verbose_name = _('Member')
        verbose_name_plural = _('Members')


class RegistrationPassword(models.Model):
    group = models.ForeignKey(Group, on_delete=models.CASCADE)
    password = models.CharField(_('Password'), default='', max_length=20, unique=True)

    class Meta:
        verbose_name = _('registration password')
        verbose_name_plural = _('registration passwords')


class LJPProposal(CommonModel):
    """A proposal for LJP"""
    title = models.CharField(verbose_name=_('Title'), max_length=30)

    goals_alpinistic = models.TextField(verbose_name=_('Alpinistic goals'))
    goals_pedagogic = models.TextField(verbose_name=_('Pedagogic goals'))
    methods = models.TextField(verbose_name=_('Content and methods'))
    evaluation = models.TextField(verbose_name=_('Evaluation'))
    experiences = models.TextField(verbose_name=_('Experiences and possible improvements'))

    excursion = models.OneToOneField(Freizeit,
                                     verbose_name=_('Excursion'),
                                     blank=True,
                                     null=True,
                                     on_delete=models.SET_NULL)

    class Meta(CommonModel.Meta):
        verbose_name = _('LJP Proposal')
        verbose_name_plural = _('LJP Proposals')
        rules_permissions = {
            'add_obj': is_leader,
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader,
            'delete_obj': is_leader,
        }

    def __str__(self):
        return self.title

class Intervention(CommonModel):
    """An intervention during a seminar as part of a LJP proposal"""
    date_start = models.DateTimeField(verbose_name=_('Starting time'))
    duration = models.DecimalField(verbose_name=_('Duration in hours'),
                                   max_digits=4,
                                   decimal_places=2)
    activity = models.TextField(verbose_name=_('Activity and method'))

    ljp_proposal = models.ForeignKey(LJPProposal,
                                     verbose_name=_('LJP Proposal'),
                                     blank=False,
                                     on_delete=models.CASCADE)

    class Meta:
        verbose_name = _('Intervention')
        verbose_name_plural = _('Interventions')
        rules_permissions = {
            'add_obj': is_leader_of_excursion,
            'view_obj': is_leader_of_excursion | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader_of_excursion,
            'delete_obj': is_leader_of_excursion,
        }


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


class PermissionMember(models.Model):
    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name='permissions')
    # every member of view_members may view this member
    list_members = models.ManyToManyField(Member, related_name='listable_by', blank=True,
                                          verbose_name=_('May list members'))
    view_members = models.ManyToManyField(Member, related_name='viewable_by', blank=True,
                                          verbose_name=_('May view members'))
    change_members = models.ManyToManyField(Member, related_name='changeable_by', blank=True,
                                            verbose_name=_('May change members'))
    delete_members = models.ManyToManyField(Member, related_name='deletable_by', blank=True,
                                            verbose_name=_('May delete members'))

    # every member in any view_group may view this member
    list_groups = models.ManyToManyField(Group, related_name='listable_by', blank=True,
                                         verbose_name=_('May list members of groups'))
    view_groups = models.ManyToManyField(Group, related_name='viewable_by', blank=True,
                                         verbose_name=_('May view members of groups'))
    change_groups = models.ManyToManyField(Group, related_name='changeable_by', blank=True,
                                           verbose_name=_('May change members of groups'))
    delete_groups = models.ManyToManyField(Group, related_name='deletable_by', blank=True,
                                           verbose_name=_('May delete members of groups'))

    class Meta:
        verbose_name = _('Permissions')
        verbose_name_plural = _('Permissions')

    def __str__(self):
        return str(_('Permissions'))


class PermissionGroup(models.Model):
    group = models.OneToOneField(Group, on_delete=models.CASCADE, related_name='permissions')
    # every member of view_members may view all members of group
    list_members = models.ManyToManyField(Member, related_name='group_members_listable_by', blank=True,
                                          verbose_name=_('May list members'))
    view_members = models.ManyToManyField(Member, related_name='group_members_viewable_by', blank=True,
                                          verbose_name=_('May view members'))
    change_members = models.ManyToManyField(Member, related_name='group_members_changeable_by_group', blank=True,
                                            verbose_name=_('May change members'))
    delete_members = models.ManyToManyField(Member, related_name='group_members_deletable_by', blank=True,
                                            verbose_name=_('May delete members'))

    # every member in any view_group may view all members of group
    list_groups = models.ManyToManyField(Group, related_name='group_members_listable_by', blank=True,
                                         verbose_name=_('May list members of groups'))
    view_groups = models.ManyToManyField(Group, related_name='group_members_viewable_by', blank=True,
                                         verbose_name=_('May view members of groups'))
    change_groups = models.ManyToManyField(Group, related_name='group_members_changeable_by', blank=True,
                                           verbose_name=_('May change members of groups'))
    delete_groups = models.ManyToManyField(Group, related_name='group_members_deletable_by', blank=True,
                                           verbose_name=_('May delete members of groups'))

    class Meta:
        verbose_name = _('Group permissions')
        verbose_name_plural = _('Group permissions')

    def __str__(self):
        return str(_('Group permissions'))


class TrainingCategory(models.Model):
    """Represents a type of training, e.g. Grundausbildung, Fortbildung, Aufbaumodul, etc."""
    name = models.CharField(verbose_name=_('Name'), max_length=50)
    permission_needed = models.BooleanField(verbose_name=_('Permission needed'))

    class Meta:
        verbose_name = _('Training category')
        verbose_name_plural = _('Training categories')

    def __str__(self):
        return self.name


class MemberTraining(CommonModel):
    """Represents a training planned or attended by a member."""
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name='traininigs')
    title = models.CharField(verbose_name=_('Title'), max_length=30)
    date = models.DateField(verbose_name=_('Date'), null=True, blank=True)
    category = models.ForeignKey(TrainingCategory, on_delete=models.PROTECT, verbose_name=_('Category'))
    comments = models.TextField(verbose_name=_('Comments'), blank=True)
    participated = models.BooleanField(verbose_name=_('Participated'))
    passed = models.BooleanField(verbose_name=_('Passed'))

    class Meta(CommonModel.Meta):
        verbose_name = _('Training')
        verbose_name_plural = _('Trainings')
        rules_permissions = {
            # sine this is used in an inline, the member and not the training is passed
            'add_obj': is_oneself | has_global_perm('members.add_global_membertraining'),
            'view_obj': is_oneself | has_global_perm('members.view_global_membertraining'),
            'change_obj': is_oneself | has_global_perm('members.change_global_membertraining'),
            'delete_obj': is_oneself | has_global_perm('members.delete_global_membertraining'),
        }



def import_from_csv(path):
    with open(path, encoding='ISO-8859-1') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        rows = list(reader)

    def transform_field(key, value):
        new_key = CLUBDESK_TO_KOMPASS[key]
        if isinstance(new_key, str):
            return (new_key, value)
        else:
            return (new_key[0], new_key[1](value))

    def transform_row(row):
        kwargs = dict([ transform_field(k, v) for k, v in row.items() if k in CLUBDESK_TO_KOMPASS ])
        kwargs_filtered = { k : v for k, v in kwargs.items() if k not in  ['group', 'last_training', 'has_fundamental_training', 'special_training'] }
        mem = Member(**kwargs_filtered)
        mem.save()
        mem.group.set(kwargs['group'])

        if kwargs['has_fundamental_training']:
            try:
                ga_cat = TrainingCategory.objects.get(name='Grundausbildung')
            except TrainingCategory.DoesNotExist:
                ga_cat = TrainingCategory(name='Grundausbildung', permission_needed=True)
                ga_cat.save()
            ga_training = MemberTraining(member=mem, title='Grundausbildung', date=None, category=ga_cat,
                                         participated=True, passed=True)
            ga_training.save()

        if kwargs['last_training'] is not None:
            try:
                cat = TrainingCategory.objects.get(name='Fortbildung')
            except TrainingCategory.DoesNotExist:
                cat = TrainingCategory(name='Fortbildung', permission_needed=False)
                cat.save()
            training = MemberTraining(member=mem, title='Unbekannt', date=kwargs['last_training'], category=cat,
                                      participated=True, passed=True)
            training.save()

        if kwargs['special_training'] != '':
            try:
                cat = TrainingCategory.objects.get(name='Sonstiges')
            except TrainingCategory.DoesNotExist:
                cat = TrainingCategory(name='Sonstiges', permission_needed=False)
                cat.save()
            training = MemberTraining(member=mem, title=kwargs['special_training'], date=None, category=cat,
                                      participated=True, passed=True)
            training.save()

    for row in rows:
        transform_row(row)


def parse_group(value):
    groups_raw = re.split(',', value)

    # need to determine if member is youth leader
    roles = set()
    def extract_group_name_and_role(raw):
        obj = re.search('^(.*?)(?: \((.*)\))?$', raw)
        if obj.group(2) is not None:
            roles.add(obj.group(2).strip())
        return obj.group(1).strip()

    group_names = [extract_group_name_and_role(raw) for raw in groups_raw if raw != '']

    if "Jugendleiter" in roles:
        group_names.append("Jugendleiter")
    groups = []
    for group_name in group_names:
        try:
            group = Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            group = Group(name=group_name)
            group.save()
        groups.append(group)
    return groups


def parse_date(value):
    if value == '':
        return None
    return datetime.strptime(value, '%d.%m.%Y').date()


def parse_datetime(value):
    tz = pytz.timezone('Europe/Berlin')
    if value == '':
        return None
    return tz.localize(datetime.strptime(value, '%d.%m.%Y %H:%M:%S'))


def parse_status(value):
    return value != "Passivmitglied"


def parse_boolean(value):
    return value.lower() == "ja"


CLUBDESK_TO_KOMPASS = {
    'Nachname': 'lastname',
    'Vorname': 'prename',
    'Adresse': 'street',
    'PLZ': 'plz',
    'Ort': 'town',
    'Telefon Privat': 'phone_number_private',
    'Telefon Mobil': 'phone_number_mobile',
    'Adress-Zusatz': 'address_extra',
    'Land': 'country',
    'Nationalität': 'nationality',
    'E-Mail': 'email',
    'E-Mail Alternativ': 'alternative_email',
    'Status': ('active', parse_status),
    'Eintritt': ('join_date', parse_date),
    'Austritt': ('leave_date', parse_date),
    'Geburtsdatum': ('birth_date', parse_date),
    'Geburtstag': ('birth_date', parse_date),
    'Bemerkungen': 'comments',
    'IBAN': 'iban',
    'Vorlage Führungszeugnis': ('good_conduct_certificate_presented_date', parse_date),
    'Vorlage Führungszeugnis notwendig': ('good_conduct_certificate_presentation_needed', parse_boolean),
    'Letzte Fortbildung': ('last_training', parse_date),
    'Grundausbildung': ('has_fundamental_training', parse_boolean),
    'Besondere Ausbildung': 'special_training',
    '[Gruppen]' : ('group', parse_group),
    'Schlüssel': ('has_key', parse_boolean),
    'Freikarte': ('has_free_ticket_gym', parse_boolean),
    'DAV Ausweis Nr.': 'dav_badge_no',
    'Schwimmabzeichen': 'swimming_badge',
    'Kletterschein': 'climbing_badge',
    'Felserfahrung': 'alpine_experience',
    'Allergien': 'allergies',
    'Medikamente': 'medication',
    'Tetanusimpfung': 'tetanus_vaccination',
    'Fotoerlaubnis': ('photos_may_be_taken', parse_boolean),
    'Erziehungsberechtigte': 'legal_guardians',
    'Mobil Eltern': 'phone_number_parents',
    'Sonstiges': 'application_text',
    'Erhalten am': ('application_date', parse_datetime),
}


def import_from_csv_waitinglist(path):
    with open(path, encoding='ISO-8859-1') as csvfile:
        reader = csv.DictReader(csvfile, delimiter=';')
        rows = list(reader)

    def transform_field(key, value):
        new_key = CLUBDESK_TO_KOMPASS[key]
        if isinstance(new_key, str):
            return (new_key, value)
        else:
            return (new_key[0], new_key[1](value))

    def transform_field(key, value):
        new_key = CLUBDESK_TO_KOMPASS[key]
        if isinstance(new_key, str):
            return (new_key, value)
        else:
            return (new_key[0], new_key[1](value))

    def transform_row(row):
        kwargs = dict([ transform_field(k, v) for k, v in row.items() if k in CLUBDESK_TO_KOMPASS ])
        kwargs_filtered = { k : v for k, v in kwargs.items() if k in ['prename', 'lastname', 'email', 'birth_date', 'application_text', 'application_date'] }
        mem = MemberWaitingList(**kwargs_filtered)
        mem.save()

    for row in rows:
        transform_row(row)
