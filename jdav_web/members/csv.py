import csv
import datetime
import json

from .models import DIVERSE
from .models import EmergencyContact
from .models import FEMALE
from .models import Group
from .models import MALE
from .models import Member


def get_gender_char(gender):
    if gender == MALE:
        return "m"
    if gender == FEMALE:
        return "f"
    return "d"


def get_gender_from_char(char):
    char = char.lower()
    if char == "m":
        return MALE
    if char == "f":
        return FEMALE
    return DIVERSE


def export_generalized_csv(queryset, file_handle):
    fieldnames = [
        "id",
        "prename",
        "lastname",
        "birth_date",
        "gender",
        "email",
        "alternative_email",
        "phone_number",
        "street",
        "plz",
        "town",
        "address_extra",
        "country",
        "dav_badge_no",
        "ticket_no",
        "swimming_badge",
        "climbing_badge",
        "alpine_experience",
        "allergies",
        "medication",
        "tetanus_vaccination",
        "photos_may_be_taken",
        "legal_guardians",
        "may_cancel_appointment_independently",
        "iban",
        "gets_newsletter",
        "has_key",
        "has_free_ticket_gym",
        "join_date",
        "leave_date",
        "good_conduct_certificate_presented_date",
        "active",
        "groups",
        "emergency_contacts",
    ]
    writer = csv.DictWriter(file_handle, fieldnames=fieldnames)
    writer.writeheader()

    for member in queryset:
        groups = ",".join([g.name for g in member.group.all()])
        ecs = []
        for ec in member.emergencycontact_set.all():
            ecs.append(
                {
                    "prename": ec.prename,
                    "lastname": ec.lastname,
                    "phone_number": ec.phone_number,
                    "email": ec.email,
                }
            )

        row = {
            "id": member.pk,
            "prename": member.prename,
            "lastname": member.lastname,
            "birth_date": member.birth_date.isoformat() if member.birth_date else "",
            "gender": get_gender_char(member.gender),
            "email": member.email,
            "alternative_email": member.alternative_email or "",
            "phone_number": member.phone_number,
            "street": member.street,
            "plz": member.plz,
            "town": member.town,
            "address_extra": member.address_extra,
            "country": member.country,
            "dav_badge_no": member.dav_badge_no,
            "ticket_no": member.ticket_no,
            "swimming_badge": member.swimming_badge,
            "climbing_badge": member.climbing_badge,
            "alpine_experience": member.alpine_experience,
            "allergies": member.allergies,
            "medication": member.medication,
            "tetanus_vaccination": member.tetanus_vaccination,
            "photos_may_be_taken": member.photos_may_be_taken,
            "legal_guardians": member.legal_guardians,
            "may_cancel_appointment_independently": member.may_cancel_appointment_independently
            if member.may_cancel_appointment_independently is not None
            else "",
            "iban": member.iban,
            "gets_newsletter": member.gets_newsletter,
            "has_key": member.has_key,
            "has_free_ticket_gym": member.has_free_ticket_gym,
            "join_date": member.join_date.isoformat() if member.join_date else "",
            "leave_date": member.leave_date.isoformat() if member.leave_date else "",
            "good_conduct_certificate_presented_date": member.good_conduct_certificate_presented_date.isoformat()
            if member.good_conduct_certificate_presented_date
            else "",
            "active": member.active,
            "groups": groups,
            "emergency_contacts": json.dumps(ecs),
        }
        writer.writerow(row)


def import_generalized_csv(file_handle, email_domain_override=None):
    """
    Import members from a CSV file.

    Args:
        file_handle: File handle for the CSV file
        email_domain_override: Optional domain to replace all email domains with
    """
    reader = csv.DictReader(file_handle)
    created_members = []

    def override_email_domain(email):
        """Replace email domain if override is specified."""
        if not email or not email_domain_override:
            return email
        if "@" in email:
            local_part = email.split("@")[0]
            return f"{local_part}@{email_domain_override}"
        return email  # pragma: no cover

    for row in reader:
        birth_date = None
        if row.get("birth_date"):
            birth_date = datetime.datetime.strptime(row["birth_date"], "%Y-%m-%d").date()

        join_date = None
        if row.get("join_date"):
            join_date = datetime.datetime.strptime(row["join_date"], "%Y-%m-%d").date()

        leave_date = None
        if row.get("leave_date"):
            leave_date = datetime.datetime.strptime(row["leave_date"], "%Y-%m-%d").date()

        gcc_date = None
        if row.get("good_conduct_certificate_presented_date"):
            gcc_date = datetime.datetime.strptime(
                row["good_conduct_certificate_presented_date"], "%Y-%m-%d"
            ).date()

        may_cancel = None
        if row.get("may_cancel_appointment_independently"):
            val = row["may_cancel_appointment_independently"].strip()
            if val.lower() in ["true", "false"]:
                may_cancel = val.lower() == "true"

        member = Member(
            prename=row.get("prename", "fehlt"),
            lastname=row.get("lastname", "fehlt"),
            birth_date=birth_date,
            email=override_email_domain(row.get("email", "")),
            gender=get_gender_from_char(row.get("gender", "d")),
            alternative_email=override_email_domain(row.get("alternative_email")) if row.get("alternative_email") else None,
            phone_number=row.get("phone_number", ""),
            street=row.get("street", ""),
            plz=row.get("plz", ""),
            town=row.get("town", ""),
            address_extra=row.get("address_extra", ""),
            country=row.get("country", ""),
            dav_badge_no=row.get("dav_badge_no", ""),
            ticket_no=row.get("ticket_no", ""),
            swimming_badge=row.get("swimming_badge", "").lower() == "true",
            climbing_badge=row.get("climbing_badge", ""),
            alpine_experience=row.get("alpine_experience", ""),
            allergies=row.get("allergies", ""),
            medication=row.get("medication", ""),
            tetanus_vaccination=row.get("tetanus_vaccination", ""),
            photos_may_be_taken=row.get("photos_may_be_taken", "").lower() == "true",
            legal_guardians=row.get("legal_guardians", ""),
            may_cancel_appointment_independently=may_cancel,
            iban=row.get("iban", ""),
            gets_newsletter=row.get("gets_newsletter", "true").lower() == "true",
            has_key=row.get("has_key", "").lower() == "true",
            has_free_ticket_gym=row.get("has_free_ticket_gym", "").lower() == "true",
            join_date=join_date,
            leave_date=leave_date,
            good_conduct_certificate_presented_date=gcc_date,
            confirmed=row.get("confirmed", "true").lower() == "true",
            active=row.get("active", "true").lower() == "true",
        )
        member.save()

        if row.get("groups"):
            for name in row["groups"].split(","):
                name = name.strip()
                if name:
                    group, _ = Group.objects.get_or_create(name=name)
                    member.group.add(group)

        if row.get("emergency_contacts"):
            try:
                for ec_data in json.loads(row["emergency_contacts"]):
                    EmergencyContact.objects.create(
                        member=member,
                        prename=ec_data.get("prename", ""),
                        lastname=ec_data.get("lastname", ""),
                        phone_number=ec_data.get("phone_number", ""),
                        email=override_email_domain(ec_data.get("email", "")),
                    )
            except json.JSONDecodeError:  # pragma: no cover
                pass

        created_members.append(member)
    return created_members
