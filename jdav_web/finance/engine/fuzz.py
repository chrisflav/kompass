"""Random statements, to find the answer a section's rules did not expect.

The cases a ruleset ships are the situations its author thought of. The fuzzer
is for the ones they did not: it builds a statement out of random but *valid*
data — a trip of some length, some participants of some ages, some receipts
somebody paid — asks the ruleset what to ask the person, answers those
questions at random within the domains the ruleset itself declared, and checks
the two things that must hold whatever the answers are:

* the rules report no error, because every input was one they offered, and
* the books balance, because the engine closed them.

It is not a proof and it is not a substitute for a case with an expected
figure. It is the cheapest way to find the rule that divides by a participant
count nobody checked for zero.

``random`` lives here, in the engine, and never in a ruleset: a rule that could
read a random number could not be replayed.
"""

import random
from dataclasses import replace
from decimal import Decimal
from pathlib import Path
from typing import Any

from finance.rules_api import Bill
from finance.rules_api import CONTEXT_VERSION
from finance.rules_api import Excursion
from finance.rules_api import Input
from finance.rules_api import Inputs
from finance.rules_api import LJP
from finance.rules_api import LJPGoal
from finance.rules_api import Member
from finance.rules_api import MemberId
from finance.rules_api import Params
from finance.rules_api import Participant
from finance.rules_api import Roles
from finance.rules_api import RuleContext
from finance.rules_api import Ruleset
from finance.rules_api import SECTION
from finance.rules_api import StatementInfo
from finance.rules_api import TourApproach

from .declared import ask
from .evaluation import evaluate
from .versions import check_directory
from .versions import decimal_params
from .versions import parameters_from_settings

#: The approaches a random trip may have taken.
APPROACHES: tuple[TourApproach, ...] = ("muscle", "public", "car")

#: The LJP goals a random trip may have declared, plus "no proposal at all".
GOALS: tuple[LJPGoal | None, ...] = (
    "qualification",
    "participation",
    "development",
    "environment",
    None,
)


def random_context(rng: random.Random, params: dict[str, Decimal]) -> RuleContext:
    """A statement that could plausibly have been handed in."""
    leaders = tuple(Member(MemberId(index)) for index in range(1, rng.randint(1, 6) + 1))
    people = tuple(
        Participant(
            member=Member(MemberId(100 + index)),
            age=rng.randint(6, 70),
            age_at_start=rng.randint(6, 70),
            is_leader=False,
        )
        for index in range(rng.randint(0, 20))
    )
    nights = rng.randint(0, 7)
    goal = rng.choice(GOALS)
    ljp = (
        None
        if goal is None
        else LJP(
            goal=goal,
            participant_count=rng.randint(0, 20),
            theoretic_participant_count=rng.randint(0, 20),
            duration=Decimal(rng.randint(0, 2 * (nights + 1))) / 2,
        )
    )
    bills = tuple(
        Bill(
            id=index + 1,
            amount=Decimal(rng.randint(0, 200000)) / 100,
            covered=bool(rng.getrandbits(1)),
            # Always somebody: a receipt with no payer is a statement that is
            # wrong, not a ruleset that is.
            payer=rng.choice(leaders),
            has_proof=bool(rng.getrandbits(1)),
            description=f"Beleg {index + 1}",
        )
        for index in range(rng.randint(0, 6))
    )
    return RuleContext(
        version=CONTEXT_VERSION,
        params=Params(params),
        inputs=Inputs({}),
        bills=bills,
        excursion=Excursion(
            duration=Decimal(rng.randint(1, 2 * (nights + 1))) / 2,
            nights=nights,
            kilometers=rng.randint(0, 2000),
            approach=rng.choice(APPROACHES),
            leaders=leaders,
            staff_count=len(leaders),
            approved_staff_count=rng.randint(0, len(leaders) + 2),
            participants=people,
            ljp=ljp,
        ),
        statement=StatementInfo(id=1, creator=leaders[0], submitter=None),
        # Unresolved rather than empty: a random statement is not a statement
        # where nobody holds any role, it is one where the roles were never
        # looked up. Reading one must raise, which is the whole point of the
        # sentinel — handing the fuzzer `Roles({})` would make it blind to
        # exactly the bug the sentinel exists for.
        roles=Roles.unresolved(),
        permissions={},
    )


def random_answer(rng: random.Random, declaration: Input) -> Any:
    """An answer to one declared question, inside the domain it declared."""
    if declaration.type == "money":
        return Decimal(rng.randint(0, 50000)) / 100
    if declaration.type == "int":
        return rng.randint(0, declaration.max if declaration.max is not None else 10)
    if declaration.type == "bool":
        return bool(rng.getrandbits(1))
    if declaration.type == "text":
        return rng.choice(["", "Hinweis"])
    if declaration.type == "choice":
        # Out of what the declaration itself offers, plus "nothing chosen" —
        # which is a state a required question can be in while the form is
        # being filled in, and therefore one the rules have to survive.
        return rng.choice(["", *(choice.value for choice in declaration.choices)])
    if declaration.type == "member":
        options = list(declaration.options)
        return rng.choice(options + [None]) if options else None
    # `member_set`, the last of the vocabulary.
    options = list(declaration.options)
    rng.shuffle(options)
    limit = declaration.max if declaration.max is not None else len(options)
    return tuple(options[: rng.randint(0, min(limit, len(options)))])


def fuzz(ruleset: Ruleset, rounds: int, *, seed: int | None = None) -> list[str]:
    """Run ``rounds`` random statements through ``ruleset``; report what broke.

    One message per round that reported an error or did not balance, each with
    the seed it came from so it can be reproduced.
    """
    problems: list[str] = []
    params = decimal_params(parameters_from_settings())
    for round_number in range(rounds):
        round_seed = round_number if seed is None else seed + round_number
        rng = random.Random(round_seed)
        context = random_context(rng, params)
        # Guarded like every other call into a section's rules — `ask` is what
        # opens the guard: `inputs` is a rule too, and a declaration that
        # resolved its options with a query would be a question whose answer
        # depends on the day it was asked. Reported rather than raised, because
        # a fuzzer that falls over is a fuzzer that tells you nothing about the
        # other 199 rounds.
        try:
            declarations = list(ask(ruleset, context))
        except Exception as problem:
            problems.append(f"seed {round_seed}: the section's rules failed: {problem}")
            continue
        # A derived question is not answered at random, because it is not
        # answered at all: `evaluate` resolves it from the context. Answering
        # it here would be fuzzing a value no statement can ever hold.
        answers = {
            declaration.key: random_answer(rng, declaration)
            for declaration in declarations
            if not declaration.derived
        }
        result = evaluate(ruleset, replace(context, inputs=Inputs(answers)))
        if result.errors:
            problems.append(f"seed {round_seed}: {result.errors[0]}")
            continue
        paid = sum((t.amount for t in result.transfers if t.source == SECTION), Decimal("0.00"))
        received = sum(
            (t.amount for t in result.transfers if t.destination == SECTION), Decimal("0.00")
        )
        if paid != received:
            problems.append(f"seed {round_seed}: the section is out by {paid - received}")
    return problems


def check_and_fuzz(directory: Path, rounds: int, *, seed: int | None = None) -> list[str]:
    """The whitelist, the cases and ``rounds`` random statements, in one call."""
    ruleset, problems = check_directory(directory)
    if ruleset is None:
        return problems
    if rounds:
        problems = problems + fuzz(ruleset, rounds, seed=seed)
    return problems
