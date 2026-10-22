# The finance rules of the JDAV Sektion Ludwigsburg

This is Ludwigsburg's real configuration, and the worked example of
`deploy/config-template/`. The template says what a section *may* write; this
says what one section *did* write, out of its own signed documents, with a case
for every figure.

```
.
├── pyproject.toml          mypy and ruff, unchanged from the template
├── README.md               this file
└── rules/
    ├── __init__.py         the rules: inputs, transfers, checks, approval
    ├── rates.py            every figure, each with the clause it comes from
    └── cases/*.json        twenty-six worked examples; these gate activation
```

The policy it implements comes from four documents:

| | Document | In force | Character |
| --- | --- | --- | --- |
| **Q1** | Finanzordnung der Sektion Ludwigsburg, Ä0 | signed 25.06.2026 | who signs |
| **Q2** | Reisekostenrichtlinie **Ehrenamtliche Mitarbeiter**, Ä1 – 06/2024 | 01.06.2024 | what is reimbursed |
| **Q3** | Reisekostenrichtlinie **Tourenleitungen**, Ä1 – 01/2025 | 13.01.2025 | what is reimbursed |
| **Q4** | „Finanzzeug LuBu“ | undated, informal | three standing Sonderabsprachen |

Of Q4 only point 1 — the three Sonderabsprachen — is treated as policy. The
rest of that file is explicitly a vision and is not implemented; see "What this
ruleset does not do".

## Two regimes, and why the first question is a question

Ludwigsburg has **two travel-cost policies in force at the same time**, and
they differ in nearly every rate:

| | **Q2 — Ehrenamt und Verwaltung** | **Q3 — Tourenleitung** |
| --- | --- | --- |
| Privatfahrzeug | **0,30 €/km** | **0,20 €/km** |
| weitere Mitfahrende | nothing | **+0,03 €/km each, at most 0,30 €/km** |
| Übernachtung | against the receipt (an ordinary bill) | **10 €/Nacht flat** |
| Tagegeld | **yes**, by country and duration | none |
| Vergütung | none | **2,50 €/Stunde** |

Which one applies is decided by **the role the person was acting in**, not by
whether the statement settles a trip: a Jugendleitung settling a tour is Q3,
and the same person settling their referat's purchases a week later is Q2. Both
happen in the Jugend. So the form's first question is which policy this
statement is settled under, as a `choice`, and
`LudwigsburgRules.relevant_inputs` then takes the other policy's questions off
the form. A question that is off the form reads as its type's **empty value**,
so an answer left behind when a regime was corrected cannot move money under
the regime that replaced it.

The regime narrows the Fahrten table's **columns** on the same reasoning:
`Mitfahrende` is a column under Q3, which pays 0,03 €/km for each of them, and
no column at all under Q2, which pays „keine zusätzlichen Kosten“ for any. That
is `journey_fields` in `rules/__init__.py` rather than `relevant_inputs`,
because a cell is part of a declaration and `relevant_inputs` chooses among
keys. A count entered under Q3 and left behind when the regime is corrected is
**kept and not read** — correcting the regime does not throw the number away,
and correcting it back finds it again (`cases/04` and `cases/27`).

The trip's own figures are **not** questions. Nights and duration are declared
with `source="excursion.…"`, so the engine supplies them from the excursion and
the form shows them as figures. A statement that settles a purchase or a repair
has no excursion, and the same declarations are then ordinary questions. The
rules read them the same way either way, which is why there is not one
`if ctx.excursion is None` in `rules/__init__.py`.

## The Fahrten are a table, one row per traveller

A statement settles a trip several people went on, and they travelled
differently: one drove, one took the train, one cycled. Whether somebody gets
the Kilometerpauschale **at all** is decided by *their* means of travel — a
private car yes, the Bahn no, because there the ticket is the claim — so the
means and the distance belong to the same person in the same row.

`reisen` is therefore one `rows` question — three cells under Q2 and four under
Q3 — and `_travel` pays each row under its own approach at its own distance:

| Cell | Heading | What it holds |
| --- | --- | --- |
| `member` | Person | who covered this stretch |
| `approach` | Verkehrsmittel | Muskelkraft, ÖPNV/Bahn/Fernbus, or Privatfahrzeug — **seeded from the trip** |
| `kilometers` | Kilometer | the shortest connection; parking is covered — **seeded from the trip** |
| `passengers` | Mitfahrende | Q3's „weitere Mitfahrende“ — **only a column under Tourenleitung** |

A row whose approach is not the Privatfahrzeug pays nothing and is still worth
entering: it is how the statement records who did not drive, and Bahn, Fernbus
and ÖPNV are reimbursed against their receipts as ordinary covered bills.

**The two cells the trip records are seeded, not derived.** A `seed` is written
**once**, when the statement's excursion is set, and is then the person's own to
correct or to split into as many rows as there were travellers — where a
`source` belongs to the excursion, is refused on the form and is re-resolved on
every read. A statement with no trip seeds no row and the table starts empty;
`cases/24` is exactly that statement, with its rows typed by hand.

**Two people in one car is one row, and the cap belongs to the car.** Four
„weitere Mitfahrende“ raise 0,20 €/km to the ceiling of 0,30 €/km for *that*
journey and leave a second car at its own rate — `cases/23`.

**Hin- und Rückfahrt belong in one row, as the total distance.** The engine
accepts the same person in two rows deliberately: it cannot tell a double entry
from a there-and-back somebody split in half, and refusing would make the
honest table unsayable in order to catch a mistake it cannot recognise. So
which of the two Ludwigsburg means is a `Check` of its own — the statement is
blocked, nothing is deduplicated, and `cases/25` pins that both rows are paid
while the check says `false`.

**Stadtmobil and Aus-/Fortbildung take the whole table away**, not a row: both
are facts of the statement rather than of one journey. That is a limitation as
much as a decision — see reading 11 below.

## What is implemented

| Rule | Source | Where |
| --- | --- | --- |
| Belege an die auslegende Person; ein übernommener Beleg ohne Zahlende ist ein Fehler | Q1 §§ 1.2–1.3 | `transfers`, `bills` |
| Bahn, Schlafwagen, Fahrradmitnahme, Fernbus, ÖPNV, Q2-Übernachtungen — gegen Beleg | Q2/Q3 §§ 1.1–1.2, Q2 § 4 | nothing to write: a covered bill |
| 0,30 €/km im Privatfahrzeug (Ehrenamt) | Q2 „Privatfahrzeug“ | `rates.travel_rate` |
| 0,20 €/km + 0,03 €/km je Mitfahrender, höchstens 0,30 €/km (Tourenleitung) | Q3 § 1.5 | `rates.travel_rate` |
| Je Fahrt eine Zeile, mit eigenem Verkehrsmittel und eigener Strecke | Q2/Q3 § 1, gelesen | `reisen`, `_travel` |
| Stadtmobil: keine weiteren Fahrtkosten | Q2/Q3 „Stadtmobil“ | `_travel` plus a check |
| Keine Fahrtkosten bei Aus-/Fortbildung und Arbeitseinsatz | Q3 § 5, Q2 § 7 | `_travel` |
| Übernachtungspauschale 10 €/Nacht je Leitung | Q3 § 3 | `_nights` |
| Keine Pauschale bei der 5+1-Regel in AV-Hütten | Q3 § 3 | `_nights` (`no_night_cost`) |
| Keine Pauschale, wenn den Leitenden keine Kosten entstehen | **Q4 Sonderabsprache 3** | `_nights` (`no_night_cost`) |
| Schlafwagen tritt an die Stelle der Übernachtung | Q2/Q3 § 1.1 | `_nights` (`sleeper_car`) |
| Tagegeld nach Land und Dauer, inkl. Tagestouren | Q2 § 5 | `rates.per_diem` |
| Verpflegungsmehraufwand bei Arbeitseinsätzen in Höhe des Tagegelds | Q2 § 7 | `rates.per_diem`, same rule |
| Tourenleitervergütung 2,50 €/Stunde mit DAV-Lizenz | Q3 § 4 | `_tour_leader_fee` |
| Belegpflicht (jeder Beleg braucht ein Bild) | Q1 §§ 1.2–1.3 | `checks` |
| 3+1 und Teilnehmerliste als Voraussetzung | Q3, Vorbemerkung | `checks`, **self-reported** |
| Freigabe bis 1.000 € durch die Leitung allein | Q1 § 1.2 | `approval`, constraint 1 |
| Über 1.000 € zusätzlich der Schatzmeister | Q1 § 1.2 | `approval`, constraint 2 |
| Befangenheit: wer bezahlt wird, gibt nicht frei | Q1 § 1.2, lines 2–3 | `approval`, `Forbid` |
| Mit LJP immer Jugendleitung **und** Schatzmeister, unabhängig vom Betrag | Q1 § 2.4, **Q4 Sonderabsprache 1** | `approval`, constraints 3–4 |

**The 1.000-€ threshold is read against the statement's total** — everything
the section pays out to people on this statement, which is what Kompass settles
in one go. Q1 says „Rechnung“; the section's answer was the statement.

**The Landesjugendplan moves no money in Ludwigsburg.** Nothing in the four
documents passes a state contribution on to a youth leader, and the one thing
they do say about the LJP is who has to sign. So `excursion.ljp` is read by
`approval` and by nothing else, and `cases/12_ljp_bewegt_kein_geld.json` pins
exactly that. (The reference ruleset's `_ljp_amount` is Heidelberg's policy,
not a default.)

**No `ctx.params.*` is read at all.** Not one of Ludwigsburg's figures is one of
the seven parameter names Kompass serves, so every figure is a constant in
`rates.py`, next to the clause that set it. It is hashed into the version
exactly as a parameter would be, so changing a rate is a new version either
way. The numbers under `[finance]` and `[LJP]` in `settings.toml` therefore do
not affect what this ruleset pays — they only change the version hash.

## What this ruleset does not do

Deliberately, and each one for a reason that is not going to change by writing
more rules:

- **The 8 hours per day, 200 hours per year and 3.000 € per year ceilings on
  the Tourenleitervergütung.** They are sums across days, across statements and
  across a whole tax year, and over income from other organisations as well; a
  rule sees exactly one statement and has no memory. Q3 already puts them where
  they are: on the Tourenleitung („eigenverantwortlich“) and on the
  Geschäftsstelle's annual confirmation. **The 2,50 €/Stunde itself is
  implemented** — the ceilings are not, and nothing in Kompass warns when one
  is passed.
- **The further 2,50 €/Stunde for a DOSB licence.** It is paid by the WLSB at
  the end of the year, not by the section, so there is no transfer for this
  ruleset to write.
- **The prior approval of a PKW journey** (Q2 § 3, Q3 § 1.3). Freigaben in
  Kompass happen *after* a statement is handed in; an approval *before the
  journey* has no place to live. A `Check` cannot stand in for it, because a
  check is read when the statement is filed, which is already too late.
- **The 3+1 rule and the Teilnehmerliste, as facts.** Whether a participant is
  a member of the section is not in a rule's context, and whether a list
  reached the Service-Center before the group left is not in Kompass at all.
  Both are a single self-reported confirmation and a check — which is a
  reminder, not a verification.
- **„Reise im Budget eingeplant“** (Q2). Budgets are not modelled in Kompass.
- **Bergbahnen und Lifte sind nicht abrechenbar** (Q3 § 2). Only recognisable
  from a receipt's text, which no rule should be reading.
- **Service-Center-Rechnungen** (Q1 § 2.1: up to 5.000 € without a signature).
  These are the Geschäftsstelle's invoices and do not come through Kompass's
  statements at all.
- **Everything in Q4 after point 1.** A hierarchy with delegated personal
  limits, a „hinterfragen“ state between approve and reject, processing by
  mail, every step attached to the statement as a document, and paying
  tax-relevant amounts out separately. These are Kompass features that do not
  exist, not rules — the specification's Teil G.3 lists them one by one.
- **Deadlines and reminders** („Abrechnung innerhalb eines Monats“). There is
  no clock in a rule, on purpose. A reminder is a scheduled task in Kompass.

## The readings we had to make

Where the documents do not settle something, the rules take the defensible
reading, say so in a comment at the line, and list it here. **Each of these is
for the section to confirm.**

1. **„Maximal sind 0,30 € pro Fahrt möglich“ (Q3 § 1.5) is read as a ceiling on
   the rate per kilometre**, applied per row of `reisen`. Both figures the
   sentence caps are per kilometre, and read as a ceiling per *journey* it would
   be nearly worthless — 0,30 € for a 300 km drive, next to a rate of
   0,20 €/km. So the cap starts biting at four passengers:
   0,20 + 4 × 0,03 = 0,32 is paid as 0,30.

   Half of this argument used to be that the engine *could* not say „Fahrt“: it
   had the trip's kilometres as one total. The table has taken that half away —
   a row is a Fahrt — so **the section can now choose the other reading**, and
   this one is implemented because the sentence reads that way and not because
   nothing else was expressible.
2. **The Tagegeld's two tiers are applied the statutory way:** every full day
   away at the „ab 24 Stunden“ rate and the day of departure and of return at
   the „ab 8 Stunden“ rate each, so a trip of *n* nights has *n − 1* full days
   and two travel days. Q2 prints the two rates and not the rule for combining
   them.
3. **Whether a day trip lasted eight hours is read off Kompass's half-day
   step:** a duration of a full day or more counts as at least eight hours, a
   half day as less and therefore as no Tagegeld. Neither the trip nor the
   engine records times of day.
4. **The 1.000-€ threshold is the statement's total**, not the largest single
   receipt in it (spec question 5, answered by the section).
5. **JDAV statements occur under both regimes**, which is why the regime is
   asked rather than fixed to Q3 (spec question 1, answered by the section).
6. **With an LJP proposal, the Jugend's signature may also come from the
   responsible stellvertretende Vorsitzende.** Q1 § 2.4 names the
   Jugendleitung and § 1.2 says whoever claims does not release their own
   claim; both at once would make a Jugendleitung's own LJP statement
   unapprovable by anybody, because the conflict-of-interest forbid empties the
   only eligible set there is. The treasurer's signature stays required
   separately, which is the control § 2.4 is really about.
7. **The Tourenleitervergütung is settled for one person per statement**, as
   the „Auslagen-Buchungsbeleg Tourenleitervergütung“ itself is. The 10 €/night
   and the Tagegeld are settled for several people at once, because those
   figures are the same for everybody on the trip while hours are not.
8. **Aus-/Fortbildung and Arbeitseinsatz are one question**, because both
   policies' answer to it is the same: no travel costs (Q3 § 5, Q2 § 7).
9. **The Finanzordnung Ä0 of 25.06.2026 is taken to be in force**, and is what
   `valid_from` declares (spec question 6). If a transitional older version
   applies, that date and the signature rules are what change.
10. **For a statement without participants** — a Verwaltungs- or
    Referatsabrechnung — the balancing row is still
    `PARTICIPANTS → SECTION`. The engine allows no third party there and
    refuses a member, so that row is the section's own budget carrying the
    cost rather than a contribution anybody collects.
11. **Stadtmobil and Aus-/Fortbildung are asked once for the whole statement**,
    and they take the whole Fahrten table away. Before `reisen` there was only
    one journey and the question did not arise; now it does, and the honest
    answer is that **a statement on which one person took the Stadtmobil and
    another drove their own car cannot be written down** — the flag suppresses
    both. Two statements, or a `Verkehrsmittel` choice of its own per row, are
    the two ways out, and the section should say which it wants before this is
    in front of anybody.
12. **A count entered under Q3 and left behind is kept, not cleared.** The
    `Mitfahrende` column is off the form under Q2, and the number stays in
    `Statement.inputs` where nothing reads it. Clearing it would throw away an
    answer somebody gave; refusing the row it sits in would make switching the
    regime back and forth refuse every later edit over a column nobody can see.
    So it is simply not read, and `cases/04` and `cases/27` pin both halves of
    that: Q2 pays its plain rate with the count lying there, and Q3 pays the
    supplement from the very same stored row.

## The six roles, which somebody has to assign

Every signature is routed by office, and the offices are
`RoleAssignment` rows in the admin (*Finance → Role assignments*), with the
dates they were held — so a statement from 2026 is approved by whoever was the
treasurer in 2026. The rules read exactly these names:

| Role name | Q1's wording |
| --- | --- |
| `schatzmeister` | Schatzmeister |
| `jugendleitung` | Jugendleitung (§ 2.4) |
| `ressortleitung` | Ressort- bzw. Gruppenleitung |
| `stellv_vorsitz` | jeweilige stellvertretende Vorsitzende |
| `stellv_vorsitz_finanzen` | stellvertretende Vorsitzende Finanzen |
| `erste_vorsitzende` | 1. Vorsitzende |

> **A role nobody holds means nobody may sign.** That is the engine's safe
> reading of an empty eligible set, and it is the right one — but it means that
> until `schatzmeister` and at least one of the leadership roles are assigned,
> **no statement can be approved at all**. Assign them before the first
> statement is handed in.

## How the instance reads this directory

Ludwigsburg's instance is the stock Kompass image with the configuration
directory mounted read-only:

```yaml
# docker-compose.yaml
services:
  master:
    image: ghcr.io/chrisflav/kompass:latest   # pin a digest; see the template
    environment:
      - KOMPASS_CONFIG_DIR_PATH=/app/config/
    volumes:
      - ./config:/app/config:ro
```

Copy `rules/` and `pyproject.toml` into that configuration repository, beside
the `settings.toml` it already has, and name the package there:

```toml
[finance]
ruleset = "rules"        # the package directory, relative to this directory
```

`manage.py importruleset` runs when the `master` container starts — of the five
containers the image runs, the only entrypoint that imports — so a merged rule
change needs no Kompass release and no rebuild: pull the repository on the host
and restart the instance, or

```console
docker compose exec master python jdav_web/manage.py importruleset
```

and the next statement created uses the new rules. The admin's
"Import from configuration" button and `[finance] ruleset_poll_minutes` do the
same thing.

Activation is gated on the checks below. A package that fails one is stored as
a **draft**, the previous version stays active, the command exits non-zero and
says what is wrong — and the container keeps serving. A statement keeps the
version it was created under, so changing a rate never moves a figure that has
already been settled.

## Checking it

Three commands, all inside the image the instance runs, and **not** in the same
working directory:

```console
cd /app/config && mypy --strict rules      # reads ./pyproject.toml
cd /app/config && ruff check rules         # reads ./pyproject.toml
cd /app && python jdav_web/manage.py checkruleset /app/config/rules --fuzz 200
```

The third must not run from `/app/config`: Kompass pulls in Celery, whose
Django fixup puts the working directory at the front of `sys.path`, and a
`rules/` package there shadows `django-rules`, which Kompass itself depends on.
`deploy/config-template/.github/workflows/check-rules.yml` is the workflow that
runs all three with the mounts and the pinned tool versions; copy it into the
configuration repository.

From a checkout of this repository, against this branch's engine:

```console
docker run --rm \
    -e KOMPASS_CONFIG_DIR_PATH=/app/config/ \
    -v "$PWD/jdav_web":/app/jdav_web:ro \
    -v "$PWD/deploy":/app/deploy:ro \
    -v "$PWD/docker/development/config":/app/config:ro \
    -w /app ghcr.io/chrisflav/kompass:latest \
    python3 jdav_web/manage.py checkruleset /app/deploy/ludwigsburg/rules --fuzz 200
```

### What the cases prove, and the one thing they cannot

The twenty-seven cases in `rules/cases/` pin the figures of both regimes, with
and without a trip: the per-kilometre rate with no passengers, with three, and
at the cap; the flat rate per night and the two reasons it may not be claimed;
the Tagegeld; the Tourenleitervergütung; a purchase with no excursion, where
nothing is seeded and the rows are typed by hand; and the statement totals the
1.000-€ threshold is read against, at 1.000,00 € exactly and at 1.010,00 €.
They gate activation: a failing case means the version is not activated.

Six of them are about the table, and each states something the four
single-journey questions could not: two leaders driving different distances
(21), one driving while another takes the train (22), two cars where the cap
bites in one of them (23), a trip-less statement whose rows were typed by hand
(24), the same person in two rows paid twice with the check saying so (25), and
a row with no Verkehrsmittel paying nothing with the check saying so (26).

Two more are one stored row read under each regime in turn, which is how the
`Mitfahrende` column being Q3's alone is pinned from both sides: the count lies
unread under Q2 and the plain rate is paid (4), and the identical answer pays
the supplement again under Q3 (27).

**What no case can prove is the seed.** A seed is written when a statement gets
an excursion, and a case file is a context with no edit history — so what a
case states is the row as the answer it ended up being. The prefill is tested
in Kompass, against the API and the admin.

**What no case can assert is `approval()`.** The case runner compares
transfers, errors and checks, and the fuzzer insists that every random
statement balances — none of them signs anything. So the two cases named for
the threshold and for the conflict of interest pin the *inputs* that routing
reads (the total, and who is paid), and the routing itself was checked by hand
against this ruleset:

| Statement | Konstellation | Result |
| --- | --- | --- |
| 999,99 € | no LJP | leadership only, 1 signature |
| 1.000,00 € | no LJP | leadership only — the threshold is „über 1.000 €“ |
| 1.000,01 € | no LJP | leadership **and** the treasurer |
| 12,00 € | with LJP | Jugendleitung **and** the treasurer, however small |
| any | the signer is paid | the forbid removes them from every eligible set |

Repeat it on the real instance before trusting it with somebody's actual
reimbursement: the admin's *Dry run* page for a ruleset version shows the
constraints it resolves for a statement you pick.
