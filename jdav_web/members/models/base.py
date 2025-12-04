from django.db import models
from django.utils.translation import gettext_lazy as _
from django.utils.html import format_html
from django.conf import settings
from contrib.models import CommonModel
from mailer.mailutils import send as send_mail, get_mail_confirmation_link
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import uuid
from .constants import MALE, FEMALE, DIVERSE

def gen_key():
    return uuid.uuid4().hex

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
