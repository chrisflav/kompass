import math
from datetime import datetime

from contrib.media import media_path
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Case
from django.db.models import Q
from django.db.models import Sum
from django.db.models import Value
from django.db.models import When
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import prepend_base_url
from mailer.mailutils import send as send_mail
from members.pdf import render_tex
from members.rules import is_leader
from utils import coming_midnight
from utils import cvt_to_decimal

from .activity import ActivityCategory
from .constants import AUSBILDUNGS_TOUR
from .constants import FAHRGEMEINSCHAFT_ANREISE
from .constants import FUEHRUNGS_TOUR
from .constants import GEMEINSCHAFTS_TOUR
from .constants import MUSKELKRAFT_ANREISE
from .constants import OEFFENTLICHE_ANREISE
from .group import Group
from .member_on_list import NewMemberOnList


class Freizeit(CommonModel):
    """Lets the user create a 'Freizeit' and generate a members overview in pdf format."""

    name = models.CharField(verbose_name=_("Activity"), default="", max_length=50)
    place = models.CharField(verbose_name=_("Place"), default="", max_length=50)
    postcode = models.CharField(
        verbose_name=_("Postcode"),
        default="",
        max_length=30,
        blank=True,
        help_text=_("only relevant for a LJP application"),
    )
    destination = models.CharField(
        verbose_name=_("Destination (optional)"),
        default="",
        max_length=50,
        blank=True,
        help_text=_("e.g. a peak"),
    )
    date = models.DateTimeField(default=timezone.now, verbose_name=_("Begin"))
    end = models.DateTimeField(verbose_name=_("End (optional)"), default=timezone.now)
    description = models.TextField(verbose_name=_("Description"), blank=True, default="")
    # comment = models.TextField(_('Comments'), default='', blank=True)
    groups = models.ManyToManyField(Group, verbose_name=_("Groups"))
    jugendleiter = models.ManyToManyField("Member")
    approved_extra_youth_leader_count = models.PositiveIntegerField(
        verbose_name=_("Number of additional approved youth leaders"),
        default=0,
        help_text=_(
            "The number of approved youth leaders per excursion is determined by the number of participants. In special circumstances, e.g. in case of a technically demanding excursion, more youth leaders may be approved."
        ),
    )
    tour_type_choices = (
        (GEMEINSCHAFTS_TOUR, "Gemeinschaftstour"),
        (FUEHRUNGS_TOUR, "Führungstour"),
        (AUSBILDUNGS_TOUR, "Ausbildung"),
    )
    # verbose_name is overriden by form, label is set in admin.py
    tour_type = models.IntegerField(choices=tour_type_choices)
    tour_approach_choices = (
        (MUSKELKRAFT_ANREISE, "Muskelkraft"),
        (OEFFENTLICHE_ANREISE, "ÖPNV"),
        (FAHRGEMEINSCHAFT_ANREISE, "Fahrgemeinschaften"),
    )
    tour_approach = models.IntegerField(
        choices=tour_approach_choices,
        default=MUSKELKRAFT_ANREISE,
        verbose_name=_("Means of transportation"),
    )
    kilometers_traveled = models.IntegerField(
        verbose_name=_("Kilometers traveled"),
        validators=[MinValueValidator(0)],
        default=0,
        help_text=_(
            "The total kilometers traveled (away and back) during this excursion. This is relevant for the section subsidies."
        ),
    )
    activity = models.ManyToManyField(ActivityCategory, default=None, verbose_name=_("Categories"))
    difficulty_choices = [(1, _("easy")), (2, _("medium")), (3, _("hard"))]
    # verbose_name is overriden by form, label is set in admin.py
    difficulty = models.IntegerField(choices=difficulty_choices)
    membersonlist = GenericRelation(NewMemberOnList)

    # approval: None means no decision taken, False means rejected
    approved = models.BooleanField(
        verbose_name=_("Approved"),
        null=True,
        default=None,
        help_text=_(
            "Choose no in case of rejection or yes in case of approval. Leave empty, if not yet decided."
        ),
    )
    approval_comments = models.TextField(
        verbose_name=_("Approval comments"), blank=True, default=""
    )

    # automatic sending of crisis intervention list
    crisis_intervention_list_sent = models.BooleanField(default=False)
    notification_crisis_intervention_list_sent = models.BooleanField(default=False)

    def __str__(self):
        """String represenation"""
        return self.name

    def get_dropdown_display(self):
        """Return a string suitable for display in admin dropdown menus."""
        return f"{self.name} - {self.date.strftime('%d.%m.%Y')}"

    class Meta(CommonModel.Meta):
        verbose_name = _("Excursion")
        verbose_name_plural = _("Excursions")
        permissions = (
            ("manage_approval_excursion", "Can edit the approval status of excursions."),
            ("view_approval_excursion", "Can view the approval status of excursions."),
        )
        rules_permissions = {
            "add_obj": has_global_perm("members.add_global_freizeit"),
            "view_obj": is_leader | has_global_perm("members.view_global_freizeit"),
            "change_obj": is_leader | has_global_perm("members.change_global_freizeit"),
            "delete_obj": is_leader | has_global_perm("members.delete_global_freizeit"),
        }

    @property
    def code(self):
        return f"B{self.date:%y}-{self.pk}"

    @staticmethod
    def filter_queryset_date_next_n_hours(hours, queryset=None):
        if queryset is None:
            queryset = Freizeit.objects.all()
        return queryset.filter(
            date__lte=timezone.now() + timezone.timedelta(hours=hours), date__gte=timezone.now()
        )

    @staticmethod
    def to_notify_crisis_intervention_list():
        qs = Freizeit.objects.filter(notification_crisis_intervention_list_sent=False)
        return Freizeit.filter_queryset_date_next_n_hours(48, queryset=qs)

    @staticmethod
    def to_send_crisis_intervention_list():
        qs = Freizeit.objects.filter(crisis_intervention_list_sent=False)
        return Freizeit.filter_queryset_date_next_n_hours(24, queryset=qs)

    def get_tour_type(self):
        if self.tour_type == FUEHRUNGS_TOUR:
            return "Führungstour"
        elif self.tour_type == AUSBILDUNGS_TOUR:
            return "Ausbildung"
        return "Gemeinschaftstour"

    def get_tour_approach(self):
        if self.tour_approach == MUSKELKRAFT_ANREISE:
            return "Muskelkraft"
        elif self.tour_approach == OEFFENTLICHE_ANREISE:
            return "ÖPNV"
        return "Fahrgemeinschaften"

    def get_absolute_url(self):
        return reverse("admin:members_freizeit_change", args=[str(self.id)])

    @property
    def night_count(self):
        # convert to date first, since we might start at 11pm and end at 1am, which is one night
        return (self.end.date() - self.date.date()).days

    @property
    def duration(self):
        # number of nights is number of full days + 1
        full_days = max(self.night_count - 1, 0)
        extra_days = 0

        if self.date.date() == self.end.date():
            # excursion starts and ends on the same day
            hours = max(self.end.hour - self.date.hour, 0)
            # at least 6 hours counts as full day
            extra_days = 1.0 if hours >= 6 else 0.5
        else:
            extra_days += 1.0 if self.date.hour <= 12 else 0.5
            extra_days += 1.0 if self.end.hour >= 12 else 0.5

        return full_days + extra_days

    @property
    def total_intervention_hours(self):
        if hasattr(self, "ljpproposal"):
            return sum([i.duration for i in self.ljpproposal.intervention_set.all()])
        else:
            return 0

    @property
    def total_seminar_days(self):
        """calculate seminar days based on intervention hours in every day"""
        # TODO: add tests for this
        if hasattr(self, "ljpproposal"):
            hours_per_day = self.seminar_time_per_day
            # Calculate the total number of seminar days
            # Each day is counted as 1 if total_duration is >= 5 hours, as 0.5 if total_duration is >= 2.5
            # otherwise 0
            sum_days = sum([h["sum_days"] for h in hours_per_day])

            return sum_days
        else:
            return 0

    @property
    def seminar_time_per_day(self):
        if hasattr(self, "ljpproposal"):
            return (
                self.ljpproposal.intervention_set.annotate(
                    day=Cast("date_start", output_field=models.DateField())
                )  # Force it to date
                .values("day")  # Group by day
                .annotate(total_duration=Sum("duration"))  # Sum durations for each day
                .annotate(
                    sum_days=Case(
                        When(total_duration__gte=5.0, then=Value(1.0)),
                        When(total_duration__gte=2.5, then=Value(0.5)),
                        default=Value(0.0),
                    )
                )
                .order_by("day")  # Sort results by date
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
        ps_correct_age = {
            m for m in ps_only if m.age_at(self.date) >= 6 and m.age_at(self.date) < 27
        }
        # m = the official non-youth-leader participant count
        # and, assuming there exist enough participants, unrounded m satisfies the equation
        # len(ps_correct_age) + 1/5 * m = m
        # if there are not enough participants,
        # m = len(ps_only)
        m = min(len(ps_only), math.floor(5 / 4 * len(ps_correct_age)))
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
        return self.theoretic_ljp_participant_count

    @property
    def maximal_ljp_contributions(self):
        """This is the maximal amount of LJP contributions that can be requested given participants and length
        This calculation if intended for the LJP application, not for the payout."""
        return cvt_to_decimal(
            settings.LJP_CONTRIBUTION_PER_DAY * self.ljp_participant_count * self.duration
        )

    @property
    def potential_ljp_contributions(self):
        """The maximal amount can be reduced if the actual costs are lower than the maximal amount
        This calculation if intended for the LJP application, not for the payout."""
        if not hasattr(self, "statement"):
            return cvt_to_decimal(0)
        return cvt_to_decimal(
            min(
                self.maximal_ljp_contributions,
                0.9 * float(self.statement.total_bills_theoretic)
                + float(self.statement.total_staff),
            )
        )

    @property
    def payable_ljp_contributions(self):
        """the payable contributions can differ from potential contributions if a tax is deducted for risk reduction.
        the actual payout depends on more factors, e.g. the actual costs that had to be paid by the trip organisers."""
        if hasattr(self, "statement") and self.statement.ljp_to:
            return self.statement.paid_ljp_contributions
        return cvt_to_decimal(
            self.potential_ljp_contributions * cvt_to_decimal(1 - settings.LJP_TAX)
        )

    @property
    def total_relative_costs(self):
        if not hasattr(self, "statement"):
            return 0
        total_costs = self.statement.total_bills_theoretic
        total_contributions = self.statement.total_subsidies + self.payable_ljp_contributions
        return total_costs - total_contributions

    @property
    def time_period_str(self):
        time_period = self.date.strftime("%d.%m.%Y")
        if self.end != self.date:
            time_period += " - " + self.end.strftime("%d.%m.%Y")
        return time_period

    @property
    def groups_str(self):
        return ", ".join(g.name for g in self.groups.all())

    @property
    def staff_str(self):
        return ", ".join(yl.name for yl in self.jugendleiter.all())

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
                qualities.append("\\textit{{{}:}} {}".format(activity, value))
            people.append(
                dict(
                    name=m.name, qualities=", ".join(qualities), comments=memberonlist.comments_tex
                )
            )

        sks = []
        for activity in activities:
            skill_avg = (
                0 if len(skills[activity]) == 0 else sum(skills[activity]) / len(skills[activity])
            )
            skill_min = 0 if len(skills[activity]) == 0 else min(skills[activity])
            skill_max = 0 if len(skills[activity]) == 0 else max(skills[activity])
            sks.append(
                dict(name=activity, skill_avg=skill_avg, skill_min=skill_min, skill_max=skill_max)
            )
        return (people, sks)

    def sjr_application_numbers(self):
        members = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        participants = members - jls
        b27_local = len(
            [m for m in participants if m.age_at(self.date) <= 27 and settings.SEKTION in m.town]
        )
        b27_non_local = len(
            [
                m
                for m in participants
                if m.age_at(self.date) <= 27 and settings.SEKTION not in m.town
            ]
        )
        staff = len(jls)
        total = b27_local + b27_non_local + len(jls)
        relevant_b27 = min(b27_local + b27_non_local, math.floor(3 / 2 * b27_local))
        subsidizable = relevant_b27 + min(math.ceil(relevant_b27 / 7), staff)
        duration = self.night_count + 1
        return {
            "b27_local": b27_local,
            "b27_non_local": b27_non_local,
            "staff": staff,
            "total": total,
            "relevant_b27": relevant_b27,
            "subsidizable": subsidizable,
            "subsidized_days": duration * subsidizable,
            "duration": duration,
        }

    def sjr_application_fields(self):
        members = set(map(lambda x: x.member, self.membersonlist.distinct()))
        jls = set(self.jugendleiter.distinct())
        numbers = self.sjr_application_numbers()
        title = self.ljpproposal.title if hasattr(self, "ljpproposal") else self.name
        base = {
            "Haushaltsjahr": str(datetime.now().year),
            "Art / Thema / Titel": title,
            "Ort": self.place,
            "Datum von": self.date.strftime("%d.%m.%Y"),
            "Datum bis": self.end.strftime("%d.%m.%Y"),
            "Dauer": str(numbers["duration"]),
            "Teilnehmenden gesamt": str(numbers["total"]),
            "bis 27 aus HD": str(numbers["b27_local"]),
            "bis 27 nicht aus HD": str(numbers["b27_non_local"]),
            "Verpflegungstage": str(numbers["subsidized_days"]).replace(".", ","),
            "Betreuer/in": str(numbers["staff"]),
            "Auswahl Veranstaltung": "Auswahl2",
            "Ort, Datum": "{p}, {d}".format(
                p=settings.SEKTION, d=datetime.now().strftime("%d.%m.%Y")
            ),
        }
        for i, m in enumerate(members):
            suffix = str(" {}".format(i + 1))
            # indexing starts at zero, but the listing in the pdf starts at 1
            if i + 1 == 1:
                suffix = ""
            elif i + 1 >= 13:
                suffix = str(i + 1)
            base["Vor- und Nachname" + suffix] = m.name
            base["Anschrift" + suffix] = m.address
            base["Alter" + suffix] = str(m.age_at(self.date))
            base["Status" + str(i + 1)] = (
                "2" if m in jls else "Auswahl1" if settings.SEKTION in m.address else "Auswahl2"
            )
        return base

    def v32_fields(self):
        title = self.ljpproposal.title if hasattr(self, "ljpproposal") else self.name
        base = {
            # AntragstellerIn
            "Textfeld 2": settings.ADDRESS,
            # Dachorganisation
            "Textfeld 3": settings.V32_HEAD_ORGANISATION,
            # Datum der Maßnahme am/vom
            "Textfeld 20": self.date.strftime("%d.%m.%Y"),
            # bis
            "Textfeld 28": self.end.strftime("%d.%m.%Y"),
            # Thema der Maßnahme
            "Textfeld 22": title,
            # IBAN
            "Textfeld 36": settings.SEKTION_IBAN,
            # Kontoinhaber
            "Textfeld 37": settings.SEKTION_ACCOUNT_HOLDER,
            # Zahl der zuwendungsfähigen Teilnehemr
            "Textfeld 43": str(self.ljp_participant_count),
            # Teilnahmetage
            "Textfeld 46": str(round(self.duration * self.ljp_participant_count, 1)).replace(
                ".", ","
            ),
            # Euro Tagessatz
            "Textfeld 48": str(settings.LJP_CONTRIBUTION_PER_DAY),
            # Erbetener Zuschuss
            "Textfeld 50": str(self.maximal_ljp_contributions).replace(".", ","),
            # Stunden Bildungsprogramm
            "Textfeld 52": "??",
            # Tage
            "Textfeld 53": str(round(self.duration, 1)).replace(".", ","),
            # Haushaltsjahr
            "Textfeld 54": str(datetime.now().year),
            # nicht anrechenbare Teilnahmetage
            "Textfeld 55": "0",
            # Gesamt-Teilnahmetage
            "Textfeld 56": str(round(self.duration * self.ljp_participant_count, 1)).replace(
                ".", ","
            ),
            # Ort, Datum
            "DatumOrt 2": "{place}, {date}".format(
                place=settings.SEKTION, date=datetime.now().strftime("%d.%m.%Y")
            ),
        }
        if hasattr(self, "statement"):
            possible_contributions = self.maximal_ljp_contributions
            total_contributions = min(self.statement.total_theoretic, possible_contributions)
            self_participation = max(
                cvt_to_decimal(0), self.statement.total_theoretic - possible_contributions
            )
            # Gesamtkosten von
            base["Textfeld 62"] = str(self.statement.total_theoretic).replace(".", ",")
            # Eigenmittel und Teilnahmebeiträge
            base["Textfeld 59"] = str(self_participation).replace(".", ",")
            # Drittmittel
            base["Textfeld 60"] = "0,00"
            # Erbetener Zuschuss
            base["Textfeld 61"] = str(total_contributions).replace(".", ",")
            # Ergibt wieder
            base["Textfeld 58"] = base["Textfeld 62"]
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

    @classmethod
    def filter_queryset_by_change_permissions_member(cls, member, queryset):
        return Freizeit.filter_queryset_by_permissions(member, queryset)

    def send_crisis_intervention_list(self, sending_time=None):
        """
        Send the crisis intervention list to the crisis invervention email, the
        responsible and the youth leaders of this excursion.
        """
        context = dict(memberlist=self, settings=settings)
        start_date = timezone.localtime(self.date).strftime("%d.%m.%Y")
        filename = render_tex(
            f"{self.code}_{self.name}_Krisenliste",
            "members/crisis_intervention_list.tex",
            context,
            date=self.date,
            save_only=True,
        )
        leaders = ", ".join([yl.name for yl in self.jugendleiter.all()])
        start_date = timezone.localtime(self.date).strftime("%d.%m.%Y")
        end_date = timezone.localtime(self.end).strftime("%d.%m.%Y")
        # create email with attachment
        send_mail(
            _("Crisis intervention list for %(excursion)s from %(start)s to %(end)s")
            % {"excursion": self.name, "start": start_date, "end": end_date},
            settings.SEND_EXCURSION_CRISIS_LIST.format(
                excursion=self.name,
                leaders=leaders,
                excursion_start=start_date,
                excursion_end=end_date,
            ),
            sender=settings.DEFAULT_SENDING_MAIL,
            recipients=[settings.SEKTION_CRISIS_INTERVENTION_MAIL],
            cc=[settings.RESPONSIBLE_MAIL] + [yl.email for yl in self.jugendleiter.all()],
            attachments=[media_path(filename)],
        )
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
        start_date = timezone.localtime(self.date).strftime("%d.%m.%Y")
        end_date = timezone.localtime(self.end).strftime("%d.%m.%Y")
        excursion_link = prepend_base_url(self.get_absolute_url())
        for yl in self.jugendleiter.all():
            yl.send_mail(
                _("Participant list for %(excursion)s from %(start)s to %(end)s")
                % {"excursion": self.name, "start": start_date, "end": end_date},
                settings.NOTIFY_EXCURSION_PARTICIPANT_LIST.format(
                    name=yl.prename,
                    excursion=self.name,
                    participants=participants,
                    sending_time=sending_time,
                    excursion_link=excursion_link,
                ),
            )
        self.notification_crisis_intervention_list_sent = True
        self.save()

    def add_members(self, queryset):
        content_type = ContentType.objects.get_for_model(Freizeit)

        # Add selected members to the excursion
        for member in queryset:
            NewMemberOnList.objects.get_or_create(
                member=member, content_type=content_type, object_id=self.pk
            )
