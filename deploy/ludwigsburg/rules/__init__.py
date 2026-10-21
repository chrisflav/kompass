"""The finance rules of the JDAV Sektion Ludwigsburg.

This is the section's real configuration, and the worked example of
``deploy/config-template/``. It implements what the section's four signed and
standing documents say about money — the two travel-cost policies Q2 and Q3,
the Finanzordnung's signatures, and the three Sonderabsprachen out of
„Finanzzeug LuBu“. ``rates.py`` beside it holds every figure with the clause it
comes from; what is deliberately *not* implemented is in the README, under
"What this ruleset does not do".

**Two regimes, chosen by the role somebody was acting in.** Ludwigsburg has
two travel-cost policies in force at once, and they differ in nearly every
rate: Q2 for Ehrenamt und Verwaltung (0,30 €/km, Tagegeld, nights against
receipts) and Q3 for Tourenleitung (0,20 €/km plus 0,03 € per passenger,
10 €/night flat, 2,50 €/hour). Which applies is not decided by whether there is
an excursion — both happen in the Jugend, and the same person falls under both
in the same month. So the first question is which policy this statement is
settled under, and :meth:`LudwigsburgRules.relevant_inputs` then puts away the
questions the other one asks. A question that is put away reads as its type's
empty value, so the regime cannot be worked around by an answer left over from
before it was changed.

**The trip's own figures are not questions.** The nights and the duration are
declared with :attr:`~kompass.rules.Input.source`, so the engine supplies them
from the excursion and the form shows them as figures. A statement that settles
a purchase or a repair has no excursion, and the same declarations are then
ordinary questions. Either way the rules read them the same way, which is why
there is not one ``if ctx.excursion is None`` in this file.

**The journeys are a table, one row per traveller.** A statement settles a trip
several people went on, and they travelled differently: one drove, one took the
train, one cycled. Whether somebody gets the rate per kilometre *at all* is
decided by *their* means of travel — a private car yes, the Bahn no, because
there the ticket is the claim — so the means and the distance belong to the same
person in the same row. ``reisen`` is therefore a
:data:`~kompass.rules.InputType` ``rows`` question, and ``_travel`` pays each
row under its own approach at its own distance. The two cells the trip does
record, the kilometres and the approach, name a
:attr:`~kompass.rules.Field.seed`: a trip opens the statement with **one row**,
already filled in, which the person then corrects or splits into as many as
there were travellers. A seed is written once and stays theirs — unlike a
``source``, which is the excursion's and is refused on the form. A statement
with no trip seeds no row and the table starts empty.

The policy, in the order the transfers come out:

**Belege** — every bill the finance officer marked as covered is paid back to
whoever paid it. A covered bill with nobody named is reported as an error,
because the money is owed to somebody and the statement cannot say who. This is
also the whole of Q2's overnight rule and of both policies' rules for Bahn,
Fernbus and ÖPNV: those are reimbursed against their receipts, and a receipt
needs no rate.

**Fahrtkosten** — per row of ``reisen``: the kilometres of a *private car* at
the regime's rate, to the person who drove that row. Nothing when the section
booked a Stadtmobil (Q2/Q3: „Eine Abrechnung weiterer Fahrtkosten ist nicht
möglich“) and nothing for a journey to a Aus-/Fortbildung or a Arbeitseinsatz,
where both policies refuse travel costs outright — both of those are facts of
the whole statement and take the table away whole.

**Übernachtungspauschale** — Q3 only: 10 € per night to each Tourenleitung
named. Not claimable when a sleeper replaced the night (Q2/Q3 § 1.1) and not
claimable when the leaders had no overnight costs at all, which is the 5+1 rule
in Alpenvereinshütten and Sonderabsprache 3.

**Tagegeld** — Q2 only: the statutory Verpflegungsmehraufwand by country, to
each person named. This is also how a Arbeitseinsatz is settled, where Q2 puts
the Verpflegungsmehraufwand „in Höhe des entsprechenden Tagegeldes“.

**Tourenleitervergütung** — Q3 only: 2,50 € per hour to one Tourenleitung with
a DAV licence. The hourly rate only; its caps are not this engine's to keep,
and the README says so.

**Teilnehmerbeiträge** — not computed here at all. Whatever the section pays
out net is what the participants' contributions have to cover, and the engine
works that out from :attr:`~kompass.rules.Ruleset.balance`.

Everything a rule may know is in the :class:`~kompass.rules.RuleContext` it is
given. There is no clock, no database and no way to reach either — see the
"A section's finance rules" page of the Kompass documentation.
"""

from decimal import Decimal
from decimal import ROUND_HALF_UP

from kompass.rules import CENT
from kompass.rules import Check
from kompass.rules import Choice
from kompass.rules import Constraint
from kompass.rules import Field
from kompass.rules import Forbid
from kompass.rules import Input
from kompass.rules import Member
from kompass.rules import PARTICIPANTS
from kompass.rules import Row
from kompass.rules import RuleContext
from kompass.rules import Ruleset
from kompass.rules import SECTION
from kompass.rules import Transfer

from .rates import EHRENAMT
from .rates import euro
from .rates import NIGHT_FLAT_RATE
from .rates import per_diem
from .rates import PER_DIEM_LABELS
from .rates import SIGNATURE_THRESHOLD
from .rates import TOUR_LEADER_FEE_PER_HOUR
from .rates import TOURENLEITUNG
from .rates import travel_rate
from .rates import ZERO

#: The section roles the signatures are routed by.
#:
#: Each one is a :class:`finance.store.RoleAssignment` in the admin, with the
#: dates it was held, so that a statement from 2026 is approved by whoever was
#: the treasurer in 2026. **A role nobody holds means nobody may sign that
#: constraint** — the engine's safe reading — so all six have to be assigned
#: before the first statement can be approved. The README says this twice.
TREASURER = "schatzmeister"
YOUTH_LEADERSHIP = "jugendleitung"
DEPARTMENT_LEADERSHIP = "ressortleitung"
DEPUTY_CHAIR = "stellv_vorsitz"
DEPUTY_CHAIR_FINANCE = "stellv_vorsitz_finanzen"
FIRST_CHAIR = "erste_vorsitzende"

#: Everybody Q1 § 1.2 lets sign a statement on the strength of their office.
#:
#: One eligible set rather than four constraints, because Q1's first three
#: lines differ only in *who is being paid*: the group or department
#: leadership signs, unless it is their own statement, in which case the
#: responsible deputy chair does, unless it is a chair's own statement, in
#: which case the deputy chair for finance or the first chair does. That
#: "unless it is their own" is the Forbid below, which the engine subtracts
#: from every eligible set before it counts a quorum — so the three lines are
#: one constraint plus one conflict-of-interest rule, and not three
#: constraints that have to agree with each other.
SIGNING_ROLES = (
    YOUTH_LEADERSHIP,
    DEPARTMENT_LEADERSHIP,
    DEPUTY_CHAIR,
    DEPUTY_CHAIR_FINANCE,
    FIRST_CHAIR,
)

#: The value of :attr:`~kompass.rules.Excursion.approach` that the per-kilometre
#: rates apply to. Muscle power is free and public transport is a receipt.
CAR = "car"

#: How somebody got there, as one row of ``reisen`` says it.
#:
#: Kompass's own three words, and that is not an economy: a cell that names a
#: :attr:`~kompass.rules.Field.seed` is prefilled from
#: :attr:`~kompass.rules.Excursion.approach`, and a seeded value its own cell
#: does not offer is left empty. Listing exactly what the trip can record is
#: what makes the prefilled row arrive filled in.
#:
#: Bahn, Fernbus and ÖPNV are one word here — ``public`` — because this ruleset
#: never has to tell them apart: all three are reimbursed „in Höhe der Kosten
#: gegen Vorlage von Belegen“, which is an ordinary covered bill and no rate at
#: all. What the row records about them is that this person did not drive.
APPROACHES = (
    Choice("muscle", "Muskelkraft"),
    Choice("public", "Öffentliche Verkehrsmittel (Bahn, Fernbus, ÖPNV)"),
    Choice(CAR, "Privatfahrzeug"),
)

#: How many journeys one statement may list.
#:
#: Generous on purpose: the rows are not one per leader but one per *traveller*,
#: and a there-and-back somebody chose to enter in two halves is two of them.
#: What bounds it in practice is who may be named — the trip's leaders, or
#: whoever paid a receipt — and not this number, which is here so that a
#: mis-sent request is refused rather than stored.
MAX_JOURNEYS = 12

#: The longest single journey a row may claim, in kilometres.
#:
#: Q2 and Q3 both say „kürzeste der möglichen Verbindungen“, and there is no
#: shortest connection from Ludwigsburg longer than this. A row that breaks it
#: is a typo — a decimal point in the wrong place — and the form refuses it
#: where it was typed.
MAX_KILOMETERS = 2000

#: The most „weitere Mitfahrende“ one car may carry (Q3 § 1.5).
#:
#: The cap of 0,30 €/km is reached at four, so everything above it is worth the
#: same; the ceiling is here to catch the row that meant the whole group.
MAX_PASSENGERS = 8

#: The questions only Q2 asks. Under Q3 they are off the form and read empty.
EHRENAMT_ONLY = frozenset({"country", "per_diem_to"})

#: The questions only Q3 asks. Under Q2 they are off the form and read empty —
#: which is what makes the regime decide the money rather than merely label it:
#: an hour count answered under Q3 and left behind when the regime was
#: corrected to Q2 cannot pay a Vergütung Q2 does not know, because Q2 never
#: reads it.
#:
#: ``reisen`` is in neither set, and its ``passengers`` cell therefore cannot be
#: taken off the form under Q2: the cells of a table belong to the declaration,
#: and a regime narrows *keys* rather than columns. Nothing moves on it all the
#: same — :func:`travel_rate` is where „Bei weiteren Mitfahrenden werden keine
#: zusätzlichen Kosten erstattet“ lives, and Q2's rate does not read the count.
#: The column says whose it is in its own help text, and ``cases/04`` pins that
#: a count of five does not move Q2 by a cent.
TOURENLEITUNG_ONLY = frozenset(
    {
        "participant_list_filed",
        "sleeper_car",
        "no_night_cost",
        "nights_to",
        "hours",
        "fee_to",
    }
)


def cents(amount: Decimal) -> Decimal:
    """``amount`` rounded to the cent, halves upwards.

    Rounding is the section's decision, which is why the engine refuses an
    amount finer than a cent instead of rounding it for you. Ludwigsburg's
    figures are all whole cents per unit — 0,20 €/km, 10 €/night, 2,50 €/hour —
    so this only ever has something to do for the passenger surcharge, and even
    there a whole number of kilometres times a rate in whole cents is exact.
    It is applied to every figure all the same, because a rate that gains a
    third decimal place one day should not be the day a statement stops
    resolving.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


def chosen_regime(ctx: RuleContext) -> str:
    """Which regime the answers so far name, or ``""`` for none yet.

    Read defensively rather than with :meth:`~kompass.rules.Inputs.text`,
    because :meth:`LudwigsburgRules.relevant_inputs` is asked against contexts
    whose answers are whatever has been stored so far — on a statement nobody
    has answered yet, and in the fuzzer, the key is simply not there. Inside
    ``transfers`` and ``checks`` it is always there, because the engine fills
    the whole vocabulary in, and those read it through the typed accessor.
    """
    if "regime" not in ctx.inputs.declared():
        return ""
    answer = ctx.inputs.raw("regime")
    return answer if isinstance(answer, str) else ""


def payee_source(ctx: RuleContext) -> str:
    """Where a question that names a recipient takes its people from.

    The trip's youth leaders where there is a trip, which is every statement
    settling a tour or a Freizeit. A statement that settles a purchase or a
    repair has none, and then the people it can pay are whoever paid one of its
    receipts — and, for a statement that has no receipts either, the person who
    created it, which is the one name a statement always carries.
    """
    if ctx.excursion is not None and ctx.excursion.leaders:
        return "excursion.leaders"
    if any(bill.payer is not None for bill in ctx.bills):
        return "bills.payers"
    return "statement.creator"


def driver_of(journey: Row) -> Member | None:
    """Who one row of ``reisen`` owes the per-kilometre rate to, or ``None``.

    One definition of "this row claims the Kilometerpauschale", read by
    :meth:`LudwigsburgRules._travel` and by the two checks that are about the
    same thing, so that the money and the sentences cannot drift apart.

    Three ways a row claims nothing, and none of them is an error:

    * **Another means of travel.** Muskelkraft costs nothing, and Bahn, Fernbus
      and ÖPNV are reimbursed against their receipts — the row records that this
      person did not drive, which is worth recording and worth no rate.
    * **Nobody named.** A row is filled in gradually and a cell may be empty;
      an empty one reads as ``None`` and pays nobody.
    * **No distance.** A person can always type a zero, and a journey of no
      kilometres is worth no kilometres.
    """
    if journey.text("approach") != CAR:
        return None
    if journey.number("kilometers") <= 0:
        return None
    return journey.member("member")


class LudwigsburgRules(Ruleset):
    """The rules of the JDAV Sektion Ludwigsburg."""

    #: Shown in the admin and in the logs.
    name = "ludwigsburg"
    #: The context shape these rules were written against.
    context_version = 1
    #: The date this combination of documents was in force from: the
    #: Finanzordnung Ä0, which is the youngest of the four and the one that
    #: decides the signatures. Q2 has applied since 01.06.2024 and Q3 since
    #: 13.01.2025, so every rate here is older than this date; the
    #: Finanzordnung is what completes them into one policy.
    valid_from = "2026-06-25"
    #: No permission codename is read: Q1 routes every signature by office, so
    #: :meth:`approval` reads :meth:`~kompass.rules.RuleContext.role_holders`
    #: and nothing else.
    permissions = ()
    #: Whatever the section pays out net, the participants' contributions
    #: cover. One transfer, built by the engine.
    #:
    #: For a Freizeit that is literally what happens. For a Verwaltungs- or
    #: Referatsabrechnung there are no participants, and the row is the
    #: section's own budget carrying the cost — the engine allows no third
    #: party here, and a member may not be one, so this is the shape the
    #: residue has either way.
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx: RuleContext) -> list[Input]:
        """Every answer the rules below may read, in the order to ask for them.

        This is the whole vocabulary, both regimes included;
        :meth:`relevant_inputs` is what decides which half is on the form. It
        reads no answer, because the context it is asked against during a
        context build still holds the raw stored JSON.
        """
        payees = payee_source(ctx)
        return [
            Input(
                "regime",
                "Nach welchem Regelwerk wird abgerechnet?",
                "choice",
                step="Grundlagen",
                help=(
                    "Maßgeblich ist die Rolle, in der du unterwegs warst — nicht, "
                    "ob es eine Ausfahrt gab."
                ),
                choices=(
                    Choice(
                        EHRENAMT,
                        "Ehrenamt und Verwaltung (Referat, Beirat, Vorstand, Geschäftsführung)",
                    ),
                    Choice(
                        TOURENLEITUNG,
                        "Tourenleitung (Gruppenstunde, Tour, Jugendfreizeit, Ausbildung)",
                    ),
                ),
            ),
            Input(
                "training_or_work",
                "Fahrt im Rahmen einer Aus-/Fortbildung oder eines Arbeitseinsatzes",
                "bool",
                required=False,
                step="Grundlagen",
                help=(
                    "Dann trägt die Sektion die Ausbildung bzw. die Nächtigungen, "
                    "aber die Fahrtkosten sind nicht abrechenbar."
                ),
            ),
            Input(
                "participant_list_filed",
                "Teilnehmerliste lag vor Antritt im Service-Center und mindestens "
                "3 Sektionsmitglieder waren dabei",
                "bool",
                required=False,
                step="Grundlagen",
                help="Voraussetzung für die Genehmigung einer Tourenleitungsabrechnung (3+1).",
            ),
            Input(
                "stadtmobil",
                "Fahrzeug über Stadtmobil gebucht",
                "bool",
                required=False,
                step="Fahrt",
                help="Stadtmobil rechnet direkt mit der Sektion ab.",
            ),
            Input(
                "reisen",
                "Fahrten",
                "rows",
                required=False,
                step="Fahrt",
                max=MAX_JOURNEYS,
                options_source=payees,
                help=(
                    "Eine Zeile je Person. Die Kilometerpauschale gibt es nur für das "
                    "Privatfahrzeug; Bahn, Fernbus und ÖPNV werden gegen Beleg "
                    "erstattet. Hin- und Rückfahrt zusammen in eine Zeile."
                ),
                fields=(
                    Field(
                        "member",
                        "Person",
                        "member",
                        help="Wer diese Strecke zurückgelegt hat.",
                    ),
                    Field(
                        "approach",
                        "Verkehrsmittel",
                        "choice",
                        choices=APPROACHES,
                        # Prefilled from the trip, and then the person's own:
                        # the excursion records how the *group* travelled, and
                        # the group is exactly who travelled differently.
                        seed="excursion.approach",
                    ),
                    Field(
                        "kilometers",
                        "Kilometer",
                        "int",
                        max=MAX_KILOMETERS,
                        seed="excursion.kilometers",
                        help=(
                            "Nur die kürzeste der möglichen Verbindungen; "
                            "Parkgebühren sind abgedeckt."
                        ),
                    ),
                    Field(
                        "passengers",
                        "Mitfahrende",
                        "int",
                        required=False,
                        max=MAX_PASSENGERS,
                        help=(
                            "Nur Tourenleitung: je Person 0,03 € pro Kilometer, "
                            "insgesamt höchstens 0,30 € pro Kilometer. Das Ehrenamt "
                            "erstattet keine Zuschläge und liest die Zahl nicht."
                        ),
                    ),
                ),
            ),
            Input(
                "nights",
                "Nächte",
                "int",
                required=False,
                step="Übernachtung",
                source="excursion.nights",
            ),
            Input(
                "sleeper_car",
                "Schlafwagen benutzt",
                "bool",
                required=False,
                step="Übernachtung",
                help="Der Schlafwagen tritt an die Stelle der Übernachtungskosten.",
            ),
            Input(
                "no_night_cost",
                "Den Leitenden sind keine Übernachtungskosten entstanden",
                "bool",
                required=False,
                step="Übernachtung",
                help=(
                    "5+1-Regel in Alpenvereinshütten, oder die Förderung trägt die "
                    "Kosten. Dann darf keine Pauschale abgerechnet werden."
                ),
            ),
            Input(
                "nights_to",
                "Übernachtungspauschale an",
                "member_set",
                required=False,
                step="Übernachtung",
                options_source=payees,
                help="Je Person 10 € pro Nacht.",
            ),
            Input(
                "duration",
                "Dauer in Tagen",
                "money",
                required=False,
                step="Tagegeld",
                source="excursion.duration",
            ),
            Input(
                "country",
                "Land",
                "choice",
                required=False,
                step="Tagegeld",
                help="Das Tagegeld richtet sich nach dem Land und der Dauer.",
                choices=tuple(Choice(value, label) for value, label in PER_DIEM_LABELS.items()),
            ),
            Input(
                "per_diem_to",
                "Tagegeld an",
                "member_set",
                required=False,
                step="Tagegeld",
                options_source=payees,
            ),
            Input(
                "hours",
                "Geleistete Stunden",
                "int",
                required=False,
                step="Tourenleitervergütung",
                help=(
                    "2,50 € je Stunde mit DAV-Lizenz. Die Grenzen von 8 Stunden am Tag, "
                    "200 Stunden im Jahr und 3.000 € im Jahr verfolgt die Tourenleitung "
                    "eigenverantwortlich; Kompass sieht nur diese eine Abrechnung."
                ),
            ),
            Input(
                "fee_to",
                "Tourenleitervergütung an",
                "member",
                required=False,
                step="Tourenleitervergütung",
                options_source=payees,
                help="Eine Abrechnung je Tourenleitung, wie der Buchungsbeleg selbst.",
            ),
        ]

    def relevant_inputs(self, ctx: RuleContext) -> list[Input]:
        """The vocabulary without the other regime's questions.

        The trip's own figures — nights, duration — stay in both arms: they are
        facts of the statement rather than questions, and each regime's
        arithmetic reads the ones it needs. So does ``reisen``: both policies
        pay a private car, only at different rates, and a journey is a fact of
        the statement in the same way. Everything the other policy *asks* for is
        off the form, and the rules read it as unanswered, so no leftover answer
        can move money under a regime that does not know the question.

        A table is narrowed by key and not by column, so ``reisen`` keeps its
        ``passengers`` cell under Q2 as well. Q2's rate does not read it —
        :func:`travel_rate` is the one place the surcharge exists — so the
        guarantee this method is for still holds for the count; what it does not
        buy is taking the column off the form.

        Until a regime is chosen, neither half is asked. That is the first
        step of the form doing its job, and the check below says so.
        """
        regime = chosen_regime(ctx)
        if regime == EHRENAMT:
            hidden = TOURENLEITUNG_ONLY
        elif regime == TOURENLEITUNG:
            hidden = EHRENAMT_ONLY
        else:
            hidden = EHRENAMT_ONLY | TOURENLEITUNG_ONLY
        return [declaration for declaration in self.inputs(ctx) if declaration.key not in hidden]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        """Resolve the statement into transfers, plus anything wrong with it.

        No branch on whether there is an excursion: the figures a trip would
        carry are declared with a ``source`` and read the same way either way,
        and the journeys are a table that a trip merely *seeds* — an empty one
        is what a statement settling a purchase arrives with, and a table pays
        per row, so nothing here asks whether there was a trip.
        """
        transfers: list[Transfer] = []
        errors: list[str] = []

        for bill in ctx.bills:
            # A bill that is not covered stays in the context on purpose: it is
            # what somebody paid out of their own pocket, and it belongs in the
            # statement's total even where no rule pays it back.
            if not bill.covered:
                continue
            if bill.payer is None:
                errors.append(
                    f"Für den übernommenen Beleg „{bill.description}“ ist nicht "
                    "eingetragen, wer ihn bezahlt hat."
                )
                continue
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=bill.payer,
                    amount=bill.amount,
                    category="bill",
                    rule_id="bills",
                    label=bill.description,
                )
            )

        regime = ctx.inputs.text("regime")
        transfers.extend(self._travel(ctx, regime))
        transfers.extend(self._nights(ctx, regime))
        transfers.extend(self._per_diem(ctx, regime))
        transfers.extend(self._tour_leader_fee(ctx, regime))
        return transfers, errors

    def _travel(self, ctx: RuleContext, regime: str) -> list[Transfer]:
        """Each traveller's own kilometres, at the regime's rate (Q2/Q3 § 1).

        One transfer per row of ``reisen`` that drove: its own distance, its own
        passenger count, to the person the row names. Which is the whole reason
        the question is a table — the rate is not a property of the statement
        but of a journey, and the journeys of one statement differ.

        Bahn, Fernbus and ÖPNV need no rule: both policies reimburse them „in
        Höhe der Kosten gegen Vorlage von Belegen“, which is an ordinary covered
        bill. Their rows are still worth entering — they are how the statement
        says who travelled how — and they pay nothing here, because the receipt
        is the claim. What this rule is for is the one case where the section
        owes money against no receipt at all.

        Two facts take the whole table away rather than a row, because that is
        the grain they are true at: a Stadtmobil booked through the
        Service-Center is settled with the section directly („Eine Abrechnung
        weiterer Fahrtkosten ist nicht möglich“), and on a journey to a
        Aus-/Fortbildung or a Arbeitseinsatz both policies refuse travel costs
        outright. Neither is asked per person today — see the README.
        """
        if ctx.inputs.flag("stadtmobil") or ctx.inputs.flag("training_or_work"):
            return []
        transfers: list[Transfer] = []
        for journey in ctx.inputs.rows("reisen"):
            driver = driver_of(journey)
            if driver is None:
                continue
            # The count is read under both regimes, because a table's columns
            # do not change with the regime — and it moves nothing under Q2,
            # because `travel_rate` is where „Bei weiteren Mitfahrenden werden
            # keine zusätzlichen Kosten erstattet“ lives.
            rate = travel_rate(regime, journey.number("passengers"))
            if rate == ZERO:
                continue
            kilometers = journey.number("kilometers")
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=driver,
                    amount=cents(kilometers * rate),
                    category="travel",
                    rule_id="travel",
                    label="Fahrtkosten",
                    explanation=f"{kilometers} km × {euro(rate)} €",
                )
            )
        return transfers

    def _nights(self, ctx: RuleContext, regime: str) -> list[Transfer]:
        """Q3 § 3: 10 € per night to each Tourenleitung named.

        Three things take it away, and all three are the policy's own words: a
        sleeper that „tritt an die Stelle der Übernachtungskosten“, the 5+1
        rule in Alpenvereinshütten, and Sonderabsprache 3 — where the funding
        covers the participants' costs and the leaders have none of their own,
        no flat rate may be claimed. The last two are one question, because
        they are one fact: the leaders were not out of pocket.
        """
        if regime != TOURENLEITUNG:
            return []
        if ctx.inputs.flag("sleeper_car") or ctx.inputs.flag("no_night_cost"):
            return []
        nights = ctx.inputs.number("nights")
        if nights <= 0:
            return []
        per_person = cents(nights * NIGHT_FLAT_RATE)
        return [
            Transfer(
                source=SECTION,
                destination=person,
                amount=per_person,
                category="nights",
                rule_id="nights",
                label="Übernachtungspauschale",
                explanation=f"{nights} Nächte × {euro(NIGHT_FLAT_RATE)} €",
            )
            for person in ctx.inputs.members("nights_to")
        ]

    def _per_diem(self, ctx: RuleContext, regime: str) -> list[Transfer]:
        """Q2 § 5: the Verpflegungsmehraufwand by country and duration.

        Also Q2 § 7, where a Arbeitseinsatz on a hut is settled with „den
        Verpflegungsmehraufwand in Höhe des entsprechenden Tagegeldes“: same
        rule, same table, and the Fahrtkosten the same clause refuses are
        already refused above.
        """
        if regime != EHRENAMT:
            return []
        people = ctx.inputs.members("per_diem_to")
        if not people:
            return []
        country = ctx.inputs.text("country")
        nights = ctx.inputs.number("nights")
        amount = cents(per_diem(country, nights, ctx.inputs.money("duration")))
        if amount == ZERO:
            return []
        return [
            Transfer(
                source=SECTION,
                destination=person,
                amount=amount,
                category="per_diem",
                rule_id="per_diem",
                label="Tagegeld",
                explanation=f"{PER_DIEM_LABELS[country]}, {nights} Nächte",
            )
            for person in people
        ]

    def _tour_leader_fee(self, ctx: RuleContext, regime: str) -> list[Transfer]:
        """Q3 § 4: 2,50 € per hour, to one Tourenleitung with a DAV licence.

        The hourly rate and nothing else. The 8 h/day and 200 h/year ceilings
        are sums over days and over a year, the 3.000 € one is a sum over every
        tax-free payment the person received from anybody, and a rule sees one
        statement and has no memory — Q3 puts all three on the Tourenleitung
        and on the Geschäftsstelle's annual confirmation, which is where they
        stay.
        """
        if regime != TOURENLEITUNG:
            return []
        recipient = ctx.inputs.member("fee_to")
        hours = ctx.inputs.number("hours")
        if recipient is None or hours <= 0:
            return []
        return [
            Transfer(
                source=SECTION,
                destination=recipient,
                amount=cents(hours * TOUR_LEADER_FEE_PER_HOUR),
                category="tour_leader_fee",
                rule_id="tour_leader_fee",
                label="Tourenleitervergütung",
                explanation=f"{hours} Stunden × {euro(TOUR_LEADER_FEE_PER_HOUR)} €",
            )
        ]

    def checks(self, ctx: RuleContext) -> list[Check]:
        """What has to be true before the statement may be handed in.

        Always the same six, in the same order, whatever the statement looks
        like: a check carries its message in both states, and a list that
        changed length with the regime would make a case's ``checks`` depend on
        which arm it is in.
        """
        regime = ctx.inputs.text("regime")
        journeys = ctx.inputs.rows("reisen")
        travellers = [
            person
            for person in (journey.member("member") for journey in journeys)
            if person is not None
        ]
        return [
            Check(
                ok=all(bill.has_proof for bill in ctx.bills),
                message=(
                    "Jeder Beleg braucht ein Bild, mit Datum, Firma, Menge, Artikel und Preis."
                ),
            ),
            Check(
                ok=regime in (EHRENAMT, TOURENLEITUNG),
                message=(
                    "Es muss angegeben sein, nach welchem Regelwerk abgerechnet wird: "
                    "Ehrenamt und Verwaltung oder Tourenleitung."
                ),
            ),
            Check(
                ok=not (
                    ctx.inputs.flag("stadtmobil")
                    and any(driver_of(journey) is not None for journey in journeys)
                ),
                message=(
                    "Läuft die Fahrt über Stadtmobil, rechnet die Sektion direkt ab; "
                    "weitere Fahrtkosten sind dann nicht abrechenbar."
                ),
            ),
            Check(
                # A cell may be empty — the form is filled in gradually and the
                # engine stores a row either way — so the sentence that refuses
                # a half-filled journey is the section's own. Without it the row
                # would simply pay nothing, which is the silence this replaces.
                ok=all(
                    journey.member("member") is not None and journey.text("approach") != ""
                    for journey in journeys
                ),
                message=(
                    "Jede Fahrt braucht eine Person und ein Verkehrsmittel. "
                    "Die Kilometerpauschale gibt es nur für das Privatfahrzeug; "
                    "Bahn, Fernbus und ÖPNV werden gegen Beleg erstattet."
                ),
            ),
            Check(
                # The engine accepts the same person in two rows on purpose: it
                # cannot tell a double entry from a there-and-back somebody
                # split in two, and refusing would make the honest table
                # unsayable to catch a mistake it cannot recognise. So the
                # sentence is Ludwigsburg's, and it says how to write the
                # journey it would otherwise be mistaken for.
                ok=len(set(travellers)) == len(travellers),
                message=(
                    "Jede Person steht höchstens einmal in der Fahrtentabelle. "
                    "Hin- und Rückfahrt gehören als Gesamtstrecke in eine Zeile."
                ),
            ),
            Check(
                # Self-reported, and that is as far as Kompass can take it: a
                # participant's membership of the section is not in the
                # context, and whether a list reached the Service-Center
                # before the group left is not in Kompass at all.
                ok=regime != TOURENLEITUNG or ctx.inputs.flag("participant_list_filed"),
                message=(
                    "Eine Tourenleitungsabrechnung setzt voraus, dass die Teilnehmerliste "
                    "vor Antritt im Service-Center lag und mindestens 3 Sektionsmitglieder "
                    "dabei waren (3+1)."
                ),
            ),
        ]

    def approval(
        self, ctx: RuleContext, transfers: list[Transfer]
    ) -> tuple[list[Constraint], list[Forbid]]:
        """Q1 § 1.2 and § 2.4: who has to sign, and who may not.

        Four constraints and one forbid. The amount they are routed by is what
        the section pays out to people on this statement — Q1 says
        „Rechnung“, and a Kompass statement is settled in one go, so the
        section reads the threshold against the statement's total. The
        balancing transfer is not part of it: it is between the section and the
        participants and is the consequence of the payouts rather than one of
        them.
        """
        paid = {t.destination for t in transfers if isinstance(t.destination, Member)}
        total = sum(
            (
                t.amount
                for t in transfers
                if t.source == SECTION and isinstance(t.destination, Member)
            ),
            ZERO,
        )
        ljp = ctx.excursion is not None and ctx.excursion.ljp is not None
        leadership = self._holders(ctx, SIGNING_ROLES)
        treasurer = self._holders(ctx, (TREASURER,))
        return (
            [
                Constraint(
                    name="Freigabe der Leitung",
                    description=(
                        "Die zuständige Gruppen- oder Ressortleitung, die stellvertretende "
                        "Vorsitzende oder die 1. Vorsitzende — wer selbst abrechnet, "
                        "unterschreibt nicht selbst."
                    ),
                    applicable=True,
                    required=1,
                    eligible=leadership,
                ),
                Constraint(
                    name="Schatzmeister (über 1.000 €)",
                    description=(
                        f"Abrechnungen über {euro(SIGNATURE_THRESHOLD)} € brauchen "
                        "zusätzlich die Unterschrift des Schatzmeisters, der auch die "
                        "Richtigkeit prüft."
                    ),
                    applicable=total > SIGNATURE_THRESHOLD,
                    required=1,
                    eligible=treasurer,
                ),
                Constraint(
                    name="Jugendleitung (Landesjugendplan)",
                    description=(
                        "Betrifft die Abrechnung den Landesjugendplan, unterschreibt die "
                        "Jugendleitung — unabhängig vom Betrag. Rechnet die Jugendleitung "
                        "selbst ab, unterschreibt die zuständige stellvertretende "
                        "Vorsitzende an ihrer Stelle."
                    ),
                    applicable=ljp,
                    required=1,
                    # A reading, and it is in the README: Q1 § 2.4 names the
                    # Jugendleitung, and § 1.2 says whoever claims does not
                    # release their own claim. Both at once would make a
                    # Jugendleitung's own LJP statement unapprovable by
                    # anybody, because the forbid empties the only eligible
                    # set there is — so § 1.2's own answer for a group
                    # leadership's own claim, the responsible deputy chair, is
                    # in this set too. The treasurer's signature is required
                    # separately either way, which is the control § 2.4 is
                    # really about.
                    eligible=self._holders(ctx, (YOUTH_LEADERSHIP, DEPUTY_CHAIR)),
                ),
                Constraint(
                    name="Schatzmeister (Landesjugendplan)",
                    description=(
                        "Abrechnungen, die den Landesjugendplan betreffen, laufen immer "
                        "über den Schatzmeister — unabhängig vom Betrag."
                    ),
                    applicable=ljp,
                    required=1,
                    eligible=treasurer,
                ),
            ],
            [
                # Q1's „eigene Abrechnung“, and it wins unconditionally: if the
                # only person who may sign is also being paid, the statement
                # waits for somebody else rather than paying itself out.
                Forbid(
                    name="Eigene Abrechnung",
                    applies_to=lambda member: member in paid,
                )
            ],
        )

    def _holders(self, ctx: RuleContext, roles: tuple[str, ...]) -> tuple[Member, ...]:
        """Everybody holding one of ``roles``, deduplicated and in id order.

        One person may hold two of them — the deputy chair for finance is a
        deputy chair — and an eligible set is a set.
        """
        named: set[Member] = set()
        for role in roles:
            named.update(ctx.role_holders(role))
        return tuple(sorted(named, key=lambda member: int(member.id)))


#: The ruleset Kompass loads. One instance, shared across every evaluation in
#: the process — so it keeps no state: everything a method needs is in the
#: context it is given.
ruleset = LudwigsburgRules()

__all__ = ["LudwigsburgRules", "cents", "ruleset"]
