import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute, renderWithApp } from "../../test/utils";
import { ErstattungStep } from "./StatementFlow";
import type { components } from "../../api/schema";

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
    // The rail reads them for the Erstattung leg, which the review shows now.
    transfers: [],
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
        // A section like Ludwigsburg, whose rules allow no override at all.
        may_override: false,
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
  declaration({
    key: "naechte",
    label: "Übernachtungen",
    type: "int",
    step: "Angaben",
    // A hint, so that a reading which dropped the declaration's own help is a
    // reading of a different form.
    help: "Je Nacht 10 € pro Person.",
  }),
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
      cell({ key: "kilometers", label: "Kilometer", type: "int", help: "Hin und zurück" }),
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
  const fetched: string[] = [];
  server.use(
    http.get(api("/api/finance/statements/39"), () => HttpResponse.json(statement(overrides))),
    http.get(api("/api/finance/statements/39/transactions"), () => HttpResponse.json(bookings)),
    http.get(api("/api/finance/statements/39/approval"), () => HttpResponse.json(record)),
    http.get(api("/api/finance/statements/39/form"), form),
    http.get(api("/api/finance/ledgers/"), () => {
      fetched.push("ledgers");
      return ledgers();
    }),
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
  return {
    ...renderRoute(`/kompass/finance/statements/39/review?stage=${leg}`),
    posted,
    /** Which of the endpoints the page only *sometimes* asks for it asked for. */
    fetched,
  };
}

/** The Konto cell of the one booking on the Buchungen leg. */
async function kontoCell(): Promise<HTMLElement> {
  const row = (await screen.findByText("Seil und Haken")).closest("tr") as HTMLElement;
  return within(row).getByText(/Topf|kein Konto/).closest("td") as HTMLElement;
}

/**
 * Every question on screen against its answer, as the signer reads them.
 *
 * Read off the submitter's own rendering, because that is what she is shown:
 * a reading of the trip as the `DerivedFacts` the form states it in, and a
 * question as its field, with the answer where the control was. Scoped to the
 * answer groups, so nothing else that states facts as terms is mistaken for an
 * answer.
 */
function readings(): Record<string, string> {
  const pairs: Record<string, string> = {};
  for (const term of document.querySelectorAll(".answer-group dt")) {
    pairs[term.textContent ?? ""] = term.nextElementSibling?.textContent ?? "";
  }
  for (const field of document.querySelectorAll(".answer-group .field-readonly")) {
    const label = field.querySelector(".field-label")?.textContent ?? "";
    pairs[label] = field.querySelector(".field-value")?.textContent ?? "";
  }
  return pairs;
}

/** The statement a missing account has locked. */
const LOCKED = {
  statement: { is_valid: false, validity: 2, validity_display: "Eine Buchung hat kein Konto." },
  bookings: [{ ...BOOKING, ledger: null }],
};

describe("the named signer — the account on the booking", () => {
  it("does not ask for a catalogue it may not read", async () => {
    // The request itself, and not only what was done with the answer. A page
    // that asks and discards the 403 works by accident: the next reader of
    // the code sees a ledger query beside a cell that does not use it, and
    // the browser console fills with refusals that are not defects.
    const { fetched } = openAsSigner("bookings");
    await kontoCell();
    expect(fetched).toEqual([]);
  });

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
    const { fetched } = openAsSigner("bookings", {
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
    // And she asks for the catalogue, because she is choosing out of it.
    expect(fetched).toEqual(["ledgers"]);
  });
});

describe("the named signer — the statement, not only its arithmetic", () => {
  it("shows the questions and the answers the payout was computed from", async () => {
    openAsSigner("reimbursement");

    // The grouping is the ruleset's own, so she reads the questions as the
    // person filling them in saw them.
    expect(await screen.findByText("Grundlage")).toBeInTheDocument();
    expect(screen.getByText("Angaben")).toBeInTheDocument();
    // Every question against its own answer, as a map, because a payload
    // whose answers were dropped renders a form of dashes and a test that
    // looked for the labels alone would call that a statement.
    expect(readings()).toEqual({
      // A choice reads as its label and never as the value that is stored.
      Regelwerk: "Übungsleiterpauschale",
      // A derived reading is a fact about the statement and reads like the
      // rest of it.
      "Gefahrene Kilometer": "412",
      // The nights, the hours and the Tagegeld — none of which this surface
      // showed at all.
      Übernachtungen: "3",
      Betreuungsstunden: "26",
      "Tagegeld an": "Mila Nowak",
    });
  });

  it("reads a travel table as rows rather than as the JSON it is stored as", async () => {
    openAsSigner("reimbursement");

    const table = (await screen.findByText("Fahrten")).closest("div")
      ?.querySelector("table.rows-table") as HTMLElement;
    expect(within(table).getByText("Kilometer")).toBeInTheDocument();
    // Per traveller, because whether somebody gets the rate per kilometre at
    // all depends on *their* mode of travel.
    expect(within(table).getByText("212")).toBeInTheDocument();
    expect(within(table).getByText("PKW")).toBeInTheDocument();
    expect(within(table).getByText("Melissa Gruber")).toBeInTheDocument();
    expect(within(table).getByText("Bahn")).toBeInTheDocument();
  });

  it("asks nothing of a ruleset that asks nothing, and says so", async () => {
    openAsSigner("reimbursement", {
      form: () => HttpResponse.json({ statement_id: 39, inputs: [], steps: [], answers: {} }),
    });
    expect(
      await screen.findByText("Für diese Abrechnung fragen die Regeln nichts ab."),
    ).toBeInTheDocument();
  });

  it("says the answers are missing when they cannot be loaded", async () => {
    openAsSigner("reimbursement", {
      form: () =>
        HttpResponse.json({ detail: "Die Angaben sind nicht lesbar." }, { status: 500 }),
    });
    // The leg says it is missing, in the voice the API's refusals are reported
    // in, rather than rendering an empty frame.
    expect(
      await screen.findByText(
        "Serverfehler — die Aktion konnte nicht ausgeführt werden. Bitte versuche es erneut.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps the signatures and the transfers when the answers cannot be loaded", async () => {
    openAsSigner("payout", {
      form: () =>
        HttpResponse.json({ detail: "Die Angaben sind nicht lesbar." }, { status: 500 }),
    });
    // The Freigabe leg is everything it always was: the record and the
    // transfers do not depend on the answers, and the answers are not on it.
    expect(await screen.findByText("Die zuständige Ressortleitung")).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Übergabe an die Geschäftsstelle" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Freigeben und zur Auszahlung übergeben" })).toBeEnabled();
  });
});

describe("the named signer — signing is not paying", () => {
  it("offers the signature, not only the override, when a booking has no account", async () => {
    // The defect, end to end. The payout is genuinely locked; her signature is
    // not, and it was the only act she could not reach.
    const { user, posted } = openAsSigner("payout", LOCKED);

    const sign = await screen.findByRole("button", { name: "Freigabe erteilen" });
    expect(sign).toBeEnabled();
    // The payout is not offered, because `/confirm` would refuse it...
    expect(
      screen.queryByRole("button", { name: "Freigeben und zur Auszahlung übergeben" }),
    ).not.toBeInTheDocument();
    // ...and the leg says why the money is not moving with the signature.
    expect(
      screen.getByText("Die Übergabe ist gesperrt: Eine Buchung hat kein Konto."),
    ).toBeInTheDocument();
    // Nor is there an acknowledgement: nothing is being paid out to claim.
    expect(
      screen.queryByText("Ich habe die aufgeführten Überweisungen ausgeführt."),
    ).not.toBeInTheDocument();

    await user.click(sign);
    await waitFor(() => expect(posted).toEqual(["approve"]));
  });

  it("releases the statement when the bookkeeping is in, as it always did", async () => {
    // The other side of the same branch: a statement that *is* payable offers
    // the release and not a bare signature, for the section that asks for one
    // signature and has always read as a single act.
    const { user, posted } = openAsSigner("payout");

    const release = await screen.findByRole("button", { name: "Freigeben und zur Auszahlung übergeben" });
    expect(screen.queryByRole("button", { name: "Freigabe erteilen" })).not.toBeInTheDocument();
    expect(screen.queryByText(/ist gesperrt/)).not.toBeInTheDocument();
    await user.click(release);
    await user.click(await screen.findByRole("button", { name: "Freigeben & übergeben" }));
    await waitFor(() => expect(posted).toEqual(["confirm"]));
  });

  it("asks nobody signing a locked statement to claim a payout", async () => {
    // Where the reviewer makes the transfers there *is* an acknowledgement,
    // and it belongs to the payout: "ich habe die Überweisungen ausgeführt" in
    // front of a signature that releases nothing is the false claim the
    // acknowledgement exists to prevent. The section above pays through its
    // Geschäftsstelle and asks for none, so this is the mode that can tell.
    openAsSigner("payout", {
      ...LOCKED,
      statement: { ...LOCKED.statement, payout_mode: "self" },
    });

    expect(await screen.findByRole("button", { name: "Freigabe erteilen" })).toBeEnabled();
    expect(
      screen.queryByText("Ich habe die aufgeführten Überweisungen ausgeführt."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Auszahlen ist gesperrt: Eine Buchung hat kein Konto."),
    ).toBeInTheDocument();
  });

  it("still asks it of the payout that is actually about to happen", async () => {
    // The other arm, so "the acknowledgement is absent" cannot pass against a
    // build that dropped it: the same section, nothing locked, and the payout
    // waits for the sentence it has always waited for.
    openAsSigner("payout", { statement: { payout_mode: "self" } });

    expect(
      await screen.findByText("Ich habe die aufgeführten Überweisungen ausgeführt."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Freigeben & Beleg senden" })).toBeDisabled();
  });

  it("lets her reach the leg at all while the payout is locked", async () => {
    // The lock used to make the whole leg unreachable, which is how the
    // signature disappeared: the rail refused the step, the URL fell back to
    // the first one, and nothing on screen was the act she was asked for.
    openAsSigner("payout", LOCKED);
    expect(await screen.findByRole("heading", { name: "Freigabe" })).toBeInTheDocument();
  });

  it("keeps the leg shut when a locked statement leaves her nothing to sign", async () => {
    // The bound: reachability is her own signature, not the lock being
    // ignored. Somebody with nothing left to sign gets the pipeline's first
    // leg, exactly as before.
    openAsSigner("payout", {
      ...LOCKED,
      record: approval({ may_approve: false, completes_approval: false }),
    });
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Freigabe" })).not.toBeInTheDocument();
  });
});

describe("the named signer — and somebody the rules did not name", () => {
  it("shows a member the rules named on nothing none of it", async () => {
    // The control that keeps all of the above from being "everybody sees
    // everything": the same capability, no role, and the statement is not
    // hers to open — so there is no account, no answer and no button.
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    server.use(
      http.get(api("/api/finance/statements/39"), () =>
        HttpResponse.json({ detail: "finance.view_obj_statement" }, { status: 403 }),
      ),
    );
    renderRoute("/kompass/finance/statements/39/review?stage=payout");

    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
    expect(screen.queryByText("Seil und Haken")).not.toBeInTheDocument();
    expect(screen.queryByText("Topf")).not.toBeInTheDocument();
    expect(screen.queryByText("Übungsleiterpauschale")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Freigabe erteilen" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Freigeben und zur Auszahlung übergeben" }),
    ).not.toBeInTheDocument();
  });
});

describe("the named signer — the statement in the shape it was filled in", () => {
  /**
   * What gives the leg its shape, in document order: the heading, the groups,
   * every label and hint, the readings of the trip and the table's columns.
   * Everything but the controls, which is the one thing that may differ.
   */
  function skeleton(root: HTMLElement): string[] {
    const shape =
      "h2, .answer-group-title, .field-label, .field-hint, .readout-caption, .readout dt, .rows-table th";
    return [...root.querySelectorAll(shape)]
      .map((node) => node.textContent?.trim() ?? "")
      .filter((text) => text !== "");
  }

  /** The submitter's Erstattung leg on its own, editable or not. */
  function renderLeg(readOnly: boolean) {
    useMe({ member_id: MELISSA.id, name: MELISSA.name });
    server.use(
      http.get(api("/api/finance/statements/39/form"), () => HttpResponse.json(FORM)),
      http.get(api("/api/members/"), () => HttpResponse.json([MILA, MELISSA])),
    );
    const subject = statement() as unknown as components["schemas"]["StatementOut"];
    return renderWithApp(<ErstattungStep statement={subject} readOnly={readOnly} />);
  }

  /** The labels on the review's rail, in order. */
  function rail(): string[] {
    return [...document.querySelectorAll(".etappe-label")].map(
      (label) => label.textContent?.replace(/^\d+/, "").trim() ?? "",
    );
  }

  it("is the submitter's own leg, with the answers where the controls were", async () => {
    const editable = renderLeg(false);
    await screen.findByText("Übernachtungen");
    const asFilledIn = skeleton(editable.container);
    expect(asFilledIn).toContain("Grundlage");
    expect(asFilledIn).toContain("Je Nacht 10 € pro Person.");
    // A column heading carries its own hint inside it.
    expect(asFilledIn).toContain("KilometerHin und zurück");
    // There is something to type into on this one, so the comparison below is
    // between a form and its reading rather than between two readings.
    expect(editable.container.querySelectorAll(".answer-group input").length).toBeGreaterThan(0);
    editable.unmount();

    const reading = renderLeg(true);
    await screen.findByText("Übernachtungen");
    // The same structure, to the label: editability is the only difference.
    expect(skeleton(reading.container)).toEqual(asFilledIn);
    // And that difference is total: nothing on it can be changed.
    expect(
      reading.container.querySelectorAll(
        ".answer-group input, .answer-group select, .answer-group textarea, .answer-group button",
      ),
    ).toHaveLength(0);
    expect(readings()).toMatchObject({ Übernachtungen: "3", "Tagegeld an": "Mila Nowak" });
  });

  it("is a leg of the review, where the submitter's flow has it", async () => {
    openAsSigner("expenses");
    // After the receipts, before anything is booked — and not appended under
    // the signatures, where it used to be a layout of its own.
    await waitFor(() => expect(rail()).toEqual(["Prüfen", "Erstattung", "Buchungen", "Freigabe"]));
  });

  it("takes the answers off the Freigabe leg", async () => {
    openAsSigner("payout");
    expect(await screen.findByText("Die zuständige Ressortleitung")).toBeInTheDocument();
    expect(document.querySelector(".answer-group")).toBeNull();
    expect(screen.queryByText("Angaben zur Abrechnung")).not.toBeInTheDocument();
  });

  it("has no Erstattung leg under rules that ask nothing", async () => {
    openAsSigner("payout", {
      form: () => HttpResponse.json({ statement_id: 39, inputs: [], steps: [], answers: {} }),
    });
    await screen.findByText("Die zuständige Ressortleitung");
    await waitFor(() => expect(rail()).toEqual(["Prüfen", "Buchungen", "Freigabe"]));
  });

  it("reads a table without a row to add or remove", async () => {
    openAsSigner("reimbursement");
    const table = (await screen.findByText("Fahrten")).closest(".rows-field") as HTMLElement;
    expect(within(table).getByText("212")).toBeInTheDocument();
    expect(within(table).queryByRole("button")).not.toBeInTheDocument();
    expect(within(table).queryByText("+ Zeile hinzufügen")).not.toBeInTheDocument();
  });
});
