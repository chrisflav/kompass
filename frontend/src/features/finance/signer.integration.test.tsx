import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute } from "../../test/utils";

/**
 * The review pipeline as the person the rules named sees it.
 *
 * She is a Ressortleitung: the section's rules ask for her signature, so #390
 * let her open the statement — and what she then found was a screen built for
 * somebody else. Three things were wrong and they were one thing:
 *
 * * every booking read "Konto wählen…", because the Konto column filled its
 *   picker from the section's chart of accounts and `finance.view_ledger` is a
 *   permission she does not hold. The account was on the booking all along;
 *   the empty picker threw it away and showed its placeholder instead;
 * * the surface showed the bills and the bookings and **none of the answers**
 *   — not the Regelwerk, not the travel rows, not the nights — so she was
 *   asked to approve a payout while being shown only its arithmetic;
 * * and a booking without an account took her *signature* with it, because
 *   the leg that offers it was reachable only on `is_valid`. The one act left
 *   on screen was then "Ohne Unterschrift freigeben" — the override — which
 *   is the worst of all possible offers: the exceptional act in place of the
 *   ordinary one.
 *
 * So these are tests about a signer who is not finance staff, did not create
 * the statement, and holds `finance.process_statementsubmitted` and nothing
 * else. The last one is the control: somebody the rules named on nothing sees
 * none of it.
 */

const MILA = { id: 9, name: "Mila Nowak" };
const MELISSA = { id: 11, name: "Melissa Gruber" };

/** A booking the server has already charged to an account. */
const BOOKING = {
  id: 20,
  amount: 56,
  confirmed: false,
  confirmed_date: null,
  confirmed_by: null,
  statement_id: 39,
  member: MILA,
  ledger: { id: 4, name: "Topf" },
  code: "",
  iban: "DE02120300000000202051",
  iban_valid: true,
  reference: "Seil und Haken",
  settlement_group: "",
};

/** Only the fields the review pipeline reads. */
function statement(overrides: Record<string, unknown> = {}) {
  return {
    id: 39,
    title: "F26-04 Materialkauf",
    short_description: "Materialkauf",
    explanation: "",
    submitted: true,
    confirmed: false,
    status: 1,
    status_display: "Eingereicht",
    payout_mode: "office",
    is_valid: true,
    validity: 0,
    validity_display: "Alles korrekt.",
    transaction_issues: [],
    excursion: null,
    created_by: MILA,
    submitted_by: MILA,
    confirmed_by: null,
    submitted_date: "2026-05-02",
    confirmed_date: null,
    allowance_to: [],
    subsidy_to: null,
    ljp_to: null,
    night_cost: 0,
    bills: [],
    total: 56,
    ...overrides,
  };
}

/** The record for a section whose one signature is the department head's. */
function approval(overrides: Record<string, unknown> = {}) {
  return {
    statement_id: 39,
    approved: false,
    // Hers is the signature the rules are waiting for, and it completes them.
    may_approve: true,
    completes_approval: true,
    constraints: [
      {
        name: "Freigabe der Leitung",
        description: "Die zuständige Ressortleitung",
        applicable: true,
        required: 1,
        satisfied: false,
        overridden: false,
        open: true,
        missing: 1,
        state_display: "Offen",
        eligible: [MELISSA],
        signed_by: [],
        excluded: [],
        overridden_by: null,
        override_reason: "",
      },
    ],
    signatures: [],
    ...overrides,
  };
}

/** One declaration, with the fields `/form` always sends. */
function declaration(overrides: Record<string, unknown>): Record<string, unknown> {
  return {
    required: false,
    help: "",
    max: null,
    options: [],
    choices: [],
    fields: [],
    step: "",
    derived: false,
    ...overrides,
  };
}

/** One cell of a `rows` declaration — no `options` of its own, by contract. */
function cell(overrides: Record<string, unknown>): Record<string, unknown> {
  return { required: false, help: "", max: null, choices: [], ...overrides };
}

/**
 * The questions a section like Ludwigsburg's asks, which *are* the statement.
 *
 * Grouped into two steps, with a derived reading, a choice, an int and a table
 * — so the test says the signer reads each shape as a reading and not as the
 * JSON it is stored as.
 */
const DECLARATIONS = [
  declaration({
    key: "regelwerk",
    label: "Regelwerk",
    type: "choice",
    step: "Grundlage",
    choices: [
      { value: "ehrenamt", label: "Ehrenamtspauschale" },
      { value: "uebungsleiter", label: "Übungsleiterpauschale" },
    ],
  }),
  declaration({
    key: "kilometer",
    label: "Gefahrene Kilometer",
    type: "int",
    step: "Grundlage",
    derived: true,
    source: "excursion.kilometers",
  }),
  declaration({ key: "naechte", label: "Übernachtungen", type: "int", step: "Angaben" }),
  declaration({ key: "stunden", label: "Betreuungsstunden", type: "int", step: "Angaben" }),
  declaration({
    key: "tagegeld_an",
    label: "Tagegeld an",
    type: "member",
    step: "Angaben",
    options: [MILA, MELISSA],
  }),
  declaration({
    key: "reisen",
    label: "Fahrten",
    type: "rows",
    step: "Angaben",
    options: [MILA, MELISSA],
    fields: [
      cell({ key: "person", label: "Person", type: "member" }),
      cell({ key: "kilometers", label: "Kilometer", type: "int" }),
      cell({ key: "anreise", label: "Anreise", type: "text" }),
    ],
  }),
];

const FORM = {
  statement_id: 39,
  inputs: DECLARATIONS,
  steps: [
    { label: "Grundlage", keys: ["regelwerk", "kilometer"] },
    { label: "Angaben", keys: ["naechte", "stunden", "tagegeld_an", "reisen"] },
  ],
  answers: {
    regelwerk: "uebungsleiter",
    kilometer: 412,
    naechte: 3,
    stunden: 26,
    tagegeld_an: MILA.id,
    reisen: [
      { person: MILA.id, kilometers: 212, anreise: "PKW" },
      { person: MELISSA.id, kilometers: 200, anreise: "Bahn" },
    ],
  },
};

/** What `openAsSigner` lets a test vary; everything else is the instance. */
interface Scene {
  /** Fields of the statement the pipeline reads (`is_valid`, …). */
  statement?: Record<string, unknown>;
  /** The approval record `/approval` answers with. */
  record?: Record<string, unknown>;
  /** The bookings `…/transactions` answers with. */
  bookings?: unknown[];
  /** What `…/form` answers — a payload, or a refusal. */
  form?: () => Response;
  /** What `/ledgers/` answers. The default is the 403 she actually gets. */
  ledgers?: () => Response;
  /** The codenames she holds. The default is the one she holds. */
  permissions?: string[];
}

/**
 * Open one leg of the pipeline as the named signer.
 *
 * `finance.process_statementsubmitted` and nothing else, which is exactly what
 * she holds on the instance — no `finance.view_ledger`, no
 * `finance.view_global_statement`. `/ledgers/` answers 403 the way the
 * permission layer does, so a client that asks for it anyway gets the answer
 * it got on the instance.
 *
 * Returns the mutable call log, so a test can say which endpoint her click
 * reached: the whole point is that the ordinary act is offered, not the
 * override.
 */
function openAsSigner(leg: string, scene: Scene = {}) {
  const {
    statement: overrides = {},
    record = approval(),
    bookings = [BOOKING],
    form = () => HttpResponse.json(FORM),
    ledgers = () => HttpResponse.json({ detail: "finance.view_ledger" }, { status: 403 }),
    permissions = ["finance.process_statementsubmitted"],
  } = scene;
  useMe({ member_id: MELISSA.id, name: MELISSA.name, permissions });
  const posted: string[] = [];
  server.use(
    http.get(api("/api/finance/statements/39"), () => HttpResponse.json(statement(overrides))),
    http.get(api("/api/finance/statements/39/transactions"), () => HttpResponse.json(bookings)),
    http.get(api("/api/finance/statements/39/approval"), () => HttpResponse.json(record)),
    http.get(api("/api/finance/statements/39/form"), form),
    http.get(api("/api/finance/ledgers/"), ledgers),
    http.get(api("/api/members/"), () => HttpResponse.json([MILA, MELISSA])),
    http.post(api("/api/finance/statements/39/approve"), () => {
      posted.push("approve");
      return HttpResponse.json(approval({ approved: true, may_approve: false }));
    }),
    http.post(api("/api/finance/statements/39/confirm"), () => {
      posted.push("confirm");
      return HttpResponse.json(statement({ ...overrides, confirmed: true, status: 2 }));
    }),
    http.post(api("/api/finance/statements/39/override-approval"), () => {
      posted.push("override");
      return HttpResponse.json(record);
    }),
  );
  return { ...renderRoute(`/kompass/finance/statements/39/review?stage=${leg}`), posted };
}

/** The Konto cell of the one booking on the Buchungen leg. */
async function kontoCell(): Promise<HTMLElement> {
  const row = (await screen.findByText("Seil und Haken")).closest("tr") as HTMLElement;
  return within(row).getByText(/Topf|kein Konto/).closest("td") as HTMLElement;
}

/** The statement a missing account has locked. */
const LOCKED = {
  statement: { is_valid: false, validity: 2, validity_display: "Eine Buchung hat kein Konto." },
  bookings: [{ ...BOOKING, ledger: null }],
};

describe("the named signer — the account on the booking", () => {
  it("reads the account off the booking without the chart of accounts", async () => {
    openAsSigner("bookings");

    // The name the server put there, not the placeholder of an empty picker.
    const konto = await kontoCell();
    expect(within(konto).getByText("Topf")).toBeInTheDocument();
    // And it is a reading: choosing an account means choosing out of the
    // catalogue, which is the permission she does not hold.
    expect(konto.querySelector(".ss-trigger")).toBeNull();
    expect(screen.queryByText(/Buchung\(en\) ohne Konto/)).not.toBeInTheDocument();
  });

  it("says a booking has no account rather than pretending it has one", async () => {
    // The other half, and the reason the first one is not just "hide the
    // picker": a booking that genuinely carries no account must still read as
    // one, and the leg must still say what that holds up.
    openAsSigner("bookings", LOCKED);

    const konto = await kontoCell();
    expect(within(konto).getByText("— kein Konto —")).toBeInTheDocument();
    expect(screen.getByText(/1 Buchung\(en\) ohne Konto/)).toBeInTheDocument();
  });

  it("still offers the treasurer the picker it took away from the signer", async () => {
    // The control on the permission: the same leg, the same booking, somebody
    // who may read the catalogue. Without this, "the cell is text" passes
    // against a build that made it text for everybody.
    openAsSigner("bookings", {
      permissions: ["finance.process_statementsubmitted", "finance.view_ledger"],
      ledgers: () =>
        HttpResponse.json([
          { id: 4, name: "Topf" },
          { id: 5, name: "Sektionskonto" },
        ]),
    });

    const konto = await kontoCell();
    await waitFor(() =>
      expect(within(konto).getByText("Topf").closest(".ss-trigger")).not.toBeNull(),
    );
  });
});
