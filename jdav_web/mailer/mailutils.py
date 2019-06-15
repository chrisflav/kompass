from django.core import mail
from django.core.mail import EmailMessage
import os


NOT_SENT, SENT, PARTLY_SENT = 0, 1, 2
HOST = os.environ.get('DJANGO_ALLOWED_HOST', 'localhost:8000').split(",")[0]


def send(subject, content, sender, recipients, message_id, reply_to=None,
         attachments=None):
    failed, succeeded = False, False
    if type(recipients) != list:
        recipients = [recipients]
    if reply_to is not None:
        kwargs = {"reply_to": [reply_to]}
    else:
        kwargs = {}
    with mail.get_connection() as connection:
        for recipient in set(recipients):
            email = EmailMessage(subject, content, sender, [recipient],
                                 connection=connection, **kwargs,
                                 headers={'Message-ID': message_id})
            if attachments is not None:
                for attach in attachments:
                    email.attach_file(attach)
            try:
                email.send(fail_silently=True)
            except Exception as e:
                print("Error when sending mail:", e)
                failed = True
            else:
                succeeded = True
    return NOT_SENT if failed and not succeeded else SENT if not failed\
        and succeeded else PARTLY_SENT


def get_content(content):
    # TODO: generate right url here
    url = "https://{}/newsletter/unsubscribe".format(HOST)
    text = "{}\n\n\n*********\n\nDiese Email wurde über die Webseite der JDAV Ludwigsburg"\
        " verschickt. Wenn du in Zukunft keine Emails mehr erhalten möchtest,"\
        " kannst du hier den Newsletter deabonnieren:\n{}"\
        .format(content, url)
    return text


def get_unsubscribe_link(member):
    key = member.generate_key()
    # TODO: generate right url here
    return "https://{}/newsletter/unsubscribe?key={}".format(HOST, key)


mail_root = os.environ.get('EMAIL_SENDING_ADDRESS', 'christian@localhost')
