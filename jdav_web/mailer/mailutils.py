from django.core import mail
from django.core.mail import EmailMessage
import os


NOT_SENT, SENT, PARTLY_SENT = 0, 1, 2
HOST = os.environ.get('DJANGO_ALLOWED_HOST', 'localhost:8000').split(",")[0]


def send(subject, content, sender, recipients, message_id=None, reply_to=None,
         attachments=None):
    failed, succeeded = False, False
    if type(recipients) != list:
        recipients = [recipients]
    if reply_to is not None:
        kwargs = {"reply_to": reply_to}
    else:
        kwargs = {}
    if message_id is not None:
        headers = {'Message-ID': message_id}
    else:
        headers = {}

    # construct mails
    mails = []
    for recipient in set(recipients):
        email = EmailMessage(subject, content, sender, [recipient],
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
    url = "https://{}/newsletter/unsubscribe".format(HOST)
    prepend = "WICHTIGE MITTEILUNG\n\n"\
        "Deine Anmeldung ist aktuell nicht vollständig. Bitte fülle umgehend das"\
        " Anmeldeformular aus und lasse es Deine*r Jugendleiter*in zukommen! Dieses"\
        " kannst Du unter folgendem Link herunterladen:\n"\
        "https://cloud.jdav-ludwigsburg.de/index.php/s/NQfRqA9MTKfPBkC"\
        "\n\n****************\n\n".format(HOST)
    text = "{}{}\n\n\n****************\n\nDiese Email wurde über die Webseite der JDAV Ludwigsburg"\
        " verschickt. Wenn Du in Zukunft keine Emails mehr erhalten möchtest,"\
        " kannst Du hier den Newsletter deabonnieren:\n{}"\
        .format("" if registration_complete else prepend, content, url)
    return text


def get_unsubscribe_link(member):
    key = member.generate_key()
    return "https://{}/newsletter/unsubscribe?key={}".format(HOST, key)


def get_echo_link(member):
    key = member.generate_echo_key()
    return "https://{}/members/echo?key={}".format(HOST, key)


mail_root = os.environ.get('EMAIL_SENDING_ADDRESS', 'christian@localhost')
