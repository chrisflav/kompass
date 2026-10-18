"""The finance rules of JDAV <Sektion>.

Rename the class, the ``name`` and the section in this docstring, then make the
rules say what your section actually does. What is here is a starting point
rather than a stub: it settles a real statement, its cases pass, and every
method is one you will edit rather than delete.

The policy below, in the order the transfers come out:

**Belege** — every bill the finance officer marked as covered is paid back to
whoever paid it. A covered bill with nobody named is reported as an error,
because the money is owed to somebody and the statement cannot say who.

**Aufwandsentschädigung** — a flat amount per day of the trip, to each youth
leader named on the statement, at most as many as the section approved for that
trip.

**Teilnehmerbeiträge** — not computed here at all. Whatever the section pays
out net is what the participants' contributions have to cover, and the engine
works that out from :attr:`~kompass.rules.Ruleset.balance`. That is the one
transfer this file does not write.

Everything a rule may know is in the :class:`~kompass.rules.RuleContext` it is
given. There is no clock, no database and no way to reach either — see the
"A section's finance rules" page of the Kompass documentation for what that
means in practice and for the whole of ``kompass.rules``.
"""

from decimal import Decimal
from decimal import ROUND_HALF_UP

from kompass.rules import CENT
from kompass.rules import Check
from kompass.rules import Constraint
from kompass.rules import Forbid
from kompass.rules import Input
from kompass.rules import Member
from kompass.rules import PARTICIPANTS
from kompass.rules import RuleContext
from kompass.rules import Ruleset
from kompass.rules import SECTION
from kompass.rules import Transfer

#: The permission that lets somebody sign a statement off. It is resolved by
#: the engine before evaluation and read back with `permission_holders`,
#: because rules cannot query the database themselves.
APPROVER_PERMISSION = "finance.process_statementsubmitted"


def cents(amount: Decimal) -> Decimal:
    """``amount`` rounded to the cent, halves upwards.

    Rounding is the section's decision, which is why the engine refuses an
    amount finer than a cent instead of rounding it for you. Halves upwards is
    one choice; `kompass.rules.quantize` (towards minus infinity),
    `kompass.rules.split` (a total divided n ways, adding back up exactly) and
    `kompass.rules.pct` (basis points of an amount) are the others.
    """
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


class SectionRules(Ruleset):
    """The rules of the JDAV section <Sektion>."""

    #: Shown in the admin and in the logs. Name it after your section.
    name = "section"
    #: The context shape these rules were written against. Kompass refuses to
    #: load a ruleset written against a newer one; raise this only when you
    #: start using a field a newer context added.
    context_version = 1
    #: Every permission codename `approval` reads. Resolving them is the
    #: engine's job, and an undeclared one raises rather than coming back
    #: empty.
    permissions = (APPROVER_PERMISSION,)
    #: The residual party: whatever the section pays out net, the participants'
    #: contributions cover. The engine appends exactly one transfer with the
    #: amount that brings the *destination* -- the section -- to zero.
    #:
    #: It must be between the section and the participants. A member may not be
    #: a balance party: a person is a payee and not a ledger, and balancing
    #: against one would make whoever it names the sink for everything the
    #: rules did not account for.
    balance = (PARTICIPANTS, SECTION, "participant_contribution")

    def inputs(self, ctx: RuleContext) -> list[Input]:
        """Declare every answer the rules below read.

        The statement's form is generated from these, so a question is asked
        because a rule reads its answer -- and reading a key that was never
        declared raises instead of quietly returning nothing.
        """
        excursion = ctx.excursion
        # A statement does not have to settle a trip: a purchase or a repair
        # has `ctx.excursion is None`, and every rule has to say what it does
        # then.
        leaders = excursion.leaders if excursion is not None else ()
        approved = excursion.approved_staff_count if excursion is not None else 0
        return [
            Input(
                "allowance_to",
                "Aufwandsentschädigung an",
                "member_set",
                required=False,
                help="Die Jugendleiter*innen, die eine Aufwandsentschädigung bekommen.",
                # Who may be picked. The engine re-validates the submitted
                # answer against this, so an answer can never name somebody
                # the rule did not offer.
                options=leaders,
                max=approved,
            ),
            # The next questions your section needs go here -- but read this
            # first, because it is the one restriction that can quietly cost
            # somebody money.
            #
            # A statement does not yet store its answers in one field. It has
            # four columns, so these are the ONLY keys that can hold an
            # answer today:
            #
            #     night_cost     money
            #     allowance_to   member_set
            #     subsidy_to     member
            #     ljp_to         member
            #
            # Declare any other key and the person is asked the question, the
            # answer is dropped, and the rule reads that type's empty value
            # (0.00, 0, False, "", None, ()) on every single evaluation.
            # Nothing raises and nothing is logged. `ctx.inputs.raw(...)` does
            # not help: the key is there, holding the empty value.
            #
            # A case will NOT catch this -- the case runner passes unknown
            # keys straight through, so the case goes green while production
            # pays zero. That is why this template declares only
            # `allowance_to`.
            #
            # Until Kompass #556 moves the answers into one JSON field, a
            # figure that does not fit one of those four keys belongs below as
            # a module constant (like APPROVER_PERMISSION), where it is
            # versioned with the rules that read it.
            #
            # Also: do not use the `choice` widget yet (Kompass #573). There
            # is no way to declare what may be chosen, nothing validates the
            # answer, and reading an unanswered one with `ctx.inputs.text()`
            # raises and takes the whole evaluation down with it.
        ]

    def transfers(self, ctx: RuleContext) -> tuple[list[Transfer], list[str]]:
        """Resolve the statement into transfers, plus anything wrong with it.

        While the error list is non-empty nothing is persisted and no money
        moves, so an error is a sentence for the person who has to fix the
        statement. Do not raise for a problem with the *statement*; raising is
        for a broken ruleset, and the engine turns it into an error with a
        traceback pointing at the line here.
        """
        transfers: list[Transfer] = []
        errors: list[str] = []

        for bill in ctx.bills:
            # A bill that is not covered is still in the context on purpose: it
            # may well count towards a subsidy computed from the trip's total
            # cost, which is what the reference ruleset's LJP rule does.
            if not bill.covered:
                continue
            if bill.payer is None:
                errors.append(
                    f"Für den übernommenen Beleg „{bill.description}“ ist nicht "
                    "eingetragen, wer ihn bezahlt hat."
                )
                # Dropping the transfer is safe because nothing is persisted
                # while there is an error. A section that would rather keep the
                # amount in the statement's total writes it to PARTICIPANTS
                # instead, which is what the reference ruleset does.
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

        per_day = ctx.params.ALLOWANCE_PER_DAY
        per_leader = cents(excursion.duration * per_day)
        for leader in ctx.inputs.members("allowance_to"):
            transfers.append(
                Transfer(
                    source=SECTION,
                    destination=leader,
                    amount=per_leader,
                    category="allowance",
                    rule_id="allowance",
                    label="Aufwandsentschädigung",
                    # Worth filling in: it is what a person reading the payout
                    # sees instead of a bare figure.
                    explanation=f"{excursion.duration} Tage × {per_day} €",
                )
            )

        return transfers, errors

    def checks(self, ctx: RuleContext) -> list[Check]:
        """What has to be true before the statement may be handed in.

        A check carries its message whether or not it holds, because both
        states are worth showing: the rule is the rule either way, and whether
        it is satisfied is `ok`.
        """
        checks = [
            Check(
                ok=all(bill.has_proof for bill in ctx.bills),
                message="Jeder Beleg braucht ein Bild.",
            )
        ]
        excursion = ctx.excursion
        if excursion is not None:
            refinanced = min(excursion.staff_count, excursion.approved_staff_count)
            checks.append(
                Check(
                    ok=len(ctx.inputs.members("allowance_to")) <= refinanced,
                    message=(
                        "Eine Aufwandsentschädigung bekommen höchstens "
                        f"{refinanced} Jugendleiter*innen dieser Ausfahrt."
                    ),
                )
            )
        return checks

    def approval(
        self, ctx: RuleContext, transfers: list[Transfer]
    ) -> tuple[list[Constraint], list[Forbid]]:
        """Who has to sign this statement off, and who may not.

        Routing runs on the resolved `transfers`, so "over 1.000 € it takes the
        board" and "nobody who receives money from this statement" are both
        sayable without re-deriving anything from the raw statement.

        Constraints are an unordered set -- no priorities and no workflow. Each
        asks for `required` signatures out of `eligible`, one signature counts
        against every constraint it satisfies, and a forbid is subtracted from
        every eligible set before quorum is counted.
        """
        paid = {t.destination for t in transfers if isinstance(t.destination, Member)}
        return (
            [
                Constraint(
                    name="Freigabe",
                    description="Eine Unterschrift aus der Finanzverwaltung",
                    applicable=True,
                    required=1,
                    # An empty eligible set means *nobody*, and the constraint
                    # stands open. That is the safe reading and usually the
                    # right one; `anyone_permitted=True` would fill the set
                    # from the holders of the section's approval capability
                    # instead.
                    eligible=ctx.permission_holders(APPROVER_PERMISSION),
                )
            ],
            [
                # Conflict of interest, and it wins unconditionally: if the
                # only person who may sign is also being paid, the statement
                # waits for somebody else rather than paying itself out.
                Forbid(
                    name="Eigene Abrechnung",
                    applies_to=lambda member: member in paid,
                )
            ],
        )


#: The ruleset Kompass loads. One instance, shared across every evaluation in
#: the process -- so keep no state on it: no caches, no counters, nothing about
#: "the statement I am working on". Everything a method needs is in the context
#: it is given.
ruleset = SectionRules()
