from datetime import datetime, timedelta
import uuid
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
from mailer.mailutils import send as send_mail, mail_root, get_mail_confirmation_link
from django.contrib.auth.models import User

from dateutil.relativedelta import relativedelta

GEMEINSCHAFTS_TOUR = MUSKELKRAFT_ANREISE = 0
FUEHRUNGS_TOUR = OEFFENTLICHE_ANREISE = 1
AUSBILDUNGS_TOUR = FAHRGEMEINSCHAFT_ANREISE = 2
HOST = os.environ.get('DJANGO_ALLOWED_HOST', 'localhost:8000').split(",")[0]

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
    name = models.CharField(max_length=20, verbose_name=_('name'))  # e.g: J1
    year_from = models.IntegerField(verbose_name=_('lowest year'), default=2010)
    year_to = models.IntegerField(verbose_name=_('highest year'), default=2011)
    leiters = models.ManyToManyField('members.Member', verbose_name=_('youth leaders'),
                                     related_name='leited_groups', blank=True)

    def __str__(self):
        """String representation"""
        return self.name

    class Meta:
        verbose_name = _('group')
        verbose_name_plural = _('groups')


class MemberManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=True)


class Member(models.Model):
    """
    Represents a member of the association
    Might be a member of different groups: e.g. J1, J2, Jugendleiter, etc.
    """
    prename = models.CharField(max_length=20, verbose_name=_('prename'))
    lastname = models.CharField(max_length=20, verbose_name=_('last name'))
    street = models.CharField(max_length=30, verbose_name=_('street'), default='', blank=True)
    plz = models.CharField(max_length=10, verbose_name=_('Postcode'),
                           default='', blank=True)
    town = models.CharField(max_length=30, verbose_name=_('town'), default='', blank=True)
    phone_number = models.CharField(max_length=18, verbose_name=_('phone number'), default='', blank=True)
    phone_number_parents = models.CharField(max_length=18, verbose_name=_('parents phone number'), default='', blank=True)
    email = models.EmailField(max_length=100, default="")
    email_parents = models.EmailField(max_length=100, default="", blank=True,
                                      verbose_name=_("Parents' Email"))
    cc_email_parents = models.BooleanField(default=True, verbose_name=_('Also send mails to parents'))
    birth_date = models.DateField(_('birth date'))  # to determine the age
    group = models.ManyToManyField(Group, verbose_name=_('group'))
    gets_newsletter = models.BooleanField(_('receives newsletter'),
                                          default=True)
    unsubscribe_key = models.CharField(max_length=32, default="")
    unsubscribe_expire = models.DateTimeField(default=timezone.now)
    comments = models.TextField(_('comments'), default='', blank=True)
    created = models.DateField(auto_now=True, verbose_name=_('created'))
    registered = models.BooleanField(default=False, verbose_name=_('Registration complete'))
    active = models.BooleanField(default=True, verbose_name=_('Active'))
    not_waiting = models.BooleanField(default=True, verbose_name=_('Not waiting'))
    registration_form = RestrictedFileField(verbose_name=_('registration form'),
                                            upload_to='registration_forms',
                                            blank=True,
                                            max_upload_size=5242880,
                                            content_types=['application/pdf',
                                                           'image/jpeg',
                                                           'image/png',
                                                           'image/gif'])
    echo_key = models.CharField(max_length=32, default="")
    echo_expire = models.DateTimeField(default=timezone.now)
    echoed = models.BooleanField(default=True, verbose_name=_('Echoed'))
    confirmed = models.BooleanField(default=True, verbose_name=_('Confirmed'))
    confirmed_mail = models.BooleanField(default=True, verbose_name=_('Email confirmed'))
    confirmed_mail_parents = models.BooleanField(default=True, verbose_name=_('Parents email confirmed'))
    confirm_mail_key = models.CharField(max_length=32, default="")
    confirm_mail_parents_key = models.CharField(max_length=32, default="")
    user = models.OneToOneField(User, blank=True, null=True, on_delete=models.SET_NULL)

    objects = MemberManager()

    def __str__(self):
        """String representation"""
        return self.name

    @property
    def age(self):
        """Age of member"""
        return relativedelta(datetime.today(), self.birth_date).years

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

    def request_mail_confirmation(self):
        self.confirmed_mail = False
        self.confirm_mail_key = uuid.uuid4().hex
        group = ", ".join([g.name for g in self.group.all()])
        send_mail(_('Email confirmation'),
                  CONFIRM_MAIL_TEXT.format(name=self.prename,
                                           group=group,
                                           link=get_mail_confirmation_link(self.confirm_mail_key),
                                           whattoconfirm='deiner Emailadresse'),
                  mail_root,
                  self.email)
        if self.email_parents:
            self.confirmed_mail_parents = False
            self.confirm_mail_parents_key = uuid.uuid4().hex
            send_mail(_('Email confirmation'),
                      CONFIRM_MAIL_TEXT.format(name=self.prename,
                                               group=group,
                                               link=get_mail_confirmation_link(self.confirm_mail_parents_key),
                                               whattoconfirm='der Emailadresse deiner Eltern'),
                      mail_root,
                      self.email_parents)
        else:
            self.confirmed_mail_parents = True
        self.save()

    def confirm_mail(self, key):
        if self.confirm_mail_key == key:
            self.confirm_mail_key, self.confirmed_mail = "", True
            self.save()
            return (self.email, False)
        elif self.confirm_mail_parents_key == key:
            self.confirm_mail_parents_key, self.confirmed_mail_parents = "", True
            self.save()
            return (self.email_parents, True)

    def confirm(self):
        if not self.confirmed_mail or not self.confirmed_mail_parents:
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
    def name(self):
        """Returning whole name (prename + lastname)"""
        return "{0} {1}".format(self.prename, self.lastname)

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

    @property
    def contact_phone_number(self):
        """Returning, if available phone number of parents, else member's phone number"""
        if self.phone_number_parents:
            return str(self.phone_number_parents)
        elif self.phone_number:
            return str(self.phone_number)
        else:
            return "---"

    @property
    def contact_email(self):
        """Returning, if available email of parents, else member's email"""
        if self.email_parents:
            return self.email_parents
        else:
            return self.email

    @property
    def association_email(self):
        """Returning the association email of the member"""
        raw = "{0}.{1}@{2}".format(self.prename.lower(), self.lastname.lower(), HOST)
        return raw.replace('ö', 'oe').replace('ä', 'ae').replace('ü', 'ue')

    def get_group(self):
        """Returns a string of groups in which the member is."""
        groupstring = ''.join(g.name + ',\n' for g in self.group.all())
        groupstring = groupstring[:-2]
        return groupstring
    get_group.short_description = _('Group')

    class Meta:
        verbose_name = _('member')
        verbose_name_plural = _('members')
        permissions = (('may_see_qualities', 'Is allowed to see the quality overview'),
                       ('may_set_auth_user', 'Is allowed to set auth user member connections.'))

    def get_skills(self):
        # get skills by summing up all the activities taken part in
        skills = {}
        for kind in ActivityCategory.objects.all():
            lists = Freizeit.objects.filter(activity=kind,
                                            membersonlist__member=self)
            skills[kind.name] = sum([l.difficulty * 3 for l in lists
                                     if l.date < datetime.now().date()])
        return skills

    def get_activities(self):
        # get activity overview
        return Freizeit.objects.filter(membersonlist__member=self)


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


class MemberList(models.Model):
    """Lets the user create a list of members in pdf format.
       
       DEPRECATED: Replaced by Freizeit and Notizliste
    """

    name = models.CharField(verbose_name=_('Activity'), default='',
                            max_length=50)
    place = models.CharField(verbose_name=_('Place'), default='', max_length=50)
    destination = models.CharField(verbose_name=_('Destination (optional)'),
                                   default='', max_length=50, blank=True)
    date = models.DateField(default=datetime.today, verbose_name=_('Date'))
    end = models.DateField(verbose_name=_('End (optional)'), blank=True, default=datetime.today)
    # comment = models.TextField(_('Comments'), default='', blank=True)
    groups = models.ManyToManyField(Group, verbose_name=_('Groups'))
    jugendleiter = models.ManyToManyField(Member)
    tour_type_choices = ((GEMEINSCHAFTS_TOUR, 'Gemeinschaftstour'),
                         (FUEHRUNGS_TOUR, 'Führungstour'),
                         (AUSBILDUNGS_TOUR, 'Ausbildung'))
    # verbose_name is overriden by form, label is set in admin.py
    tour_type = models.IntegerField(choices=tour_type_choices)
    activity = models.ManyToManyField(ActivityCategory, default=None,
                                      verbose_name=_('Categories'))
    difficulty_choices = [(1, _('easy')), (2, _('medium')), (3, _('hard'))]
    # verbose_name is overriden by form, label is set in admin.py
    difficulty = models.IntegerField(choices=difficulty_choices)

    def __str__(self):
        """String represenation"""
        return self.name

    class Meta:
        verbose_name = _('Memberlist')
        verbose_name_plural = _('Memberlists')

    def get_tour_type(self):
        if self.tour_type == FUEHRUNGS_TOUR:
            return "Führungstour"
        elif self.tour_type == AUSBILDUNGS_TOUR:
            return "Ausbildung"
        else:
            return "Gemeinschaftstour"

    def get_absolute_url(self):
        return reverse('admin:members_memberlist_change', args=[str(self.id)])


class OldMemberOnList(models.Model):
    """
    Connects members to a list of members.
    """
    member = models.ForeignKey(Member, verbose_name=_('Member'), on_delete=models.CASCADE)
    memberlist = models.ForeignKey(MemberList, on_delete=models.CASCADE)
    comments = models.TextField(_('Comment'), default='', blank=True)

    def __str__(self):
        return str(self.member)

    class Meta:
        verbose_name = _('Member')
        verbose_name_plural = _('Members')


class NewMemberOnList(models.Model):
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

    class Meta:
        verbose_name = _('Member')
        verbose_name_plural = _('Members')


class Freizeit(models.Model):
    """Lets the user create a 'Freizeit' and generate a members overview in pdf format. """

    name = models.CharField(verbose_name=_('Activity'), default='',
                            max_length=50)
    place = models.CharField(verbose_name=_('Place'), default='', max_length=50)
    destination = models.CharField(verbose_name=_('Destination (optional)'),
                                   default='', max_length=50, blank=True)
    date = models.DateField(default=datetime.today, verbose_name=_('Date'))
    end = models.DateField(verbose_name=_('End (optional)'), blank=True, default=datetime.today)
    # comment = models.TextField(_('Comments'), default='', blank=True)
    groups = models.ManyToManyField(Group, verbose_name=_('Groups'))
    jugendleiter = models.ManyToManyField(Member)
    tour_type_choices = ((GEMEINSCHAFTS_TOUR, 'Gemeinschaftstour'),
                         (FUEHRUNGS_TOUR, 'Führungstour'),
                         (AUSBILDUNGS_TOUR, 'Ausbildung'))
    # verbose_name is overriden by form, label is set in admin.py
    tour_type = models.IntegerField(choices=tour_type_choices)
    tour_approach_choices = ((MUSKELKRAFT_ANREISE, 'Muskelkraft'),
                         (OEFFENTLICHE_ANREISE, 'Öffentliche VM'),
                         (FAHRGEMEINSCHAFT_ANREISE, 'Fahrgemeinschaften'))
    tour_approach = models.IntegerField(choices=tour_approach_choices,
                                        default=MUSKELKRAFT_ANREISE)
    activity = models.ManyToManyField(ActivityCategory, default=None,
                                      verbose_name=_('Categories'))
    difficulty_choices = [(1, _('easy')), (2, _('medium')), (3, _('hard'))]
    # verbose_name is overriden by form, label is set in admin.py
    difficulty = models.IntegerField(choices=difficulty_choices)
    membersonlist = GenericRelation(NewMemberOnList)

    def __str__(self):
        """String represenation"""
        return self.name

    class Meta:
        verbose_name = "Freizeit"
        verbose_name_plural = "Freizeiten"

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
            return "Öffentliche VM"
        else:
            return "Fahrgemeinschaften"

    def get_absolute_url(self):
        return reverse('admin:members_freizeit_change', args=[str(self.id)])


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


def annotate_activity_score(queryset):
    one_year_ago = datetime.now() - timedelta(days=365)
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


CONFIRM_MAIL_TEXT = """Hallo {name},

du hast dich bei der JDAV Ludwigsburg für die Gruppe {group} registriert. Da bei uns alle Kommunikation
per Email funktioniert, brauchen wir eine Bestätigung {whattoconfirm}. Dazu klicke bitte einfach auf
folgenden Link:

{link}

Viele Grüße,
Deine JDAV Ludwigsburg"""
