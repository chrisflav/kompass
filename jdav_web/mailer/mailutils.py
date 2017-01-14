from django.core.mail import EmailMessage


def send(subject, content, sender, recipients, reply_to=None,
         attachments=None):
    if reply_to is not None:
        kwargs = {"reply_to": [reply_to]}
    else:
        kwargs = {}
    email = EmailMessage(subject, content, sender, recipients, **kwargs)
    if attachments is not None:
        for attach in attachments:
            email.attach_file(attach)
    try:
        email.send()
    except Exception as e:
        print("Error when sending mail:", e)
        return False
    else:
        return True


def get_content(content):
    # TODO: generate right url here
    url = "localhost:8000/newsletter/unsubscribe"
    text = "{}\n\nDiese Email wurde über die Webseite der JDAV Ludwigsburg"\
        " verschickt. Wenn du in Zukunft keine Emails mehr erhalten möchtest,"\
        " kannst du hier den Newsletter deabonnieren.\n\n{}"\
        .format(content, url)
    return text


def get_unsubscribe_link(member):
    key = member.generate_key()
    print("generating key for", member, key)
    # TODO: generate right url here
    return "localhost:8000/newsletter/unsubscribe?key={}".format(key)


mail_root = "christian@localhost"
