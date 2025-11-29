import csv  # pragma: no cover
import datetime  # pragma: no cover
import re  # pragma: no cover

import pytz  # pragma: no cover
import timezone  # pragma: no cover

from .models import DIVERSE  # pragma: no cover
from .models import FEMALE  # pragma: no cover
from .models import Group  # pragma: no cover
from .models import InvitationToGroup  # pragma: no cover
from .models import MALE  # pragma: no cover
from .models import Member  # pragma: no cover
from .models import MemberTraining  # pragma: no cover
from .models import MemberWaitingList  # pragma: no cover
from .models import TrainingCategory  # pragma: no cover


def import_from_csv(path, omit_groupless=True):  # pragma: no cover
    with open(path, encoding="ISO-8859-1") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=";")
        rows = list(reader)

    def transform_field(key, value):
        new_key = CLUBDESK_TO_KOMPASS[key]
        if isinstance(new_key, str):
            return (new_key, value)
        else:
            return (new_key[0], new_key[1](value))

    def transform_row(row):
        kwargs = dict([transform_field(k, v) for k, v in row.items() if k in CLUBDESK_TO_KOMPASS])
        kwargs_filtered = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "group",
                "last_training",
                "has_fundamental_training",
                "special_training",
                "phone_number_private",
                "phone_number_parents",
            ]
        }
        if not kwargs["group"] and omit_groupless:
            # if member does not have a group, skip them
            return
        mem = Member(**kwargs_filtered)
        mem.save()
        mem.group.set([group for group, is_jl in kwargs["group"]])
        for group, is_jl in kwargs["group"]:
            if is_jl:
                group.leiters.add(mem)

        if kwargs["has_fundamental_training"]:
            try:
                ga_cat = TrainingCategory.objects.get(name="Grundausbildung")
            except TrainingCategory.DoesNotExist:
                ga_cat = TrainingCategory(name="Grundausbildung", permission_needed=True)
                ga_cat.save()
            ga_training = MemberTraining(
                member=mem,
                title="Grundausbildung",
                date=None,
                category=ga_cat,
                participated=True,
                passed=True,
            )
            ga_training.save()

        if kwargs["last_training"] is not None:
            try:
                cat = TrainingCategory.objects.get(name="Fortbildung")
            except TrainingCategory.DoesNotExist:
                cat = TrainingCategory(name="Fortbildung", permission_needed=False)
                cat.save()
            training = MemberTraining(
                member=mem,
                title="Unbekannt",
                date=kwargs["last_training"],
                category=cat,
                participated=True,
                passed=True,
            )
            training.save()

        if kwargs["special_training"] != "":
            try:
                cat = TrainingCategory.objects.get(name="Sonstiges")
            except TrainingCategory.DoesNotExist:
                cat = TrainingCategory(name="Sonstiges", permission_needed=False)
                cat.save()
            training = MemberTraining(
                member=mem,
                title=kwargs["special_training"],
                date=None,
                category=cat,
                participated=True,
                passed=True,
            )
            training.save()

        if kwargs["phone_number_private"] != "":
            prefix = "\n" if mem.comments else ""
            mem.comments += prefix + "Telefon (Privat): " + kwargs["phone_number_private"]
            mem.save()

        if kwargs["phone_number_parents"] != "":
            prefix = "\n" if mem.comments else ""
            mem.comments += prefix + "Telefon (Eltern): " + kwargs["phone_number_parents"]
            mem.save()

    for row in rows:
        transform_row(row)


def parse_group(value):  # pragma: no cover
    groups_raw = re.split(",", value)

    # need to determine if member is youth leader
    roles = set()

    def extract_group_name_and_role(raw):
        obj = re.search(r"^(.*?)(?: \((.*)\))?$", raw)
        is_jl = False
        if obj.group(2) is not None:
            roles.add(obj.group(2).strip())
            if obj.group(2) == "Jugendleiter*in":
                is_jl = True
        return (obj.group(1).strip(), is_jl)

    group_names = [extract_group_name_and_role(raw) for raw in groups_raw if raw != ""]

    if "Jugendleiter*in" in roles:
        group_names.append(("Jugendleiter", False))
    groups = []
    for group_name, is_jl in group_names:
        try:
            group = Group.objects.get(name=group_name)
        except Group.DoesNotExist:
            group = Group(name=group_name)
            group.save()
        groups.append((group, is_jl))
    return groups


def parse_date(value):  # pragma: no cover
    if value == "":
        return None
    return datetime.strptime(value, "%d.%m.%Y").date()


def parse_datetime(value):  # pragma: no cover
    tz = pytz.timezone("Europe/Berlin")
    if value == "":
        return timezone.now()
    return tz.localize(datetime.strptime(value, "%d.%m.%Y %H:%M:%S"))


def parse_status(value):  # pragma: no cover
    return value != "Passivmitglied"


def parse_boolean(value):  # pragma: no cover
    return value.lower() == "ja"


def parse_nullable_boolean(value):  # pragma: no cover
    if value == "":
        return None
    else:
        return value.lower() == "ja"


def parse_gender(value):  # pragma: no cover
    if value == "männlich":
        return MALE
    elif value == "weiblich":
        return FEMALE
    else:
        return DIVERSE


def parse_can_swim(value):  # pragma: no cover
    return True if len(value) > 0 else False


CLUBDESK_TO_KOMPASS = {  # pragma: no cover
    "Nachname": "lastname",
    "Vorname": "prename",
    "Adresse": "street",
    "PLZ": "plz",
    "Ort": "town",
    "Telefon Privat": "phone_number_private",
    "Telefon Mobil": "phone_number",
    "Adress-Zusatz": "address_extra",
    "Land": "country",
    "E-Mail": "email",
    "E-Mail Alternativ": "alternative_email",
    "Status": ("active", parse_status),
    "Eintritt": ("join_date", parse_date),
    "Austritt": ("leave_date", parse_date),
    "Geburtsdatum": ("birth_date", parse_date),
    "Geburtstag": ("birth_date", parse_date),
    "Geschlecht": ("gender", parse_gender),
    "Bemerkungen": "comments",
    "IBAN": "iban",
    "Vorlage Führungszeugnis": ("good_conduct_certificate_presented_date", parse_date),
    "Letzte Fortbildung": ("last_training", parse_date),
    "Grundausbildung": ("has_fundamental_training", parse_boolean),
    "Besondere Ausbildung": "special_training",
    "[Gruppen]": ("group", parse_group),
    "Schlüssel": ("has_key", parse_boolean),
    "Freikarte": ("has_free_ticket_gym", parse_boolean),
    "DAV Ausweis Nr.": "dav_badge_no",
    "Schwimmabzeichen": ("swimming_badge", parse_can_swim),
    "Kletterschein": "climbing_badge",
    "Felserfahrung": "alpine_experience",
    "Allergien": "allergies",
    "Medikamente": "medication",
    "Tetanusimpfung": "tetanus_vaccination",
    "Fotoerlaubnis": ("photos_may_be_taken", parse_boolean),
    "Erziehungsberechtigte": "legal_guardians",
    "Darf sich allein von der Gruppenstunde abmelden": (
        "may_cancel_appointment_independently",
        parse_nullable_boolean,
    ),
    "Mobil Eltern": "phone_number_parents",
    "Sonstiges": "application_text",
    "Erhalten am": ("application_date", parse_datetime),
    "Angeschrieben von": "contacted_by",
    "Angeschrieben von ": "contacted_by",
}


def import_from_csv_waitinglist(path):  # pragma: no cover
    with open(path, encoding="ISO-8859-1") as csvfile:
        reader = csv.DictReader(csvfile, delimiter=";")
        rows = list(reader)

    def transform_field(key, value):
        new_key = CLUBDESK_TO_KOMPASS[key]
        if isinstance(new_key, str):
            return (new_key, value)
        else:
            return (new_key[0], new_key[1](value))

    def transform_row(row):
        kwargs = dict([transform_field(k, v) for k, v in row.items() if k in CLUBDESK_TO_KOMPASS])
        kwargs_filtered = {
            k: v
            for k, v in kwargs.items()
            if k
            in [
                "prename",
                "lastname",
                "email",
                "birth_date",
                "application_text",
                "application_date",
            ]
        }

        mem = MemberWaitingList(gender=DIVERSE, **kwargs_filtered)
        mem.save()

        if kwargs["contacted_by"]:
            group_name = kwargs["contacted_by"]
            try:
                group = Group.objects.get(name=group_name)
                invitation = InvitationToGroup(group=group, waiter=mem)
                invitation.save()
            except Group.DoesNotExist:
                pass

    for row in rows:
        transform_row(row)
