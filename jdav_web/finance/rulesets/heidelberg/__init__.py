"""Heidelberg's finance rules: the reference ruleset.

This is a port of the rules that used to be some forty ``@property``\\ s on
``finance.models.Statement``, and it is deliberately a *faithful* port: same
clamps, same conditions, same fallbacks, same order, to the cent. The one thing
that did change is the arithmetic's type — the properties went through binary
``float`` (``float(settings.ALLOWANCE_PER_DAY)``) although every amount column
is a ``DecimalField``, which made cent-exact reproducibility a matter of luck.
Here everything is :class:`~decimal.Decimal` and rounding happens once, where
the old code called ``utils.cvt_to_decimal``, with the same rounding mode.

The policy, in the order the transfers come out:

**Belege** — every bill the finance officer marked as covered is paid back to
whoever paid it. A covered bill with nobody named is an error: the money is
owed to somebody, and the statement cannot say who.

**Aufwandsentschädigung** — a flat amount per day of the trip, to each youth
leader named, at most as many as the section approved for that trip.

**Zuschuss zu Anreise und Übernachtung** — kilometres at the rate for the way
the group travelled (muscle power and public transport share the higher rate),
plus the nights at the price per night but never more than the section's
maximum, times the number of refinanced leaders, all to one person.

**Organisationsbeitrag** — participants of 27 or older pay a fee per person and
day, charged against the reimbursement rather than collected: it is a transfer
*to* the section. It is only charged when somebody actually claims an allowance
or a subsidy, and never for a trip whose Landesjugendplan goal is
qualification, where the older participants are the point of the trip.

**LJP-Beitrag** — the state's contribution, passed on to one person: the
smallest of the contribution the regulations allow, 90 % of what the trip
actually cost the organisers net of tax, and what the organisers paid out of
pocket. Below five participants in the regulations' sense there is none.

The participants' own contributions are not computed here at all. They are
whatever is left over, and the engine works that out from
:attr:`~kompass.rules.Ruleset.balance`.
"""

from decimal import Decimal
from decimal import ROUND_HALF_DOWN

from kompass.rules import CENT
from kompass.rules import Check
from kompass.rules import Constraint
from kompass.rules import first_of
from kompass.rules import Forbid
from kompass.rules import Input
from kompass.rules import PARTICIPANTS
from kompass.rules import RuleContext
from kompass.rules import Ruleset
from kompass.rules import SECTION
from kompass.rules import Transfer

#: The age from which a participant pays the organisation fee.
ORG_FEE_AGE = 27

#: The share of the trip's cost the Landesjugendplan contributes at most.
LJP_SHARE = Decimal("0.9")

#: Fewer participants than this in the regulations' sense, no contribution.
LJP_MINIMUM_PARTICIPANTS = 5

#: The approaches that travel at the train rate.
TRAIN_RATE_APPROACHES = ("muscle", "public")

#: The permission that lets somebody sign a statement off.
APPROVER_PERMISSION = "finance.process_statementsubmitted"


def cents(amount: Decimal) -> Decimal:
    """``amount`` rounded to the cent, halves downwards.

    The rounding Kompass has always used for money (``utils.cvt_to_decimal``),
    kept so that this port does not quietly move anybody's reimbursement by a
    cent. It is applied where the old properties applied it: once per figure,
    not once per factor.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_DOWN)


class HeidelbergRules(Ruleset):
    """The rules of the JDAV section Heidelberg."""

    name = "heidelberg"
    context_version = 1
    permissions = (APPROVER_PERMISSION,)
    #: Whatever the section pays out net, the participants' contributions
    #: cover. One transfer, built by the engine.
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx: RuleContext) -> list[Input]:
        """The four answers these rules need beyond the statement itself."""
        excursion = ctx.excursion
        leaders = excursion.leaders if excursion is not None else ()
        approved = excursion.approved_staff_count if excursion is not None else 0
        return [
            Input(
                "night_cost",
                "Preis pro Übernachtung",
                "money",
                required=False,
                help=(
                    "Was eine Übernachtung pro Jugendleiter*in gekostet hat. "
                    "Mehr als den Höchstbetrag der Sektion erstattet sie nicht."
                ),
            ),
            Input(
                "allowance_to",
                "Aufwandsentschädigung an",
                "member_set",
                required=False,
                help="Die Jugendleiter*innen, die eine Aufwandsentschädigung bekommen.",
                options=leaders,
                max=approved,
            ),
            Input(
                "subsidy_to",
                "Fahrt- und Übernachtungszuschuss an",
                "member",
                required=False,
                help="Wer die Fahrt- und Übernachtungskosten vorgestreckt hat.",
                options=leaders,
            ),
            Input(
                "ljp_to",
                "LJP-Beitrag an",
                "member",
                required=False,
                help="Nur ausfüllen, wenn ein LJP-Antrag gestellt wurde.",
                options=leaders,
            ),
        ]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        """Resolve the statement, bills first and the LJP contribution last."""
        transfers: list[Transfer] = []
        errors: list[str] = []

        for bill in ctx.bills:
            if not bill.covered:
                continue
            if bill.payer is None:
                errors.append(
                    f"Für den übernommenen Beleg „{bill.description}“ ist nicht "
                    "eingetragen, wer ihn bezahlt hat."
                )
                # The money is owed either way, so it stays in the statement's
                # total; only its recipient is missing.
                transfers.append(
                    Transfer(
                        source=SECTION,
                        destination=PARTICIPANTS,
                        amount=bill.amount,
                        category="bill",
                        rule_id="bills",
                        label=bill.description,
                    )
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

        excursion = ctx.excursion
        if excursion is None:
            return transfers, errors

        params = ctx.params
        allowance_to = ctx.inputs.members("allowance_to")
        subsidy_to = ctx.inputs.member("subsidy_to")
        ljp_to = ctx.inputs.member("ljp_to")

        # Not every youth leader of a trip is refinanced: the section approves a
        # number from the participant count, and that is the ceiling.
        refinanced = min(excursion.staff_count, excursion.approved_staff_count)

        per_day = params.ALLOWANCE_PER_DAY
        per_leader = cents(excursion.duration * per_day)
        for leader in allowance_to:
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=leader,
                    amount=per_leader,
                    category="allowance",
                    rule_id="allowance",
                    label="Aufwandsentschädigung",
                    explanation=f"{excursion.duration} Tage × {per_day} €",
                )
            )

        if subsidy_to is not None:
            if excursion.approach in TRAIN_RATE_APPROACHES:
                per_km = params.AID_PER_KM_TRAIN
            else:
                per_km = params.AID_PER_KM_CAR
            travel = cents(excursion.kilometers * per_km)
            per_night = min(ctx.inputs.money("night_cost"), params.MAX_NIGHT_COST)
            nights = excursion.nights * per_night
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=subsidy_to,
                    amount=(travel + nights) * refinanced,
                    category="subsidy",
                    rule_id="subsidy",
                    label="Zuschuss zu Anreise und Übernachtung",
                    explanation=(
                        f"({excursion.kilometers} km × {per_km} € + "
                        f"{excursion.nights} × {per_night} €) × {refinanced}"
                    ),
                )
            )

        claims_something = subsidy_to is not None or len(allowance_to) > 0
        qualification = excursion.ljp is not None and excursion.ljp.goal == "qualification"
        if claims_something and not qualification:
            older = sum(
                1
                for participant in excursion.participants
                if not participant.is_leader
                and participant.age is not None
                and participant.age >= ORG_FEE_AGE
            )
            fee = cents(params.EXCURSION_ORG_FEE * excursion.duration * older)
            payant = first_of(subsidy_to, *allowance_to)
            if fee and payant is not None:
                transfers.append(
                    Transfer(
                        source=payant,
                        destination=SECTION,
                        amount=fee,
                        category="org_fee",
                        rule_id="org_fee",
                        label="Organisationsbeitrag",
                        explanation=(
                            f"{older} Teilnehmende ab {ORG_FEE_AGE} × "
                            f"{excursion.duration} Tage × {params.EXCURSION_ORG_FEE} €"
                        ),
                    )
                )

        if ljp_to is not None:
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=ljp_to,
                    amount=self._ljp_amount(ctx, transfers),
                    category="ljp",
                    rule_id="ljp",
                    label="LJP-Beitrag",
                )
            )

        return transfers, errors

    def _ljp_amount(self, ctx: RuleContext, transfers: list[Transfer]) -> Decimal:
        """What the Landesjugendplan actually pays out.

        The only rule here that reads another rule's result: the trip's cost to
        its organisers is what they paid out of their own pocket plus what the
        section reimburses them as allowance and subsidy.
        """
        excursion = ctx.excursion
        ljp = excursion.ljp if excursion is not None else None
        if ljp is None or ljp.theoretic_participant_count < LJP_MINIMUM_PARTICIPANTS:
            return Decimal("0.00")
        params = ctx.params
        net = Decimal(1) - params.LJP_TAX
        staff = sum(
            (t.amount for t in transfers if t.category in ("allowance", "subsidy")),
            Decimal("0.00"),
        )
        out_of_pocket = sum(
            (bill.amount for bill in ctx.bills if not bill.covered), Decimal("0.00")
        )
        allowed = net * params.LJP_CONTRIBUTION_PER_DAY * ljp.participant_count * ljp.duration
        share = net * LJP_SHARE * (out_of_pocket + staff)
        return cents(min(allowed, share, out_of_pocket))

    def checks(self, ctx: RuleContext) -> list[Check]:
        """What has to be true before the statement may be handed in."""
        checks = [
            Check(
                ok=not (ctx.inputs.member("ljp_to") is not None and self._without_proof(ctx)),
                message="Wird ein LJP-Beitrag beantragt, braucht jeder Beleg ein Bild.",
            )
        ]
        excursion = ctx.excursion
        if excursion is not None:
            allowance_to = ctx.inputs.members("allowance_to")
            refinanced = min(excursion.staff_count, excursion.approved_staff_count)
            eligible = all(leader in excursion.leaders for leader in allowance_to)
            checks.append(
                Check(
                    ok=len(allowance_to) <= refinanced and eligible,
                    message=(
                        "Eine Aufwandsentschädigung bekommen höchstens "
                        f"{refinanced} Jugendleiter*innen dieser Ausfahrt."
                    ),
                )
            )
        return checks

    def _without_proof(self, ctx: RuleContext) -> bool:
        return any(not bill.has_proof for bill in ctx.bills)

    def approval(
        self, ctx: RuleContext, transfers: list[Transfer]
    ) -> tuple[list[Constraint], list[Forbid]]:
        """One signature from the finance department, and nobody excluded.

        Behaviourally what Heidelberg does today: whoever may process
        submitted statements may confirm one, with no amount threshold and no
        conflict-of-interest rule. Written as a constraint so that adding
        either is an edit to this method.
        """
        return (
            [
                Constraint(
                    name="Freigabe",
                    description="Eine Unterschrift aus der Finanzverwaltung",
                    applicable=True,
                    required=1,
                    eligible=ctx.permission_holders(APPROVER_PERMISSION),
                )
            ],
            [],
        )


#: The ruleset Kompass loads (see :func:`finance.engine.active_ruleset`).
ruleset = HeidelbergRules()

__all__ = ["HeidelbergRules", "cents", "ruleset"]
