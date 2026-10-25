import re
import uuid
from datetime import datetime
from datetime import timedelta

import rules
from contrib.models import CommonModel
from contrib.rules import has_global_perm
from django.conf import settings
from django.contrib.auth.models import User
from django.db import models
from django.db.models import Case
from django.db.models import Q
from django.db.models import Value
from django.db.models import When
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from mailer.mailutils import flow_link
from mailer.mailutils import get_echo_link
from mailer.mailutils import get_invite_as_user_key
from mailer.mailutils import prepend_base_url
from mailer.mailutils import send as send_mail
from members.rules import may_change
from members.rules import may_delete
from members.rules import may_view
from schwifty import IBAN
from utils import normalize_name
from utils import RestrictedFileField

from .activity import ActivityCategory
from .base import Person
from .excursion import Freizeit
from .group import Group
from .waiting_list import MemberWaitingList


class MemberManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(confirmed=True)


class Member(Person):
    """
    Represents a member of the association
    Might be a member of different groups: e.g. J1, J2, Jugendleiter, etc.
    """

    alternative_email = models.EmailField(max_length=100, default=None, blank=True, null=True)
    confirmed_alternative_mail = models.BooleanField(
        default=True, verbose_name=_("Alternative email confirmed")
    )
    confirm_alternative_mail_key = models.CharField(max_length=32, default="")

    phone_number = models.CharField(
        max_length=100, verbose_name=_("phone number"), default="", blank=True
    )
    street = models.CharField(
        max_length=30, verbose_name=_("street and house number"), default="", blank=True
    )
    plz = models.CharField(max_length=10, verbose_name=_("Postcode"), default="", blank=True)
    town = models.CharField(max_length=30, verbose_name=_("town"), default="", blank=True)
    address_extra = models.CharField(
        max_length=100, verbose_name=_("Address extra"), default="", blank=True
    )
    country = models.CharField(max_length=30, verbose_name=_("Country"), default="", blank=True)

    good_conduct_certificate_presented_date = models.DateField(
        _("Good conduct certificate presented on"), default=None, blank=True, null=True
    )
    join_date = models.DateField(_("Joined on"), default=None, blank=True, null=True)
    leave_date = models.DateField(_("Left on"), default=None, blank=True, null=True)
    has_key = models.BooleanField(_("Has key"), default=False)
    has_free_ticket_gym = models.BooleanField(
        _("Has a free ticket for the climbing gym"), default=False
    )
    dav_badge_no = models.CharField(
        max_length=20, verbose_name=_("DAV badge number"), default="", blank=True
    )

    # use this to store a climbing gym customer or membership id, used to print on meeting checklists
    ticket_no = models.CharField(
        max_length=20, verbose_name=_("entrance ticket number"), default="", blank=True
    )
    swimming_badge = models.BooleanField(verbose_name=_("Knows how to swim"), default=False)
    climbing_badge = models.CharField(
        max_length=100, verbose_name=_("Climbing badge"), default="", blank=True
    )
    alpine_experience = models.TextField(
        verbose_name=_("Alpine experience"), default="", blank=True
    )
    allergies = models.TextField(verbose_name=_("Allergies"), default="", blank=True)
    medication = models.TextField(verbose_name=_("Medication"), default="", blank=True)
    tetanus_vaccination = models.CharField(
        max_length=50, verbose_name=_("Tetanus vaccination"), default="", blank=True
    )
    photos_may_be_taken = models.BooleanField(verbose_name=_("Photos may be taken"), default=False)
    legal_guardians = models.CharField(
        max_length=100, verbose_name=_("Legal guardians"), default="", blank=True
    )
    may_cancel_appointment_independently = models.BooleanField(
        verbose_name=_("May cancel a group appointment independently"),
        null=True,
        blank=True,
        default=None,
    )

    group = models.ManyToManyField(Group, verbose_name=_("group"))

    iban = models.CharField(max_length=30, blank=True, verbose_name="IBAN")

    gets_newsletter = models.BooleanField(_("receives newsletter"), default=True)
    unsubscribe_key = models.CharField(max_length=32, default="")
    unsubscribe_expire = models.DateTimeField(default=timezone.now)
    created = models.DateField(default=timezone.now, verbose_name=_("created"))
    active = models.BooleanField(default=True, verbose_name=_("Active"))
    registration_form = RestrictedFileField(
        verbose_name=_("registration form"),
        upload_to="registration_forms",
        blank=True,
        max_upload_size=5,
        content_types=["application/pdf", "image/jpeg", "image/png", "image/gif"],
    )
    upload_registration_form_key = models.CharField(max_length=32, default="")
    image = RestrictedFileField(
        verbose_name=_("image"),
        upload_to="people",
        blank=True,
        max_upload_size=5,
        content_types=["image/jpeg", "image/png", "image/gif"],
    )
    echo_key = models.CharField(max_length=32, default="")
    echo_expire = models.DateTimeField(default=timezone.now)
    echoed = models.BooleanField(default=True, verbose_name=_("Echoed"))
    confirmed = models.BooleanField(default=True, verbose_name=_("Confirmed"))
    user = models.OneToOneField(
        User, blank=True, null=True, on_delete=models.SET_NULL, verbose_name=_("Login data")
    )
    invite_as_user_key = models.CharField(max_length=32, default="")
    # A login key sets the password of the account linked when it was issued
    # (or creates one, if there was none) until it expires; see ``for_login_key``.
    # Deleting that account keeps its id here, so a reset key does not turn
    # into an invitation.
    invite_as_user_key_expire = models.DateTimeField(null=True, blank=True, editable=False)
    invite_as_user_key_user = models.ForeignKey(
        User,
        null=True,
        blank=True,
        editable=False,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
    )
    waitinglist_application_date = models.DateTimeField(
        verbose_name=_("waitinglist application date"),
        null=True,
        blank=True,
        help_text=_(
            "If the person registered from the waitinglist, this is their application date."
        ),
    )

    objects = MemberManager()
    all_objects = models.Manager()

    INVITE_KEY_VALIDITY = timedelta(days=7)
    RESET_KEY_VALIDITY = timedelta(days=1)

    class Meta(CommonModel.Meta):
        verbose_name = _("member")
        verbose_name_plural = _("members")
        permissions = (
            ("may_see_qualities", "Is allowed to see the quality overview"),
            ("may_set_auth_user", "Is allowed to set auth user member connections."),
            ("may_change_member_group", "Can change the group field"),
            ("may_invite_as_user", "Is allowed to invite a member to set login data."),
            ("may_change_organizationals", "Is allowed to set organizational settings on members."),
        )
        rules_permissions = {
            "members": rules.always_allow,
            "add_obj": has_global_perm("members.add_global_member"),
            "view_obj": may_view | has_global_perm("members.view_global_member"),
            "change_obj": may_change | has_global_perm("members.change_global_member"),
            "delete_obj": may_delete | has_global_perm("members.delete_global_member"),
        }

    @property
    def email_fields(self):
        return [
            ("email", "confirmed_mail", "confirm_mail_key"),
            ("alternative_email", "confirmed_alternative_mail", "confirm_alternative_mail_key"),
        ]

    @property
    def place(self):
        """Returning the whole place (plz + town)"""
        return "{} {}".format(self.plz, self.town)

    @property
    def ticket_tag(self):
        """Returning the ticket number stripped of strings and spaces"""
        return "{" + "".join(re.findall(r"\d", self.ticket_no)) + "}"

    @property
    def iban_valid(self):
        return IBAN(self.iban, allow_invalid=True).is_valid

    @property
    def address(self):
        """Returning the whole address"""
        if not self.street and not self.town and not self.plz:
            return "---"
        return "{}, {}".format(self.street, self.place)

    @property
    def address_multiline(self):
        """Returning the whole address with a linebreak between street and town"""
        if not self.street and not self.town and not self.plz:
            return "---"
        return "{},\\linebreak[1] {}".format(self.street, self.place)

    def good_conduct_certificate_valid(self):
        """Returns if a good conduct certificate is still valid, depending on the last presentation."""
        if not self.good_conduct_certificate_presented_date:
            return False
        delta = datetime.now().date() - self.good_conduct_certificate_presented_date
        return delta.days // 30 <= settings.MAX_AGE_GOOD_CONDUCT_CERTIFICATE_MONTHS

    good_conduct_certificate_valid.boolean = True
    good_conduct_certificate_valid.short_description = _("Good conduct certificate valid")

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
        if self.unsubscribe_key == key and timezone.now() < self.unsubscribe_expire:
            for member in Member.objects.filter(email=self.email):
                member.gets_newsletter = False
                member.save()
            self.unsubscribe_key, self.unsubscribe_expire = "", timezone.now()
            return True
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
    registration_complete.short_description = _("Registration complete")

    def get_group(self):
        """Returns a string of groups in which the member is."""
        groupstring = "".join(g.name + ",\n" for g in self.group.all())
        groupstring = groupstring[:-2]
        return groupstring

    get_group.short_description = _("Group")

    def get_skills(self):
        # get skills by summing up all the activities taken part in, fetching
        # every (activity, difficulty) pair of past excursions in one query
        points = {}
        past = Freizeit.objects.filter(membersonlist__member=self, date__lt=timezone.now())
        for kind_id, difficulty in past.values_list("activity", "difficulty"):
            points[kind_id] = points.get(kind_id, 0) + difficulty * 3
        skills = {}
        for kind in ActivityCategory.objects.all():
            skills[kind.name] = points.get(kind.pk, 0)
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

    def registration_form_uploaded(self):
        print(self.registration_form.name)
        return self.registration_form.name is not None and self.registration_form.name != ""

    registration_form_uploaded.boolean = True
    registration_form_uploaded.short_description = _("Registration form")

    def registration_ready(self):
        """Returns if the member is currently unconfirmed and all email addresses
        are confirmed."""
        return (
            not self.confirmed
            and self.confirmed_alternative_mail
            and self.confirmed_mail
            and self.registration_form
        )

    def confirm_mail(self, key):
        ret = super().confirm_mail(key)
        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()
        return ret

    def validate_registration_form(self):
        self.upload_registration_form_key = ""
        self.save()
        if self.registration_ready():
            self.notify_jugendleiters_about_confirmed_mail()

    def get_upload_registration_form_link(self):
        # reverse() keeps the language prefix this view carries inside
        # i18n_patterns; without it the legacy link 302s to the prefixed URL.
        return flow_link(
            reverse("members:upload_registration_form"), self.upload_registration_form_key
        )

    def send_upload_registration_form_link(self):
        if not self.upload_registration_form_key:
            return
        link = self.get_upload_registration_form_link()
        self.send_mail(
            _("Upload registration form"),
            settings.UPLOAD_REGISTRATION_FORM_TEXT.format(name=self.prename, link=link),
        )

    def request_registration_form(self):
        """Ask the member to upload a registration form via email."""
        self.generate_upload_registration_form_key()
        self.send_upload_registration_form_link()

    def notify_jugendleiters_about_confirmed_mail(self):
        group = ", ".join([g.name for g in self.group.all()])
        # notify jugendleiters of group of registration
        jls = [jl for group in self.group.all() for jl in group.leiters.all()]
        for jl in jls:
            link = prepend_base_url(
                reverse("admin:members_memberunconfirmedproxy_change", args=[str(self.id)])
            )
            send_mail(
                _("New unconfirmed registration for group %(group)s") % {"group": group},
                settings.NEW_UNCONFIRMED_REGISTRATION.format(
                    name=jl.prename, group=group, link=link
                ),
                settings.DEFAULT_SENDING_MAIL,
                jl.email,
            )

    def filter_queryset_by_permissions(
        self, queryset=None, annotate=False, model=None
    ):  # pragma: no cover
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
        elif name == "MemberWaitingList":
            return self.filter_waiters_by_permissions(queryset, annotate)
        elif name == "LJPProposal":
            return queryset
        elif name == "MemberTraining":
            # A training's rules_permissions are evaluated against the owning
            # member (it is an admin inline), so a user may only see the
            # trainings of members they may list. Without this the list leaked
            # rows whose detail route correctly answers 403.
            return self.filter_related_by_member_permissions(queryset, "member")
        elif name == "NewMemberOnList":
            return queryset
        elif name == "Statement":
            return self.filter_statements_by_permissions(queryset, annotate)
        elif name == "StatementOnExcursionProxy":
            return self.filter_statements_by_permissions(queryset, annotate)
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
        elif name == "InvitationToGroup":
            return queryset
        else:
            raise ValueError(name)

    def member_acl_q(self, action):
        """A ``Q`` on ``Member`` matching the members ``self`` may ``action``.

        ``action`` is ``"list"`` or ``"view"``. The same members
        :meth:`may_list` / :meth:`may_view` accept: ``self``, the members and
        the members of groups named in ``self.permissions``, and those named in
        the permissions of a group ``self`` belongs to. Each source is a
        subquery, so filtering costs one query whatever the number of groups.
        """
        able = "{}able_by".format(action)
        by_group = "group_members_{}able_by".format(action)
        sources = [
            # self.permissions.<action>_members
            {"{}__member".format(able): self},
            # members of self.permissions.<action>_groups
            {"group__{}__member".format(able): self},
            # <own group>.permissions.<action>_members
            {"{}__group__member".format(by_group): self},
            # members of <own group>.permissions.<action>_groups
            {"group__{}__group__member".format(by_group): self},
        ]
        q = Q(pk=self.pk)
        for lookup in sources:
            q |= Q(pk__in=Member.objects.filter(**lookup).values("pk"))
        return q

    def filter_members_by_permissions(self, queryset, annotate=False):
        filtered = queryset.filter(self.member_acl_q("list"))
        if not annotate:
            return filtered

        return filtered.annotate(
            _viewable=Case(
                When(self.member_acl_q("view"), then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField(),
            )
        )

    def filter_related_by_member_permissions(self, queryset, member_field):
        """Restrict ``queryset`` to rows whose ``member_field`` the user may list.

        For models that hang off a ``Member`` and borrow its object permissions
        (``MemberTraining``, and anything else added later with the same shape).
        """
        listable = self.filter_members_by_permissions(Member.objects.all())
        return queryset.filter(**{"{}__in".format(member_field): listable})

    def annotate_view_permission(self, queryset, model):
        name = model._meta.object_name
        if name != "Member":
            return queryset
        return queryset.annotate(
            _viewable=Case(
                When(self.member_acl_q("view"), then=Value(True)),
                default=Value(False),
                output_field=models.BooleanField(),
            )
        )

    def filter_messages_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        return queryset.filter(created_by=self)

    def filter_statements_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        # Through a subquery: joining the youth leaders lists a statement once
        # per youth leader of its excursion.
        mine = queryset.filter(Q(created_by=self) | Q(excursion__jugendleiter=self))
        return queryset.filter(pk__in=mine.values("pk"))

    def filter_excursions_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        groups = self.leited_groups.all()
        # one may view all excursions by leited groups and leited excursions
        queryset = queryset.filter(Q(groups__in=groups) | Q(jugendleiter=self)).distinct()
        return queryset

    def filter_waiters_by_permissions(self, queryset, annotate=False):
        # ignores annotate
        # return waiters that have a pending, expired or rejected group invitation for a group
        # led by the member; once each, however many such invitations they have
        return queryset.filter(invitationtogroup__group__leiters=self).distinct()

    def may_list(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, "permissions"):
            if other in self.permissions.list_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.list_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, "permissions"):
                if other in group.permissions.list_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.list_groups.all()]):
                    return True

        return False

    def may_view(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, "permissions"):
            if other in self.permissions.view_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.view_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, "permissions"):
                if other in group.permissions.view_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.view_groups.all()]):
                    return True

        return False

    def may_change(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, "permissions"):
            if other in self.permissions.change_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.change_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, "permissions"):
                if other in group.permissions.change_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.change_groups.all()]):
                    return True

        return False

    def may_delete(self, other):
        if self.pk == other.pk:
            return True

        if hasattr(self, "permissions"):
            if other in self.permissions.delete_members.all():
                return True

            if any([gr in other.group.all() for gr in self.permissions.delete_groups.all()]):
                return True

        for group in self.group.all():
            if hasattr(group, "permissions"):
                if other in group.permissions.delete_members.all():
                    return True

                if any([gr in other.group.all() for gr in group.permissions.delete_groups.all()]):
                    return True

        return False

    def suggested_username(self):
        """Returns a suggested username given by {prename}.{lastname}."""
        raw = "{}.{}".format(self.prename.lower(), self.lastname.lower())
        return normalize_name(raw)

    def has_internal_email(self):
        """Returns if the configured e-mail address is a DAV360 email address."""
        match = re.match("(^[^@]*)@(.*)$", self.email)
        if not match:
            return False
        return (
            match.group(2) in settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER
            or "*" in settings.ALLOWED_EMAIL_DOMAINS_FOR_INVITE_AS_USER
        )

    def _issue_login_key(self, validity):
        self.invite_as_user_key = uuid.uuid4().hex
        self.invite_as_user_key_expire = timezone.now() + validity
        self.invite_as_user_key_user = self.user
        self.save()

    def clear_login_key(self):
        self.invite_as_user_key = ""
        self.invite_as_user_key_expire = None
        self.invite_as_user_key_user = None

    @classmethod
    def for_login_key(cls, key):
        """The member an invite or reset key is for, or ``None`` if it is not valid.

        A key is valid until it expires, and only for the account linked when it
        was issued: an invitation must not turn into a reset for an account that
        is linked later.
        """
        if not key:
            return None
        try:
            member = cls.objects.get(invite_as_user_key=key)
        except (cls.DoesNotExist, cls.MultipleObjectsReturned):
            return None
        expire = member.invite_as_user_key_expire
        if expire is None or expire < timezone.now():
            return None
        if member.invite_as_user_key_user_id != member.user_id:
            return None
        return member

    def save(self, *args, **kwargs):
        # A key mailed to the old address, or issued for the old account, must
        # not outlive a change of either.
        if self.pk and self.invite_as_user_key:
            stored = type(self).all_objects.filter(pk=self.pk).values("user_id", "email").first()
            if stored and (stored["user_id"], stored["email"]) != (self.user_id, self.email):
                self.clear_login_key()
                update_fields = kwargs.get("update_fields")
                if update_fields is not None:
                    kwargs["update_fields"] = set(update_fields) | {
                        "invite_as_user_key",
                        "invite_as_user_key_expire",
                        "invite_as_user_key_user",
                    }
        super().save(*args, **kwargs)

    def _send_login_link(self, subject, text):
        """Mail the login link to the primary, internal address only.

        Whoever holds the link can set the password of the linked account, so
        it never goes to ``alternative_email``: that address is not checked to
        be internal, and anyone who may edit the member could set it.
        """
        send_mail(
            subject,
            text.format(name=self.prename, link=get_invite_as_user_key(self.invite_as_user_key)),
            settings.DEFAULT_SENDING_MAIL,
            [self.email],
        )

    def invite_as_user(self):
        """Invites the member to join Kompass as a user."""
        if not self.has_internal_email():
            # dont invite if the email address is not an internal one
            return False
        if self.user:
            # don't reinvite if there is already userdata attached
            return False
        self._issue_login_key(self.INVITE_KEY_VALIDITY)
        self._send_login_link(_("Set login data for Kompass"), settings.INVITE_AS_USER_TEXT)
        return True

    def request_password_reset(self):
        """Sends a password reset email to the member."""
        if not self.user:
            return False
        if not self.has_internal_email():
            return False
        self._issue_login_key(self.RESET_KEY_VALIDITY)
        self._send_login_link(_("Reset your Kompass password"), settings.PASSWORD_RESET_TEXT)
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
        waiter = MemberWaitingList(
            prename=self.prename,
            lastname=self.lastname,
            email=self.email,
            birth_date=self.birth_date,
            gender=self.gender,
            comments=self.comments,
            confirmed_mail=self.confirmed_mail,
            confirm_mail_key=self.confirm_mail_key,
        )
        # if this member was created from the waitinglist, keep the original application date
        if self.waitinglist_application_date:
            waiter.application_date = self.waitinglist_application_date
        waiter.save()
        self.delete()

    def request_echo(self):
        self.send_mail(
            _("Echo required"),
            settings.ECHO_TEXT.format(name=self.prename, link=get_echo_link(self)),
        )
