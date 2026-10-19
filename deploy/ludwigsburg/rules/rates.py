"""The figures of the Sektion Ludwigsburg, and nothing that decides anything.

Every number the section voted on lives here, each one with the document and
the clause it comes from, so that a reviewer can check a rate against the
signed policy without reading a rule. The rules themselves are in
``__init__.py`` and read these.

They are module constants rather than ``ctx.params.*`` because the parameter
names Kompass serves are a fixed list — ``ALLOWANCE_PER_DAY``,
``MAX_NIGHT_COST``, ``AID_PER_KM_TRAIN``, ``AID_PER_KM_CAR``,
``EXCURSION_ORG_FEE``, ``LJP_CONTRIBUTION_PER_DAY``, ``LJP_TAX`` — and not one
of Ludwigsburg's figures is one of them. That is no loss: a constant here is
hashed into the ruleset's version exactly as a parameter would be, so changing
a rate is a new version either way, and here the figure sits next to the clause
that set it.

The sources, as the consolidated specification names them:

``Q2``
    *Reisekostenrichtlinie für ehrenamtlich tätige Mitglieder im Rahmen einer
    Funktion/Referats, Beiräte, Vorsitzende, Geschäftsführung*, Ä1 – 06/2024,
    in force from 01.06.2024.
``Q3``
    *Reisekostenrichtlinie für ehrenamtlich tätige Mitglieder, Trainer\\*innen,
    Tourenleiter\\*innen*, Ä1 – 01/2025, in force from 13.01.2025.
``Q1``
    *Finanzordnung der Sektion Ludwigsburg*, Ä0, signed 25.06.2026.
``Q4``
    „Finanzzeug LuBu“ — informal, and only its three standing
    Sonderabsprachen are treated as policy here.
"""

from decimal import Decimal
from typing import Final

#: The two travel-cost regimes, as :meth:`Inputs.text` reads the choice back.
#:
#: Which one applies is decided by the *role the person was acting in* and not
#: by whether there is an excursion: a Jugendleitung settling a tour is Q3, the
#: same person settling their referat's purchases is Q2. Both happen in the
#: Jugend, which is why this is a question and not a constant.
EHRENAMT: Final = "ehrenamt"
TOURENLEITUNG: Final = "tourenleitung"

#: Q2 Privatfahrzeug: 0,30 € per kilometre, no surcharge for passengers.
EHRENAMT_PER_KM: Final = Decimal("0.30")

#: Q3 Privatfahrzeug: 0,20 € per kilometre.
TOURENLEITUNG_PER_KM: Final = Decimal("0.20")

#: Q3: 0,03 € per kilometre for each further person travelling along.
PASSENGER_PER_KM: Final = Decimal("0.03")

#: Q3: „Maximal sind 0,30 € pro Fahrt möglich.“
#:
#: Read as a ceiling on the rate **per kilometre**, which is the only reading
#: the engine can express — it has `kilometers` as one total and no notion of a
#: single "Fahrt" — and the one the surrounding sentences support, since both
#: figures it caps are per kilometre. So the cap starts biting at four
#: passengers: 0,20 + 4 × 0,03 = 0,32 is paid as 0,30.
TOURENLEITUNG_MAX_PER_KM: Final = Decimal("0.30")

#: Q3 § 3: 10 € per night, flat.
#:
#: Q2 has no flat rate: there, a night is reimbursed against its receipt, which
#: is an ordinary bill and needs no rule.
NIGHT_FLAT_RATE: Final = Decimal("10.00")

#: Q3 § 4: 2,50 € per hour from the section, for a Tourenleitung with a DAV
#: licence.
#:
#: The hourly rate is all of it. The 8 h/day, 200 h/year and 3.000 €/year caps
#: are sums across days, statements and a whole year; the engine sees one
#: statement and is deliberately stateless, and Q3 puts them on the
#: Tourenleitung („eigenverantwortlich“) and on the Geschäftsstelle's annual
#: confirmation. The further 2,50 €/hour for a DOSB licence is paid by the
#: WLSB at the year's end and never by the section, so it is not a transfer
#: this ruleset can write.
TOUR_LEADER_FEE_PER_HOUR: Final = Decimal("2.50")

#: Q1 § 1.2: from this amount a statement needs the treasurer's signature too.
#:
#: Q1 says „Rechnung“; the section reads it as the statement's total, which is
#: what Kompass settles in one go, and that is the figure
#: :meth:`LudwigsburgRules.approval` compares.
SIGNATURE_THRESHOLD: Final = Decimal("1000.00")

#: Q2 § 5: the Tagegeld for the Verpflegungsmehraufwand, by country, as
#: ``(from 8 hours, from 24 hours)``.
#:
#: Q2 only. Q3 has no Tagegeld at all, and a Q3 statement therefore never asks
#: for a country.
PER_DIEM: Final[dict[str, tuple[Decimal, Decimal]]] = {
    "deutschland": (Decimal("14"), Decimal("28")),
    "frankreich": (Decimal("36"), Decimal("53")),
    "italien": (Decimal("28"), Decimal("42")),
    "oesterreich": (Decimal("33"), Decimal("50")),
    "schweiz": (Decimal("43"), Decimal("64")),
}

#: What each country is called on the form, in the order Q2's table lists them.
PER_DIEM_LABELS: Final[dict[str, str]] = {
    "deutschland": "Deutschland",
    "frankreich": "Frankreich",
    "italien": "Italien",
    "oesterreich": "Österreich",
    "schweiz": "Schweiz",
}

#: Nothing, to the cent — the answer of every rule that does not apply.
ZERO: Final = Decimal("0.00")


def euro(amount: Decimal) -> str:
    """``amount`` as the section writes it: two places and a comma.

    For the one line of arithmetic a transfer shows the person reading it.
    """
    return f"{amount:.2f}".replace(".", ",")


def travel_rate(regime: str, passengers: int) -> Decimal:
    """What one kilometre in a private car is worth under ``regime``.

    ``passengers`` are the „weitere Mitfahrende“ of Q3 § 1.5 and are worth
    0,03 € each, up to a rate of 0,30 €. Under Q2 they are worth nothing
    („Bei weiteren Mitfahrenden werden keine zusätzlichen Kosten erstattet“),
    and the question is not even asked — so this never sees a count there.

    With no regime chosen the rate is nothing, because a statement that does
    not say which policy it is settled under settles nothing.
    """
    if regime == EHRENAMT:
        return EHRENAMT_PER_KM
    if regime == TOURENLEITUNG:
        return min(
            TOURENLEITUNG_PER_KM + PASSENGER_PER_KM * passengers,
            TOURENLEITUNG_MAX_PER_KM,
        )
    return ZERO


def per_diem(country: str, nights: int, duration: Decimal) -> Decimal:
    """Q2's Tagegeld for a trip of ``nights`` nights lasting ``duration`` days.

    Q2's table gives two rates, „ab 8 Stunden“ and „ab 24 Stunden“, which is
    the statutory pair: every full day away is worth the 24-hour rate, and the
    day of departure and the day of return are worth the 8-hour rate each. A
    trip of ``n`` nights therefore has ``n - 1`` full days and two travel days.

    A trip of no nights is a Tagestour, which Q2 puts at the 8-hour rate
    („14 Euro (inkl. Tagestouren)“) — **if** it lasted at least eight hours.
    Whether it did is the one thing neither the trip nor the engine records, so
    this reads Kompass's own half-day step as the dividing line: a trip of a
    full day or more is treated as at least eight hours and a half day as less.
    That is an assumption, it is written down in the README, and it is the only
    place a figure here is not straight off the page.
    """
    rates = PER_DIEM.get(country)
    if rates is None:
        return ZERO
    from_eight, from_twentyfour = rates
    if nights >= 1:
        return from_twentyfour * (nights - 1) + from_eight * 2
    return from_eight if duration >= 1 else ZERO
