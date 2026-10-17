# Finance rules for JDAV &lt;Sektion&gt;

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
"rules"` names the package beside it. Anything else in `[finance]` —
`allowance_per_day`, `max_night_cost`, `aid_per_km_train`, `aid_per_km_car`,
`org_fee` — is read by your rules as `ctx.params.ALLOWANCE_PER_DAY` and so on.

**Parameter names are not free-form.** Kompass reads a fixed list of keys out
of `[finance]`, so `ctx.params.WHATEVER_YOU_LIKE` does not work: a number that
is not one of those keys belongs in `rules/` as a module constant, where it is
versioned with the rules that read it — which is arguably where a figure your
section voted on belongs anyway.

`manage.py importruleset` runs **at every container start**, so a merged rule
change is picked up without a Kompass release and without a container restart:
pull the repository on the host and restart the instance, or run

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

Three things are worth knowing before the first rule, and the documentation
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
- **The import whitelist is a lint, not a sandbox.** Whoever can write this
  repository already holds the instance's database password, so executing
  Python from here grants no new privilege. What the whitelist catches is the
  accident — a rule that reads the clock or imports half of Kompass is a rule
  whose answer can change behind an old statement's back.

### For Ludwigsburg, concretely

The next ruleset to write is Ludwigsburg's, whose instance has none and is
therefore settling under Heidelberg's rules today. What is recorded of its
policy maps onto this template like this:

| Rule | Where it goes |
| --- | --- |
| *Individualisierte* Aufwandsentschädigung | `inputs` gains a per-person amount and `transfers` stops paying one flat figure to everybody named. Mind the case-file note in `rules/__init__.py` before choosing an input key. |
| Übernachtungs- und Fahrtkosten, individualisiert | Two more inputs and two more transfer rules, with `ctx.excursion.nights`, `kilometers` and `approach` in the context already. |
| LJP wie gehabt | `ctx.excursion.ljp` carries the counts the state's regulations define, already computed. The reference ruleset's `_ljp_amount` is the worked example to read. |
| Einreichen nach Bestätigung aller Jugendleitenden | **Not implemented by the engine.** `Check`s are preconditions for handing in, but there is no per-leader confirmation to check for, and `Constraint`s are signatures *after* submission. It needs a pre-submission stage in the engine. |
| Abrechnung innerhalb eines Monats: erinnern, dann forcieren | **Not implemented by the engine.** There is no clock in a rule and no deadline in the context, deliberately; a reminder is a scheduled task in Kompass, not a rule. |

The first three are rules to write here. The last two are Kompass features that
do not exist yet, and writing them as rules is not possible — which is better
to know before the first pull request than after it.

The figures themselves are the section's to decide, so nobody should write
Ludwigsburg's ruleset without Ludwigsburg.
