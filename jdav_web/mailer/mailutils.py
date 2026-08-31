import logging

from django.conf import settings
from django.core import mail
from django.core.mail import EmailMessage

logger = logging.getLogger(__name__)


NOT_SENT, SENT, PARTLY_SENT = 0, 1, 2


def send(
    subject, content, sender, recipients, message_id=None, reply_to=None, attachments=None, cc=None
):
    failed, succeeded = False, False
    if type(recipients) is not list:
        recipients = [recipients]
    if not cc:
        cc = []
    elif type(cc) is not list:
        cc = [cc]
    if reply_to is not None:
        kwargs = {"reply_to": reply_to}
    else:
        kwargs = {}
    if sender == settings.DEFAULT_SENDING_MAIL:
        sender = addr_with_name(settings.DEFAULT_SENDING_MAIL, settings.DEFAULT_SENDING_NAME)
    url = prepend_base_url("/newsletter/unsubscribe")
    headers = {"List-Unsubscribe": "<{unsubscribe_url}>".format(unsubscribe_url=url)}
    if message_id is not None:
        headers["Message-ID"] = message_id

    # construct mails
    mails = []
    for recipient in set(recipients):
        email = EmailMessage(
            subject, content, sender, [recipient], cc=cc, headers=headers, **kwargs
        )
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
        logger.error(f"Caught exception while sending email: {e}")
        failed = True
    else:
        succeeded = True

    return (
        NOT_SENT if failed and not succeeded else SENT if not failed and succeeded else PARTLY_SENT
    )


def get_content(content, registration_complete=True):
    prepend = settings.PREPEND_INCOMPLETE_REGISTRATION_TEXT
    text = "{prepend}{content}".format(
        prepend="" if registration_complete else prepend, content=content
    )
    return text


# Old Django path -> the SPA route that replaces it. Kept next to the link
# builders so both stay in step; the SPA also redirects the legacy paths, which
# keeps links in already-sent mails working.
SPA_FLOW_PATHS = {
    "/newsletter/unsubscribe": "/abmelden",
    "/members/echo": "/echo",
    "/members/registration": "/anmeldung",
    "/members/register/upload": "/anmeldebogen",
    "/members/waitinglist/invitation/reject": "/einladung/ablehnen",
    "/members/waitinglist/invitation/confirm": "/einladung/annehmen",
    "/members/waitinglist/confirm": "/warteliste/bestaetigen",
    "/members/waitinglist/leave": "/warteliste/verlassen",
    "/members/mail/confirm": "/mail/bestaetigen",
    "/login/register": "/passwort",
}


def get_unsubscribe_link(member):
    key = member.generate_key()
    return flow_link("/newsletter/unsubscribe", key)


def get_echo_link(member):
    key = member.generate_echo_key()
    return flow_link("/members/echo", key)


def get_registration_link(key):
    return flow_link("/members/registration", key)


def get_invitation_reject_link(key):
    return flow_link("/members/waitinglist/invitation/reject", key)


def get_invitation_confirm_link(key):
    return flow_link("/members/waitinglist/invitation/confirm", key)


def get_wait_confirmation_link(waiter):
    key = waiter.generate_wait_confirmation_key()
    return flow_link("/members/waitinglist/confirm", key)


def get_leave_waitinglist_link(key):
    return flow_link("/members/waitinglist/leave", key)


def get_mail_confirmation_link(key):
    return flow_link("/members/mail/confirm", key)


def get_invite_as_user_key(key):
    return flow_link("/login/register", key)


def flow_link(legacy_path, key):
    """An absolute link to a secret-key self-service flow.

    Points at the SPA (``FRONTEND_BASE_URL``) when one is configured, otherwise
    at the Django view under this host — byte-identical to what it produced
    before — so the same code serves both the migrated and the not-yet-migrated
    deployment.

    ``legacy_path`` may carry the language prefix that ``reverse()`` adds for a
    view inside ``i18n_patterns`` (``/de/members/…``); the prefix is only
    stripped for the SPA lookup, never from the legacy link itself.
    """
    frontend = getattr(settings, "FRONTEND_BASE_URL", "")
    if frontend:
        path = SPA_FLOW_PATHS.get(_without_language_prefix(legacy_path), legacy_path)
        return "{base}{path}?key={key}".format(base=frontend.rstrip("/"), path=path, key=key)
    return prepend_base_url("{path}?key={key}".format(path=legacy_path, key=key))


#: Route prefix the authenticated Kompass SPA is served under. It is the path
#: the Django admin used to occupy, so links staff already have keep working.
APP_PATH_PREFIX = "/kompass"


def app_link(path):
    """An absolute link to a page inside the authenticated Kompass SPA.

    ``path`` is the SPA route below the app prefix (``/excursions/12``). Notify
    mails use this to point a Jugendleiter straight at the record; before the
    SPA these were ``reverse("admin:…")`` links into the Django admin.
    """
    base = getattr(settings, "FRONTEND_BASE_URL", "").rstrip("/")
    full_path = "{prefix}{path}".format(prefix=APP_PATH_PREFIX, path=path)
    if base:
        return "{base}{path}".format(base=base, path=full_path)
    return prepend_base_url(full_path)


def _without_language_prefix(path):
    """``/de/members/echo`` -> ``/members/echo``; other paths are unchanged."""
    for code, _name in settings.LANGUAGES:
        prefix = "/{}/".format(code)
        if path.startswith(prefix):
            return "/" + path[len(prefix) :]
    return path


def prepend_base_url(absolutelink):
    return "{protocol}://{base}{link}".format(
        protocol=settings.PROTOCOL, base=settings.BASE_URL, link=absolutelink
    )


def addr_with_name(addr, name):
    return "{name} <{addr}>".format(name=name, addr=addr)
