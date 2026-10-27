# Finance rules for a JDAV section

This is the template for a section's **configuration repository**: the
directory a Kompass instance mounts read-only, and the place a section's own
finance rules live. Copy it, make it your own repository, and the statements
your instance settles are settled under rules you wrote and reviewed.

> **If you skip this, your section settles its statements under Heidelberg's
> rules.** With `[finance] ruleset` unset, the reference ruleset that ships in
> the Kompass image applies — Heidelberg's allowance per day, its organisation
> fee for participants from 27, its LJP arithmetic, its single signature from
> the finance department. Nothing fails and nothing warns. The statements
> resolve, the books add up, and the figures are somebody else's.

```
.
├── .github/workflows/check-rules.yml   mypy, ruff and checkruleset, in the image
├── pyproject.toml                      how those three are configured
├── rules/
│   ├── __init__.py                     your rules
│   └── cases/*.json                    your worked examples; these gate activation
└── settings.toml                       the instance's settings (not in the template)
```

Copy it with `cp -a`, not `cp -r *`: `.github/` is a hidden directory and is
easy to leave behind.

## Getting started

1. Copy this directory into your configuration repository, beside the
   `settings.toml` your instance already uses.
2. In `rules/__init__.py`, rename `SectionRules`, set `name`, and make
   `transfers` say what your section actually reimburses.
3. Write a case for each thing it should do, in `rules/cases/`. The three that
   are here are real and they pass — start by changing their figures to yours.
4. Add to `settings.toml`:

   ```toml
   [finance]
   ruleset = "rules"        # the package directory, relative to this directory
   allowance_per_day = 22   # the numbers your rules read as ctx.params.*
   ```
5. Open a pull request. The workflow checks it. Merge it, pull it on the host,
   and the next statement is settled under the new rules.

The full reference — every type in `kompass.rules`, the widget vocabulary, the
cases format and the rules of the road — is the **"A section's finance rules"**
page of the Kompass documentation. This README is the deployment half of it.

## How the instance reads it

Your instance is the stock Kompass image with this directory mounted
read-only:

```yaml
# docker-compose.yaml
services:
  master:
    image: ghcr.io/chrisflav/kompass:latest
    environment:
      - KOMPASS_CONFIG_DIR_PATH=/app/config/
    volumes:
      - ./config:/app/config:ro
```

`settings.toml` is read from that mount at start, and `[finance] ruleset =
"rules"` names the package beside it. The section's numbers come from there
too: `[finance] allowance_per_day`, `max_night_cost`, `aid_per_km_train`,
`aid_per_km_car` and `org_fee`, plus `[LJP] contribution_per_day` and `tax`,
are what your rules read as `ctx.params.ALLOWANCE_PER_DAY`,
`ctx.params.EXCURSION_ORG_FEE`, `ctx.params.LJP_TAX` and so on.

**Parameter names are not free-form.** That list is fixed, so
`ctx.params.WHATEVER_YOU_LIKE` does not work: a number that is not one of
those keys belongs in `rules/` as a module constant, where it is versioned
with the rules that read it — which is arguably where a figure your section
voted on belongs anyway.

**Input keys are free-form as far as storage goes**, unlike the parameter
names: a statement keeps its answers in one JSON field, so `inputs` may declare
any key it likes and the rules read it back. What the engine does police is
that a declaration can be *served* — a `choice` has to list its alternatives, a
`source` has to name a real context field, an `options_source` has to be one of
the five the engine resolves, and a `source` may not also say who may be picked
— and it refuses anything else where it is written, which fails a case in this
repository's CI rather than reaching somebody's form.

> **Two key names still mean something outside the engine.** Kompass reads
> `allowance_to` and `night_cost` **by name** in model properties the rules
> engine never sees: `allowance_to` drives the `INVALID_ALLOWANCE_TO` gate that
> the admin's confirm and submit both check, and it passes *vacuously* when the
> key is absent; `night_cost` is what the printed statement summary shows as
> the price per night. Reuse those two names and you keep that behaviour. Call
> your allowance key something else and you give the gate up — quietly.

> **A derived input is not answered, so a case cannot answer it.** A
> declaration with `source="excursion.kilometers"` is resolved from the trip,
> and submitting a value for it is refused — including in a case file, where
> the engine supplies the excursion's figure over whatever `inputs` says. Put
> the number in the case's `excursion`, not in its `inputs`. The *other* arm is
> worth a case of its own: leave `excursion` out and the same declaration is an
> ordinary question, which is the statement that settles a purchase.

`manage.py importruleset` runs **when the `master` container starts** — of the
five containers the image runs, that is the only entrypoint that imports — so a
merged rule change is picked up without a Kompass release and without rebuilding
anything: pull the repository on the host and restart the instance, or run

```console
docker compose exec master python jdav_web/manage.py importruleset
```

and the next statement created uses the new rules. You can also have Kompass
poll the directory (`[finance] ruleset_poll_minutes = 60`), or press "Import
from configuration" in the admin.

Every import hashes the sources together with the parameters. An unchanged
directory hashes to the version already stored, so importing twice costs a hash
and changes nothing.

### When the checks fail

The import runs the same checks your CI ran: the import whitelist, the loader,
and every case in `rules/cases/`. If one of them fails:

- the version is stored as a **draft** and is not activated,
- the **previous version stays active** — statements keep settling under the
  rules that were in force,
- the command **exits non-zero and says what is wrong**, in the container log
  and in the admin's list of versions,
- and **the container still serves**. A typo in a rule is not a reason to take
  a section's finances offline. It is a reason to shout.

So a broken rule change is loud and inert rather than quiet and live. That is
also why the cases matter: they are the gate, and a rule change without a case
is a rule change nothing checked.

A statement keeps the version it was created under — its own copy of the
sources and of the numbers — so changing a rule never moves a figure that has
already been settled.

## Checking rules by hand

The workflow runs three commands in the image. You can run the same three:

```console
docker run --rm -v "$PWD":/app/config:ro -e KOMPASS_CONFIG_DIR_PATH=/app/config \
    ghcr.io/chrisflav/kompass:latest \
    python jdav_web/manage.py checkruleset /app/config/rules --fuzz 200
```

`checkruleset` touches no data: the whitelist and the cases are pure, and the
fuzzer builds its statements out of thin air. `mypy --strict` and `ruff check`
need `kompass.rules`, which lives in the image, so they want the same
`docker run` — see the workflow for the exact invocation.

Note the working directories, because they are not the same. `mypy` and `ruff`
read `pyproject.toml` and so must run **in** `/app/config`; `checkruleset` must
run from `/app` and be given the package by absolute path. Run it from
`/app/config` and it fails before reading a rule, with `No module named
'rules.contrib'`: Kompass pulls in Celery, whose Django fixup puts the working
directory at the front of `sys.path`, and your `rules/` package then shadows
`django-rules`, which Kompass itself depends on.

What **nothing** checks automatically is `approval()`: the cases compare
transfers, errors and checks, and the fuzzer insists that every random
statement balances, but neither one signs anything. Read that method carefully,
and try it on the real instance with a statement that is not somebody's actual
reimbursement.

## The image tag is a placeholder

`.github/workflows/check-rules.yml` pins `ghcr.io/chrisflav/kompass:latest`,
and `latest` tracks Kompass's `main` branch. It is a moving target: the image
that checked your rules this morning is not necessarily the one your instance
runs.

Immutable, versioned release tags are not published yet (Kompass issues #535
and #538). Until they are, pin a **digest** — `docker buildx imagetools
inspect ghcr.io/chrisflav/kompass:latest` prints one, and
`ghcr.io/chrisflav/kompass@sha256:…` is immutable — and re-pin it deliberately,
the way you would a release tag. The workflow says the same thing where you
have to change it.

## Writing the rules

Four things are worth knowing before the first rule, and the documentation
page has the rest:

- **A rule may read only its `RuleContext`.** No database (the engine refuses
  every ordinary route to it while rules run), no clock, no files, no other
  statements, no balances. Every amount is a `Decimal` with at most two decimal
  places; the engine refuses anything finer, because how to round is your
  section's decision.
- **A ruleset does not compute the participants' contributions.** It declares
  the residual party in `balance`, and the engine appends the one transfer that
  makes the books add up. That is why a case's last expected transfer is the
  balance.
- **An amount that may not share a bank transfer says so on its transfer.**
  Kompass bundles amounts owed to the same person out of the same ledger into
  one payment, which is the right default and wrong for anything that has to be
  payable separately — a tax-relevant Vergütung, say. Give such a transfer a
  `settlement_group="…"`, a token of your own choosing, and it is bundled only
  with transfers naming the same one. A ruleset that names no groups bundles
  exactly as every ruleset did before this existed.
- **Who makes the transfers is a declaration, and it has two readings.** With
  the default, `payout = SELF_PAYMENT`, the person reviewing a statement makes
  the bank transfers from the review screen and the statement ends up
  *ausgezahlt*. With `payout = OFFICE_PAYMENT` the section's Geschäftsstelle
  makes them, the review ends in a handoff, the statement ends up *zur
  Auszahlung übergeben*, and the summary it mails carries one payment order per
  booking — because in that arrangement the paper is the only thing the person
  making the transfers ever sees. No wording is true in both, so say which one
  your section is even though one of them is the default.
- **Whether a step may be signed off without its signatures is a declaration
  too.** An override only ever reaches a step the person could have signed —
  or one that named nobody, a vacant office, which is what it is for. The
  default, `override = OVERRIDE_BY_SIGNERS`, leaves that open;
  `override = NO_OVERRIDE` closes it, for a section that unsticks a statement
  by giving the step a signer rather than by proceeding without one; and
  `Override(roles=("kassenwart",))` keeps it for the holders of those roles.
- **The import whitelist is a lint, not a sandbox.** Whoever can write this
  repository already holds the instance's database password, so executing
  Python from here grants no new privilege. What the whitelist catches is the
  accident — a rule that reads the clock or imports half of Kompass is a rule
  whose answer can change behind an old statement's back.

### For Ludwigsburg, concretely

**There is a worked example of all of this next door: `deploy/ludwigsburg/`.**
It is the Sektion Ludwigsburg's real configuration, written out of its four
signed documents — two parallel travel-cost policies selected by a `choice`,
the trip's figures derived with `source=`, a statement with no trip paying a
bill's payer, signatures routed by office with a conflict-of-interest `Forbid`,
and twenty cases pinning the figures of both policies. Its README also names
what it deliberately does *not* implement and every reading it had to make,
which is the part of a ruleset that is easiest to leave unwritten.

Ludwigsburg's policy maps onto this template like this:

| Rule | Where it goes |
| --- | --- |
| Zwei parallele Regelwerke (Ehrenamt vs. Tourenleitung) | A `choice` with the two as its `choices`, grouped into a first `step`, and the rate read off `ctx.inputs.text("regime")`. |
| *Individualisierte* Aufwandsentschädigung | A `money` key per recipient, or one key holding the shared amount plus `allowance_to` for who. Keys are free-form now (#556), so this is a ruleset decision rather than a Kompass one. |
| Übernachtungs- und Fahrtkosten, individualisiert | Same: as many keys as the policy needs. The kilometres need no key at all — `source="excursion.kilometers"` derives them from the trip and asks for them only when there is no trip. |
| Abrechnungen ohne Fahrt (Anschaffungen, Reparaturen) | `options_source="bills.payers"` (or `"statement.creator"`) is who may be paid when there are no youth leaders to offer. |
| LJP wie gehabt | `ctx.excursion.ljp` carries the counts the state's regulations define, already computed. The reference ruleset's `_ljp_amount` is the worked example to read — and it is Heidelberg's policy, not a default: in Ludwigsburg the LJP moves no money at all and only changes who signs. |
| Einreichen nach Bestätigung aller Jugendleitenden | **Not implemented by the engine.** `Check`s are preconditions for handing in, but there is no per-leader confirmation to check for, and `Constraint`s are signatures *after* submission. It needs a pre-submission stage in the engine. |
| Abrechnung innerhalb eines Monats: erinnern, dann forcieren | **Not implemented by the engine.** There is no clock in a rule and no deadline in the context, deliberately; a reminder is a scheduled task in Kompass, not a rule. |

The first five are written, in `deploy/ludwigsburg/rules/`. The last two are
Kompass features that do not exist at all, which cannot be written as rules
however the ruleset is arranged — better known before the first pull request
than after it.

The figures themselves are the section's to decide, which is why every reading
`deploy/ludwigsburg/` had to make is listed in its README rather than settled
quietly in a rule.
