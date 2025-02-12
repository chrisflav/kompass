from django.core import mail
from django.core.mail import EmailMessage
from django.conf import settings
import os


NOT_SENT, SENT, PARTLY_SENT = 0, 1, 2

def send(subject, content, sender, recipients, message_id=None, reply_to=None,
         attachments=None, cc=None):
    failed, succeeded = False, False
    if type(recipients) != list:
        recipients = [recipients]
    if not cc:
        cc = []
    elif type(cc) != list:
        cc = [cc]
    if reply_to is not None:
        kwargs = {"reply_to": reply_to}
    else:
        kwargs = {}
    if sender == settings.DEFAULT_SENDING_MAIL:
        sender = addr_with_name(settings.DEFAULT_SENDING_MAIL, settings.DEFAULT_SENDING_NAME)
    url = prepend_base_url("/newsletter/unsubscribe")
    headers = {'List-Unsubscribe': '<{unsubscribe_url}>'.format(unsubscribe_url=url)}
    if message_id is not None:
        headers['Message-ID'] = message_id

    # construct mails
    mails = []
    for recipient in set(recipients):
        email = EmailMessage(subject, content, sender, [recipient], cc=cc,
                             headers=headers, **kwargs)
        if attachments is not None:
            for attach in attachments:
                email.attach_file(attach)
        mails.append(email)
    try:
        # connect to smtp server
        connection = mail.get_connection()
        # send all mails with one connection
        connection.send_messages(mails)
    except Exception as e:
        print("Error when sending mail:", e)
        failed = True
    else:
        succeeded = True

    return NOT_SENT if failed and not succeeded else SENT if not failed\
        and succeeded else PARTLY_SENT


def get_content(content, registration_complete=True):
    url = prepend_base_url("/newsletter/unsubscribe")
    prepend = settings.PREPEND_INCOMPLETE_REGISTRATION_TEXT
    text = "{prepend}{content}".format(prepend="" if registration_complete else prepend,
                                       content=content)
    return text


def get_unsubscribe_link(member):
    key = member.generate_key()
    return prepend_base_url("/newsletter/unsubscribe?key={}".format(key))


def get_echo_link(member):
    key = member.generate_echo_key()
    return prepend_base_url("/members/echo?key={}".format(key))


def get_registration_link(key):
    return prepend_base_url("/members/registration?key={}".format(key))


def get_invitation_reject_link(key):
    return prepend_base_url("/members/waitinglist/invitation/reject?key={}".format(key))


def get_wait_confirmation_link(waiter):
    key = waiter.generate_wait_confirmation_key()
    return prepend_base_url("/members/waitinglist/confirm?key={}".format(key))


def get_leave_waitinglist_link(key):
    return prepend_base_url("/members/waitinglist/leave?key={}".format(key))


def get_mail_confirmation_link(key):
    return prepend_base_url("/members/mail/confirm?key={}".format(key))


def get_invite_as_user_key(key):
    return prepend_base_url("/login/register?key={}".format(key))


def prepend_base_url(absolutelink):
    return "{protocol}://{base}{link}".format(protocol=settings.PROTOCOL, base=settings.BASE_URL, link=absolutelink)


def addr_with_name(addr, name):
    return "{name} <{addr}>".format(name=name, addr=addr)
