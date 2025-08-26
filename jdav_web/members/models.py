from datetime import datetime, timedelta, date
import uuid
import math
import pytz
import unicodedata
import re
from django.db import models
from django.db.models import TextField, ManyToManyField, ForeignKey, Count,\
    Sum, Case, Q, F, When, Value, IntegerField, Subquery, OuterRef
from django.db.models.functions import Cast
from django.utils.translation import gettext_lazy as _
from django.utils import timezone
from django.utils.html import format_html
from django.urls import reverse
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from utils import RestrictedFileField, normalize_name
import os
from mailer.mailutils import send as send_mail, get_mail_confirmation_link,\
    prepend_base_url, get_registration_link, get_wait_confirmation_link,\
    get_invitation_reject_link, get_invite_as_user_key, get_leave_waitinglist_link,\
    get_invitation_confirm_link
from django.contrib.auth.models import User
from django.conf import settings
from django.core.validators import MinValueValidator

from .rules import may_view, may_change, may_delete, is_own_training, is_oneself, is_leader, is_leader_of_excursion
from .pdf import render_tex
import rules
from contrib.models import CommonModel
from contrib.media import media_path
from contrib.rules import memberize_user, has_global_perm
from utils import cvt_to_decimal, coming_midnight

from dateutil.relativedelta import relativedelta
from schwifty import IBAN


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
    LJP_CATEGORIES = [('Winter', _('winter')),
                      ('Skibergsteigen', _('ski mountaineering')),
                      ('Klettern', _('climbing')),
                      ('Bergsteigen', _('mountaineering')),
                      ('Theorie', _('theory')),
                      ('Sonstiges', _('others'))]
    name = models.CharField(max_length=20, verbose_name=_('Name'))
    ljp_category = models.CharField(choices=LJP_CATEGORIES,
                                    verbose_name=_('LJP category'),
                                    max_length=20,
                                    help_text=_('The official category for LJP applications associated with this activity.'))
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
    weekday = models.IntegerField(verbose_name=_('week day'), choices=WEEKDAYS, null=True, blank=True)
    start_time = models.TimeField(verbose_name=_('Starting time'), null=True, blank=True)
    end_time = models.TimeField(verbose_name=_('Ending time'), null=True, blank=True)
    contact_email = models.ForeignKey('mailer.EmailAddress',
                                      verbose_name=_('Contact email'),
                                      null=True,
                                      blank=True,
                                      on_delete=models.SET_NULL)

    def __str__(self):
        """String representation"""
        return self.name

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')
        
    @property
    def sorted_members(self):
        """Returns the members of this group sorted by their last name."""
        return self.member_set.all().order_by('lastname')

    def has_time_info(self):
        # return if the group has all relevant time slot information filled
        return self.weekday and self.start_time and self.end_time

    def get_time_info(self):
        if self.has_time_info():
            return settings.GROUP_TIME_AVAILABLE_TEXT.format(weekday=WEEKDAYS[self.weekday][1],
                                                             start_time=self.start_time.strftime('%H:%M'),
                                                             end_time=self.end_time.strftime('%H:%M'))
        else:
            return ""
    
    def has_age_info(self):
        return self.year_from and self.year_to
    
    def get_age_info(self):
        if self.has_age_info():
            return _("years %(from)s to %(to)s") % {'from':self.year_from, 'to':self.year_to}
        else:
            return ""

    def get_invitation_text_template(self):
        """The text template used to invite waiters to this group. This contains
        placeholders for the name of the waiter and personalized links."""
        if self.show_website:
            group_link = '({url}) '.format(url=prepend_base_url(reverse('startpage:gruppe_detail', args=[self.name])))
        else:
            group_link = ''
        if self.has_time_info():
            group_time = self.get_time_info()
        else:
            group_time = settings.GROUP_TIME_UNAVAILABLE_TEXT.format(contact_email=self.contact_email)
        if self.has_age_info():
            group_age = self.get_age_info()
        else:
            group_age = _("no information available")

        return settings.INVITE_TEXT.format(group_time=group_time,
                                           group_name=self.name,
                                           group_age=group_age,
                                           group_link=group_link,
                                           contact_email=self.contact_email)


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

    def phone_number_tel_link(self):
        """Returns the phone number as tel link."""
        return format_html('<a href="tel:{tel}">{tel}</a>'.format(tel=self.phone_number))
    phone_number_tel_link.short_description = _('phone number')
    phone_number_tel_link.admin_order_field = 'phone_number'

    def email_mailto_link(self):
        """Returns the emails as a mailto link."""
        return format_html('<a href="mailto:{email}">{email}</a>'.format(email=self.email))
    email_mailto_link.short_description = 'Email'
    email_mailto_link.admin_order_field = 'email'

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
            if not getattr(self, email_fd): # pragma: no cover
                # Only reachable with misconfigured `email_fields`
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

    def send_mail(self, subject, content, cc=None):
        send_mail(subject, content, settings.DEFAULT_SENDING_MAIL,
            [getattr(self, email_fd) for email_fd, _, _ in self.email_fields], cc=cc)


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
                                 verbose_name=_('Gender'))
    comments = models.TextField(_('comments'), default='', blank=True)

    class Meta(CommonModel.Meta):
        abstract = True

    def age(self):
        """Age of member"""
        return relativedelta(datetime.today(), self.birth_date).years
    age.admin_order_field = 'birth_date'
    age.short_description = _('age')

    def age_at(self, date: date):
        """Age of member at a given date"""
        return relativedelta(date.replace(tzinfo=None), self.birth_date).years

    @property
    def birth_date_str(self):
        if self.birth_date is None:
            return "---"
        return self.birth_date.strftime("%d.%m.%Y")

    @property
    def gender_str(self):
        return self.gender_choices[self.gender][1]


class Member(Person):
    """
    Represents a member of the association
    Might be a member of different groups: e.g. J1, J2, Jugendleiter, etc.
    """
    alternative_email = models.EmailField(max_length=100, default=None, blank=True, null=True)
    confirmed_alternative_mail = models.BooleanField(default=True,
        verbose_name=_('Alternative email confirmed'))
    confirm_alternative_mail_key = models.CharField(max_length=32, default="")

    phone_number = models.CharField(max_length=100, verbose_name=_('phone number'), default='', blank=True)
    street = models.CharField(max_length=30, verbose_name=_('street and house number'), default='', blank=True)
    plz = models.CharField(max_length=10, verbose_name=_('Postcode'),
                           default='', blank=True)
    town = models.CharField(max_length=30, verbose_name=_('town'), default='', blank=True)
    address_extra = models.CharField(max_length=100, verbose_name=_('Address extra'), default='', blank=True)
    country = models.CharField(max_length=30, verbose_name=_('Country'), default='', blank=True)

    good_conduct_certificate_presented_date = models.DateField(_('Good conduct certificate presented on'), default=None, blank=True, null=True)
    join_date = models.DateField(_('Joined on'), default=None, blank=True, null=True)
    leave_date = models.DateField(_('Left on'), default=None, blank=True, null=True)
    has_key = models.BooleanField(_('Has key'), default=False)
    has_free_ticket_gym = models.BooleanField(_('Has a free ticket for the climbing gym'), default=False)
    dav_badge_no = models.CharField(max_length=20, verbose_name=_('DAV badge number'), default='', blank=True)
    
    # use this to store a climbing gym customer or membership id, used to print on meeting checklists
    ticket_no = models.CharField(max_length=20, verbose_name=_('entrance ticket number'), default='', blank=True)   
    swimming_badge = models.BooleanField(verbose_name=_('Knows how to swim'), default=False)
    climbing_badge = models.CharField(max_length=100, verbose_name=_('Climbing badge'), default='', blank=True)
    alpine_experience = models.TextField(verbose_name=_('Alpine experience'), default='', blank=True)
    allergies = models.TextField(verbose_name=_('Allergies'), default='', blank=True)
    medication = models.TextField(verbose_name=_('Medication'), default='', blank=True)
    tetanus_vaccination = models.CharField(max_length=50, verbose_name=_('Tetanus vaccination'), default='', blank=True)
    photos_may_be_taken = models.BooleanField(verbose_name=_('Photos may be taken'), default=False)
    legal_guardians = models.CharField(max_length=100, verbose_name=_('Legal guardians'), default='', blank=True)
    may_cancel_appointment_independently =\
        models.BooleanField(verbose_name=_('May cancel a group appointment independently'), null=True,
                            blank=True, default=None)

    group = models.ManyToManyField(Group, verbose_name=_('group'))

    iban = models.CharField(max_length=30, blank=True, verbose_name='IBAN')

    gets_newsletter = models.BooleanField(_('receives newsletter'),
                                          default=True)
    unsubscribe_key = models.CharField(max_length=32, default="")
    unsubscribe_expire = models.DateTimeField(default=timezone.now)
    created = models.DateField(default=timezone.now, verbose_name=_('created'))
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    registration_form = RestrictedFileField(verbose_name=_('registration form'),
                                            upload_to='registration_forms',
                                            blank=True,
                                            max_upload_size=5,
                                            content_types=['application/pdf',
                                                           'image/jpeg',
                                                           'image/png',
                                                           'image/gif'])
    upload_registration_form_key = models.CharField(max_length=32, default="")
    image = RestrictedFileField(verbose_name=_('image'),
                                upload_to='people',
                                blank=True,
                                max_upload_size=5,
                                content_types=['image/jpeg',
                                               'image/png',
                                               'image/gif'])
    echo_key = models.CharField(max_length=32, default="")
    echo_expire = models.DateTimeField(default=timezone.now)
    echoed = models.BooleanField(default=True, verbose_name=_('Echoed'))
    confirmed = models.BooleanField(default=True, verbose_name=_('Confirmed'))
    user = models.OneToOneField(User, blank=True, null=True, on_delete=models.SET_NULL,
                                verbose_name=_('Login data'))
    invite_as_user_key = models.CharField(max_length=32, default="")
    waitinglist_application_date = models.DateTimeField(verbose_name=_('waitinglist application date'),
                                                        null=True, blank=True,
                                                        help_text=_('If the person registered from the waitinglist, this is their application date.'))

    objects = MemberManager()
    all_objects = models.Manager()

    @property
    def email_fields(self):
        return [('email', 'confirmed_mail', 'confirm_mail_key'),
                ('alternative_email', 'confirmed_alternative_mail', 'confirm_alternative_mail_key')]

    @property
    def place(self):
        """Returning the whole place (plz + town)"""
        return "{0} {1}".format(self.plz, self.town)
    
    @property
    def ticket_tag(self):
        """Returning the ticket number stripped of strings and spaces"""
        return "{" + ''.join(re.findall(r'\d', self.ticket_no)) + "}"

    @property
    def iban_valid(self):
        return IBAN(self.iban, allow_invalid=True).is_valid
    
    @property
    def address(self):
        """Returning the whole address"""
        if not self.street and not self.town and not self.plz:
            return "---"
        else:
            return "{0}, {1}".format(self.street, self.place)
        
    @property
    def address_multiline(self):
        """Returning the whole address with a linebreak between street and town"""
        if not self.street and not self.town and not self.plz:
            return "---"
        else:
            return "{0},\\linebreak[1] {1}".format(self.street, self.place)

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
        self.echo_expire = timezone.now() + timezone.timedelta(days=settings.ECHO_GRACE_PERIOD)
        self.echoed = False
        self.save()
        return self.echo_key

    def confirm(self):
        if not self.confirmed_mail or not self.confirmed_alternative_mail:
            return False
        self.confirmed = True
        self.save()
        return True

    def unconfirm(self):
        self.confirmed = False
        self.save()

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
    def username(self):
        """Return the username. Either this the name of the linked user, or
        it is the suggested username."""
        if not self.user:
            return self.suggested_username()
        else:
            return self.user.username

    @property
    def association_email(self):
        """Returning the association email of the member"""
        return "{username}@{domain}".format(username=self.username, domain=settings.DOMAIN)

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
            ('may_change_member_group', 'Can change the group field'),
            ('may_invite_as_user', 'Is allowed to invite a member to set login data.'),
            ('may_change_organizationals', 'Is allowed to set organizational settings on members.'),
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

    def generate_upload_registration_form_key(self):
        self.upload_registration_form_key = uuid.uuid4().hex
        self.save()

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
            # store waitinglist application date in member, this will be used
            # if the member is later demoted to waiter again
            self.waitinglist_application_date = waiter.application_date
        if self.alternative_email:
            self.confirmed_alternative_mail = False
        self.upload_registration_form_key = uuid.uuid4().hex
        self.save()

        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()
        if waiter:
            waiter.delete()
        return self.request_mail_confirmation(rerequest=False)

    def registration_ready(self):
        """Returns if the member is currently unconfirmed and all email addresses
        are confirmed."""
        return not self.confirmed and self.confirmed_alternative_mail and self.confirmed_mail\
                and self.registration_form

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()
        return ret

    def validate_registration_form(self):
        self.upload_registration_form_key = ''
        self.save()
        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()

    def get_upload_registration_form_link(self):
        return prepend_base_url(reverse('members:upload_registration_form') + "?key="\
            + self.upload_registration_form_key)

    def send_upload_registration_form_link(self):
        if not self.upload_registration_form_key:
            return
        print(self.name, self.upload_registration_form_key)
        link = self.get_upload_registration_form_link()
        self.send_mail(_('Upload registration form'),
                       settings.UPLOAD_REGISTRATION_FORM_TEXT.format(name=self.prename,
                                                                     link=link))

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

    def filter_queryset_by_permissions(self, queryset=None, annotate=False, model=None): # pragma: no cover
        """
        Filter the given queryset of objects of type `model` by the permissions of `self`.
        For example, only returns `Message`s created by `self`.

        This method is used by the `FilteredMemberFieldMixin` to filter the selection
        in `ForeignKey` and `ManyToMany` fields.
        """
        # This method is not used by all models listed below, so covering all cases in tests
        # is hard and not useful. It is therefore exempt from testing.
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
        elif name == "MemberUnconfirmedProxy":
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

    def suggested_username(self):
        """Returns a suggested username given by {prename}.{lastname}."""
        raw = "{0}.{1}".format(self.prename.lower(), self.lastname.lower())
        return normalize_name(raw)

    def has_internal_email(self):
        """Returns if the configured e-mail address is a DAV360 email address."""
        match = re.match('(^[^@]*)@(.*)$', self.email)
        if not match:
            return False
        return match.group(2) in settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER or\
            "*" in settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER

    def invite_as_user(self):
        """Invites the member to join Kompass as a user."""
        if not self.has_internal_email():
            # dont invite if the email address is not an internal one
            return False
        if self.user:
            # don't reinvite if there is already userdata attached
            return False
        self.invite_as_user_key = uuid.uuid4().hex
        self.save()
        self.send_mail(_('Set login data for Kompass'),
                       settings.INVITE_AS_USER_TEXT.format(name=self.prename,
                                                           link=get_invite_as_user_key(self.invite_as_user_key)))
        return True

    def led_groups(self):
        """Returns a queryset of groups that this member is a youth leader of."""
        return Group.objects.filter(leiters__pk=self.pk)

    def led_freizeiten(self, limit=5):
        """Returns a queryset of freizeiten that this member is a youth leader of."""
        return Freizeit.objects.filter(jugendleiter__pk=self.pk)[:limit]

    def demote_to_waiter(self):
        """Demote this member to a waiter by creating a waiter from the data and removing
        this member."""
        waiter = MemberWaitingList(prename=self.prename,
                                   lastname=self.lastname,
                                   email=self.email,
                                   birth_date=self.birth_date,
                                   gender=self.gender,
                                   comments=self.comments,
                                   confirmed_mail=self.confirmed_mail,
                                   confirm_mail_key=self.confirm_mail_key)
        # if this member was created from the waitinglist, keep the original application date
        if self.waitinglist_application_date:
            waiter.application_date = self.waitinglist_application_date
        waiter.save()
        self.delete()


class EmergencyContact(ContactWithPhoneNumber):
    """
    Emergency contact of a member
    """
    member = models.ForeignKey(Member, verbose_name=_('Member'), on_delete=models.CASCADE)
    email = models.EmailField(max_length=100, default='', blank=True)

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
        rules_permissions = {
            'view_obj': may_view | has_global_perm('members.may_manage_all_registrations'),
            'change_obj': may_change | has_global_perm('members.may_manage_all_registrations'),
            'delete_obj': may_delete | has_global_perm('members.may_manage_all_registrations'),
        }

    def __str__(self):
        """String representation"""
        return self.name


def gen_key():
    return uuid.uuid4().hex


class InvitationToGroup(models.Model):
    """An invitation of a waiter to a group."""
    waiter = models.ForeignKey('MemberWaitingList', verbose_name=_('Waiter'), on_delete=models.CASCADE)
    group = models.ForeignKey(Group, verbose_name=_('Group'), on_delete=models.CASCADE)
    date = models.DateField(default=timezone.now, verbose_name=_('Invitation date'))
    rejected = models.BooleanField(verbose_name=_('Invitation rejected'), default=False)
    key = models.CharField(max_length=32, default=gen_key)
    created_by = models.ForeignKey(Member, verbose_name=_('Created by'),
                                   blank=True,
                                   null=True,
                                   on_delete=models.SET_NULL,
                                   related_name='created_group_invitations')

    class Meta:
        verbose_name = _('Invitation to group')
        verbose_name_plural = _('Invitations to groups')

    def is_expired(self):
        return self.date < (timezone.now() - timezone.timedelta(days=30)).date()

    def status(self):
        if self.rejected:
            return _('Rejected')
        elif self.is_expired():
            return _('Expired')
        else:
            return _('Undecided')
    status.short_description = _('Status')

    def send_left_waitinglist_notification_to(self, recipient):
        send_mail(_('%(waiter)s left the waiting list') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_LEFT_WAITINGLIST.format(name=recipient.prename,
                                                                    waiter=self.waiter,
                                                                    group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_reject_notification_to(self, recipient):
        send_mail(_('Group invitation rejected by %(waiter)s') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_REJECTED.format(name=recipient.prename,
                                                            waiter=self.waiter,
                                                            group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_confirm_notification_to(self, recipient):
        send_mail(_('Group invitation confirmed by %(waiter)s') % {'waiter': self.waiter},
                  settings.GROUP_INVITATION_CONFIRMED_TEXT.format(name=recipient.prename,
                                                                  waiter=self.waiter,
                                                                  group=self.group),
                  settings.DEFAULT_SENDING_MAIL,
                  recipient.email)

    def send_confirm_confirmation(self):
        self.waiter.send_mail(_('Trial group meeting confirmed'),
                              settings.TRIAL_GROUP_MEETING_CONFIRMED_TEXT.format(name=self.waiter.prename,
                                                                                 group=self.group,
                                                                                 contact_email=self.group.contact_email,
                                                                                 timeinfo=self.group.get_time_info()))

    def notify_left_waitinglist(self):
        """
        Inform youth leaders of the group and the inviter that the waiter left the waitinglist,
        prompted by this group invitation.
        """
        if self.created_by:
            self.send_left_waitinglist_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_left_waitinglist_notification_to(jl)

    def reject(self):
        """Reject this invitation. Informs the youth leaders of the group of the rejection."""
        self.rejected = True
        self.save()
        # send notifications
        if self.created_by:
            self.send_reject_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_reject_notification_to(jl)

    def confirm(self):
        """Confirm this invitation. Informs the youth leaders of the group of the invitation."""
        self.rejected = False
        self.save()
        # confirm the confirmation
        self.send_confirm_confirmation()
        # send notifications
        if self.created_by:
            self.send_confirm_notification_to(self.created_by)
        for jl in self.group.leiters.all():
            self.send_confirm_notification_to(jl)


class MemberWaitingList(Person):
    """A participant on the waiting list"""

    WAITING_CONFIRMATION_SUCCESS = 0
    WAITING_CONFIRMATION_INVALID = 1
    WAITING_CONFIRMATION_EXPIRED = 1
    WAITING_CONFIRMED = 2

    application_text = models.TextField(_('Do you want to tell us something else?'), default='', blank=True)
    application_date = models.DateTimeField(verbose_name=_('application date'), default=timezone.now)

    last_wait_confirmation = models.DateField(default=timezone.now, verbose_name=_('Last wait confirmation'))
    wait_confirmation_key = models.CharField(max_length=32, default="")
    wait_confirmation_key_expire = models.DateTimeField(default=timezone.now)

    leave_key = models.CharField(max_length=32, default="")

    last_reminder = models.DateTimeField(default=timezone.now, verbose_name=_('Last reminder'))
    sent_reminders = models.IntegerField(default=0, verbose_name=_('Missed reminders'))

    registration_key = models.CharField(max_length=32, default="")
    registration_expire = models.DateTimeField(default=timezone.now)

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

    def latest_group_invitation(self):
        gi = self.invitationtogroup_set.order_by('-pk').first()
        if gi:
            return "{group}: {status}".format(group=gi.group.name, status=gi.status())
        else:
            return "-"
    latest_group_invitation.short_description = _('Latest group invitation')

    @property
    def waiting_confirmation_needed(self):
        """Returns if person should be asked to confirm waiting status."""
        return not self.wait_confirmation_key \
            and self.last_wait_confirmation < timezone.now() -\
                timezone.timedelta(days=settings.WAITING_CONFIRMATION_FREQUENCY)

    def waiting_confirmed(self):
        """Returns if the persons waiting status is considered to be confirmed."""
        if self.sent_reminders > 0:
            # there was sent at least one wait confirmation request
            if timezone.now() < self.wait_confirmation_key_expire:
                # the request has not expired yet
                return None
            else:
                # we sent a request that has expired
                return False
        else:
            # if there exist no pending or expired reminders, the waiter remains confirmed
            return True
    waiting_confirmed.admin_order_field = 'last_wait_confirmation'
    waiting_confirmed.boolean = True
    waiting_confirmed.short_description = _('Waiting status confirmed')

    def ask_for_wait_confirmation(self):
        """Sends an email to the person asking them to confirm their intention to wait."""
        self.last_reminder = timezone.now()
        self.sent_reminders += 1
        self.leave_key = gen_key()
        self.save()
        self.send_mail(_('Waiting confirmation needed'),
                       settings.WAIT_CONFIRMATION_TEXT.format(name=self.prename,
                                                              link=get_wait_confirmation_link(self),
                                                              leave_link=get_leave_waitinglist_link(self.leave_key),
                                                              reminder=self.sent_reminders,
                                                              max_reminder_count=settings.MAX_REMINDER_COUNT))

    def confirm_waiting(self, key):
        # if a wrong key is supplied, we return invalid
        if not self.wait_confirmation_key == key:
            return self.WAITING_CONFIRMATION_INVALID

        # if the current wait confirmation key is not expired, return sucess
        if timezone.now() < self.wait_confirmation_key_expire:
            self.last_wait_confirmation = timezone.now()
            self.wait_confirmation_key_expire = timezone.now()
            self.sent_reminders = 0
            self.leave_key = ''
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

    def may_register(self, key):
        try:
            invitation = InvitationToGroup.objects.get(key=key)
            return self.pk == invitation.waiter.pk and timezone.now().date() < invitation.date + timezone.timedelta(days=30)
        except InvitationToGroup.DoesNotExist:
            return False

    def invite_to_group(self, group, text_template=None, creator=None):
        """
        Invite waiter to given group. Stores a new group invitation
        and sends a personalized e-mail based on the passed template.
        """
        self.invited_for_group = group
        self.save()
        if not text_template:
            text_template = group.get_invitation_text_template()
        invitation = InvitationToGroup(group=group, waiter=self, created_by=creator)
        invitation.save()
        self.send_mail(_("Invitation to trial group meeting"),
            text_template.format(name=self.prename,
                                 link=get_registration_link(invitation.key),
                                 invitation_reject_link=get_invitation_reject_link(invitation.key),
                                 invitation_confirm_link=get_invitation_confirm_link(invitation.key)),
            cc=group.contact_email.email)

    def unregister(self):
        """Delete the waiter and inform them about the deletion via email."""
        self.send_mail(_("Unregistered from waiting list"),
                       settings.LEAVE_WAITINGLIST_TEXT.format(name=self.prename))
        self.delete()

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if ret:
            self.send_mail(_("Successfully registered for the waitinglist"),
                           settings.JOIN_WAITINGLIST_CONFIRMATION_TEXT.format(name=self.prename))
        return ret


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
        activities = [a.name for a in self.memberlist.activity.all()]
        return {k: v for k, v in self.member.get_skills().items() if k in activities}

    @property
    def qualities_tex(self):
        qualities = []
        for activity, value in self.skills.items():
            qualities.append("\\textit{%s:} %s" % (activity, value))
        return ", ".join(qualities)


class Freizeit(CommonModel):
    """Lets the user create a 'Freizeit' and generate a members overview in pdf format. """

    name = models.CharField(verbose_name=_('Activity'), default='',
                            max_length=50)
    place = models.CharField(verbose_name=_('Place'), default='', max_length=50)
    postcode = models.CharField(verbose_name=_('Postcode'), default='', max_length=30)
    destination = models.CharField(verbose_name=_('Destination (optional)'),
                                   default='', max_length=50, blank=True,
                                   help_text=_('e.g. a peak'))
    date = models.DateTimeField(default=timezone.now, verbose_name=_('Begin'))
    end = models.DateTimeField(verbose_name=_('End (optional)'), default=timezone.now)
    description = models.TextField(verbose_name=_('Description'), blank=True, default='')
    # comment = models.TextField(_('Comments'), default='', blank=True)
    groups = models.ManyToManyField(Group, verbose_name=_('Groups'))
    jugendleiter = models.ManyToManyField(Member)
    approved_extra_youth_leader_count = models.PositiveIntegerField(verbose_name=_('Number of additional approved youth leaders'),
                                                                    default=0,
                                                                    help_text=_('The number of approved youth leaders per excursion is determined by the number of participants. In special circumstances, e.g. in case of a technically demanding excursion, more youth leaders may be approved.'))
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

    # approval: None means no decision taken, False means rejected
    approved = models.BooleanField(verbose_name=_('Approved'),
                                   null=True,
                                   default=None,
                                   help_text=_('Choose no in case of rejection or yes in case of approval. Leave empty, if not yet decided.'))
    approval_comments = models.TextField(verbose_name=_('Approval comments'),
                                         blank=True, default='')

    # automatic sending of crisis intervention list
    crisis_intervention_list_sent = models.BooleanField(default=False)
    notification_crisis_intervention_list_sent = models.BooleanField(default=False)

    def __str__(self):
        """String represenation"""
        return self.name

    class Meta(CommonModel.Meta):
        verbose_name = _('Excursion')
        verbose_name_plural = _('Excursions')
        permissions = (
            ('manage_approval_excursion', 'Can edit the approval status of excursions.'),
            ('view_approval_excursion', 'Can view the approval status of excursions.'),
        )
        rules_permissions = {
            'add_obj': has_global_perm('members.add_global_freizeit'),
            'view_obj': is_leader | has_global_perm('members.view_global_freizeit'),
            'change_obj': is_leader | has_global_perm('members.change_global_freizeit'),
            'delete_obj': is_leader | has_global_perm('members.delete_global_freizeit'),
        }

    @property
    def code(self):
        return f"B{self.date:%y}-{self.pk}"

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
    def total_intervention_hours(self):
        if hasattr(self, 'ljpproposal'):
            return sum([i.duration for i in self.ljpproposal.intervention_set.all()])
        else:
            return 0

    @property
    def total_seminar_days(self):
        """calculate seminar days based on intervention hours in every day"""
        # TODO: add tests for this
        if hasattr(self, 'ljpproposal'):
            hours_per_day = self.seminar_time_per_day
            # Calculate the total number of seminar days
            # Each day is counted as 1 if total_duration is >= 5 hours, as 0.5 if total_duration is >= 2.5
            # otherwise 0
            sum_days = sum([h['sum_days'] for h in hours_per_day])

            return sum_days
        else:
            return 0


    @property
    def seminar_time_per_day(self):
        if hasattr(self, 'ljpproposal'):
            return (
                self.ljpproposal.intervention_set
                .annotate(day=Cast('date_start', output_field=models.DateField()))  # Force it to date
                .values('day')  # Group by day
                .annotate(total_duration=Sum('duration'))# Sum durations for each day
                .annotate(
                    sum_days=Case(
                        When(total_duration__gte=5.0, then=Value(1.0)),
                        When(total_duration__gte=2.5, then=Value(0.5)),
                        default=Value(0.0),)
                )
                .order_by('day')  # Sort results by date
            )
        else:
            return []

    @property
    def ljp_duration(self):
        """calculate the duration in days for the LJP"""
        return min(self.duration, self.total_seminar_days)

    @property
    def staff_count(self):
        return self.jugendleiter.count()

    @property
    def staff_on_memberlist(self):
        ps = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        return ps.intersection(jls)

    @property
    def staff_on_memberlist_count(self):
        return len(self.staff_on_memberlist)

    @property
    def participant_count(self):
        return len(self.participants)

    @property
    def participants(self):
        ps = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        return list(ps - jls)

    @property
    def old_participant_count(self):
        old_ps = [m for m in self.participants if m.age() >= 27]
        return len(old_ps)

    @property
    def head_count(self):
        return self.staff_on_memberlist_count + self.participant_count

    @property
    def approved_staff_count(self):
        """Number of approved youth leaders for this excursion. The base number is calculated
        from the participant count. To this, the number of additional approved youth leaders is added."""
        participant_count = self.participant_count
        if participant_count < 4:
            base_count = 0
        elif 4 <= participant_count <= 7:
            base_count = 2
        else:
            base_count = 2 + math.ceil((participant_count - 7) / 7)
        return base_count + self.approved_extra_youth_leader_count

    @property
    def theoretic_ljp_participant_count(self):
        """
        Calculate the participant count in the sense of the LJP regulations. This means
        that all youth leaders are counted and all participants which are at least 6 years old and
        strictly less than 27 years old. Additionally, up to 20% of the participants may violate the
        age restrictions.

        This is the theoretic value, ignoring the cutoff at 5 participants.
        """
        # participants (possibly including youth leaders)
        ps = {x.member for x in self.membersonlist.distinct()}
        # youth leaders
        jls = set(self.jugendleiter.distinct())
        # non-youth leader participants
        ps_only = ps - jls
        # participants of the correct age
        ps_correct_age = {m for m in ps_only if m.age_at(self.date) >= 6 and m.age_at(self.date) < 27}
        # m = the official non-youth-leader participant count
        # and, assuming there exist enough participants, unrounded m satisfies the equation
        # len(ps_correct_age) + 1/5 * m = m
        # if there are not enough participants,
        # m = len(ps_only)
        m = min(len(ps_only), math.floor(5/4 * len(ps_correct_age)))
        return m + len(jls)

    @property
    def ljp_participant_count(self):
        """
        The number of participants in the sense of LJP regulations. If the total
        number of participants (including youth leaders and too old / young ones) is less
        than 5, this is zero, otherwise it is `theoretic_ljp_participant_count`.
        """
        # participants (possibly including youth leaders)
        ps = {x.member for x in self.membersonlist.distinct()}
        # youth leaders
        jls = set(self.jugendleiter.distinct())
        if len(ps.union(jls)) < 5:
            return 0
        else:
            return self.theoretic_ljp_participant_count

    @property
    def maximal_ljp_contributions(self):
        """This is the maximal amount of LJP contributions that can be requested given participants and length
        This calculation if intended for the LJP application, not for the payout."""
        return cvt_to_decimal(settings.LJP_CONTRIBUTION_PER_DAY * self.ljp_participant_count * self.duration)

    @property
    def potential_ljp_contributions(self):
        """The maximal amount can be reduced if the actual costs are lower than the maximal amount
        This calculation if intended for the LJP application, not for the payout."""
        if not hasattr(self, 'statement'):
            return cvt_to_decimal(0)
        return cvt_to_decimal(min(self.maximal_ljp_contributions,
                                  0.9 * float(self.statement.total_bills_theoretic) + float(self.statement.total_staff)))

    @property
    def payable_ljp_contributions(self):
        """the payable contributions can differ from potential contributions if a tax is deducted for risk reduction.
        the actual payout depends on more factors, e.g. the actual costs that had to be paid by the trip organisers."""
        if hasattr(self, 'statement') and self.statement.ljp_to:
            return self.statement.paid_ljp_contributions
        return cvt_to_decimal(self.potential_ljp_contributions * cvt_to_decimal(1 - settings.LJP_TAX))

    @property
    def total_relative_costs(self):
        if not hasattr(self, 'statement'):
            return 0
        total_costs = self.statement.total_bills_theoretic
        total_contributions = self.statement.total_subsidies + self.payable_ljp_contributions
        return total_costs - total_contributions

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

    def sjr_application_numbers(self):
        members = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        participants = members - jls
        b27_local = len([m for m in participants
                         if m.age_at(self.date) <= 27 and settings.SEKTION in m.town])
        b27_non_local = len([m for m in participants
                             if m.age_at(self.date) <= 27 and not settings.SEKTION in m.town])
        staff = len(jls)
        total = b27_local + b27_non_local + len(jls)
        relevant_b27 = min(b27_local + b27_non_local, math.floor(3/2 * b27_local))
        subsidizable = relevant_b27 + min(math.ceil(relevant_b27 / 7), staff)
        duration = self.night_count + 1
        return {
            'b27_local': b27_local,
            'b27_non_local': b27_non_local,
            'staff': staff,
            'total': total,
            'relevant_b27': relevant_b27,
            'subsidizable': subsidizable,
            'subsidized_days': duration * subsidizable,
            'duration': duration
        }

    def sjr_application_fields(self):
        members = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        numbers = self.sjr_application_numbers()
        title = self.ljpproposal.title if hasattr(self, 'ljpproposal') else self.name
        base = {'Haushaltsjahr': str(datetime.now().year),
                'Art / Thema / Titel': title,
                'Ort': self.place,
                'Datum von': self.date.strftime('%d.%m.%Y'),
                'Datum bis': self.end.strftime('%d.%m.%Y'),
                'Dauer': str(numbers['duration']),
                'Teilnehmenden gesamt': str(numbers['total']),
                'bis 27 aus HD': str(numbers['b27_local']),
                'bis 27 nicht aus HD': str(numbers['b27_non_local']),
                'Verpflegungstage': str(numbers['subsidized_days']).replace('.', ','),
                'Betreuer/in': str(numbers['staff']),
                'Auswahl Veranstaltung': 'Auswahl2',
                'Ort, Datum': '{p}, {d}'.format(p=settings.SEKTION, d=datetime.now().strftime('%d.%m.%Y'))}
        print(members)
        for i, m in enumerate(members):
            suffix = str(' {}'.format(i + 1))
            # indexing starts at zero, but the listing in the pdf starts at 1
            if i + 1 == 1:
                suffix = ''
            elif i + 1 >= 13:
                suffix = str(i + 1)
            base['Vor- und Nachname' + suffix] = m.name
            base['Anschrift' + suffix] = m.address
            base['Alter' + suffix] = str(m.age_at(self.date))
            base['Status' + str(i+1)] = '2' if m in jls else 'Auswahl1' if settings.SEKTION in m.address else 'Auswahl2'
        return base

    def v32_fields(self):
        title = self.ljpproposal.title if hasattr(self, 'ljpproposal') else self.name
        base = {
            # AntragstellerIn
            'Textfeld 2':  settings.ADDRESS,
            # Dachorganisation
            'Textfeld 3':  settings.V32_HEAD_ORGANISATION,
            # Datum der Maßnahme am/vom
            'Textfeld 20': self.date.strftime('%d.%m.%Y'),
            # bis
            'Textfeld 28': self.end.strftime('%d.%m.%Y'),
            # Thema der Maßnahme
            'Textfeld 22': title,
            # IBAN
            'Textfeld 36': settings.SEKTION_IBAN,
            # Kontoinhaber
            'Textfeld 37': settings.SEKTION_ACCOUNT_HOLDER,
            # Zahl der zuwendungsfähigen Teilnehemr
            'Textfeld 43': str(self.ljp_participant_count),
            # Teilnahmetage
            'Textfeld 46': str(round(self.duration * self.ljp_participant_count, 1)).replace('.', ','),
            # Euro Tagessatz
            'Textfeld 48': str(settings.LJP_CONTRIBUTION_PER_DAY),
            # Erbetener Zuschuss
            'Textfeld 50': str(self.maximal_ljp_contributions).replace('.', ','),
            # Stunden Bildungsprogramm
            'Textfeld 52': '??',
            # Tage
            'Textfeld 53': str(round(self.duration, 1)).replace('.', ','),
            # Haushaltsjahr
            'Textfeld 54': str(datetime.now().year),
            # nicht anrechenbare Teilnahmetage
            'Textfeld 55': '0',
            # Gesamt-Teilnahmetage
            'Textfeld 56': str(round(self.duration * self.ljp_participant_count, 1)).replace('.', ','),
            # Ort, Datum
            'DatumOrt 2': '{place}, {date}'.format(place=settings.SEKTION,
                                                   date=datetime.now().strftime('%d.%m.%Y'))
        }
        if hasattr(self, 'statement'):
            possible_contributions = self.maximal_ljp_contributions
            total_contributions = min(self.statement.total_theoretic, possible_contributions)
            self_participation = max(cvt_to_decimal(0), self.statement.total_theoretic - possible_contributions)
            # Gesamtkosten von
            base['Textfeld 62'] = str(self.statement.total_theoretic).replace('.', ',')
            # Eigenmittel und Teilnahmebeiträge
            base['Textfeld 59'] = str(self_participation).replace('.', ',')
            # Drittmittel
            base['Textfeld 60'] = '0,00'
            # Erbetener Zuschuss
            base['Textfeld 61'] = str(total_contributions).replace('.', ',')
            # Ergibt wieder
            base['Textfeld 58'] = base['Textfeld 62']
        return base

    def get_ljp_activity_category(self):
        """
        The official LJP activity category associated with this excursion. This is deduced
        from the `activity` field.
        """
        return ", ".join([a.ljp_category for a in self.activity.all()])

    @staticmethod
    def filter_queryset_by_permissions(member, queryset=None):
        if queryset is None:
            queryset = Freizeit.objects.all()

        groups = member.leited_groups.all()
        # one may view all leited groups and oneself
        queryset = queryset.filter(Q(groups__in=groups) | Q(jugendleiter__pk=member.pk)).distinct()
        return queryset

    def send_crisis_intervention_list(self, sending_time=None):
        """
        Send the crisis intervention list to the crisis invervention email, the
        responsible and the youth leaders of this excursion.
        """
        context = dict(memberlist=self, settings=settings)
        start_date= timezone.localtime(self.date).strftime('%d.%m.%Y')
        filename = render_tex(f"{self.code}_{self.name}_Krisenliste",
                              'members/crisis_intervention_list.tex', context,
                              date=self.date, save_only=True)
        leaders = ", ".join([yl.name for yl in self.jugendleiter.all()])
        start_date = timezone.localtime(self.date).strftime('%d.%m.%Y')
        end_date = timezone.localtime(self.end).strftime('%d.%m.%Y')
        # create email with attachment
        send_mail(_('Crisis intervention list for %(excursion)s from %(start)s to %(end)s') %\
                    { 'excursion': self.name,
                      'start': start_date,
                      'end': end_date },
                  settings.SEND_EXCURSION_CRISIS_LIST.format(excursion=self.name, leaders=leaders,
                                                             excursion_start=start_date,
                                                             excursion_end=end_date),
                  sender=settings.DEFAULT_SENDING_MAIL,
                  recipients=[settings.SEKTION_CRISIS_INTERVENTION_MAIL],
                  cc=[settings.RESPONSIBLE_MAIL] + [yl.email for yl in self.jugendleiter.all()],
                  attachments=[media_path(filename)])
        self.crisis_intervention_list_sent = True
        self.save()

    def notify_leaders_crisis_intervention_list(self, sending_time=None):
        """
        Send an email to the youth leaders of this excursion with a list of currently
        registered participants and a heads-up that the crisis intervention list
        will be automatically sent on the night of this day.
        """
        participants = "\n".join([f"- {p.member.name}" for p in self.membersonlist.all()])
        if not sending_time:
            sending_time = coming_midnight().strftime("%d.%m.%y %H:%M")
        elif not isinstance(sending_time, str):
            sending_time = sending_time.strftime("%d.%m.%y %H:%M")
        start_date = timezone.localtime(self.date).strftime('%d.%m.%Y')
        end_date = timezone.localtime(self.end).strftime('%d.%m.%Y')
        excursion_link = prepend_base_url(self.get_absolute_url())
        for yl in self.jugendleiter.all():
            yl.send_mail(_('Participant list for %(excursion)s from %(start)s to %(end)s') %\
                            { 'excursion': self.name,
                              'start': start_date,
                              'end': end_date },
                         settings.NOTIFY_EXCURSION_PARTICIPANT_LIST.format(name=yl.prename,
                                                                           excursion=self.name,
                                                                           participants=participants,
                                                                           sending_time=sending_time,
                                                                           excursion_link=excursion_link))
        self.notification_crisis_intervention_list_sent = True
        self.save()


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
    title = models.CharField(verbose_name=_('Title'), max_length=100,
                             blank=True, default='',
                             help_text=_('Official title of your seminar, this can differ from the informal title. Use e.g. sports climbing course instead of climbing weekend for fun.'))

    LJP_STAFF_TRAINING, LJP_EDUCATIONAL = 1, 2
    LJP_CATEGORIES = [
        (LJP_EDUCATIONAL, _('Educational programme')),
        (LJP_STAFF_TRAINING, _('Staff training'))
    ]
    category = models.IntegerField(verbose_name=_('Category'),
                                   choices=LJP_CATEGORIES,
                                   default=2,
                                   help_text=_('Type of seminar. Usually the correct choice is educational programme.'))
    LJP_QUALIFICATION, LJP_PARTICIPATION, LJP_DEVELOPMENT, LJP_ENVIRONMENT = 1, 2, 3, 4
    LJP_GOALS = [
        (LJP_QUALIFICATION, _('Qualification')),
        (LJP_PARTICIPATION, _('Participation')),
        (LJP_DEVELOPMENT, _('Personality development')),
        (LJP_ENVIRONMENT, _('Environment')),
    ]
    goal = models.IntegerField(verbose_name=_('Learning goal'),
                               choices=LJP_GOALS,
                               default=1,
                               help_text=_('Official learning goal according to LJP regulations.'))
    goal_strategy = models.TextField(verbose_name=_('Strategy'),
                                     help_text=_('How do you want to reach the learning goal? Has the goal been reached? If not, why not? If yes, what helped you to reach the goal?'),
                                     blank=True, default='')

    NOT_BW_CONTENT, NOT_BW_ROOMS, NOT_BW_CLOSE_BORDER, NOT_BW_ECONOMIC = 1, 2, 3, 4
    NOT_BW_REASONS = [
        (NOT_BW_CONTENT, _('Course content')),
        (NOT_BW_ROOMS, _('Available rooms')),
        (NOT_BW_CLOSE_BORDER, _('Close to the border')),
        (NOT_BW_ECONOMIC, _('Economic reasons')),
    ]
    not_bw_reason = models.IntegerField(verbose_name=_('Explanation if excursion not in Baden-Württemberg'),
                                        choices=NOT_BW_REASONS,
                                        default=None,
                                        blank=True,
                                        null=True,
                                        help_text=_('If the excursion takes place outside of Baden-Württemberg, please explain. Otherwise, leave this empty.'))

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
    activity = models.ManyToManyField(ActivityCategory, verbose_name=_('Activity'))
    comments = models.TextField(verbose_name=_('Comments'), blank=True)
    participated = models.BooleanField(verbose_name=_('Participated'))
    passed = models.BooleanField(verbose_name=_('Passed'))
    certificate = RestrictedFileField(verbose_name=_('certificate of attendance'),
                                      upload_to='training_forms',
                                      blank=True,
                                      max_upload_size=5,
                                      content_types=['application/pdf',
                                                      'image/jpeg',
                                                      'image/png',
                                                      'image/gif'])
    
    def __str__(self):
        return self.title + ' ' + self.date.strftime('%d.%m.%Y')
    
    def get_activities(self):
        activity_string = ', '.join(a.name for a in self.activity.all())
        return activity_string

    get_activities.short_description = _('Activities')

  
    class Meta(CommonModel.Meta):
        verbose_name = _('Training')
        verbose_name_plural = _('Trainings')
        
        permissions = (
            ('manage_success_trainings', 'Can edit the success status of trainings.'),
        )
        rules_permissions = {
            # sine this is used in an inline, the member and not the training is passed
            'add_obj': is_oneself | has_global_perm('members.add_global_membertraining'),
            'view_obj': is_oneself | has_global_perm('members.view_global_membertraining'),
            'change_obj': is_oneself | has_global_perm('members.change_global_membertraining'),
            'delete_obj': is_oneself | has_global_perm('members.delete_global_membertraining'),
        }
