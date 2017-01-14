from django.core.mail import send_mass_mail, send_mail


def send(subject, content, sender, recipicient):
    send_mail(subject, content, sender, [recipicient])


def send_mass(subject, content, sender, recipicients):
    data = [
        (subject, content, sender, [recipicient])
        for recipicient in recipicients]
    print("sending data", data)
    send_mass_mail(data)


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
