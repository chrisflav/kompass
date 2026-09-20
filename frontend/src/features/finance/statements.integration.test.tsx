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
    // Numbers and null, never the form's strings.
    expect(body).toEqual({
      short_description: "Skifreizeit",
      explanation: "",
      excursion_id: null,
      night_cost: 0,
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

    await user.click(await screen.findByRole("button", { name: "Einreichen" }));
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
    await user.click(await screen.findByRole("button", { name: "Einreichen" }));
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
    await user.click(await screen.findByRole("button", { name: "Einreichen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Einreichen" }),
    );
    expect(await screen.findByText("Es fehlen Belege.")).toBeInTheDocument();
  });

  it("adds its own breakdown up, receipts included", async () => {
    flowReturns();
    // No bill is covered yet at submission — the treasurer decides that later —
    // so `statement.total` excludes them all. The claim must still count them.
    detailReturns({
      ...READY,
      total: 0,
      total_bills: 0,
      total_bills_theoretic: 180,
      total_allowance: 80,
      allowance_per_yl: 40,
      allowances_paid: 2,
      total_subsidies: 60,
      total_org_fee: 0,
      paid_ljp_contributions: 0,
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    await screen.findByRole("heading", { name: "Prüfen und einreichen" });
    const shown = within(document.querySelector(".summary-card") as HTMLElement);
    expect(shown.getByText("180,00 €")).toBeInTheDocument();
    expect(shown.getByText("80,00 €")).toBeInTheDocument();
    expect(shown.getByText("60,00 €")).toBeInTheDocument();
    // 180 + 80 + 60 — not statement.total, which would read 0,00 €.
    expect(shown.getByText("320,00 €")).toBeInTheDocument();
  });

  it("always shows the allowance, so it cannot be mistaken for the travel line", async () => {
    flowReturns();
    detailReturns({
      ...READY,
      total_allowance: 0,
      allowances_paid: 0,
      allowance_per_yl: 40,
      total_subsidies: 60,
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    await screen.findByRole("heading", { name: "Prüfen und einreichen" });
    const card = document.querySelector(".summary-card") as HTMLElement;
    // Zero rows used to be filtered out, which removed the allowance entirely
    // and left the travel subsidy looking like it.
    expect(within(card).getByText("Aufwandsentschädigung")).toBeInTheDocument();
    expect(within(card).getByText("0 × 40,00 € pro Person")).toBeInTheDocument();
    expect(within(card).getByText("Fahrt- und Übernachtungszuschuss")).toBeInTheDocument();
  });

  it("names the LJP amount, not only its recipient", async () => {
    flowReturns();
    detailReturns({
      ...READY,
      ljp_to: { id: 9, name: "Mila Nowak" },
      paid_ljp_contributions: 210,
    });
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    await screen.findByRole("heading", { name: "Prüfen und einreichen" });
    const card = document.querySelector(".summary-card") as HTMLElement;
    expect(within(card).getByText("LJP-Beitrag")).toBeInTheDocument();
    expect(within(card).getByText("an Mila Nowak")).toBeInTheDocument();
    expect(within(card).getByText("210,00 €")).toBeInTheDocument();
  });

  it("blocks submitting and names the blocker before it is pressed", async () => {
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
    renderRoute("/kompass/finance/statements/1/edit?stage=submit");

    expect(await screen.findByText(/Beleg\(e\) ohne Zahler/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Einreichen" })).toBeDisabled();
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
    expect(row.querySelector("svg")).not.toBeNull();
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
