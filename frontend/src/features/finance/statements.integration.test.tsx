import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  api,
  djangoValidation,
  http,
  HttpResponse,
  multipartFields,
  multipartFilenames,
  server,
  useMe,
} from "../../test/server";
import { currentSearch, renderRoute, sortByEveryColumn } from "../../test/utils";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

const BRIEFS = [
  {
    id: 1,
    title: "F26-01 Skifreizeit",
    status_display: "Entwurf",
    submitted: false,
    confirmed: false,
    excursion_id: 3,
    created_by: { id: 7, name: "Hannah Beckers" },
    total: 240.5,
    total_pretty: "240,50 €",
    short_description: "Skifreizeit",
    status: 0,
    submitted_date: null,
    confirmed_date: null,
  },
  {
    id: 2,
    title: "F26-02 Materialkauf",
    status_display: "Eingereicht",
    submitted: true,
    confirmed: false,
    excursion_id: null,
    created_by: { id: 8, name: "Tobias Werner" },
    total: 89,
    total_pretty: "89,00 €",
    short_description: "Materialkauf",
    status: 1,
    submitted_date: "2026-05-02",
    confirmed_date: null,
  },
];

const LEDGERS = [
  { id: 1, name: "Jugendetat" },
  { id: 2, name: "Sektionskonto" },
];

const ENUMS = {
  status: [
    { value: 0, label: "Entwurf" },
    { value: 1, label: "Eingereicht" },
    { value: 2, label: "Bezahlt" },
  ],
};

/** A full StatementOut; `overrides` moves it through the workflow. */
function statement(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    title: "F26-01 Skifreizeit",
    status_display: "Entwurf",
    submitted: false,
    confirmed: false,
    is_valid: true,
    validity: 0,
    validity_display: "Gültig",
    // Who makes the transfers. The reference arrangement, so every test above
    // describes the section Kompass shipped for.
    payout_mode: "self",
    transaction_issues: [],
    excursion: { id: 3, code: "F26-01", name: "Skifreizeit" },
    created_by: { id: 7, name: "Hannah Beckers" },
    submitted_by: null,
    confirmed_by: null,
    subsidy_to: null,
    ljp_to: null,
    allowance_to: [],
    night_cost: 11,
    bills: [],
    // The payout as the engine resolved it. Every money figure below is a
    // summary of these, and the flow's preview reads them rather than
    // re-deriving a breakdown from the named totals.
    transfers: [],
    total: 240.5,
    total_bills: 240.5,
    total_bills_theoretic: 240.5,
    total_bills_not_covered: 0,
    total_theoretic: 240.5,
    total_allowance: 0,
    allowance_per_yl: 0,
    allowances_paid: 0,
    total_subsidies: 0,
    subsidies_paid: 0,
    total_transportation: 0,
    transportation_per_yl: 0,
    total_nights: 0,
    nights_per_yl: 0,
    real_night_cost: 0,
    euro_per_km: 0.3,
    total_per_yl: 0,
    total_staff: 0,
    total_staff_paid: 0,
    theoretical_total_staff: 0,
    real_staff_count: 0,
    total_org_fee: 0,
    total_org_fee_theoretical: 0,
    paid_ljp_contributions: 0,
    short_description: "Skifreizeit",
    explanation: "",
    status: 0,
    submitted_date: null,
    confirmed_date: null,
    ...overrides,
  };
}

const LEADERS = [
  { id: 7, name: "Hannah Beckers" },
  { id: 9, name: "Mila Nowak" },
];

/** The alternatives a `choice` declaration offers, as `/form` sends them. */
const REGIMES = [
  { value: "ehrenamt", label: "Ehrenamtspauschale" },
  { value: "uebungsleiter", label: "Übungsleiterpauschale" },
];

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

/**
 * One cell of a `rows` declaration, with the fields `/form` always sends.
 *
 * No `options` of its own, and that is the contract rather than an omission:
 * the people a party-valued cell may name are the *question's* options, stated
 * once for the whole table, because one column served two different sets of
 * people in two rows is not a thing a form can explain.
 */
function cell(overrides: Record<string, unknown>): Record<string, unknown> {
  return { required: false, help: "", max: null, choices: [], ...overrides };
}

/** How a section's rules name the ways somebody got to the trip. */
const APPROACHES = [
  { value: "pkw", label: "PKW" },
  { value: "bahn", label: "Bahn" },
  { value: "rad", label: "Fahrrad" },
];

/**
 * The repeating row, as `/form` declares one.
 *
 * `max` is the number of **rows**; the ceiling on a cell is on the cell. The
 * people are on the question.
 */
const REISEN = declaration({
  key: "reisen",
  label: "Fahrten",
  type: "rows",
  help: "Für jede Person, die unterwegs war, eine Zeile.",
  max: 3,
  options: LEADERS,
  fields: [
    cell({ key: "member", label: "Person", type: "member" }),
    cell({ key: "approach", label: "Verkehrsmittel", type: "choice", choices: APPROACHES }),
    cell({ key: "kilometers", label: "Kilometer", type: "int", max: 2000 }),
  ],
});

/**
 * `inputs` partitioned into steps the way the API partitions them.
 *
 * `/form` always sends a partition of the whole form — a ruleset that named no
 * steps comes back as one step labelled `""` — so a stub that says what the
 * rules ask has to say how they group too. Computed the same way the backend
 * computes it rather than written out beside every `inputs`, so a test about
 * something else does not have to carry a grouping.
 */
function stepsOf(inputs: Record<string, unknown>[]) {
  const grouped = new Map<string, string[]>();
  for (const input of inputs) {
    const label = String(input.step ?? "");
    grouped.set(label, [...(grouped.get(label) ?? []), String(input.key)]);
  }
  return [...grouped].map(([label, keys]) => ({ label, keys }));
}

/**
 * The form the section's rules ask for, and what stands in the way.
 *
 * The flow's reimbursement step renders whatever `/form` declares and its last
 * leg prints whatever `/preflight` finds — neither is a list of fields or a
 * list of checks written in the client any more, so both are stubbed.
 */
const FORM_INPUTS = [
  declaration({
    key: "night_cost",
    label: "Preis pro Übernachtung",
    type: "money",
    help: "Was eine Übernachtung pro Jugendleiter*in gekostet hat.",
  }),
  declaration({
    key: "allowance_to",
    label: "Aufwandsentschädigung an",
    type: "member_set",
    options: LEADERS,
    max: 2,
  }),
  declaration({
    key: "subsidy_to",
    label: "Fahrt- und Übernachtungszuschuss an",
    type: "member",
    options: LEADERS,
  }),
];

const FORM = {
  statement_id: 1,
  inputs: FORM_INPUTS,
  steps: stepsOf(FORM_INPUTS),
  answers: { night_cost: "11.00", allowance_to: [], subsidy_to: null },
};

const PREFLIGHT = {
  statement_id: 1,
  ok: true,
  checks: [{ ok: true, message: "Jeder Beleg hat ein Bild." }],
  failing: [],
  errors: [],
};

/** The approval record, as `/approval` sends it for a one-signature section. */
const APPROVAL = {
  statement_id: 1,
  approved: false,
  may_approve: false,
  // One constraint satisfied by one signature: the next click is the payout,
  // which is what keeps a section like Heidelberg reading as the single act it
  // has always been.
  completes_approval: true,
  constraints: [
    {
      name: "Freigabe",
      description: "Eine Unterschrift aus der Finanzverwaltung",
      applicable: true,
      required: 1,
      satisfied: false,
      overridden: false,
      open: true,
      missing: 1,
      state_display: "Offen",
      eligible: [LEADERS[0]],
      signed_by: [],
      excluded: [],
      overridden_by: null,
      override_reason: "",
    },
  ],
  signatures: [],
};

/** Everything the detail page and its inlines fetch. */
function detailReturns(data: Record<string, unknown> = {}) {
  const s = statement(data);
  server.use(
    http.get(api("/api/finance/statements/1"), () => HttpResponse.json(s)),
    http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
    http.get(api("/api/finance/statements/1/form"), () => HttpResponse.json(FORM)),
    http.get(api("/api/finance/statements/1/preflight"), () => HttpResponse.json(PREFLIGHT)),
    // The record is a tab of the statement and the review's last leg reads it
    // to know which act it is offering, so both pages ask for it.
    http.get(api("/api/finance/statements/1/approval"), () => HttpResponse.json(APPROVAL)),
    http.get(api("/api/members/"), () => HttpResponse.json(LEADERS)),
    http.get(api("/api/finance/ledgers/"), () => HttpResponse.json(LEDGERS)),
  );
  return s;
}

/** A transfer the engine resolved, as `StatementOut.transfers` carries it. */
function transfer(overrides: Record<string, unknown> = {}) {
  return {
    source: { kind: "section", member: null },
    destination: { kind: "member", member: LEADERS[0] },
    amount: 80,
    category: "allowance",
    rule_id: "allowance",
    label: "Aufwandsentschädigung",
    explanation: "2 × 40,00 €",
    reference: "",
    ...overrides,
  };
}

const EXCURSION_DETAIL = {
  id: 3,
  code: "F26-01",
  name: "Skifreizeit",
  duration: 3,
  night_count: 2,
  tour_approach_str: "PKW",
  kilometers_traveled: 120,
  staff_count: 2,
  participant_count: 8,
  jugendleiter: [
    { id: 7, name: "Hannah Beckers" },
    { id: 9, name: "Mila Nowak" },
  ],
};

/** Everything the submission flow fetches for its excursion branch. */
function flowReturns(excursions: Record<string, unknown>[] = [{ id: 3, code: "F26-01", name: "Skifreizeit" }]) {
  server.use(
    http.get(api("/api/members/excursions"), () => HttpResponse.json(excursions)),
    http.get(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION_DETAIL)),
    http.get(api("/api/members/"), () =>
      HttpResponse.json([
        { id: 7, name: "Hannah Beckers" },
        { id: 9, name: "Mila Nowak" },
      ]),
    ),
  );
}

function listReturns() {
  server.use(
    http.get(api("/api/finance/statements"), () => HttpResponse.json(BRIEFS)),
    http.get(api("/api/finance/enums"), () => HttpResponse.json(ENUMS)),
  );
}

describe("statements list", () => {
  it("shows both statements with their status", async () => {
    listReturns();
    renderRoute("/kompass/finance/statements");

    expect(await screen.findByText("F26-01 Skifreizeit")).toBeInTheDocument();
    expect(screen.getByText("F26-02 Materialkauf")).toBeInTheDocument();
    expect(screen.getByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByText("Eingereicht")).toBeInTheDocument();
    expect(screen.getByText("240,50 €")).toBeInTheDocument();
  });

  it("filters by the status enum fetched from the backend", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");

    // The status filter is a custom combobox, not a native <select>.
    await user.click(screen.getByRole("button", { name: /Status:/ }));
    const dropdown = document.querySelector(".ms-dropdown") as HTMLElement;
    await user.click(within(dropdown).getByRole("button", { name: "Eingereicht" }));

    await waitFor(() =>
      expect(screen.queryByText("F26-01 Skifreizeit")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("F26-02 Materialkauf")).toBeInTheDocument();
    // The header keeps naming the unfiltered total, so nobody thinks rows vanished.
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("hides the create button without finance.add_global_statement", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");
    expect(screen.queryByRole("button", { name: "Neue Abrechnung" })).not.toBeInTheDocument();
  });
});

describe("statements list — remaining paths", () => {
  it("searches by title and short description", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");
    await user.type(screen.getByPlaceholderText("Suchen…"), "material");
    await waitFor(() =>
      expect(screen.queryByText("F26-01 Skifreizeit")).not.toBeInTheDocument(),
    );
  });

  it("sorts by every column in both directions", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("shows an em dash for a statement nobody created", async () => {
    server.use(
      http.get(api("/api/finance/statements"), () =>
        HttpResponse.json([{ ...BRIEFS[0], created_by: null }]),
      ),
      http.get(api("/api/finance/enums"), () => HttpResponse.json(ENUMS)),
    );
    renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("opens a statement from its row", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements");

    await user.click(await screen.findByText("F26-01 Skifreizeit"));
    expect(await screen.findByRole("button", { name: "Weiter bearbeiten" })).toBeInTheDocument();
  });

  it("starts a new statement in the submission flow rather than a dialog", async () => {
    listReturns();
    flowReturns();
    const { user } = renderRoute("/kompass/finance/statements");

    await user.click(await screen.findByRole("button", { name: "Neue Abrechnung" }));
    expect(
      await screen.findByRole("heading", { name: "Wofür ist diese Abrechnung?" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("copes with an API that sends null for the optional fields", async () => {
    detailReturns({
      short_description: null,
      explanation: null,
      night_cost: null,
      created_by: null,
      submitted_by: null,
      confirmed_by: null,
      allowance_to: null,
      excursion: { id: 3, code: "F26-01", name: "" },
    });
    const { user } = renderRoute("/kompass/finance/statements/1");
    // Every missing value renders as an em dash rather than blowing up.
    await screen.findByRole("button", { name: "Weiter bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: "Empfänger" }));
    expect(screen.getByText(/Erstattungs-Schritt/)).toBeInTheDocument();
  });

  it("reports a rejected save whose body is not JSON", async () => {
    flowReturns([]);
    detailReturns();
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        new HttpResponse("<html>500</html>", { status: 500 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=purpose");
    await user.click(await screen.findByRole("button", { name: "Weiter" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("unconfirms a paid statement without a further prompt", async () => {
    detailReturns({
      submitted: true,
      confirmed: true,
      status: 2,
      status_display: "Bezahlt",
    });
    let unconfirmed = false;
    server.use(
      http.post(api("/api/finance/statements/1/unconfirm"), () => {
        unconfirmed = true;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bestätigung aufheben" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Bestätigen" }),
    );
    await waitFor(() => expect(unconfirmed).toBe(true));
  });
});

describe("submission flow — Anlass", () => {
  it("creates the draft and continues into the Belege step", async () => {
    flowReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    detailReturns();

    const { user } = renderRoute("/kompass/finance/statements/new");
    await user.click(await screen.findByRole("radio", { name: /Sonstige Ausgabe/ }));
    await user.type(screen.getByLabelText(/Kurzbeschreibung/), "Skifreizeit");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    await waitFor(() => expect(body).not.toBeNull());
    // What the statement is for, and nothing a section's rules might not ask
    // about: `night_cost` used to be here because it used to be a column.
    expect(body).toEqual({
      short_description: "Skifreizeit",
      explanation: "",
      excursion_id: null,
    });
    expect(await screen.findByRole("heading", { name: "Belege" })).toBeInTheDocument();
  });

  it("sends the chosen excursion as a number and names the draft after it", async () => {
    flowReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    detailReturns();

    const { user } = renderRoute("/kompass/finance/statements/new");
    await user.click(await screen.findByRole("button", { name: "Fahrt" }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ excursion_id: 3, short_description: "Skifreizeit" });
  });

  it("states the trip facts the payout is derived from", async () => {
    flowReturns();
    const { user } = renderRoute("/kompass/finance/statements/new");
    await user.click(await screen.findByRole("button", { name: "Fahrt" }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));

    const readout = (await screen.findByText("Übernachtungen")).closest(".readout") as HTMLElement;
    expect(within(readout).getByText("PKW")).toBeInTheDocument();
    expect(within(readout).getByText("120")).toBeInTheDocument();
  });

  it("shows a server field error on every field of the step", async () => {
    flowReturns([]);
    server.use(
      http.post(api("/api/finance/statements"), () =>
        djangoValidation({
          short_description: ["Die Beschreibung fehlt."],
          explanation: ["Zu lang."],
          excursion: ["Unbekannte Ausfahrt."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/new");
    await user.type(await screen.findByLabelText(/Kurzbeschreibung/), "x");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    expect(await screen.findAllByText("Die Beschreibung fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();
    expect(screen.getByText("Unbekannte Ausfahrt.")).toBeInTheDocument();
  });
});

describe("submission flow — Belege", () => {
  it("adds a receipt as multipart and totals what is claimed", async () => {
    flowReturns();
    detailReturns({
      bills: [
        {
          id: 12,
          short_description: "Hütte",
          explanation: "",
          amount: 180,
          costs_covered: false,
          refunded: false,
          statement_id: 1,
          paid_by: { id: 7, name: "Hannah Beckers" },
          has_proof: true,
          proof_url: "/media/bill_images/huette.jpg",
        },
      ],
    });
    let fields: Record<string, string> | null = null;
    server.use(
      http.post(api("/api/finance/bills"), async ({ request }) => {
        fields = await multipartFields(request);
        return HttpResponse.json({ id: 13 });
      }),
    );

    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");
    const row = (await screen.findByText("Hütte")).closest(".beleg") as HTMLElement;
    expect(within(row).getByText("ausgelegt von Hannah Beckers")).toBeInTheDocument();
    expect(within(row).getByText("180,00 €")).toBeInTheDocument();
    // A stored scan is openable, not merely announced.
    expect(within(row).getByRole("link", { name: "Beleg ansehen" })).toHaveAttribute(
      "href",
      expect.stringContaining("/media/bill_images/huette.jpg"),
    );

    await user.click(screen.getByRole("button", { name: "+ Beleg hinzufügen" }));
    await user.type(screen.getByLabelText("Wofür"), "Sprit");
    await user.type(screen.getByLabelText("Betrag"), "60");
    await user.click(screen.getByRole("button", { name: "Beleg hinzufügen" }));

    await waitFor(() => expect(fields).not.toBeNull());
    expect(fields).toMatchObject({
      statement_id: "1",
      short_description: "Sprit",
      amount: "60",
      costs_covered: "false",
    });
  });

  it("edits a receipt in place and replaces its scan", async () => {
    flowReturns();
    detailReturns({ bills: [BILL] });
    let patched: Record<string, unknown> | null = null;
    let uploaded: string | undefined;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(BILL);
      }),
      http.post(api("/api/finance/bills/12/proof"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const amount = screen.getByDisplayValue("40");
    await user.clear(amount);
    await user.type(amount, "45");
    await user.upload(
      screen.getByLabelText(/Beleg-Bild/),
      new File(["%PDF"], "neu.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ amount: 45, paid_by_id: 9 });
    await waitFor(() => expect(uploaded).toBe("neu.pdf"));
  });

  it("removes a receipt once confirmed", async () => {
    flowReturns();
    detailReturns({ bills: [BILL] });
    let deleted = false;
    server.use(
      http.delete(api("/api/finance/bills/12"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(false);

    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Entfernen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("reports a refused receipt without losing what was typed", async () => {
    flowReturns();
    detailReturns();
    server.use(
      http.post(api("/api/finance/bills"), () =>
        HttpResponse.json({ detail: "Der Betrag fehlt." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");
    await user.click(await screen.findByRole("button", { name: "+ Beleg hinzufügen" }));
    await user.type(screen.getByLabelText("Wofür"), "Verpflegung");
    await user.click(screen.getByRole("button", { name: "Beleg hinzufügen" }));

    expect(await screen.findByText("Der Betrag fehlt.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Verpflegung")).toBeInTheDocument();
  });

  it("flags a receipt without a scan", async () => {
    flowReturns();
    detailReturns({
      bills: [
        {
          id: 12,
          short_description: "Hütte",
          explanation: "",
          amount: 180,
          costs_covered: false,
          refunded: false,
          statement_id: 1,
          paid_by: null,
          has_proof: false,
          proof_url: null,
        },
      ],
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=receipts");
    expect(await screen.findByText("Bild fehlt")).toBeInTheDocument();
    expect(screen.getByText("kein Zahler eingetragen")).toBeInTheDocument();
  });

  it("refuses to move on while a receipt is still being entered", async () => {
    // Reported from the running instance: a receipt typed into the form was
    // gone after saving the draft. Nothing had posted it — the form is local
    // state on a panel that `key={step}` throws away when the flow moves — so
    // "Weiter" dropped what was typed without saying anything.
    flowReturns();
    detailReturns();
    let posted = 0;
    server.use(
      http.post(api("/api/finance/bills"), () => {
        posted += 1;
        return HttpResponse.json({ id: 13 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");

    await user.click(await screen.findByRole("button", { name: "+ Beleg hinzufügen" }));
    await user.type(screen.getByLabelText("Wofür"), "Sprit");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    expect(await screen.findByText(/Der Beleg ist noch nicht hinzugefügt/)).toBeInTheDocument();
    // Still on the receipts leg, with what was typed still on screen — and
    // nothing invented a receipt out of a half-filled form either.
    expect(currentSearch()).toBe("?stage=receipts");
    expect(screen.getByDisplayValue("Sprit")).toBeInTheDocument();
    expect(posted).toBe(0);
  });

  it("moves on once the receipt is added", async () => {
    // The other half of the guard: it must let go of the flow again, or the
    // receipts leg becomes a dead end.
    flowReturns();
    detailReturns();
    server.use(
      http.post(api("/api/finance/bills"), () => HttpResponse.json({ id: 13 })),
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");

    await user.click(await screen.findByRole("button", { name: "+ Beleg hinzufügen" }));
    await user.type(screen.getByLabelText("Wofür"), "Sprit");
    await user.click(screen.getByRole("button", { name: "Beleg hinzufügen" }));
    await screen.findByText("Beleg hinzugefügt.");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    await waitFor(() => expect(currentSearch()).toBe("?stage=reimbursement"));
  });

  it("lets a receipt being entered be abandoned deliberately", async () => {
    flowReturns();
    detailReturns();
    server.use(http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())));
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=receipts");

    await user.click(await screen.findByRole("button", { name: "+ Beleg hinzufügen" }));
    await user.type(screen.getByLabelText("Wofür"), "Sprit");
    // Scoped to the receipt form: the page header carries an "Abbrechen" too,
    // and that one leaves the whole flow.
    const form = within(document.querySelector(".beleg-form") as HTMLElement);
    await user.click(form.getByRole("button", { name: "Abbrechen" }));
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    await waitFor(() => expect(currentSearch()).toBe("?stage=reimbursement"));
  });
});

describe("submission flow — Erstattung", () => {
  /**
   * The picker under the question labelled `label`.
   *
   * `Field` wraps its control in a `<label>`, which swallows the trigger's
   * accessible name — the same reason the review pipeline reaches for
   * `.ss-trigger` directly.
   */
  function pickerFor(label: string) {
    const field = screen.getByText(label).closest(".field") as HTMLElement;
    return field.querySelector(".ss-trigger, .ms-toggle") as HTMLElement;
  }

  /** Open the reimbursement leg with `form` as what the rules ask for. */
  function openForm(form: Record<string, unknown> = {}) {
    flowReturns();
    detailReturns();
    const body: Record<string, unknown> = { ...FORM, ...form };
    // A stub that changes the questions gets the grouping that goes with them,
    // because the API never serves one without the other.
    if (!("steps" in form)) body.steps = stepsOf(body.inputs as Record<string, unknown>[]);
    server.use(
      http.get(api("/api/finance/statements/1/form"), () => HttpResponse.json(body)),
    );
    return renderRoute("/kompass/finance/statements/1/edit?stage=reimbursement");
  }

  it("asks what the rules declare, not four fields of its own", async () => {
    openForm();

    expect(await screen.findByText("Preis pro Übernachtung")).toBeInTheDocument();
    expect(screen.getByText("Aufwandsentschädigung an")).toBeInTheDocument();
    expect(screen.getByText("Fahrt- und Übernachtungszuschuss an")).toBeInTheDocument();
    // The declaration's own help, in the section's language.
    expect(screen.getByText(/Was eine Übernachtung pro Jugendleiter\*in gekostet hat/))
      .toBeInTheDocument();
    // The answer the statement already carries seeds the control.
    expect(screen.getByDisplayValue("11.00")).toBeInTheDocument();
  });

  it("renders every type in the widget vocabulary", async () => {
    // Four of the seven have no section in tree that asks for them, and the
    // renderer is the only thing standing between a declaration and a form.
    openForm({
      inputs: [
        declaration({ key: "nights", label: "Nächte", type: "int", max: 9 }),
        declaration({ key: "catered", label: "Mit Verpflegung", type: "bool" }),
        declaration({ key: "note", label: "Anmerkung", type: "text" }),
        declaration({ key: "pick", label: "Variante", type: "choice", choices: REGIMES }),
      ],
      answers: { nights: 3, catered: true, note: "eine Zeile", pick: "ehrenamt" },
    });

    expect(await screen.findByText("Nächte")).toBeInTheDocument();
    expect(screen.getByDisplayValue("3")).toHaveAttribute("max", "9");
    expect(screen.getByRole("checkbox")).toBeChecked();
    expect(screen.getByDisplayValue("eine Zeile")).toBeInTheDocument();
    // A picker showing the chosen alternative's label, not its stored value.
    expect(pickerFor("Variante")).toHaveTextContent("Ehrenamtspauschale");
  });

  it("sends an answer under the key the rules declared", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm();

    await screen.findByText("Fahrt- und Übernachtungszuschuss an");
    await user.click(pickerFor("Fahrt- und Übernachtungszuschuss an"));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));

    // That key and nothing else: the API merges answers by key, and a body
    // restating the questions nobody touched is how an answer the rules have
    // since retired used to travel with an unrelated edit.
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ inputs: { subsidy_to: 9 } });
  });

  it("picks several people for a set-valued answer", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm();

    await screen.findByText("Aufwandsentschädigung an");
    await user.click(pickerFor("Aufwandsentschädigung an"));
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect((patched as unknown as { inputs: { allowance_to: number[] } }).inputs.allowance_to)
      .toEqual([7]);
  });

  it("waits for a pause before sending a typed answer", async () => {
    let patches = 0;
    server.use(
      http.patch(api("/api/finance/statements/1"), () => {
        patches += 1;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm();

    const field = await screen.findByDisplayValue("11.00");
    await user.clear(field);
    await user.type(field, "27");
    // Four keystrokes, not four requests.
    expect(patches).toBe(0);
    await waitFor(() => expect(patches).toBe(1), { timeout: 2000 });
  });

  it("names the answer a refusal is about", async () => {
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        djangoValidation({
          allowance_to: ["Diese Fahrt hat nur 2 anerkannte Jugendleiter*innen."],
        }),
      ),
    );
    const { user } = openForm();

    await screen.findByText("Aufwandsentschädigung an");
    await user.click(pickerFor("Aufwandsentschädigung an"));
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));

    // Under the question, because the 422 is keyed by the answer it is about —
    // and in a toast, like any refusal.
    const messages = await screen.findAllByText(/nur 2 anerkannte/);
    expect(messages.map((node) => node.className)).toContain("field-error");
  });

  it("sends back only the questions the form still asks", async () => {
    // A ruleset may retire a question once an earlier answer makes it moot, and
    // the API refuses a key the rules do not ask for — `retired` here is an
    // answer the form served without asking for it. Neuter it — send the whole
    // local draft along with the edit — and this goes red with `retired` in the
    // body, which is a 422 on the running instance.
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm({
      answers: { night_cost: "11.00", allowance_to: [], subsidy_to: null, retired: "alt" },
    });

    await screen.findByText("Fahrt- und Übernachtungszuschuss an");
    await user.click(pickerFor("Fahrt- und Übernachtungszuschuss an"));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ inputs: { subsidy_to: 9 } });
  });

  it("asks the ruleset's questions of a statement without a trip", async () => {
    // Reported from the running instance: the flow offered no way to say which
    // set of rules applies. The statement in question named no excursion — both
    // trips already had one — and this leg, the only place the ruleset's
    // questions are asked, was gated on there being a trip. A leftover from
    // when the leg was four fields about a trip's allowances: the section's
    // rules ask the same `regime` of a training as of a Freizeit.
    flowReturns();
    detailReturns({ excursion: null });
    const inputs = [
      declaration({ key: "regime", label: "Regelwerk", type: "choice", choices: REGIMES }),
    ];
    server.use(
      http.get(api("/api/finance/statements/1/form"), () =>
        HttpResponse.json({ ...FORM, inputs, steps: stepsOf(inputs), answers: { regime: null } }),
      ),
    );
    renderRoute("/kompass/finance/statements/1/edit?stage=reimbursement");

    expect(await screen.findByText("Regelwerk")).toBeInTheDocument();
    // And it is on the rail, so it is reachable without typing a URL.
    expect(screen.getByRole("navigation", { name: "Etappen" })).toHaveTextContent("Erstattung");
  });

  it("says so when the rules ask for nothing", async () => {
    openForm({ inputs: [], answers: {} });
    expect(
      await screen.findByText("Für diese Abrechnung fragen die Regeln nichts ab."),
    ).toBeInTheDocument();
    // The leg a person is standing on is never retired under them: bouncing
    // back to Anlass because a query landed is worse than a leg that says the
    // rules ask nothing.
    expect(screen.getByRole("navigation", { name: "Etappen" })).toHaveTextContent("Erstattung");
  });

  it("retires the leg on a statement whose rules ask nothing", async () => {
    // The other side of the same coin: the leg follows what the rules ask, so
    // it is neither pinned to the excursion nor simply always there.
    flowReturns();
    detailReturns({ excursion: null });
    server.use(
      http.get(api("/api/finance/statements/1/form"), () =>
        HttpResponse.json({ ...FORM, inputs: [], steps: [], answers: {} }),
      ),
    );
    renderRoute("/kompass/finance/statements/1/edit?stage=receipts");

    const rail = await screen.findByRole("navigation", { name: "Etappen" });
    await waitFor(() => expect(rail).not.toHaveTextContent("Erstattung"));
    expect(rail).toHaveTextContent("Belege");
  });

  it("offers the alternatives the declaration names, and sends the one picked", async () => {
    // `choice` used to be a free-text box, because a declaration had no way to
    // name its alternatives (#573). Now it does, and the API refuses anything
    // outside them — so typing is no longer a thing a client may offer.
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm({
      inputs: [
        declaration({ key: "regime", label: "Regelwerk", type: "choice", choices: REGIMES }),
      ],
      answers: { regime: null },
    });

    await screen.findByText("Regelwerk");
    await user.click(pickerFor("Regelwerk"));
    // Exactly the alternatives the rules offered, plus "not chosen yet" — which
    // is an answer the API stores, not the absence of one.
    expect(dropdown().getByText("— nicht gewählt —")).toBeInTheDocument();
    expect(dropdown().getByText("Übungsleiterpauschale")).toBeInTheDocument();
    await user.click(dropdown().getByRole("button", { name: "Übungsleiterpauschale" }));

    // The stored value, not the label it was picked by.
    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ inputs: { regime: "uebungsleiter" } });
  });

  it("sends each pick of a choice at once, because clicking is not typing", async () => {
    // `choice` was a text box, so it sat in the set of controls whose change
    // waits for a pause — a keystroke must not be a request. A picker has no
    // keystrokes: every pick is a whole answer, so two picks are two requests
    // and not one, which is what going back on a choice has to amount to.
    let patches = 0;
    server.use(
      http.patch(api("/api/finance/statements/1"), () => {
        patches += 1;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm({
      inputs: [
        declaration({ key: "regime", label: "Regelwerk", type: "choice", choices: REGIMES }),
      ],
      answers: { regime: null },
    });

    await screen.findByText("Regelwerk");
    await user.click(pickerFor("Regelwerk"));
    await user.click(dropdown().getByRole("button", { name: "Ehrenamtspauschale" }));
    await user.click(pickerFor("Regelwerk"));
    await user.click(dropdown().getByRole("button", { name: "Übungsleiterpauschale" }));

    await waitFor(() => expect(patches).toBe(2));
  });

  it("names the question a refused choice is about", async () => {
    // An answer outside the declaration's own choices is a 422 keyed by that
    // question, like any other refusal — not a toast over the whole form.
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        djangoValidation({ regime: ["Regelwerk ist keine der angebotenen Möglichkeiten."] }),
      ),
    );
    const { user } = openForm({
      inputs: [
        declaration({ key: "regime", label: "Regelwerk", type: "choice", choices: REGIMES }),
        declaration({ key: "nights", label: "Nächte", type: "int" }),
      ],
      answers: { regime: null, nights: 2 },
    });

    await screen.findByText("Regelwerk");
    await user.click(pickerFor("Regelwerk"));
    await user.click(dropdown().getByRole("button", { name: "Ehrenamtspauschale" }));

    // Under "Regelwerk", and not under the other question on the form — in a
    // toast as well, like any refusal.
    const messages = await screen.findAllByText(/keine der angebotenen Möglichkeiten/);
    expect(messages.map((node) => node.className)).toContain("field-error");
    const refused = screen.getByText("Regelwerk").closest(".field") as HTMLElement;
    expect(within(refused).getByText(/keine der angebotenen Möglichkeiten/)).toBeInTheDocument();
    const other = screen.getByText("Nächte").closest(".field") as HTMLElement;
    expect(within(other).queryByText(/keine der angebotenen Möglichkeiten/)).toBeNull();
  });

  it("states a derived answer as a reading instead of asking for it", async () => {
    // The engine resolves these from the statement's own data on every request.
    // Rendered as a field they would read as something to fill in — and a
    // disabled one as something broken.
    openForm({
      inputs: [
        declaration({ key: "km", label: "Gefahrene Kilometer", type: "int", derived: true }),
        declaration({ key: "fare", label: "Fahrtkosten", type: "money", derived: true }),
        declaration({ key: "nights", label: "Nächte", type: "int" }),
      ],
      answers: { km: 120, fare: "36.00", nights: 2 },
    });

    const readout = (await screen.findByText("Gefahrene Kilometer")).closest(
      ".readout",
    ) as HTMLElement;
    expect(readout).not.toBeNull();
    // Where the figure comes from, in the same words the trip's own facts get.
    expect(within(readout).getByText("Aus der Fahrt übernommen")).toBeInTheDocument();
    expect(within(readout).getByText("120")).toBeInTheDocument();
    // Money arrives as text, exactly as a stored answer does, and reads as money.
    expect(within(readout).getByText("36,00 €")).toBeInTheDocument();
    // Nothing to type into: not a control, not a disabled control.
    expect(screen.queryByDisplayValue("120")).toBeNull();
    expect(screen.queryByDisplayValue("36.00")).toBeNull();
    // The question beside them is still a question.
    expect(screen.getByDisplayValue("2")).toBeInTheDocument();
  });

  it("reads a derived answer in every shape a stored one comes in", async () => {
    // `/form` hands a derived value over in the shape `Statement.inputs` holds
    // it — money as text, a person as an id, a set of people as a list of ids —
    // so one path reads both and a figure the engine supplied reads like a
    // figure somebody answered.
    openForm({
      inputs: [
        declaration({ key: "fare", label: "Fahrtkosten", type: "money", derived: true }),
        declaration({ key: "catered", label: "Verpflegt", type: "bool", derived: true }),
        declaration({ key: "warm", label: "Winterfahrt", type: "bool", derived: true }),
        declaration({
          key: "regime",
          label: "Regelwerk",
          type: "choice",
          choices: REGIMES,
          derived: true,
        }),
        declaration({
          key: "regime_open",
          label: "Zweitregelwerk",
          type: "choice",
          choices: REGIMES,
          derived: true,
        }),
        declaration({
          key: "lead",
          label: "Fahrtenleitung",
          type: "member",
          options: LEADERS,
          derived: true,
        }),
        declaration({
          key: "gone",
          label: "Kassenwart",
          type: "member",
          options: [],
          derived: true,
        }),
        declaration({
          key: "nobody",
          label: "Vertretung",
          type: "member",
          options: LEADERS,
          derived: true,
        }),
        declaration({
          key: "crew",
          label: "Anerkannte Leitung",
          type: "member_set",
          options: LEADERS,
          derived: true,
        }),
        declaration({
          key: "extra",
          label: "Begleitung",
          type: "member_set",
          options: LEADERS,
          derived: true,
        }),
        declaration({ key: "note", label: "Vermerk", type: "text", derived: true }),
      ],
      answers: {
        fare: "36.00",
        catered: true,
        warm: false,
        regime: "ehrenamt",
        regime_open: null,
        lead: 9,
        gone: 4,
        nobody: null,
        crew: [7, 9],
        extra: [],
        note: "",
      },
    });

    const readout = (await screen.findByText("Fahrtkosten")).closest(".readout") as HTMLElement;
    const read = (label: string) =>
      (within(readout).getByText(label).nextElementSibling as HTMLElement).textContent;
    expect(read("Fahrtkosten")).toBe("36,00 €");
    expect(read("Verpflegt")).toBe("Ja");
    expect(read("Winterfahrt")).toBe("Nein");
    // A choice reads as the label it was offered under, not as its stored value.
    expect(read("Regelwerk")).toBe("Ehrenamtspauschale");
    expect(read("Zweitregelwerk")).toBe("—");
    expect(read("Fahrtenleitung")).toBe("Mila Nowak");
    // A person the rules no longer offer: an id with no name behind it.
    expect(read("Kassenwart")).toBe("unbekannt");
    expect(read("Vertretung")).toBe("—");
    expect(read("Anerkannte Leitung")).toBe("Hannah Beckers, Mila Nowak");
    expect(read("Begleitung")).toBe("—");
    expect(read("Vermerk")).toBe("—");
  });

  it("never sends an answer for a derived question", async () => {
    // `PATCH` refuses a value for a derived key, keyed by that question. The
    // form serves the figure in `answers` like any other answer, so a client
    // that echoes back what it was served gets a 422. Two locks: a derived
    // declaration is a reading and never a control, so nothing can edit one,
    // and the send filters against the questions the form asks. Neuter either —
    // render the readings as fields, or send the whole draft — and this goes
    // red with `km` in the body.
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openForm({
      inputs: [
        declaration({ key: "km", label: "Gefahrene Kilometer", type: "int", derived: true }),
        declaration({
          key: "subsidy_to",
          label: "Zuschuss an",
          type: "member",
          options: LEADERS,
        }),
      ],
      answers: { km: 120, subsidy_to: null },
    });

    await screen.findByText("Zuschuss an");
    await user.click(pickerFor("Zuschuss an"));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ inputs: { subsidy_to: 9 } });
  });

  it("groups the questions into the steps the rules named", async () => {
    openForm({
      inputs: [
        declaration({
          key: "regime",
          label: "Regelwerk",
          type: "choice",
          choices: REGIMES,
          step: "Grundlagen",
        }),
        declaration({ key: "km", label: "Kilometer", type: "int", step: "Fahrtkosten" }),
        declaration({ key: "note", label: "Anmerkung", type: "text", step: "Fahrtkosten" }),
      ],
      answers: { regime: null, km: 120, note: "" },
    });

    const grundlagen = (await screen.findByText("Grundlagen")).closest(
      ".answer-group",
    ) as HTMLElement;
    expect(within(grundlagen).getByText("Regelwerk")).toBeInTheDocument();
    expect(within(grundlagen).queryByText("Kilometer")).toBeNull();

    const fahrtkosten = screen.getByText("Fahrtkosten").closest(".answer-group") as HTMLElement;
    expect(within(fahrtkosten).getByText("Kilometer")).toBeInTheDocument();
    expect(within(fahrtkosten).getByText("Anmerkung")).toBeInTheDocument();
    expect(within(fahrtkosten).queryByText("Regelwerk")).toBeNull();
  });

  it("reads as one flat list when the rules named no steps", async () => {
    // A ruleset that named no steps comes back as a single step labelled `""`,
    // and that degenerate case must not look like a multi-page flow: no
    // heading, nothing announcing a group, just the questions.
    openForm();

    expect(await screen.findByText("Preis pro Übernachtung")).toBeInTheDocument();
    expect(FORM.steps).toEqual([
      { label: "", keys: ["night_cost", "allowance_to", "subsidy_to"] },
    ]);
    expect(document.querySelector(".answer-group-title")).toBeNull();
  });

  it("offers nobody when the rules offer nobody", async () => {
    const { user } = openForm({
      inputs: [declaration({ key: "allowance_to", label: "An", type: "member_set" })],
      answers: {},
    });
    await screen.findByText("An");
    await user.click(pickerFor("An"));
    expect(dropdown().getByText("Hier bieten die Regeln niemanden an.")).toBeInTheDocument();
  });

  /**
   * The repeating row.
   *
   * A statement settles a trip several people went on and they travelled
   * differently — one drove, one took the train, one cycled — and whether
   * somebody gets the rate per kilometre at all depends on *their* approach.
   * So approach and distance belong to the same traveller, which is a row.
   */
  describe("Fahrten — eine Zeile pro Person", () => {
    /** The table and nothing else, answered with `rows`. */
    function openRows(rows: unknown, extra: Record<string, unknown>[] = []) {
      return openForm({
        inputs: [REISEN, ...extra],
        answers: {
          reisen: rows,
          ...Object.fromEntries(extra.map((input) => [input.key as string, null])),
        },
      });
    }

    /** The control in the `label` column of the `index`-th row, 1-based. */
    function cellAt(label: string, index: number) {
      return screen.getByLabelText(`${label}, Zeile ${index}`);
    }

    /** What the last `PATCH` sent under `reisen`. */
    function sentRows(patched: unknown) {
      return (patched as { inputs: { reisen: unknown } }).inputs.reisen;
    }

    /** Record every `PATCH` body, and answer each one with a plain statement. */
    function recordPatches() {
      const seen: Record<string, unknown>[] = [];
      server.use(
        http.patch(api("/api/finance/statements/1"), async ({ request }) => {
          seen.push((await request.json()) as Record<string, unknown>);
          return HttpResponse.json(statement());
        }),
      );
      return seen;
    }

    it("renders one row per answer, with the people the question offers", async () => {
      openRows([
        { member: 7, approach: "pkw", kilometers: 120 },
        { member: 9, approach: "bahn", kilometers: 0 },
      ]);

      await screen.findByText("Fahrten");
      // One column per declared field, said once above the grid rather than
      // once per row.
      const table = document.querySelector(".rows-table") as HTMLElement;
      expect(within(table).getAllByRole("columnheader").map((th) => th.textContent)).toEqual([
        "Nr.",
        "Person",
        "Verkehrsmittel",
        "Kilometer",
        "",
      ]);
      // Two answers, two rows — and each cell answered where its own row is.
      expect(within(table).getAllByRole("row")).toHaveLength(3); // + the heading
      expect(cellAt("Person", 1)).toHaveTextContent("Hannah Beckers");
      expect(cellAt("Verkehrsmittel", 1)).toHaveTextContent("PKW");
      expect(cellAt("Kilometer", 1)).toHaveValue(120);
      expect(cellAt("Person", 2)).toHaveTextContent("Mila Nowak");
      expect(cellAt("Verkehrsmittel", 2)).toHaveTextContent("Bahn");
      expect(cellAt("Kilometer", 2)).toHaveValue(0);
      // A cell's own ceiling is on the cell; the question's `max` is the row
      // count and has nothing to do with it.
      expect(cellAt("Kilometer", 1)).toHaveAttribute("max", "2000");
    });

    it("offers a party-valued cell the question's own people", async () => {
      // The domain is stated once, on the declaration, because a `Field`
      // carries no `options`. A renderer that looked for them on the field
      // would offer an empty picker in every row.
      const { user } = openRows([{ member: null, approach: "", kilometers: 0 }]);

      await screen.findByText("Fahrten");
      await user.click(cellAt("Person", 1));
      expect(dropdown().getByRole("button", { name: "Hannah Beckers" })).toBeInTheDocument();
      expect(dropdown().getByRole("button", { name: "Mila Nowak" })).toBeInTheDocument();
    });

    it("invites a first row instead of reading as broken", async () => {
      // `[]`, an absent key and a table the rules have retired all mean the
      // same thing — a question nobody has answered yet — so nothing here is a
      // refusal, and there is something to do.
      openRows([]);

      expect(await screen.findByText("Fahrten")).toBeInTheDocument();
      expect(screen.getByText(/Noch keine Zeile/)).toBeInTheDocument();
      expect(document.querySelector(".rows-table")).toBeNull();
      expect(document.querySelector(".rows-field .field-error")).toBeNull();
      expect(screen.getByRole("button", { name: "+ Zeile hinzufügen" })).toBeEnabled();
    });

    it("adds a row and sends the longer list", async () => {
      const seen = recordPatches();
      const { user } = openRows([{ member: 7, approach: "pkw", kilometers: 120 }]);

      await screen.findByText("Fahrten");
      await user.click(screen.getByRole("button", { name: "+ Zeile hinzufügen" }));

      // The row is there to type into at once…
      expect(cellAt("Kilometer", 2)).toBeInTheDocument();
      // …and the answer that goes back is the whole list, the new row included.
      // An empty object and not a row of blanks: the API fills every cell it
      // asks for with its type's own empty value.
      await waitFor(() => expect(seen).toHaveLength(1), { timeout: 2000 });
      expect(sentRows(seen[0])).toEqual([{ member: 7, approach: "pkw", kilometers: 120 }, {}]);
    });

    it("stops offering a row at the number of rows the question allows", async () => {
      // `max` on a table bounds the rows. Read as a cell's ceiling instead, a
      // three-row table would accept any number of them and the API would
      // refuse the fourth.
      recordPatches();
      const { user } = openRows([
        { member: 7, approach: "pkw", kilometers: 120 },
        { member: 9, approach: "bahn", kilometers: 0 },
      ]);

      await screen.findByText("Fahrten");
      const add = screen.getByRole("button", { name: "+ Zeile hinzufügen" });
      expect(add).toBeEnabled();
      await user.click(add);

      await waitFor(() => expect(add).toBeDisabled());
      expect(screen.getByText("Höchstens 3 Zeilen.")).toBeInTheDocument();
    });

    it("removes a row and sends what is left", async () => {
      const seen = recordPatches();
      const { user } = openRows([
        { member: 7, approach: "pkw", kilometers: 120 },
        { member: 9, approach: "bahn", kilometers: 0 },
      ]);

      await screen.findByText("Fahrten");
      await user.click(screen.getByRole("button", { name: "Zeile 1 entfernen" }));

      await waitFor(() => expect(seen).toHaveLength(1), { timeout: 2000 });
      expect(sentRows(seen[0])).toEqual([{ member: 9, approach: "bahn", kilometers: 0 }]);
      // And the row that is left is the one that is left, renumbered.
      expect(cellAt("Person", 1)).toHaveTextContent("Mila Nowak");
      expect(screen.queryByLabelText("Person, Zeile 2")).toBeNull();
    });

    it("lets a seeded row be corrected, and sends the correction", async () => {
      // The trip records one distance and one mode, and a seed writes them into
      // the first row *once*. That is an answer and not a reading: it is
      // stored, it does not follow the trip afterwards, and the whole point is
      // that it can be edited — so it must not be rendered the way a `derived`
      // value is.
      const seen = recordPatches();
      const { user } = openRows([{ member: 7, approach: "pkw", kilometers: 120 }]);

      await screen.findByText("Fahrten");
      // Not a reading: a control, and not a disabled one.
      const km = cellAt("Kilometer", 1);
      expect(km).toBeEnabled();
      expect(document.querySelector(".rows-field .readout")).toBeNull();

      await user.clear(km);
      await user.type(km, "96");

      await waitFor(() => expect(seen).toHaveLength(1), { timeout: 2000 });
      expect(sentRows(seen[seen.length - 1])).toEqual([
        { member: 7, approach: "pkw", kilometers: "96" },
      ]);
    });

    it("waits for a pause before a typed cell becomes a request", async () => {
      // `TYPED_INTO` is keyed by the declaration's type, so a table left out of
      // it makes every keystroke in every cell a `PATCH` — and a table goes
      // back whole, so that is the entire table per character.
      const seen = recordPatches();
      const { user } = openRows([{ member: 7, approach: "pkw", kilometers: 0 }]);

      await screen.findByText("Fahrten");
      const km = cellAt("Kilometer", 1);
      await user.clear(km);
      await user.type(km, "120");

      // Four edits, not four requests.
      expect(seen).toHaveLength(0);
      await waitFor(() => expect(seen).toHaveLength(1), { timeout: 2000 });
    });

    it("prints a refusal about a cell against that cell", async () => {
      // The 422's keys are a path — `reisen[1].kilometers` — precisely so that
      // an error about one person's kilometres does not surface under the whole
      // table. Zero-based, in the order the request sent the rows.
      server.use(
        http.patch(api("/api/finance/statements/1"), () =>
          djangoValidation({
            "reisen[1].kilometers": ["Kilometer darf höchstens 2000 sein."],
            "reisen[0].approach": ["Verkehrsmittel ist keine der angebotenen Möglichkeiten."],
          }),
        ),
      );
      // Provoked by correcting one cell, because a table goes back whole: the
      // request carries every row, so cells nobody touched are refused along
      // with the one that was.
      const { user } = openRows([
        { member: 7, approach: "flug", kilometers: 120 },
        { member: 9, approach: "pkw", kilometers: 9000 },
      ]);

      await screen.findByText("Fahrten");
      await user.click(cellAt("Verkehrsmittel", 1));
      await user.click(dropdown().getByRole("button", { name: "Bahn" }));

      // Every bad cell at once, each against the cell that caused it.
      await screen.findByText("Kilometer darf höchstens 2000 sein.");
      const refused = cellAt("Kilometer", 2).closest(".rows-cell") as HTMLElement;
      expect(within(refused).getByText(/höchstens 2000/)).toBeInTheDocument();
      // And marked, so the cell looks refused and not merely annotated.
      expect(refused).toHaveClass("has-error");
      const wrongMode = cellAt("Verkehrsmittel", 1).closest(".rows-cell") as HTMLElement;
      expect(within(wrongMode).getByText(/keine der angebotenen/)).toBeInTheDocument();
      expect(wrongMode).toHaveClass("has-error");

      // And not under the whole table, nor against the row that is fine.
      const table = document.querySelector(".rows-field") as HTMLElement;
      expect(
        [...table.querySelectorAll(":scope > .field-error")].map((n) => n.textContent),
      ).toEqual([]);
      const fine = cellAt("Kilometer", 1).closest(".rows-cell") as HTMLElement;
      expect(within(fine).queryByText(/höchstens 2000/)).toBeNull();
    });

    it("prints a refusal about the table under the table", async () => {
      // The other end of the path: too many rows, or an answer that is not a
      // list of rows at all, is about the question and belongs under it.
      server.use(
        http.patch(api("/api/finance/statements/1"), () =>
          djangoValidation({ reisen: ["Fahrten darf höchstens 3 Zeilen haben."] }),
        ),
      );
      const { user } = openRows([{ member: 7, approach: "pkw", kilometers: 120 }]);

      await screen.findByText("Fahrten");
      await user.click(screen.getByRole("button", { name: "Zeile 1 entfernen" }));

      const table = await waitFor(() => {
        const field = document.querySelector(".rows-field") as HTMLElement;
        expect(field.querySelector(":scope > .field-error")).not.toBeNull();
        return field;
      });
      expect(within(table).getByText(/höchstens 3 Zeilen/)).toBeInTheDocument();
    });

    it("renders a row the rules no longer offer as an unanswered table", async () => {
      // A table falls out of its domain whole: one cell naming somebody the
      // rules no longer offer drops the table, and `/form` serves `null` for
      // it, which is the shape an unanswered question comes in.
      openRows(null);

      expect(await screen.findByText("Fahrten")).toBeInTheDocument();
      expect(screen.getByText(/Noch keine Zeile/)).toBeInTheDocument();
    });
  });

  /**
   * What answering the regime does to the rest of the form.
   *
   * `regime` decides which questions the rules ask at all:
   * `participant_list_filed` is in Ludwigsburg's `TOURENLEITUNG_ONLY` set, so
   * choosing Ehrenamt takes it off the form — and `PATCH` then *refuses* a body
   * that still carries it, because a question the rules have retired must not
   * move money (#579).
   *
   * Reported from the running instance: switching the Regelwerk back and forth
   * produced "Diese Regeln fragen Teilnehmerliste nicht ab." — *sometimes*.
   * What decided it was whether the refetched form had landed before the next
   * edit went out, so these hold the refetch open rather than hope to lose the
   * race.
   */
  describe("Regelwerk — ein Wechsel ändert, was gefragt wird", () => {
    const REGELWERKE = [
      { value: "ehrenamt", label: "Ehrenamt und Verwaltung" },
      { value: "tourenleitung", label: "Tourenleitung" },
    ];

    const REGIME = declaration({
      key: "regime",
      label: "Regelwerk",
      type: "choice",
      choices: REGELWERKE,
    });

    /** Tourenleitung's question, and nobody else's. */
    const LISTE = declaration({
      key: "participant_list_filed",
      label: "Teilnehmerliste lag vor Antritt vor",
      type: "bool",
    });

    /**
     * The two halves of the engine this is about, as a server.
     *
     * `GET …/form` answers with the questions the rules ask *of the answers as
     * stored*, and `PATCH` refuses a key they do not ask — where
     * `finance.inputs.clean` refuses it, against the declarations the stored
     * answers imply rather than the ones the request would imply. A handler
     * that merely recorded bodies could not go red on this bug: the refusal is
     * the bug.
     *
     * `hold` is what makes the race a test rather than a coin toss. A form
     * fetch taken while it is held does not answer until `release`, so the
     * window between "the regime is saved" and "the client knows what the rules
     * ask now" is as wide as the test needs.
     */
    function rulesBackend(
      initial: Record<string, unknown>,
      asking: (answers: Record<string, unknown>) => Record<string, unknown>[] = (answers) =>
        answers.regime === "tourenleitung" ? [REGIME, LISTE] : [REGIME],
    ) {
      const stored: Record<string, unknown> = { ...initial };
      const patches: Record<string, unknown>[] = [];
      const refused: string[] = [];
      let waiting = 0;
      let held: Promise<void> | null = null;
      let release = () => {};
      const asked = () => asking(stored);
      server.use(
        http.get(api("/api/finance/statements/1/form"), async () => {
          if (held) {
            waiting += 1;
            await held;
          }
          const inputs = asked();
          return HttpResponse.json({
            statement_id: 1,
            inputs,
            steps: stepsOf(inputs),
            answers: Object.fromEntries(
              inputs.map((input) => [input.key, stored[input.key as string] ?? null]),
            ),
          });
        }),
        http.patch(api("/api/finance/statements/1"), async ({ request }) => {
          const body = (await request.json()) as { inputs: Record<string, unknown> };
          patches.push(body.inputs);
          const keys = asked().map((input) => input.key as string);
          const stray = Object.keys(body.inputs).find((key) => !keys.includes(key));
          if (stray !== undefined) {
            refused.push(stray);
            return djangoValidation({ __all__: [`Diese Regeln fragen ${stray} nicht ab.`] });
          }
          Object.assign(stored, body.inputs);
          return HttpResponse.json(statement());
        }),
      );
      return {
        stored,
        patches,
        refused,
        /**
         * How many form fetches have run into the hold and are stuck in it.
         *
         * More than one is normal: a save invalidates three keys and the form's
         * is a prefix of all three, so the refetch is started (and the previous
         * one cancelled) once per key. One stuck fetch is already the thing
         * these tests wait for — no form can have landed since the hold.
         */
        waiting: () => waiting,
        /** Stop answering form fetches, so the client keeps the old questions. */
        hold: () => {
          held = new Promise<void>((resolve) => {
            release = () => {
              held = null;
              resolve();
            };
          });
        },
        release: () => release(),
      };
    }

    /** Open the reimbursement leg against a server that answers as the rules do. */
    function openRules(
      initial: Record<string, unknown>,
      asking?: (answers: Record<string, unknown>) => Record<string, unknown>[],
    ) {
      flowReturns();
      detailReturns();
      const backend = rulesBackend(initial, asking);
      const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=reimbursement");
      return { backend, user };
    }

    /** Pick `label` under the Regelwerk question. */
    async function pickRegime(user: ReturnType<typeof renderRoute>["user"], label: string) {
      await user.click(pickerFor("Regelwerk"));
      await user.click(dropdown().getByRole("button", { name: label }));
    }

    it("never re-answers a question the regime has just retired", async () => {
      // The reported bug as a sequence rather than as a stroke of luck: pick a
      // regime, and before the form that goes with it has landed, pick the
      // other one. The second request used to carry the whole answerable
      // subset — the Teilnehmerliste nobody had touched included — against a
      // statement that was by then not being asked about it at all.
      const { backend, user } = openRules({
        regime: "tourenleitung",
        participant_list_filed: true,
      });

      await screen.findByText("Regelwerk");
      expect(screen.getByRole("checkbox")).toBeChecked();

      backend.hold();
      await pickRegime(user, "Ehrenamt und Verwaltung");
      await waitFor(() => expect(backend.patches).toHaveLength(1));
      // The form that retires the Teilnehmerliste is in flight and stuck there,
      // so the client is holding the questions of the regime it has just left.
      await waitFor(() => expect(backend.waiting()).toBeGreaterThan(0));
      expect(screen.getByRole("checkbox")).toBeInTheDocument();

      await pickRegime(user, "Tourenleitung");
      backend.release();

      await waitFor(() => expect(backend.patches).toHaveLength(2));
      // Nothing was refused, because nothing answered a retired question.
      expect(backend.refused).toEqual([]);
      expect(backend.stored.regime).toBe("tourenleitung");
      // And switching away never dropped the answer: the question is back, and
      // so is what was said about it — on the form and on the server.
      expect(await screen.findByRole("checkbox")).toBeChecked();
      expect(screen.getByText(/Teilnehmerliste/)).toBeInTheDocument();
      expect(backend.stored.participant_list_filed).toBe(true);
    });

    it("holds an edit back until it is known whether the rules still ask it", async () => {
      // The same window from the other side: the question is still on screen
      // while the form that retires it is in flight, so it can still be
      // answered — and that answer must not go out to rules that have stopped
      // asking it.
      const { backend, user } = openRules({
        regime: "tourenleitung",
        participant_list_filed: false,
      });

      await screen.findByText("Regelwerk");
      backend.hold();
      await pickRegime(user, "Ehrenamt und Verwaltung");
      await waitFor(() => expect(backend.patches).toHaveLength(1));
      await waitFor(() => expect(backend.waiting()).toBeGreaterThan(0));

      // Answered inside the window, against questions that are already history.
      await user.click(screen.getByRole("checkbox"));
      backend.release();

      // The form lands, the question is gone, and it was never answered.
      await waitFor(() => expect(screen.queryByRole("checkbox")).toBeNull());
      expect(backend.refused).toEqual([]);
      expect(backend.stored.participant_list_filed).toBe(false);
    });

    it("shows the answer a question the rules have just revealed arrives with", async () => {
      // The other end of the same narrowing, and a gap the holding fix left.
      //
      // A ruleset may narrow to its *first* question — Ludwigsburg asks only
      // the Regelwerk until it has one, because a kilometre has two rates and
      // a night two meanings until then — and the Fahrten table it then
      // reveals comes with the row the excursion seeded at creation. The draft
      // was seeded once, off the form this leg mounted on, so it had never
      // heard of that key and rendered the table empty: the seeded row looked
      // eaten by the question nobody had been asked yet.
      //
      // Neuter it — drop the effect that merges arriving keys — and the table
      // appears with "Noch keine Zeile" over a row that is in storage.
      const seeded = { member: null, approach: "pkw", kilometers: 120 };
      const gated = (answers: Record<string, unknown>) =>
        answers.regime ? [REGIME, REISEN] : [REGIME];
      const { backend, user } = openRules({ reisen: [seeded] }, gated);

      await screen.findByText("Regelwerk");
      expect(screen.queryByText("Fahrten")).toBeNull();

      await pickRegime(user, "Ehrenamt und Verwaltung");

      expect(await screen.findByText("Fahrten")).toBeInTheDocument();
      expect(screen.getByLabelText("Kilometer, Zeile 1")).toHaveValue(120);
      expect(screen.getByLabelText("Verkehrsmittel, Zeile 1")).toHaveTextContent("PKW");
      // Revealing a question is not a refusal looking for somewhere to land:
      // the question set changed under the client and nothing was re-asserted.
      expect(backend.patches).toEqual([{ regime: "ehrenamt" }]);
      expect(backend.refused).toEqual([]);
    });

    /**
     * And it reads as the first step of a form rather than as a broken one.
     *
     * Nothing new reaches the client for this: `steps` already partitions the
     * whole form into the groups the rules named, so **one named step is a
     * form showing fewer groups than it has**, and that is what the leg lays
     * out as its opening step (`opensWithOneStep`). A single question floating
     * over an empty payout looks like a page that did not load; what it is, is
     * the question that decides the others.
     */
    describe("zuerst ist sie die einzige Frage", () => {
      /** The gate, in a step of its own, as a ruleset that groups declares it. */
      const GATE = declaration({ ...REGIME, step: "Grundlagen" });

      /** What the answer reveals — the seeded table, in a step of its own. */
      const REVEALED = declaration({ ...REISEN, step: "Fahrt" });

      /** The row the excursion seeded, sitting in storage while nothing asks. */
      const SEEDED = { member: null, approach: "pkw", kilometers: 120 };

      /** `relevant_inputs` as a gating ruleset writes it. */
      const gated = (answers: Record<string, unknown>) =>
        answers.regime ? [GATE, REVEALED] : [GATE];

      it("asks nothing else, and says the rest is waiting on it", async () => {
        // Neuter it — have `opensWithOneStep` return false — and this is one
        // bare question under "Diese Fragen stellt die Finanzordnung", over a
        // payout of nothing: a leg that reads as broken rather than as begun.
        openRules({ reisen: [SEEDED] }, gated);

        await screen.findByText("Regelwerk");
        expect(screen.queryByText("Fahrten")).toBeNull();
        expect(screen.getByText(/Die erste Frage entscheidet/)).toBeInTheDocument();
        const group = screen.getByText("Grundlagen").closest(".answer-group") as HTMLElement;
        expect(group).toHaveClass("answer-opening");
        expect(within(group).getByText(/Die weiteren Fragen erscheinen/)).toBeInTheDocument();
        // And no payout: every figure in it would be a reading of an answer
        // nobody has been asked for, so "Noch nichts zu erstatten." here says
        // "this pays nothing" where the truth is "not yet".
        expect(document.querySelector(".payout")).toBeNull();
      });

      it("is a whole form again once the question is answered", async () => {
        const { user } = openRules({ reisen: [SEEDED] }, gated);

        await screen.findByText("Regelwerk");
        await pickRegime(user, "Ehrenamt und Verwaltung");

        expect(await screen.findByText("Fahrten")).toBeInTheDocument();
        expect(document.querySelector(".answer-opening")).toBeNull();
        expect(screen.queryByText(/Die weiteren Fragen erscheinen/)).toBeNull();
        expect(document.querySelector(".payout")).not.toBeNull();
      });

      it("opens on the whole form when the regime was answered before", async () => {
        // No regression for the statements already in the database: the gate
        // reads the stored answer, so there is no opening step to pass through
        // and no second request to wait for.
        openRules({ regime: "ehrenamt", reisen: [SEEDED] }, gated);

        expect(await screen.findByText("Fahrten")).toBeInTheDocument();
        expect(document.querySelector(".answer-opening")).toBeNull();
        expect(screen.getByText(/Diese Fragen stellt die Finanzordnung/)).toBeInTheDocument();
      });

      it("is no opening step for a ruleset that named no steps at all", async () => {
        // The degenerate case, and the reason the *label* carries this rather
        // than the count: Heidelberg names no steps, so its whole form comes
        // back as one step labelled `""`. One question there is all there is,
        // and nothing may promise more.
        openForm({ inputs: [REGIME], answers: { regime: null } });

        await screen.findByText("Regelwerk");
        expect(document.querySelector(".answer-opening")).toBeNull();
        expect(screen.queryByText(/Die weiteren Fragen erscheinen/)).toBeNull();
        expect(screen.getByText(/Diese Fragen stellt die Finanzordnung/)).toBeInTheDocument();
        expect(document.querySelector(".payout")).not.toBeNull();
      });
    });
  });
});

describe("submission flow — Abschluss", () => {
  const READY = {
    bills: [
      {
        id: 12,
        short_description: "Hütte",
        explanation: "",
        amount: 180,
        costs_covered: false,
        refunded: false,
        statement_id: 1,
        paid_by: { id: 7, name: "Hannah Beckers" },
        has_proof: true,
        proof_url: "/media/bill_images/huette.jpg",
      },
    ],
  };

  it("asks before submitting and then posts the transition", async () => {
    flowReturns();
    detailReturns(READY);
    let submitted = false;
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () => {
        submitted = true;
        return HttpResponse.json(statement({ submitted: true, status: 1 }));
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    // The button is disabled until the preflight has answered, which is the
    // point of asking the rules rather than guessing in the client.
    const button = await screen.findByRole("button", { name: "Einreichen" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    const dialog = within(await screen.findByRole("dialog"));
    expect(submitted).toBe(false);

    await user.click(dialog.getByRole("button", { name: "Einreichen" }));
    await waitFor(() => expect(submitted).toBe(true));
    expect(await screen.findByText("Abrechnung eingereicht.")).toBeInTheDocument();
  });

  it("does not submit when the confirmation is dismissed", async () => {
    flowReturns();
    detailReturns(READY);
    let submitted = false;
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () => {
        submitted = true;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=submit");
    const button = await screen.findByRole("button", { name: "Einreichen" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(submitted).toBe(false);
  });

  it("reports a refused submission", async () => {
    flowReturns();
    detailReturns(READY);
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () =>
        HttpResponse.json({ detail: "Es fehlen Belege." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=submit");
    const button = await screen.findByRole("button", { name: "Einreichen" });
    await waitFor(() => expect(button).toBeEnabled());
    await user.click(button);
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Einreichen" }),
    );
    expect(await screen.findByText("Es fehlen Belege.")).toBeInTheDocument();
  });

  it("prints the payout the engine resolved, transfer by transfer", async () => {
    flowReturns();
    // `claimedTotal` used to add five named totals up in the client, and
    // `payoutLines` to name four line kinds that only one section's rules have.
    // These are the engine's own answer, and the last one is its balancing
    // transfer — so the list adds up to zero by construction.
    detailReturns({
      ...READY,
      total: 0,
      transfers: [
        transfer({ amount: 180, category: "bill", label: "Beleg Hütte", explanation: "" }),
        transfer({ amount: 80 }),
        transfer({
          destination: { kind: "member", member: LEADERS[1] },
          amount: 60,
          category: "subsidy",
          label: "Fahrt- und Übernachtungszuschuss",
          explanation: "",
        }),
        transfer({
          source: { kind: "participants", member: null },
          destination: { kind: "section", member: null },
          amount: 320,
          category: "participant_contribution",
          label: "Beitrag der Teilnehmenden",
          explanation: "",
        }),
      ],
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    await screen.findByRole("heading", { name: "Prüfen und einreichen" });
    const payout = within(document.querySelector(".payout") as HTMLElement);
    expect(payout.getByText("Beleg Hütte")).toBeInTheDocument();
    expect(payout.getByText("Aufwandsentschädigung")).toBeInTheDocument();
    expect(payout.getByText("180,00 €")).toBeInTheDocument();
    expect(payout.getByText("80,00 €")).toBeInTheDocument();
    expect(payout.getByText("60,00 €")).toBeInTheDocument();
    // Who pays whom, from the resolved parties rather than from a field name.
    expect(payout.getByText(/die Sektion → Hannah Beckers · 2 × 40,00 €/)).toBeInTheDocument();
    expect(payout.getByText(/die Teilnehmenden → die Sektion/)).toBeInTheDocument();
    // 180 + 80 + 60 goes to people; the balancing transfer is not theirs — and
    // it comes to the same figure here, which is the books closing.
    const sum = document.querySelector(".payout-sum") as HTMLElement;
    expect(within(sum).getByText("An Personen")).toBeInTheDocument();
    expect(within(sum).getByText("320,00 €")).toBeInTheDocument();
  });

  it("charges a transfer away from a person against what they receive", async () => {
    flowReturns();
    detailReturns({
      ...READY,
      transfers: [
        transfer({ amount: 100 }),
        transfer({
          source: { kind: "member", member: LEADERS[0] },
          destination: { kind: "section", member: null },
          amount: 30,
          category: "org_fee",
          label: "Orga-Pauschale",
          explanation: "",
        }),
      ],
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    await screen.findByRole("heading", { name: "Prüfen und einreichen" });
    const payout = within(document.querySelector(".payout") as HTMLElement);
    expect(payout.getByText("Orga-Pauschale")).toBeInTheDocument();
    expect(payout.getByText("70,00 €")).toBeInTheDocument();
  });

  it("says so when the rules resolved nothing to pay out", async () => {
    flowReturns();
    detailReturns(READY);
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");
    expect(await screen.findByText("Noch nichts zu erstatten.")).toBeInTheDocument();
  });

  it("blocks submitting and names the blocker the rules found", async () => {
    flowReturns();
    detailReturns(READY);
    // Not re-derived here any more: the section's own checks, which is also
    // exactly what `submit` refuses on.
    server.use(
      http.get(api("/api/finance/statements/1/preflight"), () =>
        HttpResponse.json({
          statement_id: 1,
          ok: false,
          checks: [{ ok: false, message: "Für den LJP-Beitrag braucht jeder Beleg ein Bild." }],
          failing: [{ ok: false, message: "Für den LJP-Beitrag braucht jeder Beleg ein Bild." }],
          errors: ["Ein übernommener Beleg hat keine Zahler*in."],
        }),
      ),
    );
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    expect(await screen.findByText(/braucht jeder Beleg ein Bild/)).toBeInTheDocument();
    expect(screen.getByText(/keine Zahler\*in/)).toBeInTheDocument();
    expect(screen.getByText("Das fehlt noch, bevor du einreichen kannst.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einreichen" })).toBeDisabled();
  });

  it("says so when the rules have nothing to check", async () => {
    flowReturns();
    detailReturns(READY);
    server.use(
      http.get(api("/api/finance/statements/1/preflight"), () =>
        HttpResponse.json({ statement_id: 1, ok: true, checks: [], failing: [], errors: [] }),
      ),
    );
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");
    expect(
      await screen.findByText("Die Regeln der Sektion haben nichts zu beanstanden."),
    ).toBeInTheDocument();
  });

  it("saves a draft instead of handing it in", async () => {
    flowReturns();
    detailReturns(READY);
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=submit");
    await user.click(await screen.findByRole("button", { name: "Als Entwurf speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(await screen.findByText("Entwurf gespeichert.")).toBeInTheDocument();
  });
});

describe("statement detail — draft", () => {
  it("is a record view that hands a draft back to the flow", async () => {
    flowReturns([]);
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    expect(await screen.findByRole("button", { name: "Weiter bearbeiten" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Löschen" })).toBeInTheDocument();
    // There is exactly one way to change a statement, and it is not this page.
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Einreichen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prüfen & auszahlen" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Weiter bearbeiten" }));
    expect(
      await screen.findByRole("heading", { name: "Wofür ist diese Abrechnung?" }),
    ).toBeInTheDocument();
  });

  it("shows the record's own fields without any input", async () => {
    detailReturns();
    renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Weiter bearbeiten" });

    expect(screen.getByText("Skifreizeit")).toBeInTheDocument();
    expect(screen.getByText("11,00 €")).toBeInTheDocument();
    expect(document.querySelector(".tab-panel:not([hidden]) input")).toBeNull();
  });
});

describe("statement detail — validity and rejected saves", () => {
  it("marks an invalid statement as such", async () => {
    detailReturns({ is_valid: false, validity_display: "Belege fehlen" });
    renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Weiter bearbeiten" });
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("keeps the flow open and names the field when the save is rejected", async () => {
    flowReturns([]);
    detailReturns();
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        djangoValidation({ explanation: ["Zu lang."] }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1/edit?stage=purpose");
    await user.click(await screen.findByRole("button", { name: "Weiter" }));

    expect(await screen.findAllByText("Zu lang.")).not.toHaveLength(0);
    // The step stays put rather than advancing past a refused save.
    expect(
      screen.getByRole("heading", { name: "Wofür ist diese Abrechnung?" }),
    ).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("deletes a draft once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/finance/statements"), () => HttpResponse.json([])),
      http.get(api("/api/finance/enums"), () => HttpResponse.json(ENUMS)),
      http.delete(api("/api/finance/statements/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Abrechnung gelöscht.")).toBeInTheDocument();
  });

  it("does nothing when the delete is cancelled", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/finance/statements/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(deleted).toBe(false);
  });


});

const BILL: Record<string, unknown> = {
    id: 12,
    amount: 40,
    statement_id: 1,
    paid_by: { id: 9, name: "Mila Nowak" },
    proof_url: "/media/beleg.pdf",
    has_proof: true,
    short_description: "Verpflegung",
    explanation: "Einkauf",
  costs_covered: true,
  refunded: false,
};

describe("statement detail — Belege tab", () => {
  it("says so when the statement has no bills yet", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));
    expect(await screen.findByText("Keine Belege.")).toBeInTheDocument();
  });

  it("lists the bills read-only and opens one from its row", async () => {
    detailReturns({ bills: [BILL] });
    server.use(http.get(api("/api/finance/bills/12"), () => HttpResponse.json(BILL)));
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));

    const panelEl = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    const panel = within(panelEl);
    expect(await panel.findByText("Verpflegung")).toBeInTheDocument();
    expect(panel.getByText("40,00 €")).toBeInTheDocument();
    expect(panel.getByText("Mila Nowak")).toBeInTheDocument();
    // Receipts are written in the flow, so nothing here is editable.
    expect(panelEl.querySelector("input")).toBeNull();

    await user.click(panel.getByText("Verpflegung"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("flags a bill with no payer and no scan", async () => {
    detailReturns({ bills: [{ ...BILL, paid_by: null, has_proof: false, proof_url: null }] });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await panel.findByText("Verpflegung");
    expect(panel.getByText("—")).toBeInTheDocument();
    expect(panel.getByText("Fehlt")).toBeInTheDocument();
  });
});

describe("statement detail — Empfänger tab", () => {
  it("says where the recipients are actually chosen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Weiter bearbeiten" });
    await user.click(screen.getByRole("tab", { name: "Empfänger" }));

    // Read-only by design: recipients are chosen in the flow, which enforces
    // that only the trip's youth leaders may receive the money.
    expect(screen.getByText(/Erstattungs-Schritt der Abrechnung/)).toBeInTheDocument();
  });

  it("explains the empty case for a statement without an excursion", async () => {
    detailReturns({ excursion: null });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Weiter bearbeiten" });
    await user.click(screen.getByRole("tab", { name: "Empfänger" }));

    expect(
      screen.getByText(/gibt es nur für Abrechnungen, die zu einer Ausfahrt gehören/),
    ).toBeInTheDocument();
  });
});

describe("review pipeline", () => {
  const TRANSACTION = {
    id: 20,
    amount: 42.5,
    confirmed: false,
    confirmed_date: null,
    confirmed_by: null,
    statement_id: 1,
    member: { id: 9, name: "Mila Nowak" },
    ledger: { id: 1, name: "Jugendetat" },
    code: "BCD\n001\n1\nSCT\n\nMila Nowak\nDE02120300000000202051\nEUR42.5\n\n\nFahrtkosten",
    iban: "DE02120300000000202051",
    iban_valid: true,
    reference: "Fahrtkosten",
    settlement_group: "",
  };

  const SUBMITTED = { submitted: true, status: 1, status_display: "Eingereicht" };

  function bill(overrides: Record<string, unknown> = {}) {
    return {
      id: 12,
      short_description: "Hütte",
      explanation: "",
      amount: 180,
      costs_covered: false,
      refunded: false,
      statement_id: 1,
      paid_by: { id: 7, name: "Hannah Beckers" },
      has_proof: true,
      proof_url: "/media/bill_images/huette.jpg",
      ...overrides,
    };
  }

  /** Render one stage of the pipeline for a treasurer. */
  function openStage(
    stage: string,
    overrides: Record<string, unknown> = {},
    transactions: unknown[] = [],
  ) {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    detailReturns({ ...SUBMITTED, ...overrides });
    server.use(
      http.get(api("/api/finance/statements/1/transactions"), () =>
        HttpResponse.json(transactions),
      ),
    );
    return renderRoute(`/kompass/finance/statements/1/review?stage=${stage}`);
  }

  /* --- stage 1: judging the expenses ------------------------------------- */

  it("shows each expense beside the receipt it is judged on", async () => {
    openStage("expenses", { bills: [bill()] });

    const list = (await screen.findByRole("heading", { name: "Ausgaben prüfen" }))
      .closest(".review-list") as HTMLElement;
    const row = within(list).getByText("Hütte").closest(".beleg") as HTMLElement;
    expect(within(row).getByRole("button", { name: "Übernehmen" })).toBeInTheDocument();
    expect(within(row).getByRole("button", { name: "Ablehnen" })).toBeInTheDocument();

    const proof = document.querySelector(".review-proof img") as HTMLImageElement;
    expect(proof.getAttribute("src")).toContain("/media/bill_images/huette.jpg");
  });

  it("says when a receipt has no scan to inspect", async () => {
    openStage("expenses", { bills: [bill({ has_proof: false, proof_url: null })] });
    expect(await screen.findByText("Kein Bild hinterlegt")).toBeInTheDocument();
  });

  it("covers an expense and tallies what was decided", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(bill({ costs_covered: true }));
      }),
    );
    const { user } = openStage("expenses", { bills: [bill()] });

    await user.click(await screen.findByRole("button", { name: "Übernehmen" }));
    await waitFor(() => expect(patched).toEqual({ costs_covered: true }));

    const tally = document.querySelector(".decide-tally") as HTMLElement;
    expect(within(tally).getByText("Übernommen")).toBeInTheDocument();
    expect(within(tally).getByText("Abgelehnt")).toBeInTheDocument();
  });

  it("rejects an expense", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(bill());
      }),
    );
    const { user } = openStage("expenses", { bills: [bill({ costs_covered: true })] });

    await user.click(await screen.findByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(patched).toEqual({ costs_covered: false }));
  });

  it("reports a refused expense decision", async () => {
    server.use(
      http.patch(api("/api/finance/bills/12"), () =>
        HttpResponse.json({ detail: "Nicht erlaubt." }, { status: 403 }),
      ),
    );
    const { user } = openStage("expenses", { bills: [bill()] });
    await user.click(await screen.findByRole("button", { name: "Übernehmen" }));
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("selects another expense to inspect its receipt", async () => {
    const second = bill({ id: 13, short_description: "Sprit", proof_url: "/media/b/sprit.pdf" });
    const { user } = openStage("expenses", { bills: [bill(), second] });

    await user.click(await screen.findByText("Sprit"));
    const object = document.querySelector(".review-proof object") as HTMLObjectElement;
    expect(object.getAttribute("data")).toContain("/media/b/sprit.pdf");
  });

  /* --- stage 2: building the transfers ------------------------------------ */

  it("generates the transactions when there are none", async () => {
    let generated = false;
    server.use(
      http.post(api("/api/finance/statements/1/generate-transactions"), () => {
        generated = true;
        return HttpResponse.json(statement(SUBMITTED));
      }),
    );
    const { user } = openStage("bookings", { bills: [bill({ costs_covered: true })] });

    await user.click(await screen.findByRole("button", { name: "Buchungen erzeugen" }));
    await waitFor(() => expect(generated).toBe(true));
    expect(await screen.findByText("Buchungen erzeugt.")).toBeInTheDocument();
  });

  it("offers to merge only when two rows share a recipient and account", async () => {
    const twin = { ...TRANSACTION, id: 21, reference: "Verpflegung" };
    const { user } = openStage("bookings", {}, [TRANSACTION, twin]);

    const merge = await screen.findByRole("button", { name: /zusammenfassen/ });
    let reduced = false;
    server.use(
      http.post(api("/api/finance/statements/1/reduce-transactions"), () => {
        reduced = true;
        return HttpResponse.json(statement(SUBMITTED));
      }),
    );
    await user.click(merge);
    await waitFor(() => expect(reduced).toBe(true));
  });

  it("has nothing to merge for a single booking", async () => {
    openStage("bookings", {}, [TRANSACTION]);
    expect(
      await screen.findByRole("button", { name: "Nichts zusammenzufassen" }),
    ).toBeDisabled();
  });

  it("does not offer to merge two rows the rules keep apart", async () => {
    // What becomes one transfer is `(member, ledger, settlement_group)`. Keyed
    // on the first two, this pair read as one recipient to bundle, the POST
    // ran and nothing merged — a button that did nothing and said nothing.
    const vergütung = {
      ...TRANSACTION,
      id: 21,
      reference: "Tourenleitervergütung",
      settlement_group: "steuerrelevant",
    };
    openStage("bookings", {}, [TRANSACTION, vergütung]);

    expect(
      await screen.findByRole("button", { name: "Nichts zusammenzufassen" }),
    ).toBeDisabled();
  });

  it("still offers to merge two rows inside the same group", async () => {
    const twin = { ...TRANSACTION, id: 21, reference: "Tagegeld" };
    openStage("bookings", {}, [
      { ...TRANSACTION, settlement_group: "steuerrelevant" },
      { ...twin, settlement_group: "steuerrelevant" },
    ]);

    expect(
      await screen.findByRole("button", { name: "1 Empfänger*in zusammenfassen" }),
    ).toBeEnabled();
  });

  it("says why one person has two rows, and names the group on hover", async () => {
    // Otherwise the second row reads as a duplicate, and the finance officer
    // hunts for the way to combine it that the rules have taken away.
    openStage("bookings", {}, [
      TRANSACTION,
      {
        ...TRANSACTION,
        id: 21,
        reference: "Tourenleitervergütung",
        settlement_group: "steuerrelevant",
      },
    ]);

    const marks = await screen.findAllByText("wird getrennt überwiesen");
    expect(marks).toHaveLength(1);
    // The token is the ruleset's own vocabulary, so it is offered rather than
    // printed as prose.
    expect(marks[0]).toHaveAttribute("title", "Abrechnungsgruppe: steuerrelevant");
  });

  it("marks the separated transfer on the payout list too", async () => {
    openStage("payout", {}, [
      {
        ...TRANSACTION,
        reference: "Tourenleitervergütung",
        settlement_group: "steuerrelevant",
      },
    ]);

    const row = (await screen.findByText("Mila Nowak")).closest(".payout-row") as HTMLElement;
    expect(within(row).getByText("wird getrennt überwiesen")).toBeInTheDocument();
  });

  it("assigns an account straight from the row", async () => {
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/transactions/20"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRANSACTION);
      }),
    );
    const { user } = openStage("bookings", {}, [{ ...TRANSACTION, ledger: null }]);

    await screen.findByText("Fahrtkosten");
    await user.click(document.querySelector(".ss-trigger") as HTMLElement);
    await user.click(dropdown().getByRole("button", { name: "Sektionskonto" }));
    await waitFor(() => expect(patched).toEqual({ ledger_id: 2 }));
  });

  it("opens the account dropdown outside the scrolling table", async () => {
    const { user } = openStage("bookings", {}, [{ ...TRANSACTION, ledger: null }]);
    await screen.findByText("Fahrtkosten");
    await user.click(document.querySelector(".ss-trigger") as HTMLElement);

    // `.table-wrap` scrolls horizontally, which clips vertically too — an
    // in-flow panel was cut off and stretched the last row instead of
    // overlaying it. The panel must live outside that container.
    const panel = document.querySelector(".ms-dropdown") as HTMLElement;
    expect(panel).not.toBeNull();
    expect(panel.closest(".table-wrap")).toBeNull();
    expect(panel.classList.contains("is-anchored")).toBe(true);
  });

  it("warns while a booking has no account", async () => {
    openStage("bookings", {}, [{ ...TRANSACTION, ledger: null }]);
    expect(await screen.findByText(/1 Buchung\(en\) ohne Konto/)).toBeInTheDocument();
  });

  it("edits a booking in place and reports a rejected edit", async () => {
    let attempt = 0;
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/transactions/20"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return HttpResponse.json({ detail: "Betrag ungültig." }, { status: 422 });
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRANSACTION);
      }),
    );
    const { user } = openStage("bookings", {}, [TRANSACTION]);

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Betrag ungültig.")).toBeInTheDocument();

    const amount = screen.getByDisplayValue("42.5");
    await user.clear(amount);
    await user.type(amount, "50");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ amount: 50, reference: "Fahrtkosten", member_id: 9 });
    expect(await screen.findByText("Buchung gespeichert.")).toBeInTheDocument();
  });

  it("abandons a booking edit on Abbrechen", async () => {
    const { user } = openStage("bookings", {}, [TRANSACTION]);
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument(),
    );
  });

  it("marks a paid booking as such", async () => {
    openStage("bookings", {}, [{ ...TRANSACTION, confirmed: true }]);
    expect(await screen.findByText("Ja")).toBeInTheDocument();
  });

  it("lists the soll/ist differences when the books do not add up", async () => {
    openStage(
      "bookings",
      {
        is_valid: false,
        validity: 1,
        validity_display: "Die Buchungen passen nicht zu den Kosten.",
        transaction_issues: [
          { member: { id: 9, name: "Mila Nowak" }, current: 42.5, target: 60, difference: 17.5 },
        ],
      },
      [TRANSACTION],
    );
    expect(await screen.findByText("17,50 €")).toBeInTheDocument();
    expect(screen.getByText("Gebucht")).toBeInTheDocument();
  });

  it("says the books agree when there are no differences", async () => {
    openStage("bookings", {}, [TRANSACTION]);
    expect(await screen.findByText("Die Buchungen decken die Ausgaben genau.")).toBeInTheDocument();
  });

  /* --- stage 3: paying ---------------------------------------------------- */

  it("lists the payout and confirms without notifying", async () => {
    let sendQuery: string | null | undefined;
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), ({ request }) => {
        sendQuery = new URL(request.url).searchParams.get("send");
        return HttpResponse.json(statement({ submitted: true, confirmed: true, status: 2 }));
      }),
    );
    const { user } = openStage("payout", {}, [TRANSACTION]);

    expect(await screen.findByText("Mila Nowak")).toBeInTheDocument();
    await user.click(screen.getByLabelText(/Ich habe die aufgeführten Überweisungen ausgeführt/));
    await user.click(screen.getByRole("button", { name: "Nur bestätigen" }));

    await waitFor(() => expect(sendQuery).toBe(null));
    expect(await screen.findByText("Abrechnung bestätigt.")).toBeInTheDocument();
  });

  it("confirms and sends the summary after a prompt", async () => {
    let sendQuery: string | null = null;
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), ({ request }) => {
        sendQuery = new URL(request.url).searchParams.get("send");
        return HttpResponse.json(statement({ submitted: true, confirmed: true, status: 2 }));
      }),
    );
    const { user } = openStage("payout", {}, [TRANSACTION]);

    await screen.findByText("Mila Nowak");
    await user.click(screen.getByLabelText(/Ich habe die aufgeführten Überweisungen ausgeführt/));
    await user.click(screen.getByRole("button", { name: "Bestätigen & Beleg senden" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bestätigen & senden" }));

    await waitFor(() => expect(sendQuery).toBe("true"));
  });

  it("shows each transfer's IBAN and a scannable QR code", async () => {
    openStage("payout", {}, [TRANSACTION]);

    const row = (await screen.findByText("Mila Nowak")).closest(".payout-row") as HTMLElement;
    // The IBAN is grouped in fours, the way a bank prints it.
    expect(within(row).getByText("DE02 1203 0000 0000 2020 51")).toBeInTheDocument();
    // The EPC payload is rendered as a QR, not shown as text.
    // The encoder is loaded lazily, so the code arrives a moment after the row.
    await waitFor(() => expect(row.querySelector("svg")).not.toBeNull());
    expect(within(row).getByText("Scannen zum Überweisen")).toBeInTheDocument();
  });

  it("says why a transfer has no QR code", async () => {
    openStage("payout", {}, [
      { ...TRANSACTION, code: "", iban: "DE00", iban_valid: false },
    ]);

    const row = (await screen.findByText("Mila Nowak")).closest(".payout-row") as HTMLElement;
    expect(within(row).getByText("ungültig")).toBeInTheDocument();
    expect(within(row).getByText("Keine gültige IBAN")).toBeInTheDocument();
    expect(row.querySelector("svg")).toBeNull();
    expect(screen.getByText(/1 Buchung\(en\) ohne QR-Code/)).toBeInTheDocument();
  });

  it("refuses to confirm until the transfers are acknowledged", async () => {
    const { user } = openStage("payout", {}, [TRANSACTION]);
    await screen.findByText("Mila Nowak");

    expect(screen.getByRole("button", { name: "Nur bestätigen" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Bestätigen & Beleg senden" })).toBeDisabled();

    await user.click(screen.getByLabelText(/Ich habe die aufgeführten Überweisungen ausgeführt/));
    expect(screen.getByRole("button", { name: "Nur bestätigen" })).toBeEnabled();
  });

  it("reports a refused confirmation", async () => {
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), () =>
        HttpResponse.json({ detail: "Noch nicht bereit." }, { status: 422 }),
      ),
    );
    const { user } = openStage("payout", {}, [TRANSACTION]);
    await screen.findByText("Mila Nowak");
    await user.click(screen.getByLabelText(/Ich habe die aufgeführten Überweisungen ausgeführt/));
    await user.click(screen.getByRole("button", { name: "Nur bestätigen" }));
    expect(await screen.findByText("Noch nicht bereit.")).toBeInTheDocument();
  });

  /* --- gating and returning ----------------------------------------------- */

  it("locks the payout stage until the statement reconciles", async () => {
    openStage("payout", {
      is_valid: false,
      validity: 1,
      validity_display: "Die Buchungen passen nicht zu den Kosten.",
    });
    // The request for the locked stage falls back to the first one.
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
    expect(
      screen.getByText(/Auszahlen ist gesperrt: Die Buchungen passen nicht zu den Kosten\./),
    ).toBeInTheDocument();
  });

  it("hands the statement back to its author", async () => {
    let rejected = false;
    server.use(
      http.post(api("/api/finance/statements/1/reject"), () => {
        rejected = true;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = openStage("expenses", { bills: [bill()] });

    await user.click(await screen.findByRole("button", { name: "Zurückgeben" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Zurückgeben" }),
    );
    await waitFor(() => expect(rejected).toBe(true));
    expect(await screen.findByText("Abrechnung zurückgegeben.")).toBeInTheDocument();
  });

  it("walks forward and back through the stages", async () => {
    const { user } = openStage("expenses", { bills: [bill()] }, [TRANSACTION]);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));
    expect(await screen.findByRole("heading", { name: "Buchungen" })).toBeInTheDocument();

    const nav = within(document.querySelector(".flow-nav") as HTMLElement);
    await user.click(nav.getByRole("button", { name: "Zurück" }));
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
  });
});

/**
 * The other arrangement: the Geschäftsstelle makes the transfers.
 *
 * Everything above describes a section whose reviewer transfers the money, and
 * nothing in it may move — a sentence true in one arrangement is false in the
 * other, so these tests are written against the strings the other one must
 * *not* say as much as against the ones it must.
 */
describe("statement review — the office makes the transfers", () => {
  const TRANSACTION = {
    id: 20,
    amount: 42.5,
    confirmed: false,
    confirmed_date: null,
    confirmed_by: null,
    statement_id: 1,
    member: { id: 9, name: "Mila Nowak" },
    ledger: { id: 1, name: "Jugendetat" },
    code: "BCD\n001\n1\nSCT\n\nMila Nowak\nDE02120300000000202051\nEUR42.5\n\n\nFahrtkosten",
    iban: "DE02120300000000202051",
    iban_valid: true,
    reference: "Fahrtkosten",
    settlement_group: "",
  };

  const HANDOFF = {
    submitted: true,
    status: 1,
    status_display: "Eingereicht",
    payout_mode: "office",
  };

  function openStage(
    stage: string,
    overrides: Record<string, unknown> = {},
    transactions: unknown[] = [TRANSACTION],
  ) {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    detailReturns({ ...HANDOFF, ...overrides });
    server.use(
      http.get(api("/api/finance/statements/1/transactions"), () =>
        HttpResponse.json(transactions),
      ),
    );
    return renderRoute(`/kompass/finance/statements/1/review?stage=${stage}`);
  }

  it("asks nobody to claim a transfer they do not make", async () => {
    openStage("payout");

    expect(
      await screen.findByRole("heading", { name: "Übergabe an die Geschäftsstelle" }),
    ).toBeInTheDocument();
    await screen.findByText("Mila Nowak");
    expect(
      screen.getByText(/Die Geschäftsstelle überweist die folgenden 1 Beträge an 1 Empfänger/),
    ).toBeInTheDocument();
    // The acknowledgement is the sentence with nobody who could truthfully
    // tick it here, so it is not asked at all — and the button is not waiting
    // for it.
    expect(
      screen.queryByLabelText(/Ich habe die aufgeführten Überweisungen ausgeführt/),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Zur Auszahlung übergeben" })).toBeEnabled();
    expect(screen.queryByRole("heading", { name: "Auszahlung" })).not.toBeInTheDocument();
  });

  it("offers one act, not the pair that belongs to paying from here", async () => {
    openStage("payout");
    await screen.findByText("Mila Nowak");
    // "Release without mailing" would be a status claiming a handoff with
    // nothing handed over, so the mode does not offer it.
    expect(screen.queryByRole("button", { name: "Nur bestätigen" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Bestätigen & Beleg senden" }),
    ).not.toBeInTheDocument();
  });

  it("draws no QR code, because nobody here is going to scan one", async () => {
    openStage("payout");

    const row = (await screen.findByText("Mila Nowak")).closest(".payout-row") as HTMLElement;
    // The account, the reference and the amount are still there: this is the
    // last look at what is about to be handed over.
    expect(within(row).getByText("DE02 1203 0000 0000 2020 51")).toBeInTheDocument();
    expect(within(row).getByText("Fahrtkosten")).toBeInTheDocument();
    expect(within(row).getByText("42,50 €")).toBeInTheDocument();
    expect(row.querySelector(".payout-row-qr")).toBeNull();
    expect(screen.queryByText("Scannen zum Überweisen")).not.toBeInTheDocument();
  });

  it("hands the statement over after a prompt, and the server sends the Beleg", async () => {
    let sendQuery: string | null | undefined;
    let posted = false;
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), ({ request }) => {
        posted = true;
        sendQuery = new URL(request.url).searchParams.get("send");
        return HttpResponse.json(
          statement({ ...HANDOFF, confirmed: true, status: 2, status_display: "Abgeschlossen" }),
        );
      }),
    );
    const { user } = openStage("payout");
    await screen.findByText("Mila Nowak");

    await user.click(screen.getByRole("button", { name: "Zur Auszahlung übergeben" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/Der Beleg mit allen Überweisungsaufträgen geht an die/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Übergeben" }));

    await waitFor(() => expect(posted).toBe(true));
    // No `send` flag: the mail *is* the handoff, so the server sends it and
    // asking for it here as well would be a second mail for one act.
    expect(sendQuery).toBe(null);
    expect(
      await screen.findByText("Abrechnung zur Auszahlung übergeben."),
    ).toBeInTheDocument();
  });

  it("says a released statement was handed over, not paid out", async () => {
    openStage("payout", { confirmed: true, status: 2, status_display: "Abgeschlossen" });
    expect(
      await screen.findByText("Diese Abrechnung ist zur Auszahlung übergeben."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Diese Abrechnung ist bereits ausgezahlt.")).not.toBeInTheDocument();
    // And so does the leg's readout on the rail.
    expect(screen.getByText("übergeben")).toBeInTheDocument();
    expect(screen.queryByText("ausgezahlt")).not.toBeInTheDocument();
  });

  it("locks the handover rather than the payout", async () => {
    openStage("payout", {
      is_valid: false,
      validity: 1,
      validity_display: "Die Buchungen passen nicht zu den Kosten.",
    });
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
    expect(
      screen.getByText(/Die Übergabe ist gesperrt: Die Buchungen passen nicht zu den Kosten\./),
    ).toBeInTheDocument();
  });

  it("names the missing account rather than the missing QR code", async () => {
    // The person making the transfer has the paper and nothing else, so an
    // account they cannot act on has to be fixed before the handoff.
    openStage("payout", {}, [{ ...TRANSACTION, code: "", iban: "DE00", iban_valid: false }]);

    expect(await screen.findByText(/1 Buchung\(en\) ohne gültige IBAN/)).toBeInTheDocument();
    expect(screen.getByText(/hinterlege die IBAN vor der Übergabe/)).toBeInTheDocument();
    expect(screen.queryByText(/ohne QR-Code/)).not.toBeInTheDocument();
  });

  it("counts a booking of nothing as nothing to transfer", async () => {
    // Zero euro needs no bank transfer under either arrangement, so it is not
    // an account anybody has to go and fix.
    openStage("payout", {}, [{ ...TRANSACTION, amount: 0, code: "", iban: "", iban_valid: false }]);
    await screen.findByText("Mila Nowak");
    expect(screen.queryByText(/ohne gültige IBAN/)).not.toBeInTheDocument();
  });

  it("says what the bookings leg is holding up", async () => {
    openStage("bookings", {}, [{ ...TRANSACTION, ledger: null }]);
    expect(
      await screen.findByText(/Zusammenfassen und Übergeben brauchen es/),
    ).toBeInTheDocument();
  });

  it("does not call a handed-over booking paid", async () => {
    // `Transaction.confirmed` is set by the release, so here it means the
    // booking was handed over. Kompass does not know whether it was paid.
    openStage("bookings", {}, [{ ...TRANSACTION, confirmed: true }]);
    expect(await screen.findByRole("columnheader", { name: "Übergeben" })).toBeInTheDocument();
    expect(
      screen.queryByRole("columnheader", { name: "Bezahlt" }),
    ).not.toBeInTheDocument();
  });

  it("names the record rows after the act that filled them", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    detailReturns({
      ...HANDOFF,
      confirmed: true,
      status: 2,
      status_display: "Abgewickelt",
      confirmed_by: { id: 7, name: "Hannah Beckers" },
      confirmed_date: "2026-05-09",
    });
    renderRoute("/kompass/finance/statements/1");

    expect(await screen.findByText("Übergeben von")).toBeInTheDocument();
    expect(screen.getByText("Übergeben am")).toBeInTheDocument();
    expect(screen.queryByText("Bezahlt von")).not.toBeInTheDocument();
    expect(screen.queryByText("Bezahlt am")).not.toBeInTheDocument();
  });

  it("names the door after what is behind it", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    detailReturns(HANDOFF);
    const { user } = renderRoute("/kompass/finance/statements/1");

    expect(await screen.findByRole("button", { name: "Prüfen & übergeben" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prüfen & auszahlen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Prüfen & übergeben" }));
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
  });
});

describe("statement detail — submitted and confirmed", () => {
  it("swaps editing for the review pipeline once submitted", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    detailReturns({ submitted: true, status: 1, status_display: "Eingereicht" });
    const { user } = renderRoute("/kompass/finance/statements/1");

    expect(await screen.findByRole("button", { name: "Prüfen & auszahlen" })).toBeInTheDocument();
    // A submitted statement is frozen: no inline editing, no delete, and the
    // draft's own flow is closed.
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Weiter bearbeiten" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Prüfen & auszahlen" }));
    expect(await screen.findByRole("heading", { name: "Ausgaben prüfen" })).toBeInTheDocument();
  });

  it("hides the review pipeline from someone who may not process statements", async () => {
    detailReturns({ submitted: true, status: 1, status_display: "Eingereicht" });
    renderRoute("/kompass/finance/statements/1");

    expect(await screen.findByText("Eingereicht")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prüfen & auszahlen" })).not.toBeInTheDocument();
  });

  it("carries the approval record as a tab, read-only", async () => {
    // Not gated on the treasurer's permission, unlike the review pipeline:
    // what a statement is waiting for is what the person who handed it in most
    // wants to know. It used to be a page of its own with the signature on it,
    // beside the review pipeline, which signs too — so the record stayed here
    // and the act went where the payout it releases is shown.
    detailReturns({ submitted: true, status: 1, status_display: "Eingereicht" });
    const { user } = renderRoute("/kompass/finance/statements/1");

    await user.click(await screen.findByRole("tab", { name: "Freigabe" }));
    expect(
      await screen.findByText("Eine Unterschrift aus der Finanzverwaltung"),
    ).toBeInTheDocument();
    expect(screen.getByText("Es fehlt noch eine Unterschrift.")).toBeInTheDocument();
    // No signing and no override here: this is the record, not the act.
    expect(screen.queryByRole("button", { name: "Jetzt freigeben" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Ohne Unterschrift freigeben" }),
    ).not.toBeInTheDocument();
    // And there is one door into the room, not two.
    expect(screen.queryByRole("button", { name: "Freigabe" })).not.toBeInTheDocument();
  });

  it("does not offer the approval record for a draft", async () => {
    detailReturns();
    renderRoute("/kompass/finance/statements/1");
    await screen.findByText("Entwurf");
    expect(screen.queryByRole("tab", { name: "Freigabe" })).not.toBeInTheDocument();
  });

  it("offers the summary PDF and an undo once confirmed", async () => {
    detailReturns({
      submitted: true,
      confirmed: true,
      status: 2,
      status_display: "Bezahlt",
      confirmed_by: { id: 8, name: "Tobias Werner" },
      confirmed_date: "2026-05-10",
    });
    const { user } = renderRoute("/kompass/finance/statements/1");

    expect(
      await screen.findByRole("button", { name: /Zusammenfassung \(PDF\)/ }),
    ).toBeInTheDocument();
    // Only one workflow action remains, so it is a plain button, not a menu.
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bestätigung aufheben" })).toBeInTheDocument(),
    );
    await user.click(screen.getByRole("button", { name: "Bestätigung aufheben" }));
    expect(await screen.findByText("Wirklich zurücksetzen?")).toBeInTheDocument();
  });
});
