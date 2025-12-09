"""
Functions to populate and clear test data.

Can be used in Django migrations or as standalone functions.
"""

import logging
import os
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone
from finance.models import Bill
from finance.models import Statement
from members.csv import import_generalized_csv
from members.models import AUSBILDUNGS_TOUR
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import Freizeit
from members.models import FUEHRUNGS_TOUR
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Group
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList
from members.models import OEFFENTLICHE_ANREISE

logger = logging.getLogger(__name__)


def create_groups():
    """Create test groups."""
    groups_data = [
        {
            "name": "Alpingruppe",
            "description": "Erfahrene Kletterer und Bergsteiger",
            "show_website": True,
            "year_from": 2008,
            "year_to": 2011,
            "weekday": 2,  # Wednesday
        },
        {
            "name": "Klettergruppe",
            "description": "Regelmäßiges Klettertraining in der Halle",
            "show_website": True,
            "year_from": 2010,
            "year_to": 2013,
            "weekday": 4,  # Friday
        },
        {
            "name": "Spielgruppe",
            "description": "Spielerischer Einstieg ins Klettern",
            "show_website": True,
            "year_from": 2012,
            "year_to": 2015,
            "weekday": 1,  # Tuesday
        },
        {
            "name": "Jugendausschuss",
            "description": "Ältere Mitglieder mit Organisationsaufgaben",
            "show_website": False,
            "year_from": 2005,
            "year_to": 2010,
            "weekday": None,
        },
        {
            "name": "Jugendleiter",
            "description": "Ausgebildete Jugendleiter",
            "show_website": False,
            "year_from": 1990,
            "year_to": 2010,
            "weekday": None,
        },
    ]

    for group_data in groups_data:
        Group.objects.get_or_create(name=group_data["name"], defaults=group_data)


def create_members_and_contacts():
    """Create test members with emergency contacts from CSV data."""
    # Find the CSV file path
    # Go up from test_data to jdav_web, then to members/test_data/members.csv
    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_file_path = os.path.join(
        os.path.dirname(current_dir),  # jdav_web
        "test_data",
        "members.csv",
    )

    # Import members from CSV
    if os.path.exists(csv_file_path):
        with open(csv_file_path, encoding="utf-8") as f:
            import_generalized_csv(f)


def create_excursions():
    """Create test excursions (Freizeit)."""
    alpingruppe = Group.objects.filter(name="Alpingruppe").first()
    klettergruppe = Group.objects.filter(name="Klettergruppe").first()

    # Get youth leaders
    tobias = Member.objects.filter(email="tobias.werner@alpenverein-heidelberg.de").first()
    victoria = Member.objects.filter(email="v.schneider@alpenverein-heidelberg.de").first()
    charlotte = Member.objects.filter(email="charlotte.sommer@yahoo.com").first()

    # Get some members from different groups to add as participants
    alpingruppe_members = list(Member.objects.filter(group__name="Alpingruppe", active=True)[:5])
    klettergruppe_members = list(
        Member.objects.filter(group__name="Klettergruppe", active=True)[:5]
    )

    excursions_data = [
        {
            "name": "Klettertour Pfalz",
            "place": "Dahn",
            "postcode": "66994",
            "destination": "Dahner Felsenland",
            "date": timezone.now() - timedelta(days=60),
            "end": timezone.now() - timedelta(days=58),
            "description": "Wochenend-Klettertour im Dahner Felsenland",
            "tour_type": GEMEINSCHAFTS_TOUR,
            "tour_approach": FAHRGEMEINSCHAFT_ANREISE,
            "kilometers_traveled": 120,
            "difficulty": 2,
            "approved": True,
            "groups": [alpingruppe],
            "jugendleiter": [tobias, victoria],
            "participants": alpingruppe_members,
        },
        {
            "name": "Alpenwoche Zillertal",
            "place": "Mayrhofen",
            "postcode": "6290",
            "destination": "Zillertal",
            "date": timezone.now() - timedelta(days=30),
            "end": timezone.now() - timedelta(days=23),
            "description": "Einwöchige Alpentour im Zillertal mit Gletscherwanderung",
            "tour_type": FUEHRUNGS_TOUR,
            "tour_approach": OEFFENTLICHE_ANREISE,
            "kilometers_traveled": 450,
            "difficulty": 3,
            "approved": True,
            "approved_extra_youth_leader_count": 1,
            "groups": [alpingruppe],
            "jugendleiter": [tobias, victoria, charlotte],
            "participants": alpingruppe_members,
        },
        {
            "name": "Kletterkurs Anfänger",
            "place": "Heidelberg",
            "postcode": "69115",
            "date": timezone.now() + timedelta(days=14),
            "end": timezone.now() + timedelta(days=14),
            "description": "Anfängerkurs für Toprope-Klettern",
            "tour_type": AUSBILDUNGS_TOUR,
            "tour_approach": MUSKELKRAFT_ANREISE,
            "kilometers_traveled": 0,
            "difficulty": 1,
            "approved": True,
            "groups": [klettergruppe],
            "jugendleiter": [victoria],
            "participants": klettergruppe_members,
        },
    ]

    created_excursions = []
    for excursion_data in excursions_data:
        groups = excursion_data.pop("groups")
        jugendleiter = excursion_data.pop("jugendleiter")
        participants = excursion_data.pop("participants") + jugendleiter

        # Use get_or_create to avoid duplicates based on name and place
        excursion, created = Freizeit.objects.get_or_create(
            name=excursion_data["name"], place=excursion_data["place"], defaults=excursion_data
        )

        # Add many-to-many relationships
        for group in groups:
            excursion.groups.add(group)
        for jl in jugendleiter:
            excursion.jugendleiter.add(jl)
        freizeit_ct = ContentType.objects.get_for_model(Freizeit)
        for participant in participants:
            NewMemberOnList.objects.get_or_create(
                member=participant,
                content_type=freizeit_ct,
                object_id=excursion.pk,
            )

        created_excursions.append(excursion)

    return created_excursions


def create_statements():
    """Create test financial statements."""
    tobias = Member.objects.filter(email="tobias.werner@alpenverein-heidelberg.de").first()
    victoria = Member.objects.filter(email="v.schneider@alpenverein-heidelberg.de").first()

    # Create statement for the first excursion (Pfalz tour)
    excursion1 = Freizeit.objects.filter(name="Klettertour Pfalz").first()
    statement1, created = Statement.objects.get_or_create(
        short_description="Abrechnung Pfalz-Tour",
        excursion=excursion1,
        defaults={
            "explanation": "Kosten für Klettertour im Dahner Felsenland",
            "night_cost": Decimal("15.00"),
            "status": 0,  # UNSUBMITTED
            "created_by": tobias,
        },
    )

    if created:
        statement1.allowance_to.add(tobias, victoria)
        statement1.subsidy_to = tobias
        statement1.save()

        # Add some bills to the statement
        Bill.objects.get_or_create(
            statement=statement1,
            short_description="Unterkunft",
            defaults={
                "explanation": "Übernachtung Jugendherberge Dahn",
                "amount": Decimal("120.00"),
                "paid_by": tobias,
                "costs_covered": True,
            },
        )

        Bill.objects.get_or_create(
            statement=statement1,
            short_description="Verpflegung",
            defaults={
                "explanation": "Lebensmittel für die Gruppe",
                "amount": Decimal("85.50"),
                "paid_by": victoria,
                "costs_covered": True,
            },
        )

    # Create statement for the second excursion (Zillertal)
    excursion2 = Freizeit.objects.filter(name="Alpenwoche Zillertal").first()
    statement2, created = Statement.objects.get_or_create(
        short_description="Abrechnung Zillertal",
        excursion=excursion2,
        defaults={
            "explanation": "Kosten für Alpenwoche im Zillertal",
            "night_cost": Decimal("20.00"),
            "status": 0,  # UNSUBMITTED
            "created_by": victoria,
        },
    )
    if created:
        statement2.allowance_to.add(tobias, victoria)
        statement2.subsidy_to = victoria
        statement2.save()

        Bill.objects.get_or_create(
            statement=statement2,
            short_description="Unterkunft Hütte",
            defaults={
                "explanation": "Übernachtung Berliner Hütte",
                "amount": Decimal("350.00"),
                "paid_by": victoria,
                "costs_covered": True,
            },
        )

        Bill.objects.get_or_create(
            statement=statement2,
            short_description="Bergführer",
            defaults={
                "explanation": "Bergführer für Gletschertour",
                "amount": Decimal("280.00"),
                "paid_by": tobias,
                "costs_covered": True,
            },
        )


def associate_superuser_with_member():
    """Associate the superuser with a member."""
    superuser = User.objects.filter(is_superuser=True).first()

    # Get Tobias Werner as the admin member
    member = Member.objects.filter(email="tobias.werner@alpenverein-heidelberg.de").first()
    member.user = superuser
    member.save()


def populate_test_data():
    """Main function to populate all test data."""
    create_groups()
    create_members_and_contacts()
    create_excursions()
    create_statements()
    associate_superuser_with_member()
