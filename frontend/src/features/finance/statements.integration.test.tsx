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
import { renderRoute, sortByEveryColumn } from "../../test/utils";

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
    transaction_issues: [],
    excursion: { id: 3, code: "F26-01", name: "Skifreizeit" },
    created_by: { id: 7, name: "Hannah Beckers" },
    submitted_by: null,
    confirmed_by: null,
    subsidy_to: null,
    ljp_to: null,
    allowance_to: [],
    bills: [],
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
    night_cost: 11,
    status: 0,
    submitted_date: null,
    confirmed_date: null,
    ...overrides,
  };
}

/** Everything the detail page and its inlines fetch. */
function detailReturns(data: Record<string, unknown> = {}) {
  const s = statement(data);
  server.use(
    http.get(api("/api/finance/statements/1"), () => HttpResponse.json(s)),
    http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
    http.get(api("/api/members/"), () =>
      HttpResponse.json([
        { id: 7, name: "Hannah Beckers" },
        { id: 9, name: "Mila Nowak" },
      ]),
    ),
    http.get(api("/api/finance/ledgers/"), () => HttpResponse.json(LEDGERS)),
  );
  return s;
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

  it("opens a statement from its row and closes the create modal with ×", async () => {
    listReturns();
    detailReturns();
    server.use(http.get(api("/api/members/excursions"), () => HttpResponse.json([])));
    const { user } = renderRoute("/kompass/finance/statements");

    await user.click(await screen.findByRole("button", { name: "Neue Abrechnung" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("F26-01 Skifreizeit"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: "Empfänger" }));
    // The link falls back to the excursion's code when it has no name.
    expect(screen.getByRole("link", { name: /F26-01 öffnen/ })).toBeInTheDocument();
  });

  it("reports a rejected save whose body is not JSON", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        new HttpResponse("<html>500</html>", { status: 500 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
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

describe("creating a statement", () => {
  it("sends numbers for the numeric fields and opens the new statement", async () => {
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/excursions"), () =>
        HttpResponse.json([{ id: 3, code: "F26-01", name: "Skifreizeit" }]),
      ),
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    detailReturns();

    const { user } = renderRoute("/kompass/finance/statements");
    await screen.findByText("F26-01 Skifreizeit");
    await user.click(screen.getByRole("button", { name: "Neue Abrechnung" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Kurzbeschreibung/), "Skifreizeit");
    await user.clear(dialog.getByLabelText(/Preis pro Übernachtung/));
    await user.type(dialog.getByLabelText(/Preis pro Übernachtung/), "11");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    // `night_cost` and `excursion_id` are numbers/null, never the form's strings.
    expect(body).toEqual({
      short_description: "Skifreizeit",
      explanation: "",
      excursion_id: null,
      night_cost: 11,
    });
    expect(await screen.findByText("Abrechnung angelegt.")).toBeInTheDocument();
  });
});

describe("creating a statement — rejections", () => {
  it("shows a server field error on every field of the create form", async () => {
    listReturns();
    server.use(
      http.get(api("/api/members/excursions"), () => HttpResponse.json([])),
      http.post(api("/api/finance/statements"), () =>
        djangoValidation({
          short_description: ["Die Beschreibung fehlt."],
          explanation: ["Zu lang."],
          excursion: ["Unbekannte Ausfahrt."],
          night_cost: ["Ungültiger Betrag."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(await screen.findByRole("button", { name: "Neue Abrechnung" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Kurzbeschreibung/), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Die Beschreibung fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();
    expect(screen.getByText("Unbekannte Ausfahrt.")).toBeInTheDocument();
    expect(screen.getByText("Ungültiger Betrag.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("sends the chosen excursion as a number", async () => {
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/excursions"), () =>
        HttpResponse.json([{ id: 3, code: "F26-01", name: "Skifreizeit" }]),
      ),
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement());
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(await screen.findByRole("button", { name: "Neue Abrechnung" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Kurzbeschreibung/), "Skifreizeit");
    await user.click(dialog.getByRole("button", { name: "Fahrt" }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 Skifreizeit" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ excursion_id: 3 });
  });
});

describe("statement detail — draft", () => {
  it("offers editing, submitting and deleting", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();

    // Two workflow buttons collapse into one "Aktionen ▾" menu.
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    expect(screen.getByRole("button", { name: "Einreichen" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Löschen" })).toBeInTheDocument();
    // The confirm-and-pay workflow belongs to the submitted stage only.
    expect(
      screen.queryByRole("button", { name: "Buchungen & Bestätigung" }),
    ).not.toBeInTheDocument();
  });

  it("asks before submitting and then posts the transition", async () => {
    detailReturns();
    let submitted = false;
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () => {
        submitted = true;
        return HttpResponse.json(statement({ submitted: true, status: 1 }));
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Bearbeiten" });

    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Einreichen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Wirklich einreichen?")).toBeInTheDocument();
    expect(submitted).toBe(false);

    await user.click(dialog.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(submitted).toBe(true));
  });

  it("saves an inline edit as numbers", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(statement({ night_cost: 9 }));
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const nightCost = screen.getByDisplayValue("11");
    await user.clear(nightCost);
    await user.type(nightCost, "9");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ night_cost: 9 });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });
});

describe("statement detail — validity and rejected saves", () => {
  it("marks an invalid statement as such", async () => {
    detailReturns({ is_valid: false, validity_display: "Belege fehlen" });
    renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("keeps edit mode and names the field when the save is rejected", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/finance/statements/1"), () =>
        djangoValidation({ night_cost: ["Höchstens 11 €."] }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Höchstens 11 €.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("11")).not.toBeInTheDocument();
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
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
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
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(deleted).toBe(false);
  });

  it("reports a refused transition", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () =>
        HttpResponse.json({ detail: "Es fehlen Belege." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Einreichen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Bestätigen" }),
    );
    expect(await screen.findByText("Es fehlen Belege.")).toBeInTheDocument();
  });

  it("closes the confirmation without acting on Abbrechen", async () => {
    detailReturns();
    let submitted = false;
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () => {
        submitted = true;
        return HttpResponse.json(statement());
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Einreichen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(submitted).toBe(false);
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

describe("statement detail — Belege inline", () => {
  it("says so when the statement has no bills yet", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));
    expect(await screen.findByText("Keine Belege.")).toBeInTheDocument();
  });

  it("lists the bills read-only, linking each to its own page", async () => {
    detailReturns({ bills: [BILL] });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));

    expect(await screen.findByText("Verpflegung")).toBeInTheDocument();
    expect(screen.getByText("40.00 €")).toBeInTheDocument();
    expect(screen.getByText("Mila Nowak")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Öffnen" })).toHaveAttribute(
      "href",
      "/kompass/finance/bills/12",
    );
  });

  it("shows an em dash for a bill nobody paid", async () => {
    detailReturns({ bills: [{ ...BILL, paid_by: null }] });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("tab", { name: "Belege" }));
    await screen.findByText("Verpflegung");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("stages a new bill and posts it as multipart on save", async () => {
    detailReturns();
    let fields: Record<string, string> = {};
    let files: string[] = [];
    server.use(
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.post(api("/api/finance/bills"), async ({ request }) => {
        const clone = request.clone();
        files = await multipartFilenames(request);
        fields = await multipartFields(clone);
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.click(await screen.findByRole("button", { name: "+ Beleg" }));

    const dialog = within(await screen.findByRole("dialog"));
    // The add button stays disabled until the row is identifiable.
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "Verpflegung");
    await user.type(dialog.getByLabelText("Erklärung"), "Einkauf");
    await user.clear(dialog.getByLabelText("Betrag"));
    await user.type(dialog.getByLabelText("Betrag"), "40");
    await user.click(dialog.getByRole("button", { name: "Bezahlt von" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(dialog.getByLabelText("Übernommen"));
    await user.upload(
      dialog.getByLabelText(/Beleg-Scan/),
      new File(["%PDF"], "beleg.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    // Staged only: the row is in the table but nothing has been uploaded yet.
    expect(files).toEqual([]);
    expect(screen.getByDisplayValue("Verpflegung")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(files).toEqual(["beleg.pdf"]));
    expect(fields).toMatchObject({
      statement_id: "1",
      short_description: "Verpflegung",
      amount: "40",
      paid_by_id: "9",
      costs_covered: "true",
    });
  });

  it("closes the bill dialog with ×, and clears a chosen scan", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.click(await screen.findByRole("button", { name: "+ Beleg" }));

    const dialog = await screen.findByRole("dialog");
    const file = within(dialog).getByLabelText(/Beleg-Scan/);
    await user.upload(file, new File(["x"], "b.pdf", { type: "application/pdf" }));
    await user.upload(file, []);
    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("clears a bill row's scan again", async () => {
    detailReturns({ bills: [BILL] });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));

    const input = document.querySelector(
      '.tab-panel:not([hidden]) input[type="file"]',
    ) as HTMLInputElement;
    await user.upload(input, new File(["x"], "b.pdf", { type: "application/pdf" }));
    await user.upload(input, []);
    expect(input.files).toHaveLength(0);
  });

  it("copes with a bill whose description and amount are null", async () => {
    detailReturns({
      bills: [{ ...BILL, short_description: null, explanation: null, amount: null }],
    });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    expect((await screen.findAllByDisplayValue("")).length).toBeGreaterThan(0);
  });

  it("drops a staged bill again on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.click(await screen.findByRole("button", { name: "+ Beleg" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "Versehen");
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText("Versehen")).not.toBeInTheDocument();
  });

  it("edits an existing bill in place, sending only what changed", async () => {
    detailReturns({ bills: [BILL] });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.patch(api("/api/finance/bills/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));

    const amount = await screen.findByDisplayValue("40");
    await user.clear(amount);
    await user.type(amount, "45");
    const [covered, refunded] = screen.getAllByRole("checkbox");
    await user.click(covered);
    await user.click(refunded);

    // Reassign the payer through the row's own select.
    await user.click(screen.getByRole("button", { name: /Mila Nowak/ }));
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      amount: 45,
      costs_covered: false,
      refunded: true,
      paid_by_id: 7,
    });
  });

  it("replaces a bill's scan on save", async () => {
    detailReturns({ bills: [BILL] });
    let uploaded: string | undefined;
    server.use(
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.patch(api("/api/finance/bills/12"), () => HttpResponse.json(BILL)),
      http.post(api("/api/finance/bills/12/proof"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json(BILL);
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.upload(
      document.querySelector('.tab-panel:not([hidden]) input[type="file"]') as HTMLInputElement,
      new File(["%PDF"], "neu.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(uploaded).toBe("neu.pdf"));
  });

  it("removes a bill on save", async () => {
    detailReturns({ bills: [BILL] });
    let deleted = false;
    server.use(
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.delete(api("/api/finance/bills/12"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("reports a failed bill upload without losing the draft", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.post(api("/api/finance/bills"), () =>
        HttpResponse.json({ detail: "Der Betrag fehlt." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Belege" }));
    await user.click(await screen.findByRole("button", { name: "+ Beleg" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Kurzbeschreibung"), "Verpflegung");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(
      await screen.findByText(/Ein verknüpfter Eintrag konnte nicht gespeichert werden/),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });
});

describe("statement detail — Empfänger tab", () => {
  it("says where the recipients are actually edited and links there", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Bearbeiten" });
    await user.click(screen.getByRole("tab", { name: "Empfänger" }));

    // Read-only by design: the fields live on the excursion, because only its
    // youth leaders may receive the money.
    expect(
      screen.getByText(/Diese Felder werden auf der Ausfahrt gepflegt/),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Skifreizeit öffnen/ })).toHaveAttribute(
      "href",
      "/kompass/excursions/3",
    );
  });

  it("explains the empty case for a statement without an excursion", async () => {
    detailReturns({ excursion: null });
    const { user } = renderRoute("/kompass/finance/statements/1");
    await screen.findByRole("button", { name: "Bearbeiten" });
    await user.click(screen.getByRole("tab", { name: "Empfänger" }));

    expect(
      screen.getByText(/gibt es nur für Abrechnungen, die zu einer Ausfahrt gehören/),
    ).toBeInTheDocument();
  });
});

describe("statement processing modal", () => {
  const TRANSACTION = {
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

  const SUBMITTED = { submitted: true, status: 1, status_display: "Eingereicht" };

  async function openModal(overrides: Record<string, unknown> = {}, transactions: unknown[] = []) {
    detailReturns({ ...SUBMITTED, ...overrides });
    server.use(
      http.get(api("/api/finance/statements/1/transactions"), () =>
        HttpResponse.json(transactions),
      ),
    );
    const rendered = renderRoute("/kompass/finance/statements/1");
    await rendered.user.click(
      await screen.findByRole("button", { name: "Buchungen & Bestätigung" }),
    );
    return rendered;
  }

  it("summarises the statement and its expenses", async () => {
    await openModal({
      bills: [
        {
          id: 12,
          amount: 40,
          statement_id: 1,
          paid_by: null,
          proof_url: null,
          has_proof: false,
          short_description: "Verpflegung",
          explanation: "",
          costs_covered: true,
          refunded: false,
        },
      ],
    });

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Verpflegung")).toBeInTheDocument();
    expect(dialog.getByText("40.00 €")).toBeInTheDocument();
    // An excursion statement also gets the contribution summary.
    expect(dialog.getByText("Aufwandsentschädigung")).toBeInTheDocument();
    expect(dialog.getByText("Orga-Pauschale")).toBeInTheDocument();
  });

  it("omits the contribution summary for a statement without an excursion", async () => {
    await openModal({ excursion: null });
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Keine Belege.")).toBeInTheDocument();
    expect(dialog.queryByText("Orga-Pauschale")).not.toBeInTheDocument();
  });

  it("shows the validity badge when the statement is not ready", async () => {
    await openModal({ is_valid: false, validity_display: "Belege fehlen" });
    expect(await screen.findByText("Belege fehlen")).toBeInTheDocument();
    const dialog = within(screen.getByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Bestätigen" })).toBeDisabled();
    expect(dialog.getByRole("button", { name: "Bestätigen & senden" })).toBeDisabled();
  });

  it("generates the transactions when there are none", async () => {
    let generated = false;
    const { user } = await openModal();
    server.use(
      http.post(api("/api/finance/statements/1/generate-transactions"), () => {
        generated = true;
        return HttpResponse.json([TRANSACTION]);
      }),
    );

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Keine Buchungen. Über „Buchungen erzeugen“ anlegen.")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Buchungen erzeugen" }));

    await waitFor(() => expect(generated).toBe(true));
    expect(await screen.findByText("Buchungen erzeugt.")).toBeInTheDocument();
  });

  it("offers to summarise once transactions exist", async () => {
    let reduced = false;
    const { user } = await openModal({}, [TRANSACTION]);
    server.use(
      http.post(api("/api/finance/statements/1/reduce-transactions"), () => {
        reduced = true;
        return HttpResponse.json([TRANSACTION]);
      }),
    );

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.queryByRole("button", { name: "Buchungen erzeugen" })).not.toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Zusammenfassen" }));

    await waitFor(() => expect(reduced).toBe(true));
    expect(await screen.findByText("Buchungen zusammengefasst.")).toBeInTheDocument();
  });

  it("edits a planned transaction in place", async () => {
    let patched: Record<string, unknown> | null = null;
    const { user } = await openModal({}, [TRANSACTION]);
    server.use(
      http.patch(api("/api/finance/transactions/20"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRANSACTION);
      }),
    );

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Mila Nowak")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Bearbeiten" }));

    const amount = dialog.getByDisplayValue("42.5");
    await user.clear(amount);
    await user.type(amount, "50");
    const reference = dialog.getByDisplayValue("Fahrtkosten");
    await user.clear(reference);
    await user.type(reference, "Übernachtung");
    await user.click(dialog.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({
      amount: 50,
      reference: "Übernachtung",
      member_id: 9,
      ledger_id: 1,
    });
    expect(await screen.findByText("Buchung gespeichert.")).toBeInTheDocument();
  });

  it("can reassign the recipient and clear the ledger", async () => {
    let patched: Record<string, unknown> | null = null;
    const { user } = await openModal({}, [{ ...TRANSACTION, ledger: null }]);
    server.use(
      http.patch(api("/api/finance/transactions/20"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRANSACTION);
      }),
    );

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bearbeiten" }));

    const triggers = dialog.getAllByRole("button", { name: /▾/ });
    await user.click(triggers[0]);
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));
    await user.click(dialog.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ member_id: 7, ledger_id: null });
  });

  it("assigns a ledger to a transaction", async () => {
    let patched: Record<string, unknown> | null = null;
    const { user } = await openModal({}, [{ ...TRANSACTION, ledger: null, amount: 0 }]);
    server.use(
      http.patch(api("/api/finance/transactions/20"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRANSACTION);
      }),
    );
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bearbeiten" }));

    const triggers = dialog.getAllByRole("button", { name: /▾/ });
    await user.click(triggers[1]);
    await user.click(dropdown().getByRole("button", { name: "Jugendetat" }));
    await user.click(dialog.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).toMatchObject({ ledger_id: 1, amount: 0 }));
  });

  it("shows an unpaid bill as such in the expense table", async () => {
    await openModal({
      bills: [{ ...BILL, costs_covered: false }],
    });
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getAllByText("Nein").length).toBeGreaterThan(0);
  });

  it("abandons a transaction edit on Abbrechen", async () => {
    const { user } = await openModal({}, [TRANSACTION]);
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bearbeiten" }));
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    expect(dialog.queryByDisplayValue("42.5")).not.toBeInTheDocument();
  });

  it("reports a rejected transaction edit", async () => {
    const { user } = await openModal({}, [TRANSACTION]);
    server.use(
      http.patch(api("/api/finance/transactions/20"), () =>
        HttpResponse.json({ detail: "Betrag ungültig." }, { status: 422 }),
      ),
    );
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bearbeiten" }));
    await user.click(dialog.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Betrag ungültig.")).toBeInTheDocument();
  });

  it("marks a confirmed transaction as paid", async () => {
    await openModal({}, [{ ...TRANSACTION, confirmed: true }]);
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getAllByText("Ja").length).toBeGreaterThan(0);
  });

  it("lists the soll/ist differences when the books do not add up", async () => {
    await openModal({
      transaction_issues: [
        { member: { id: 9, name: "Mila Nowak" }, current: 40, target: 50, difference: -10 },
      ],
    });
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("-10.00 €")).toBeInTheDocument();
    expect(
      dialog.queryByText("Die Buchungen stimmen mit den Ausgaben überein."),
    ).not.toBeInTheDocument();
  });

  it("says the books agree when there are no differences", async () => {
    await openModal();
    expect(
      await screen.findByText("Die Buchungen stimmen mit den Ausgaben überein."),
    ).toBeInTheDocument();
  });

  it("confirms without notifying", async () => {
    let sendQuery: string | null = "unset";
    const { user } = await openModal();
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), ({ request }) => {
        sendQuery = new URL(request.url).searchParams.get("send");
        return HttpResponse.json(statement({ confirmed: true }));
      }),
    );
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Bestätigen" }),
    );
    await waitFor(() => expect(sendQuery).toBeNull());
    expect(await screen.findByText("Abrechnung bestätigt.")).toBeInTheDocument();
  });

  it("rejects the statement back to its author", async () => {
    let rejected = false;
    const { user } = await openModal();
    server.use(
      http.post(api("/api/finance/statements/1/reject"), () => {
        rejected = true;
        return HttpResponse.json(statement());
      }),
    );
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Ablehnen" }),
    );
    await waitFor(() => expect(rejected).toBe(true));
    expect(await screen.findByText("Abrechnung abgelehnt.")).toBeInTheDocument();
  });

  it("reports a refused confirmation", async () => {
    const { user } = await openModal();
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), () =>
        HttpResponse.json({ detail: "Die Buchungen stimmen nicht." }, { status: 422 }),
      ),
    );
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Bestätigen" }),
    );
    expect(await screen.findByText("Die Buchungen stimmen nicht.")).toBeInTheDocument();
  });

  it("closes without acting", async () => {
    const { user } = await openModal();
    // Both the header × and the footer button are labelled "Schließen"; take the
    // one in the action row.
    const dialog = within(await screen.findByRole("dialog"));
    const closers = dialog.getAllByRole("button", { name: "Schließen" });
    await user.click(closers[closers.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("statement detail — submitted and confirmed", () => {
  it("swaps editing for the confirmation workflow once submitted", async () => {
    detailReturns({ submitted: true, status: 1, status_display: "Eingereicht" });
    renderRoute("/kompass/finance/statements/1");

    expect(
      await screen.findByRole("button", { name: "Buchungen & Bestätigung" }),
    ).toBeInTheDocument();
    // A submitted statement is frozen: no inline editing and no delete.
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("confirms from the workflow modal and can send the notification", async () => {
    detailReturns({ submitted: true, status: 1, status_display: "Eingereicht" });
    let sendQuery: string | null = null;
    server.use(
      http.post(api("/api/finance/statements/1/confirm"), ({ request }) => {
        sendQuery = new URL(request.url).searchParams.get("send");
        return HttpResponse.json(statement({ submitted: true, confirmed: true, status: 2 }));
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements/1");
    await user.click(await screen.findByRole("button", { name: "Buchungen & Bestätigung" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Bestätigen & senden" }));

    await waitFor(() => expect(sendQuery).toBe("true"));
    expect(await screen.findByText("Abrechnung bestätigt.")).toBeInTheDocument();
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
