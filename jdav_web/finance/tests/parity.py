"""The parity suite: the ported rules against the properties they replaced.

``finance.rulesets.heidelberg`` is a port of about forty ``@property``\\ s on
``Statement``. This module pins the port cent-exactly, and it does it the only
way that keeps working after the properties stop computing anything: the old
arithmetic is reproduced here, in :func:`legacy`, exactly as ``models.py``
performed it before the refactor — ``float(settings.X)``, ``float(...)`` again
on the way out of the snapshot, ``0.9`` as a binary float, one
``cvt_to_decimal`` at the end — and compared with what the engine resolves over
a spread of realistic statements.

**What is pinned, exactly.** Five aggregates — ``total_allowance``,
``total_subsidies``, ``total_org_fee``, ``paid_ljp_contributions``, ``total`` —
plus the ``transaction_issues`` targets member by member and the rows
``generate_transactions`` writes. That is the money. The *display* figures the
documents narrate around it (``allowance_per_yl``, ``transportation_per_yl``,
``nights_per_yl``, ``theoretical_total_staff``) are **not** pinned here: they
still compute their own formula until step 5's summaries read rows instead, and
under the awkward numbers below they move for the same two reasons the
aggregates do. Forty properties were *ported*; five aggregates and the payout
are what this suite holds down.

**Where the two differ, and why the new value wins.** Two causes, and they are
not the same thing:

*A half cent decided by a bit pattern.* The old properties put money through
binary floats although every amount column is a ``DecimalField``:
``_capture_settings_snapshot`` stored ``float(settings.X)`` and
``_get_setting`` returned ``float(...)`` again. ``Decimal(21.675)`` is
``21.67500000000000142…``, just above the half cent, so the rounding went *up*
where the section's own ``21,675 €`` sits exactly on the half.

What decides that is worth stating precisely: ``cents()`` rounds
``ROUND_HALF_DOWN``, which is what ``utils.cvt_to_decimal`` has always done, so
the exact half goes down and **the change moves money down by a cent**. The
*rounding mode* decides this, not ``Decimal`` — kaufmännisches Runden
(``ROUND_HALF_UP``) would give the old ``21,68 €``. The port kept the mode it
found; a section that wants commercial rounding is asking for a different
``cents()`` and should say so in its own rules.

*An amount that was never rounded at all.* ``nights_per_yl`` multiplied the
night count by ``Decimal(float(MAX_NIGHT_COST))`` and quantised nothing, so a
maximum a float cannot hold produced a subsidy of 28 significant digits in a
column with two — stored rounded, compared unrounded, and therefore never
reconcilable. That one is a live bug rather than a cent.

:data:`DIFFERENCES` records every figure this suite finds moving, with both
values. The entry that carries real money — ``total_subsidies`` 226.88 → 226.86
— belongs to the *first* cause: 517 km × 0,155 € is 80,135 € exactly, a third
half cent. The unquantised nights are in that number too, but they contribute
about 1e-14 of it.
"""

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.test import override_settings
from django.test import TestCase
from django.utils import timezone
from finance.engine import import_from_directory
from finance.engine import reference_directory
from finance.models import Bill
from finance.models import Statement
from finance.rules_api import SECTION
from members.models import DIVERSE
from members.models import FAHRGEMEINSCHAFT_ANREISE
from members.models import Freizeit
from members.models import GEMEINSCHAFTS_TOUR
from members.models import Intervention
from members.models import LJPProposal
from members.models import Member
from members.models import MUSKELKRAFT_ANREISE
from members.models import NewMemberOnList
from utils import cvt_to_decimal

#: The section's numbers as a stock deployment has them.
HEIDELBERG_PARAMETERS = {
    "ALLOWANCE_PER_DAY": 22,
    "MAX_NIGHT_COST": 11,
    "AID_PER_KM_TRAIN": 0.15,
    "AID_PER_KM_CAR": 0.10,
    "EXCURSION_ORG_FEE": 10,
    "LJP_CONTRIBUTION_PER_DAY": 25,
    "LJP_TAX": 0.2,
}

#: Numbers chosen to land on an exact half cent, which is where a binary float
#: and a ``Decimal`` disagree. A section is free to set these; nothing stops
#: ``22,345 €`` a day.
AWKWARD_PARAMETERS = {
    "ALLOWANCE_PER_DAY": 21.675,
    "MAX_NIGHT_COST": 11.1,
    "AID_PER_KM_TRAIN": 0.155,
    "AID_PER_KM_CAR": 0.105,
    "EXCURSION_ORG_FEE": 10.005,
    "LJP_CONTRIBUTION_PER_DAY": 23.335,
    "LJP_TAX": 0.19,
}


# --- the arithmetic as it was, before the port -----------------------------


class legacy:
    """``models.py`` before this refactor, kept as the thing to agree with.

    Every method is the body of the property it is named after, at
    ``35cbf87``, including its float round trips. Nothing here is used in
    production; it exists so that the parity assertions keep meaning
    "unchanged" once the properties themselves read transfers.
    """

    @staticmethod
    def get_setting(statement, key):
        if (
            statement.submitted
            and statement.settings_snapshot
            and key in statement.settings_snapshot
        ):
            return float(statement.settings_snapshot[key])
        return float(getattr(settings, key, 0))

    @staticmethod
    def euro_per_km(statement):
        if statement.excursion is None:
            return 0
        if statement.excursion.tour_approach in (0, 1):
            return legacy.get_setting(statement, "AID_PER_KM_TRAIN")
        return legacy.get_setting(statement, "AID_PER_KM_CAR")

    @staticmethod
    def transportation_per_yl(statement):
        if statement.excursion is None:
            return 0
        return cvt_to_decimal(
            statement.excursion.kilometers_traveled * legacy.euro_per_km(statement)
        )

    @staticmethod
    def allowance_per_yl(statement):
        if statement.excursion is None:
            return 0
        return cvt_to_decimal(
            statement.excursion.duration * legacy.get_setting(statement, "ALLOWANCE_PER_DAY")
        )

    @staticmethod
    def real_night_cost(statement):
        return min(statement.night_cost, Decimal(legacy.get_setting(statement, "MAX_NIGHT_COST")))

    @staticmethod
    def nights_per_yl(statement):
        if statement.excursion is None:
            return 0
        return statement.excursion.night_count * legacy.real_night_cost(statement)

    @staticmethod
    def real_staff_count(statement):
        if statement.excursion is None:
            return 0
        return min(statement.excursion.staff_count, statement.excursion.approved_staff_count)

    @staticmethod
    def total_allowance(statement):
        return legacy.allowance_per_yl(statement) * len(statement.allowance_to)

    @staticmethod
    def total_subsidies(statement):
        if statement.subsidy_to:
            return (
                legacy.transportation_per_yl(statement) + legacy.nights_per_yl(statement)
            ) * legacy.real_staff_count(statement)
        return cvt_to_decimal(0)

    @staticmethod
    def total_org_fee_theoretical(statement):
        if statement.excursion is None:
            return 0
        return cvt_to_decimal(
            legacy.get_setting(statement, "EXCURSION_ORG_FEE")
            * statement.excursion.duration
            * statement.excursion.old_participant_count
        )

    @staticmethod
    def total_org_fee(statement):
        if not statement.subsidy_to and not statement.allowance_to:
            return cvt_to_decimal(0)
        if hasattr(statement.excursion, "ljpproposal"):
            proposal = statement.excursion.ljpproposal
            if proposal.goal == proposal.LJP_QUALIFICATION:
                return cvt_to_decimal(0)
        return legacy.total_org_fee_theoretical(statement)

    @staticmethod
    def org_fee_payant(statement):
        if legacy.total_org_fee(statement) == 0:
            return None
        if statement.subsidy_to:
            return statement.subsidy_to
        return sorted(statement.allowance_to, key=lambda member: member.pk)[0]

    @staticmethod
    def total_staff(statement):
        return legacy.total_allowance(statement) + legacy.total_subsidies(statement)

    @staticmethod
    def total_bills(statement):
        return sum(bill.amount for bill in statement.bill_set.all() if bill.costs_covered)

    @staticmethod
    def total_bills_not_covered(statement):
        return sum(bill.amount for bill in statement.bill_set.all()) - legacy.total_bills(statement)

    @staticmethod
    def paid_ljp_contributions(statement):
        if hasattr(statement.excursion, "ljpproposal") and statement.ljp_to:
            if statement.excursion.theoretic_ljp_participant_count < 5:
                return 0
            not_covered = float(legacy.total_bills_not_covered(statement))
            return cvt_to_decimal(
                min(
                    (1 - legacy.get_setting(statement, "LJP_TAX"))
                    * legacy.get_setting(statement, "LJP_CONTRIBUTION_PER_DAY")
                    * statement.excursion.ljp_participant_count
                    * statement.excursion.ljp_duration,
                    (1 - legacy.get_setting(statement, "LJP_TAX"))
                    * 0.9
                    * (not_covered + float(legacy.total_staff(statement))),
                    not_covered,
                )
            )
        return 0

    @staticmethod
    def total(statement):
        return (
            legacy.total_bills(statement)
            + legacy.total_staff(statement)
            - legacy.total_org_fee(statement)
            + legacy.paid_ljp_contributions(statement)
        )

    @staticmethod
    def targets(statement):
        """``{member: amount}``, as ``transaction_issues`` derived it."""
        amounts: dict[Member, Decimal] = {}

        def add(member, amount):
            amounts[member] = amounts.get(member, Decimal(0)) + amount

        for bill in statement.bill_set.all():
            if bill.costs_covered and bill.paid_by:
                add(bill.paid_by, bill.amount)
        if statement.excursion is not None:
            for leader in statement.allowance_to:
                add(leader, legacy.allowance_per_yl(statement))
        if statement.subsidy_to:
            add(statement.subsidy_to, legacy.total_subsidies(statement))
        if legacy.total_org_fee(statement):
            add(legacy.org_fee_payant(statement), -legacy.total_org_fee(statement))
        if statement.ljp_to:
            add(statement.ljp_to, legacy.paid_ljp_contributions(statement))
        return amounts


# --- the fixtures ----------------------------------------------------------


@dataclass
class Trip:
    """An excursion to settle, as a scenario describes it."""

    #: Nights away; ``0`` is a day trip, which counts as one day.
    nights: int = 0
    #: Kilometres there and back.
    kilometers: int = 0
    #: ``MUSKELKRAFT_ANREISE`` (train rate) or ``FAHRGEMEINSCHAFT_ANREISE``.
    approach: int = MUSKELKRAFT_ANREISE
    #: How many youth leaders led it.
    leaders: int = 1
    #: Ages of the people on the member list, leaders aside.
    participant_ages: tuple[int, ...] = ()
    #: Extra leaders the section approved beyond the participant ratio.
    extra_approved: int = 0
    #: The LJP proposal's goal, or ``None`` for a trip without one.
    ljp_goal: int | None = None
    #: Hours of programme per day, which is what seminar days are counted from.
    interventions: tuple[float, ...] = ()


@dataclass
class Scenario:
    """One statement worth comparing, described in the terms a treasurer uses."""

    name: str
    #: ``(description, amount, covered, with_payer)`` per receipt.
    bills: tuple[tuple[str, str, bool, bool], ...] = ()
    trip: Trip | None = None
    #: What one night cost, as the person handing in the statement typed it.
    night_cost: str = "0"
    #: How many of the leaders claim the allowance.
    allowance_to: int = 0
    #: Whether somebody claims the travel and night subsidy.
    subsidy: bool = False
    #: Whether an LJP contribution is claimed.
    ljp: bool = False
    #: Whether every bill carries a scan.
    proofs: bool = True


#: The spread the suite runs over: no trip, bills only, allowance only,
#: subsidy only, both, the fee charged and the fee exempt, the LJP claimed and
#: below its cutoff, and uncovered bills feeding the LJP.
SCENARIOS = (
    Scenario(name="nothing at all"),
    Scenario(
        name="bills only, no trip",
        bills=(("Essen", "67.30", True, True), ("Geschenk", "10.00", False, True)),
    ),
    Scenario(
        name="a covered bill nobody paid",
        bills=(("Hüttenrechnung", "42.00", True, False),),
    ),
    Scenario(
        name="a day trip with an allowance and one older participant",
        trip=Trip(nights=0, leaders=2, participant_ages=(14, 15, 16, 17, 30)),
        allowance_to=2,
    ),
    Scenario(
        name="a night at exactly the maximum",
        trip=Trip(nights=2, kilometers=200, leaders=2, participant_ages=(14, 15, 16, 17)),
        night_cost="11.10",
        subsidy=True,
    ),
    Scenario(
        name="allowance only",
        trip=Trip(nights=3, leaders=4, participant_ages=(14, 15, 16, 17, 18, 19, 20, 21)),
        allowance_to=3,
    ),
    Scenario(
        name="subsidy only, nights above the maximum",
        trip=Trip(nights=3, kilometers=517, leaders=4, participant_ages=(14, 15, 16, 17)),
        night_cost="27.00",
        subsidy=True,
    ),
    Scenario(
        name="subsidy by car, nights below the maximum",
        trip=Trip(
            nights=2,
            kilometers=321,
            approach=FAHRGEMEINSCHAFT_ANREISE,
            leaders=3,
            participant_ages=(14, 15, 16, 17, 18),
        ),
        night_cost="7.50",
        subsidy=True,
    ),
    Scenario(
        name="allowance and subsidy, organisation fee charged",
        trip=Trip(
            nights=3,
            kilometers=512,
            leaders=3,
            participant_ages=(30, 41, 27, 16, 15, 14, 13, 12),
        ),
        night_cost="27.00",
        allowance_to=2,
        subsidy=True,
        bills=(("Essen", "42.69", True, True),),
    ),
    Scenario(
        name="organisation fee with no subsidy recipient, charged to the first allowance",
        trip=Trip(nights=1, leaders=2, participant_ages=(30, 41, 16, 15)),
        allowance_to=2,
    ),
    Scenario(
        name="a qualification trip charges no organisation fee",
        trip=Trip(
            nights=2,
            kilometers=100,
            leaders=2,
            participant_ages=(30, 41, 16, 15),
            ljp_goal=LJPProposal.LJP_QUALIFICATION,
            interventions=(6.0, 6.0),
        ),
        allowance_to=1,
        subsidy=True,
        night_cost="11.00",
    ),
    Scenario(
        name="LJP claimed, capped by the regulations",
        trip=Trip(
            nights=3,
            kilometers=120,
            leaders=2,
            participant_ages=(14, 15, 16, 17, 18, 19, 20, 21, 22),
            ljp_goal=LJPProposal.LJP_ENVIRONMENT,
            interventions=(2.0, 3.0, 4.0),
        ),
        bills=(("Bus", "300.00", True, True), ("Hütte", "900.00", False, True)),
        ljp=True,
        night_cost="11.00",
    ),
    Scenario(
        name="LJP claimed, capped by what the trip cost its organisers",
        trip=Trip(
            nights=3,
            kilometers=120,
            leaders=2,
            participant_ages=(14, 15, 16, 17, 18, 19, 20, 21, 22),
            ljp_goal=LJPProposal.LJP_PARTICIPATION,
            interventions=(6.0, 6.0, 6.0),
        ),
        bills=(("Material", "80.05", False, True),),
        allowance_to=2,
        subsidy=True,
        ljp=True,
        night_cost="9.95",
    ),
    Scenario(
        name="LJP claimed below the five-participant cutoff",
        trip=Trip(
            nights=1,
            leaders=1,
            participant_ages=(4, 5, 70),
            ljp_goal=LJPProposal.LJP_DEVELOPMENT,
            interventions=(6.0,),
        ),
        bills=(("Hütte", "900.00", False, True),),
        ljp=True,
    ),
    Scenario(
        name="everything at once",
        trip=Trip(
            nights=4,
            kilometers=733,
            leaders=5,
            participant_ages=(28, 31, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23),
            extra_approved=1,
            ljp_goal=LJPProposal.LJP_ENVIRONMENT,
            interventions=(5.5, 3.0, 2.5, 6.0),
        ),
        bills=(
            ("Bus", "412.55", True, True),
            ("Essen", "233.33", True, True),
            ("Hütte", "1020.90", False, True),
        ),
        night_cost="13.75",
        allowance_to=3,
        subsidy=True,
        ljp=True,
    ),
)


def _member(index, age=None):
    birth = timezone.now().date()
    if age is not None:
        birth = birth - relativedelta(years=age, days=1)
    return Member.objects.create(
        prename=f"Person {index}",
        lastname="Parität",
        birth_date=birth,
        email=settings.TEST_MAIL,
        gender=DIVERSE,
    )


def with_parameters(parameters):
    """Import a ruleset version whose parameters are ``parameters``.

    The section's numbers are a version's data now, and a statement is settled
    against the version that was active when it was created — so a scenario
    under different numbers is a scenario under a different version, and
    importing one is how a test asks for them. The sources are the same, the
    parameters are not, so the hash is not either, which is exactly what makes
    a parameter change a new version rather than an edit to a settled one.
    """
    return import_from_directory(reference_directory())


def build(scenario):
    """The statement a scenario describes, saved and ready to evaluate."""
    # The answers, under the keys the rules declare rather than in the four
    # columns this suite was written against.
    answers = {"night_cost": scenario.night_cost}
    statement = Statement.objects.create(short_description=scenario.name[:30], inputs=answers)
    leaders = []
    if scenario.trip is not None:
        trip = scenario.trip
        start = timezone.now().replace(hour=8, minute=0, second=0, microsecond=0)
        excursion = Freizeit.objects.create(
            name=scenario.name[:50],
            kilometers_traveled=trip.kilometers,
            tour_type=GEMEINSCHAFTS_TOUR,
            tour_approach=trip.approach,
            difficulty=1,
            date=start,
            end=(start + timedelta(days=trip.nights)).replace(hour=17),
            approved_extra_youth_leader_count=trip.extra_approved,
        )
        for index in range(trip.leaders):
            leader = _member(f"L{index}", age=25)
            excursion.jugendleiter.add(leader)
            leaders.append(leader)
        for index, age in enumerate(trip.participant_ages):
            NewMemberOnList.objects.create(
                member=_member(f"P{index}", age=age), memberlist=excursion
            )
        if trip.ljp_goal is not None:
            proposal = LJPProposal.objects.create(
                title=scenario.name[:50],
                category=LJPProposal.LJP_EDUCATIONAL,
                goal=trip.ljp_goal,
                excursion=excursion,
            )
            for index, hours in enumerate(trip.interventions):
                Intervention.objects.create(
                    date_start=start + timedelta(days=index, hours=4),
                    duration=hours,
                    activity="Programm",
                    ljp_proposal=proposal,
                )
        statement.excursion = excursion

    payer = leaders[0] if leaders else _member("Z", age=33)
    for description, amount, covered, with_payer in scenario.bills:
        Bill.objects.create(
            statement=statement,
            short_description=description,
            amount=Decimal(amount),
            costs_covered=covered,
            paid_by=payer if with_payer else None,
            proof="bill_images/proof.pdf" if scenario.proofs else "",
        )
    if scenario.subsidy and leaders:
        answers["subsidy_to"] = leaders[0].pk
    if scenario.ljp and leaders:
        answers["ljp_to"] = leaders[-1].pk
    if scenario.allowance_to:
        # **Reversed on purpose.** The legacy reference this suite compares
        # against bills the organisation fee to `sorted(allowance_to)[0]`,
        # because `allowance_to.order_by("pk")[0]` is what the column did; the
        # engine bills `first_of(*allowance_to)`, the first element as the
        # answer holds it. Writing the ids already sorted made the two agree
        # whether or not anything normalised the order, so this suite
        # structurally could not see the normalisation go missing — and it did
        # go missing when the column became a list. Written backwards, the
        # agreement is evidence.
        answers["allowance_to"] = [
            leader.pk for leader in reversed(leaders[: scenario.allowance_to])
        ]
    statement.inputs = answers
    statement.save()
    return statement


#: Every difference this suite found between the old float arithmetic and the
#: engine's ``Decimal``, as ``(parameters, scenario, figure): (before, after)``.
#:
#: There are none under :data:`HEIDELBERG_PARAMETERS`: a stock deployment's
#: numbers (``22``, ``11``, ``0.15``, ``0.10``, ``10``, ``25``, ``0.2``) either
#: are binary-exact or never land on a half cent, which is why nobody noticed.
#: They are all under :data:`AWKWARD_PARAMETERS`, and they come in two shapes.
#:
#: **A half cent decided by the binary expansion** (cause one). The entries
#: for the day trip, the qualification trip — and ``total_subsidies`` /
#: ``total`` wherever an *odd* number of kilometres meets ``0,155 €`` or
#: ``0,105 €``, which is where the real money is. ``Decimal(21.675)`` is
#: ``21.67500000000000142108547152020037174224853515625``, just above the half
#: cent, so the old code rounded *up* to ``21.68`` while the section's own
#: ``21,675 €`` sits exactly on the half; ``517 × 0,155`` is ``80,135``
#: exactly, the same story one factor along. ``ROUND_HALF_DOWN`` — Kompass's
#: historical mode, which the port kept — then takes the half down, so these
#: move money down by a cent. See the module docstring on why that is the
#: mode's doing and not ``Decimal``'s.
#:
#: **An amount that was never rounded at all** (cause two). ``nights_per_yl``
#: multiplied the night count by ``Decimal(float(MAX_NIGHT_COST))`` and
#: quantised nothing, so a maximum that a float cannot hold — ``11,10 €`` —
#: produced ``106.3999999999999985789145285``: 28 significant digits into a
#: column with two. ``Transaction.amount`` would store it rounded while
#: ``transaction_issues`` compared against the unrounded figure, so such a
#: statement could never be brought into agreement and never confirmed. That
#: is the live bug. It is also why several entries below carry a long decimal
#: on the left: the tail is this cause, while the cent that actually moved is
#: usually cause one.
DIFFERENCES: dict[tuple[str, str, str], tuple[str, str]] = {
    # 21,675 € a day, twice, on a one-day trip.
    ("awkward", "a day trip with an allowance and one older participant", "total_allowance"): (
        "43.36",
        "43.34",
    ),
    # 10,005 € × 1 day × 1 participant of 30.
    ("awkward", "a day trip with an allowance and one older participant", "total_org_fee"): (
        "10.01",
        "10.00",
    ),
    ("awkward", "a day trip with an allowance and one older participant", "total"): (
        "33.35",
        "33.34",
    ),
    # 21,675 € × 1,5 days × 2 leaders.
    ("awkward", "a qualification trip charges no organisation fee", "total_allowance"): (
        "65.03",
        "65.02",
    ),
    ("awkward", "a qualification trip charges no organisation fee", "total"): (
        "140.03",
        "140.02",
    ),
    # The night cost clamped to a maximum no float can hold.
    ("awkward", "a night at exactly the maximum", "total_subsidies"): (
        "106.3999999999999985789145285",
        "106.40",
    ),
    ("awkward", "a night at exactly the maximum", "total"): (
        "106.3999999999999985789145285",
        "106.40",
    ),
    # Cause one, in the kilometres: 517 × 0,155 € = 80,135 € exactly, twice
    # over for two refinanced leaders. The long tail on the left is cause two
    # (the unquantised nights) and worth about 1e-14 of it.
    ("awkward", "subsidy only, nights above the maximum", "total_subsidies"): (
        "226.8799999999999978683717928",
        "226.86",
    ),
    ("awkward", "subsidy only, nights above the maximum", "total"): (
        "226.8799999999999978683717928",
        "226.86",
    ),
    ("awkward", "allowance and subsidy, organisation fee charged", "total_subsidies"): (
        "337.9799999999999968025576892",
        "337.98",
    ),
    ("awkward", "allowance and subsidy, organisation fee charged", "total"): (
        "434.0099999999999968025576892",
        "434.01",
    ),
    ("awkward", "everything at once", "total_subsidies"): (
        "632.0399999999999943156581140",
        "632.04",
    ),
    ("awkward", "everything at once", "total"): (
        "2466.949999999999994315658114",
        "2466.95",
    ),
}


class ParityTestCase(TestCase):
    """Every money figure of every scenario, old arithmetic against new."""

    maxDiff = None

    def _compare(self, parameters_name, scenario, statement):
        figures = {
            "total_allowance": (
                legacy.total_allowance(statement),
                statement.rule_result.total_of("allowance"),
            ),
            "total_subsidies": (
                legacy.total_subsidies(statement),
                statement.rule_result.total_of("subsidy"),
            ),
            "total_org_fee": (
                legacy.total_org_fee(statement),
                statement.rule_result.total_of("org_fee"),
            ),
            "paid_ljp_contributions": (
                legacy.paid_ljp_contributions(statement),
                statement.rule_result.total_of("ljp"),
            ),
            "total": (legacy.total(statement), statement.total),
        }
        for figure, (before, after) in figures.items():
            key = (parameters_name, scenario.name, figure)
            expected = DIFFERENCES.get(key)
            with self.subTest(figure=figure):
                if expected is None:
                    self.assertEqual(
                        Decimal(str(before)),
                        Decimal(str(after)),
                        f"{figure} of “{scenario.name}” under {parameters_name} moved",
                    )
                else:
                    self.assertEqual(
                        (str(before), str(after)),
                        expected,
                        f"{figure} of “{scenario.name}” under {parameters_name} is a "
                        "documented difference, but not the documented one",
                    )

    def _run(self, parameters_name, parameters):
        with override_settings(**parameters):
            with_parameters(parameters)
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario.name):
                    statement = build(scenario)
                    self._compare(parameters_name, scenario, statement)

    def test_the_stock_numbers(self):
        self._run("heidelberg", HEIDELBERG_PARAMETERS)

    def test_numbers_that_land_on_a_half_cent(self):
        self._run("awkward", AWKWARD_PARAMETERS)

    def test_the_recipients_and_amounts_a_payout_consists_of(self):
        """``transaction_issues`` targets, member by member and cent by cent."""
        with override_settings(**HEIDELBERG_PARAMETERS):
            with_parameters(HEIDELBERG_PARAMETERS)
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario.name):
                    statement = build(scenario)
                    before = {
                        member.pk: Decimal(str(amount))
                        for member, amount in legacy.targets(statement).items()
                    }
                    issues = statement.transaction_issues
                    after = {issue.member.pk: Decimal(str(issue.target)) for issue in issues}
                    # Only recipients whose amount is zero *and* who have no
                    # transaction yet are left out of the issue list, which is
                    # what the old property did too.
                    before = {pk: amount for pk, amount in before.items() if amount != 0}
                    self.assertEqual(before, after)

    def test_the_generated_transactions(self):
        """The rows ``generate_transactions`` writes, amount and reference."""
        with override_settings(**HEIDELBERG_PARAMETERS):
            with_parameters(HEIDELBERG_PARAMETERS)
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario.name):
                    statement = build(scenario)
                    expected = legacy.targets(statement)
                    generated = statement.generate_transactions()
                    rows = statement.transaction_set.all()
                    if not generated:
                        self.assertEqual(rows.count(), 0)
                        self.assertTrue(
                            any("Beleg" in error for error in statement.rule_result.errors)
                        )
                        continue
                    booked: dict[int, Decimal] = {}
                    for row in rows:
                        booked[row.member.pk] = booked.get(row.member.pk, Decimal(0)) + row.amount
                    self.assertEqual(
                        {member.pk: Decimal(str(amount)) for member, amount in expected.items()},
                        booked,
                    )
                    self.assertEqual(
                        Decimal(str(legacy.total(statement))),
                        sum((row.amount for row in rows), Decimal(0)),
                    )

    def test_a_submitted_statement_is_settled_against_its_own_snapshot(self):
        """The snapshot keeps its grip after the numbers change under it.

        ``_get_setting`` reads the snapshot for a submitted statement, and the
        port has to read the same one — including through the engine's
        ``Decimal(str(...))``, where the snapshot holds the JSON float the old
        code wrote.
        """
        with override_settings(**HEIDELBERG_PARAMETERS):
            with_parameters(HEIDELBERG_PARAMETERS)
            scenario = SCENARIOS[-1]
            statement = build(scenario)
            statement.submit(submitter=statement.excursion.jugendleiter.first())
        with override_settings(ALLOWANCE_PER_DAY=99, MAX_NIGHT_COST=99):
            self.assertEqual(
                Decimal(str(legacy.total_allowance(statement))),
                statement.rule_result.total_of("allowance"),
            )
            self.assertEqual(
                Decimal(str(legacy.get_setting(statement, "ALLOWANCE_PER_DAY"))),
                statement._get_setting("ALLOWANCE_PER_DAY"),
            )
            self.assertEqual(statement._get_setting("ALLOWANCE_PER_DAY"), Decimal("22.0"))

    def test_the_old_arithmetic_had_a_branch_for_a_statement_without_a_trip(self):
        """What the replaced properties answered when there was no excursion.

        ``finance.tests.models.test_statement_without_excursion`` pins the
        properties that are still there; this pins the reference
        implementation beside it, so the comparison above means the same thing
        for a statement that settles a purchase rather than a trip.
        """
        statement = build(SCENARIOS[1])
        self.assertEqual(legacy.euro_per_km(statement), 0)
        self.assertEqual(legacy.transportation_per_yl(statement), 0)
        self.assertEqual(legacy.nights_per_yl(statement), 0)
        self.assertEqual(legacy.real_staff_count(statement), 0)
        self.assertEqual(legacy.total_org_fee_theoretical(statement), 0)
        self.assertIsNone(legacy.org_fee_payant(statement))
        self.assertEqual(legacy.allowance_per_yl(statement), 0)

    def test_the_section_comes_out_at_zero(self):
        """What the section pays out is what the balancing transfer brings in.

        The ruleset declares that the participants' contributions cover
        whatever is left (``balance = (PARTICIPANTS, SECTION, …)``), so the
        section's net position over *every* transfer, the engine's own
        included, has to be nothing — for every scenario, under numbers chosen
        to be awkward.
        """
        with override_settings(**AWKWARD_PARAMETERS):
            with_parameters(AWKWARD_PARAMETERS)
            for scenario in SCENARIOS:
                with self.subTest(scenario=scenario.name):
                    result = build(scenario).rule_result
                    paid = sum(
                        (t.amount for t in result.transfers if t.source == SECTION), Decimal(0)
                    )
                    received = sum(
                        (t.amount for t in result.transfers if t.destination == SECTION),
                        Decimal(0),
                    )
                    self.assertEqual(paid, received)
                    self.assertEqual(
                        [t.rule_id for t in result.transfers].count("balance"),
                        1,
                        "there must be exactly one balancing transfer",
                    )
