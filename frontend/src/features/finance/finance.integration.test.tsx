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
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

const MEMBERS = [
  { id: 7, name: "Hannah Beckers" },
  { id: 9, name: "Mila Nowak" },
];
const LEDGERS = [
  { id: 1, name: "Jugendetat" },
  { id: 2, name: "Sektionskonto" },
];

/** A complete StatementOut, for the detail page's own form. */
const FULL_STATEMENT: Record<string, unknown> = {
  id: 1,
  title: "F26-01 Skifreizeit",
  status_display: "Entwurf",
  submitted: false,
  confirmed: false,
  is_valid: true,
  validity: 0,
  validity_display: "Gültig",
  transaction_issues: [],
  excursion: null,
  created_by: null,
  submitted_by: null,
  confirmed_by: null,
  subsidy_to: null,
  ljp_to: null,
  allowance_to: [],
  bills: [],
  total: 0,
  total_bills: 0,
  total_bills_theoretic: 0,
  total_bills_not_covered: 0,
  total_theoretic: 0,
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
  night_cost: 11,
  status: 0,
  submitted_date: null,
  confirmed_date: null,
};

/* --- Konten (Ledger) ------------------------------------------------------ */

describe("finance — Konten", () => {
  function listReturns(rows = LEDGERS) {
    server.use(http.get(api("/api/finance/ledgers/"), () => HttpResponse.json(rows)));
  }

  it("lists the ledgers", async () => {
    listReturns();
    renderRoute("/app/finance/ledgers");
    expect(await screen.findByText("Jugendetat")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/finance/ledgers");
    expect(await screen.findByText("Keine Konten vorhanden.")).toBeInTheDocument();
  });

  it("searches by name", async () => {
    listReturns();
    const { user } = renderRoute("/app/finance/ledgers");
    await screen.findByText("Jugendetat");
    await user.type(screen.getByPlaceholderText("Suchen…"), "sektion");
    await waitFor(() => expect(screen.queryByText("Jugendetat")).not.toBeInTheDocument());
  });

  it("sorts by name in both directions", async () => {
    listReturns();
    const { user } = renderRoute("/app/finance/ledgers");
    await screen.findByText("Jugendetat");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/finance/ledgers");
    await screen.findByText("Jugendetat");
    expect(screen.queryByRole("button", { name: "Neues Konto" })).not.toBeInTheDocument();
  });

  it("creates a ledger and opens it", async () => {
    useMe({ permissions: ["finance.add_ledger"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/finance/ledgers/"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 3, name: "Materialkonto" });
      }),
      http.get(api("/api/finance/ledgers/3"), () =>
        HttpResponse.json({ id: 3, name: "Materialkonto" }),
      ),
    );
    const { user } = renderRoute("/app/finance/ledgers");
    await user.click(await screen.findByRole("button", { name: "Neues Konto" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Materialkonto");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ name: "Materialkonto" }));
    expect(await screen.findByText("Konto angelegt.")).toBeInTheDocument();
  });

  it("fills the create form's only field", async () => {
    useMe({ permissions: ["finance.add_ledger"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/finance/ledgers/"), async ({ request }) => {
        body = await request.json();
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/finance/ledgers");
    await user.click(await screen.findByRole("button", { name: "Neues Konto" }));
    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(body).toEqual({ name: "Text" }));
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    useMe({ permissions: ["finance.add_ledger"] });
    listReturns();
    server.use(
      http.post(api("/api/finance/ledgers/"), () =>
        djangoValidation({ name: ["Dieses Konto gibt es schon."] }),
      ),
    );
    const { user } = renderRoute("/app/finance/ledgers");
    await user.click(await screen.findByRole("button", { name: "Neues Konto" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Jugendetat");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Dieses Konto gibt es schon.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("renames a ledger and reports a rejected rename", async () => {
    let attempt = 0;
    let patched: unknown = null;
    server.use(
      http.get(api("/api/finance/ledgers/1"), () =>
        HttpResponse.json({ id: 1, name: "Jugendetat" }),
      ),
      http.patch(api("/api/finance/ledgers/1"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ name: ["Der Name fehlt."] });
        patched = await request.json();
        return HttpResponse.json({ id: 1, name: "Jugendetat 2026" });
      }),
    );
    const { user } = renderRoute("/app/finance/ledgers/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    const name = screen.getByDisplayValue("Jugendetat");
    await user.clear(name);
    await user.type(name, "Jugendetat 2026");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toEqual({ name: "Jugendetat 2026" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    server.use(
      http.get(api("/api/finance/ledgers/1"), () =>
        HttpResponse.json({ id: 1, name: "Jugendetat" }),
      ),
    );
    const { user } = renderRoute("/app/finance/ledgers/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Jugendetat")).not.toBeInTheDocument();
  });

  it("deletes a ledger once confirmed, and reports a refusal", async () => {
    let attempt = 0;
    server.use(
      http.get(api("/api/finance/ledgers/1"), () =>
        HttpResponse.json({ id: 1, name: "Jugendetat" }),
      ),
      http.get(api("/api/finance/ledgers/"), () => HttpResponse.json([])),
      http.delete(api("/api/finance/ledgers/1"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "Noch Buchungen zugeordnet." }, { status: 409 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/finance/ledgers/1");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Noch Buchungen zugeordnet.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Konto gelöscht.")).toBeInTheDocument();
  });

  it("closes the create modal with × and opens a ledger from its row", async () => {
    useMe({ permissions: ["finance.add_ledger"] });
    listReturns();
    server.use(
      http.get(api("/api/finance/ledgers/1"), () =>
        HttpResponse.json({ id: 1, name: "Jugendetat" }),
      ),
    );
    const { user } = renderRoute("/app/finance/ledgers");

    await user.click(await screen.findByRole("button", { name: "Neues Konto" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Jugendetat"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    server.use(
      http.get(api("/api/finance/ledgers/1"), () =>
        HttpResponse.json({ id: 1, name: "Jugendetat" }),
      ),
    );
    const { user } = renderRoute("/app/finance/ledgers/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Buchungen (Transaction, read-only) ----------------------------------- */

const TRANSACTION: Record<string, unknown> = {
  id: 20,
  amount: 42.5,
  confirmed: false,
  confirmed_date: null,
  confirmed_by: null,
  statement_id: 1,
  member: { id: 9, name: "Mila Nowak" },
  ledger: { id: 1, name: "Jugendetat" },
  code: "T-20",
  reference: "Fahrtkosten",
};

const STATEMENT_BRIEFS = [
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
];

describe("finance — Buchungen", () => {
  function listReturns(rows = [TRANSACTION]) {
    server.use(
      http.get(api("/api/finance/transactions"), () => HttpResponse.json(rows)),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
    );
  }

  it("lists the transactions with their ledger and statement", async () => {
    listReturns();
    renderRoute("/app/finance/transactions");
    expect(await screen.findByText("Fahrtkosten")).toBeInTheDocument();
    expect(screen.getByText("Mila Nowak")).toBeInTheDocument();
    expect(screen.getByText("Jugendetat")).toBeInTheDocument();
    expect(screen.getByText("42.50 €")).toBeInTheDocument();
  });

  it("says so when none are visible", async () => {
    listReturns([]);
    renderRoute("/app/finance/transactions");
    expect(await screen.findByText("Keine Buchungen sichtbar.")).toBeInTheDocument();
  });

  it("copes with a transaction that has no ledger", async () => {
    listReturns([{ ...TRANSACTION, ledger: null }]);
    renderRoute("/app/finance/transactions");
    await screen.findByText("Fahrtkosten");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("searches by reference and by recipient", async () => {
    listReturns([TRANSACTION, { ...TRANSACTION, id: 21, reference: "Übernachtung" }]);
    const { user } = renderRoute("/app/finance/transactions");
    await screen.findByText("Fahrtkosten");
    await user.type(screen.getByPlaceholderText("Suchen…"), "übernacht");
    await waitFor(() => expect(screen.queryByText("Fahrtkosten")).not.toBeInTheDocument());
  });

  it("names an unknown statement by its id and drops transactions with no ledger", async () => {
    listReturns([
      { ...TRANSACTION, statement_id: 99 },
      { ...TRANSACTION, id: 21, reference: "Ohne Konto", ledger: null, statement_id: 99 },
    ]);
    const { user } = renderRoute("/app/finance/transactions");
    await screen.findByText("Fahrtkosten");
    expect(screen.getAllByText("#99").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: /Konto:/ }));
    await user.click(dropdown().getByRole("button", { name: "Jugendetat" }));
    await waitFor(() => expect(screen.queryByText("Ohne Konto")).not.toBeInTheDocument());
  });

  it("filters by ledger, by statement and by paid status", async () => {
    listReturns([
      TRANSACTION,
      {
        ...TRANSACTION,
        id: 21,
        reference: "Übernachtung",
        confirmed: true,
        confirmed_date: "2026-05-10",
        confirmed_by: { id: 7, name: "Hannah Beckers" },
        ledger: { id: 2, name: "Sektionskonto" },
      },
    ]);
    const { user } = renderRoute("/app/finance/transactions");
    await screen.findByText("Fahrtkosten");

    await user.click(screen.getByRole("button", { name: /Konto:/ }));
    await user.click(dropdown().getByRole("button", { name: "Sektionskonto" }));
    await waitFor(() => expect(screen.queryByText("Fahrtkosten")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Bezahlt:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(screen.queryByText("Fahrtkosten")).not.toBeInTheDocument());
    expect(screen.getByText("Übernachtung")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Abrechnung:/ }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([TRANSACTION, { ...TRANSACTION, id: 21, ledger: null, confirmed_by: null }]);
    const { user } = renderRoute("/app/finance/transactions");
    await screen.findAllByText("Fahrtkosten");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("opens a transaction from its row and goes back", async () => {
    listReturns();
    server.use(
      http.get(api("/api/finance/transactions/20"), () => HttpResponse.json(TRANSACTION)),
    );
    const { user } = renderRoute("/app/finance/transactions");
    await user.click(await screen.findByText("Fahrtkosten"));
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("marks a paid transaction and names who authorised it", async () => {
    server.use(
      http.get(api("/api/finance/transactions/20"), () =>
        HttpResponse.json({
          ...TRANSACTION,
          confirmed: true,
          confirmed_date: "2026-05-10",
          confirmed_by: { id: 7, name: "Hannah Beckers" },
        }),
      ),
    );
    renderRoute("/app/finance/transactions/20");
    expect(await screen.findByText("Ja")).toBeInTheDocument();
  });

  it("copes with a transaction that is unconfirmed and unassigned", async () => {
    server.use(
      http.get(api("/api/finance/transactions/20"), () =>
        HttpResponse.json({
          ...TRANSACTION,
          ledger: null,
          confirmed_by: null,
          confirmed_date: null,
          statement_id: null,
        }),
      ),
    );
    renderRoute("/app/finance/transactions/20");
    await screen.findAllByText("Fahrtkosten");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("shows a single transaction read-only", async () => {
    server.use(
      http.get(api("/api/finance/transactions/20"), () => HttpResponse.json(TRANSACTION)),
    );
    renderRoute("/app/finance/transactions/20");
    // The reference doubles as the page's breadcrumb title.
    expect(await screen.findAllByText("Fahrtkosten")).toHaveLength(2);
    expect(screen.getByText("Mila Nowak")).toBeInTheDocument();
  });
});

/* --- Belege (Bill) -------------------------------------------------------- */

const BILL_BRIEF: Record<string, unknown> = {
  id: 12,
  amount: 40,
  statement_id: 1,
  statement_title: "F26-01 Skifreizeit",
  paid_by: { id: 9, name: "Mila Nowak" },
  proof_url: "/media/beleg.pdf",
  has_proof: true,
  short_description: "Verpflegung",
  explanation: "Einkauf",
  costs_covered: true,
  refunded: false,
};

const BILL = { ...BILL_BRIEF };

describe("finance — Belege", () => {
  function listReturns(rows = [BILL_BRIEF]) {
    server.use(
      http.get(api("/api/finance/bills"), () => HttpResponse.json(rows)),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/finance/bills/12"), () => HttpResponse.json({ ...BILL, ...overrides })),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
    );
  }

  it("lists the bills with their statement and amount", async () => {
    listReturns();
    renderRoute("/app/finance/bills");
    expect(await screen.findByText("Verpflegung")).toBeInTheDocument();
    expect(screen.getByText("40.00 €")).toBeInTheDocument();
    expect(screen.getByText("F26-01 Skifreizeit")).toBeInTheDocument();
  });

  it("searches by description and explanation", async () => {
    listReturns([BILL_BRIEF, { ...BILL_BRIEF, id: 13, short_description: "Benzin" }]);
    const { user } = renderRoute("/app/finance/bills");
    await screen.findByText("Verpflegung");
    await user.type(screen.getByPlaceholderText("Suchen…"), "benzin");
    await waitFor(() => expect(screen.queryByText("Verpflegung")).not.toBeInTheDocument());
  });

  it("names an unknown statement by its id and marks an uncovered bill", async () => {
    server.use(
      http.get(api("/api/finance/bills"), () =>
        HttpResponse.json([{ ...BILL_BRIEF, statement_id: 99, costs_covered: false }]),
      ),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    );
    const { user } = renderRoute("/app/finance/bills");
    await screen.findByText("Verpflegung");
    // A statement the list cannot resolve still shows as "#id".
    expect(screen.getAllByText("#99").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);

    // The statement filter offers it under the same "#id" label.
    await user.click(screen.getByRole("button", { name: /Abrechnung:/ }));
    expect(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: "#99",
      }),
    ).toBeInTheDocument();
  });

  it("filters out bills nobody paid", async () => {
    listReturns([BILL_BRIEF, { ...BILL_BRIEF, id: 13, paid_by: null }]);
    const { user } = renderRoute("/app/finance/bills");
    await screen.findAllByText("Verpflegung");
    await user.click(screen.getByRole("button", { name: /Bezahlt von:/ }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await waitFor(() => expect(screen.getByText("1 / 2")).toBeInTheDocument());
  });

  it("says so when none are visible", async () => {
    listReturns([]);
    renderRoute("/app/finance/bills");
    expect(await screen.findByText("Keine Belege sichtbar.")).toBeInTheDocument();
  });

  it("copes with a bill without payer or explanation", async () => {
    listReturns([{ ...BILL_BRIEF, paid_by: null, explanation: "", statement_title: null }]);
    renderRoute("/app/finance/bills");
    await screen.findByText("Verpflegung");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("filters by statement, payer and refunded status", async () => {
    listReturns([
      BILL_BRIEF,
      {
        ...BILL_BRIEF,
        id: 13,
        short_description: "Benzin",
        refunded: true,
        paid_by: { id: 7, name: "Hannah Beckers" },
      },
    ]);
    const { user } = renderRoute("/app/finance/bills");
    await screen.findByText("Verpflegung");

    await user.click(screen.getByRole("button", { name: /Ausgezahlt:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(screen.queryByText("Verpflegung")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Bezahlt von:/ }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await waitFor(() => expect(screen.queryByText("Benzin")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Abrechnung:/ }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([BILL_BRIEF, { ...BILL_BRIEF, id: 13, paid_by: null, statement_title: null }]);
    const { user } = renderRoute("/app/finance/bills");
    await screen.findAllByText("Verpflegung");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without finance.view_statement", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/finance/bills");
    await screen.findByText("Verpflegung");
    expect(screen.queryByRole("button", { name: "Neuer Beleg" })).not.toBeInTheDocument();
  });

  it("creates a bill as multipart, with its scan", async () => {
    useMe({ permissions: ["finance.view_statement"] });
    listReturns();
    let fields: Record<string, string> = {};
    let files: string[] = [];
    server.use(
      http.post(api("/api/finance/bills"), async ({ request }) => {
        const clone = request.clone();
        files = await multipartFilenames(request);
        fields = await multipartFields(clone);
        return HttpResponse.json(BILL);
      }),
      http.get(api("/api/finance/bills/12"), () => HttpResponse.json(BILL)),
    );
    const { user } = renderRoute("/app/finance/bills");
    await user.click(await screen.findByRole("button", { name: "Neuer Beleg" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Abrechnung" }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "Verpflegung");
    await user.type(dialog.getByLabelText("Erklärung"), "Einkauf");
    await user.clear(dialog.getByLabelText("Betrag"));
    await user.type(dialog.getByLabelText("Betrag"), "40");
    await user.click(dialog.getByLabelText("Übernommen"));
    await user.click(dialog.getByRole("button", { name: "Bezahlt von" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.upload(
      dialog.getByLabelText(/Beleg-Scan/),
      new File(["%PDF"], "beleg.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(files).toEqual(["beleg.pdf"]));
    expect(fields).toMatchObject({
      statement_id: "1",
      short_description: "Verpflegung",
      explanation: "Einkauf",
      amount: "40",
      costs_covered: "true",
      paid_by_id: "9",
    });
    expect(await screen.findByText("Beleg angelegt.")).toBeInTheDocument();
  });

  it("reports a rejected create, including a non-JSON failure", async () => {
    useMe({ permissions: ["finance.view_statement"] });
    listReturns();
    let attempt = 0;
    server.use(
      http.post(api("/api/finance/bills"), () => {
        attempt += 1;
        if (attempt === 1) {
          return djangoValidation({
            amount: ["Betrag fehlt."],
            statement: ["Abrechnung fehlt."],
            short_description: ["Beschreibung fehlt."],
            explanation: ["Zu lang."],
          });
        }
        return new HttpResponse("<html>502</html>", { status: 502 });
      }),
    );
    const { user } = renderRoute("/app/finance/bills");
    await user.click(await screen.findByRole("button", { name: "Neuer Beleg" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Betrag fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Abrechnung fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Beschreibung fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows a bill with its scan, statement link and flags", async () => {
    detailReturns();
    renderRoute("/app/finance/bills/12");
    expect(await screen.findByRole("link", { name: "Öffnen" })).toHaveAttribute(
      "href",
      "/media/beleg.pdf",
    );
    // The detail links the statement by id (the title is only on the list).
    expect(screen.getByRole("link", { name: "#1" })).toHaveAttribute(
      "href",
      "/app/finance/statements/1",
    );
  });

  it("says so when a bill has no scan and no statement", async () => {
    detailReturns({ has_proof: false, proof_url: null, statement_id: null, statement_title: null });
    renderRoute("/app/finance/bills/12");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.queryByRole("link", { name: "Öffnen" })).not.toBeInTheDocument();
    expect(screen.getByText("Fehlt")).toBeInTheDocument();
  });

  it("saves an inline edit with numbers and the payer id", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const amount = screen.getByDisplayValue("40");
    await user.clear(amount);
    await user.type(amount, "45.5");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ amount: 45.5, paid_by_id: 9 });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save without leaving edit mode", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/finance/bills/12"), () =>
        djangoValidation({ amount: ["Betrag ungültig."] }),
      ),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Betrag ungültig.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("40")).not.toBeInTheDocument();
  });

  it("replaces the scan through the dedicated multipart endpoint", async () => {
    detailReturns();
    let uploaded: string | undefined;
    server.use(
      http.post(api("/api/finance/bills/12/proof"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("tab", { name: /Beleg-Scan/ }));

    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["%PDF"], "neu.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    await waitFor(() => expect(uploaded).toBe("neu.pdf"));
  });

  it("deletes a bill once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/finance/bills"), () => HttpResponse.json([])),
      http.delete(api("/api/finance/bills/12"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("closes the create modal with ×, opens a bill from its row and clears the scan", async () => {
    useMe({ permissions: ["finance.view_statement"] });
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/finance/bills");

    await user.click(await screen.findByRole("button", { name: "Neuer Beleg" }));
    const dialog = await screen.findByRole("dialog");
    const file = within(dialog).getByLabelText(/Beleg-Scan/);
    await user.upload(file, new File(["x"], "b.pdf", { type: "application/pdf" }));
    await user.upload(file, []);
    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Verpflegung"));
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("reports a refused delete and a refused scan upload", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/finance/bills/12"), () =>
        HttpResponse.json({ detail: "finance.delete_bill" }, { status: 403 }),
      ),
      http.post(api("/api/finance/bills/12/proof"), () =>
        new HttpResponse("<html>502</html>", { status: 502 }),
      ),
    );
    const { user } = renderRoute("/app/finance/bills/12");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: /Beleg-Scan/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "b.pdf", { type: "application/pdf" }));
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("marks a refunded bill as such", async () => {
    detailReturns({ refunded: true });
    renderRoute("/app/finance/bills/12");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("Ja").length).toBeGreaterThan(0);
  });

  it("shows an uncovered, unrefunded bill as such and clears the scan input", async () => {
    detailReturns({ costs_covered: false, refunded: false });
    const { user } = renderRoute("/app/finance/bills/12");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: /Beleg-Scan/ }));
    const input = document.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["x"], "b.pdf", { type: "application/pdf" }));
    await user.upload(input, []);
    expect(screen.getByRole("button", { name: "Hochladen" })).toBeDisabled();
  });

  it("sends a blank amount as zero", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue("40"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toMatchObject({ amount: 0 }));
  });

  it("shows a rejected payer on the create form", async () => {
    useMe({ permissions: ["finance.view_statement"] });
    listReturns();
    server.use(
      http.post(api("/api/finance/bills"), () =>
        djangoValidation({ paid_by: ["Unbekannte Person."] }),
      ),
    );
    const { user } = renderRoute("/app/finance/bills");
    await user.click(await screen.findByRole("button", { name: "Neuer Beleg" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Unbekannte Person.")).not.toHaveLength(0);
  });

  it("copes with a bill whose optional fields are null", async () => {
    detailReturns({
      explanation: null,
      short_description: null,
      paid_by: null,
      statement_id: null,
      has_proof: false,
      proof_url: null,
    });
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

describe("finance — every field", () => {
  it("Beleg: carries every edited field into the PATCH", async () => {
    server.use(
      http.get(api("/api/finance/bills/12"), () => HttpResponse.json(BILL)),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
    );
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/app/finance/bills/12");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      short_description: "Text",
      explanation: "Text",
      amount: 3,
      costs_covered: false,
      refunded: true,
    });
  });

  it("Beleg: fills every field of the create form", async () => {
    useMe({ permissions: ["finance.view_statement"] });
    server.use(
      http.get(api("/api/finance/bills"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    );
    let fields: Record<string, string> = {};
    server.use(
      http.post(api("/api/finance/bills"), async ({ request }) => {
        fields = await multipartFields(request);
        return djangoValidation({ amount: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/finance/bills");
    await user.click(await screen.findByRole("button", { name: "Neuer Beleg" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(Object.keys(fields).length).toBeGreaterThan(0));
    expect(fields).toMatchObject({
      short_description: "Text",
      explanation: "Text",
      amount: "3",
      costs_covered: "true",
    });
  });

  it("Abrechnung: carries every edited field into the PATCH", async () => {
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(FULL_STATEMENT)),
      http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
      http.get(api("/api/finance/ledgers/"), () => HttpResponse.json(LEDGERS)),
    );
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_STATEMENT);
      }),
    );
    const { user } = renderRoute("/app/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    for (const tab of ["Abrechnung", "Verwaltung"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await fillEveryField(user, panel);
    }
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      short_description: "Text",
      explanation: "Text",
      night_cost: 3,
    });
  });

  it("Abrechnung: fills every field of the create form", async () => {
    server.use(
      http.get(api("/api/finance/statements"), () => HttpResponse.json(STATEMENT_BRIEFS)),
      http.get(api("/api/finance/enums"), () =>
        HttpResponse.json({ status: [{ value: 0, label: "Entwurf" }] }),
      ),
      http.get(api("/api/members/excursions"), () =>
        HttpResponse.json([{ id: 3, code: "F26-01", name: "Skifreizeit" }]),
      ),
    );
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ short_description: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/finance/statements");
    await user.click(await screen.findByRole("button", { name: "Neue Abrechnung" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      short_description: "Text",
      explanation: "Text",
      night_cost: 3,
      // The optional excursion select clears on its first option.
      excursion_id: null,
    });
  });
});
