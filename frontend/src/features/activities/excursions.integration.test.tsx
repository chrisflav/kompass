import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

/** Stub the object-URL pair so DownloadButton can run in jsdom. */
function stubDownloads() {
  Object.defineProperty(URL, "createObjectURL", {
    configurable: true,
    writable: true,
    value: () => "blob:x",
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    configurable: true,
    writable: true,
    value: () => {},
  });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
}

const GROUPS = [
  { id: 5, name: "Klettergruppe" },
  { id: 6, name: "Bouldergruppe" },
];
const MEMBERS = [
  { id: 42, name: "Anna Ärmel" },
  { id: 43, name: "Mila Nowak" },
];
const ACTIVITY_CATEGORIES = [{ id: 1, name: "Klettern" }];

const BRIEF = {
  id: 3,
  code: "F26-01",
  name: "Skifreizeit",
  date: "2026-02-14T08:00:00Z",
  place: "Südtirol",
  approved: true,
  groups: [{ id: 5, name: "Klettergruppe" }],
  participant_ids: [42],
};

const EXCURSION = {
  id: 3,
  code: "F26-01",
  name: "Skifreizeit",
  date: "2026-02-14T08:00:00Z",
  end: "2026-02-16T18:00:00Z",
  tour_type: 0,
  tour_type_str: "Gemeinschaftstour",
  tour_approach: 2,
  tour_approach_str: "Fahrgemeinschaften",
  difficulty: 2,
  difficulty_str: "mittel",
  night_count: 2,
  duration: 3,
  staff_count: 2,
  participant_count: 8,
  head_count: 10,
  statement_id: null,
  groups: [{ id: 5, name: "Klettergruppe" }],
  jugendleiter: [{ id: 42, name: "Anna Ärmel" }],
  activity: [{ id: 1, name: "Klettern" }],
  place: "Südtirol",
  postcode: "39030",
  destination: "Gipfel",
  description: "Drei Tage im Schnee.",
  kilometers_traveled: 420,
  approved: true,
  approval_comments: "",
  approved_extra_youth_leader_count: 0,
};

function listReturns(rows: unknown[] = [BRIEF]) {
  server.use(
    http.get(api("/api/members/excursions"), () => HttpResponse.json(rows)),
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
  );
}

function detailReturns(overrides: Record<string, unknown> = {}, ljp: unknown = null) {
  server.use(
    http.get(api("/api/members/excursions/3"), () =>
      HttpResponse.json({ ...EXCURSION, ...overrides }),
    ),
    http.get(api("/api/members/excursions/3/participants"), () => HttpResponse.json([])),
    http.get(api("/api/members/excursions/3/ljp-proposal"), () =>
      ljp === null
        ? HttpResponse.json({ detail: "Kein LJP-Antrag" }, { status: 404 })
        : HttpResponse.json(ljp),
    ),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/members/activity-categories"), () =>
      HttpResponse.json(ACTIVITY_CATEGORIES),
    ),
  );
}

describe("activities — Ausfahrten list", () => {
  it("lists the excursions with their approval state", async () => {
    listReturns();
    renderRoute("/kompass/excursions");
    expect(await screen.findByText("F26-01")).toBeInTheDocument();
    expect(screen.getByText("Skifreizeit")).toBeInTheDocument();
    expect(screen.getByText("Südtirol")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/kompass/excursions");
    expect(await screen.findByText("Keine Ausfahrten sichtbar.")).toBeInTheDocument();
  });

  it("shows an em dash for a nameless excursion without a place", async () => {
    listReturns([{ ...BRIEF, name: "", place: "", date: null }]);
    renderRoute("/kompass/excursions");
    await screen.findByText("F26-01");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(2);
  });

  it("searches by name, code and place", async () => {
    listReturns([BRIEF, { ...BRIEF, id: 4, code: "F26-02", name: "Sommerfahrt", place: "Allgäu" }]);
    const { user } = renderRoute("/kompass/excursions");
    await screen.findByText("Skifreizeit");

    await user.type(screen.getByPlaceholderText("Suchen…"), "allgäu");
    await waitFor(() => expect(screen.queryByText("Skifreizeit")).not.toBeInTheDocument());
    expect(screen.getByText("Sommerfahrt")).toBeInTheDocument();
  });

  it("filters by approval, group and participant", async () => {
    listReturns([
      BRIEF,
      {
        ...BRIEF,
        id: 4,
        code: "F26-02",
        name: "Abgelehnt",
        approved: false,
        groups: [{ id: 6, name: "Bouldergruppe" }],
        participant_ids: [43],
      },
      { ...BRIEF, id: 5, code: "F26-03", name: "Offen", approved: null, participant_ids: [] },
    ]);
    const { user } = renderRoute("/kompass/excursions");
    await screen.findByText("Skifreizeit");

    const pick = async (filter: RegExp, option: string) => {
      await user.click(screen.getByRole("button", { name: filter }));
      await user.click(dropdown().getByRole("button", { name: option }));
    };

    await pick(/Genehmigt:/, "Abgelehnt");
    await waitFor(() => expect(screen.getByText("1 / 3")).toBeInTheDocument());
    await pick(/Genehmigt:/, "Unbekannt");
    await waitFor(() => expect(screen.getByText("Offen")).toBeInTheDocument());
    await pick(/Genehmigt:/, "Genehmigt");
    await waitFor(() => expect(screen.getByText("Skifreizeit")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await pick(/Gruppe:/, "Bouldergruppe");
    await waitFor(() => expect(screen.getByText("1 / 3")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await pick(/Teilnehmer\*in:/, "Mila Nowak");
    await waitFor(() => expect(screen.getByText("1 / 3")).toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([BRIEF, { ...BRIEF, id: 4, code: "F26-02", name: "", place: "", approved: null }]);
    const { user } = renderRoute("/kompass/excursions");
    await screen.findByText("F26-01");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("crosses over to the activity categories", async () => {
    listReturns();
    server.use(
      http.get(api("/api/members/activity-categories"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/kompass/excursions");
    await user.click(await screen.findByRole("button", { name: "Kategorien verwalten" }));
    expect(await screen.findByText("Keine Kategorien.")).toBeInTheDocument();
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/excursions");
    await screen.findByText("Skifreizeit");
    expect(screen.queryByRole("button", { name: "Neue Ausfahrt" })).not.toBeInTheDocument();
  });

  it("creates an excursion, sending choices as numbers and dates as ISO", async () => {
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/excursions"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/excursions");
    await user.click(await screen.findByRole("button", { name: "Neue Ausfahrt" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Aktivität"), "Skifreizeit");
    await user.type(dialog.getByLabelText(/Stützpunkt/), "Südtirol");
    await user.type(dialog.getByLabelText("Von"), "2026-02-14T08:00");
    await user.click(dialog.getByRole("button", { name: "Schwierigkeit" }));
    await user.click(dropdown().getByRole("button", { name: "schwer" }));
    await user.click(dialog.getByRole("button", { name: "Tourtyp" }));
    await user.click(dropdown().getByRole("button", { name: "Ausbildung" }));
    await user.click(dialog.getByRole("button", { name: "Gruppen" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: /Jugendleiter/ }));
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      name: "Skifreizeit",
      place: "Südtirol",
      difficulty: 3,
      tour_type: 2,
      group_ids: [5],
      jugendleiter_ids: [42],
      activity_ids: [],
      // An empty "Bis" is null, and "Von" becomes a full ISO timestamp.
      end: null,
    });
    expect(String(body!.date)).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(await screen.findByText("Ausfahrt angelegt.")).toBeInTheDocument();
  });

  it("sends a null place when it is left blank", async () => {
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/excursions"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/excursions");
    await user.click(await screen.findByRole("button", { name: "Neue Ausfahrt" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Aktivität"), "Ohne Ort");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ place: null, date: null, end: null });
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    listReturns();
    server.use(
      http.post(api("/api/members/excursions"), () =>
        djangoValidation({ name: ["Der Name fehlt."] }),
      ),
    );
    const { user } = renderRoute("/kompass/excursions");
    await user.click(await screen.findByRole("button", { name: "Neue Ausfahrt" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("activities — Ausfahrt detail", () => {
  it("shows the excursion across its tabs", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/excursions/3");

    // The code shows in the breadcrumb and in the Code row.
    expect(await screen.findAllByText("F26-01")).not.toHaveLength(0);
    expect(screen.getByText("Südtirol")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Genehmigung" }));
    expect(screen.getAllByText("Genehmigt").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));
    expect(
      await screen.findByText(/Gib hier bitte alle Personen an, die bei der Ausfahrt dabei sind/),
    ).toBeInTheDocument();
  });

  it("shows an em dash for an excursion with no leaders", async () => {
    detailReturns({ jugendleiter: [] });
    renderRoute("/kompass/excursions/3");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("sends the approval fields only when they actually changed", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).not.toBeNull());
    // Untouched: the approval fields are left out of the PATCH entirely.
    expect(patched).not.toHaveProperty("approved");
    expect(patched).not.toHaveProperty("approval_comments");
    expect(patched).not.toHaveProperty("approved_extra_youth_leader_count");

    patched = null;
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Genehmigung" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getByRole("button", { name: /Genehmigt/ }));
    await user.click(dropdown().getByRole("button", { name: "Abgelehnt" }));
    await user.type(panel.getAllByRole("textbox")[0], "Zu wenige Jugendleiter*innen");
    const extra = panel.getByRole("spinbutton");
    await user.clear(extra);
    await user.type(extra, "1");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      approved: false,
      approval_comments: "Zu wenige Jugendleiter*innen",
      approved_extra_youth_leader_count: 1,
    });
  });

  it("clears the approval back to unknown", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Genehmigung" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getByRole("button", { name: /Genehmigt/ }));
    await user.click(dropdown().getByRole("button", { name: "Unbekannt" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ approved: null });
  });

  it("adds a participant on save", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.post(api("/api/members/excursions/3/participants"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 40 });
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).toMatchObject({ member_id: 43 }));
  });

  it("saves an inline edit with ids and numbers", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const place = screen.getByDisplayValue("Südtirol");
    await user.clear(place);
    await user.type(place, "Tirol");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      place: "Tirol",
      difficulty: 2,
      tour_type: 0,
      group_ids: [5],
      jugendleiter_ids: [42],
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/excursions/3"), () =>
        djangoValidation({ place: ["Der Ort fehlt."] }),
      ),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Ort fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Südtirol")).not.toBeInTheDocument();
  });

  it("offers every document download", async () => {
    stubDownloads();
    detailReturns();
    const requested: string[] = [];
    for (const doc of [
      "crisis-intervention-list",
      "notes-list",
      "seminar-vbk",
      "seminar-report-docx",
      "seminar-report-costs",
      "ljp-proofs",
      "sjr-application",
    ]) {
      server.use(
        http.post(api(`/api/members/documents/excursions/3/${doc}`), () => {
          requested.push(doc);
          return HttpResponse.json({});
        }),
      );
    }
    const { user } = renderRoute("/kompass/excursions/3");

    for (const label of [
      "Kriseninterventionsliste",
      "Notizenliste",
      "Seminar V-BK",
      "Seminarbericht (docx)",
      "Seminar TN/Kosten",
      "LJP-Nachweis",
      "SJR-Antrag",
    ]) {
      await user.click(await screen.findByRole("button", { name: /Dokumente/ }));
      await user.click(screen.getByRole("button", { name: label }));
    }

    await waitFor(() => expect(requested).toHaveLength(7));
  });

  it("deletes an excursion once confirmed", async () => {
    useMe({ permissions: ["members.delete_global_freizeit"] });
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/excursions"), () => HttpResponse.json([])),
      http.delete(api("/api/members/excursions/3"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Ausfahrt gelöscht.")).toBeInTheDocument();
  });

  it("hides the delete button without the permission", async () => {
    useMe({ permissions: [] });
    detailReturns();
    renderRoute("/kompass/excursions/3");
    await screen.findByText("Südtirol");
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("activities — Ausfahrt LJP-Antrag", () => {
  const LJP = {
    id: 4,
    excursion_id: 3,
    title: "Sportklettern",
    category: 2,
    category_display: "Themenorientierte Bildungsmaßnahme",
    goal: 1,
    goal_display: "Qualifizierung",
    goal_strategy: "Übungen am Fels",
    not_bw_reason: null,
    not_bw_reason_display: null,
    interventions: [],
  };

  it("says the proposal must be saved before a schedule can be added", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "LJP-Antrag" }));
    expect(
      await screen.findByText(
        "Bitte zuerst den LJP-Antrag speichern, um Programmpunkte anzulegen.",
      ),
    ).toBeInTheDocument();
  });

  it("creates the proposal on the first save that fills it in", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.post(api("/api/members/excursions/3/ljp-proposal"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(LJP);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    const titleRow = [...panel.querySelectorAll(".detail-row")].find((r) =>
      r.querySelector("dt")?.textContent?.startsWith("Titel"),
    ) as HTMLElement;
    await user.type(titleRow.querySelector("input") as HTMLInputElement, "Sportklettern");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toMatchObject({
      title: "Sportklettern",
      category: 2,
      goal: 2,
      not_bw_reason: null,
    });
  });

  it("seeds the 'not in Baden-Württemberg' reason from the stored proposal", async () => {
    detailReturns({}, { ...LJP, not_bw_reason: 3, not_bw_reason_display: "Grenznähe" });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/members/ljp-proposals/4"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(LJP);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ not_bw_reason: 3 });
  });

  it("updates an existing proposal instead of creating a second one", async () => {
    detailReturns({}, LJP);
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/members/ljp-proposals/4"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(LJP);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));

    const strategy = await screen.findByDisplayValue("Übungen am Fels");
    await user.clear(strategy);
    await user.type(strategy, "Toprope und Vorstieg");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      title: "Sportklettern",
      goal_strategy: "Toprope und Vorstieg",
      category: 2,
      goal: 1,
    });
  });

  it("adds, edits and removes a schedule entry", async () => {
    detailReturns({}, {
      ...LJP,
      interventions: [
        { id: 7, date_start: "2026-02-14T09:00:00Z", duration: 2, activity: "Materialkunde" },
      ],
    });
    let created: Record<string, unknown> | null = null;
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/members/ljp-proposals/4"), () => HttpResponse.json(LJP)),
      http.post(api("/api/members/ljp-proposals/4/interventions"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 8 });
      }),
      http.patch(api("/api/members/interventions/7"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 7 });
      }),
      http.delete(api("/api/members/interventions/7"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));

    // Edit the existing row…
    const activity = await screen.findByDisplayValue("Materialkunde");
    await user.clear(activity);
    await user.type(activity, "Knotenkunde");

    // …and add a new one.
    await user.click(screen.getByRole("button", { name: "+ Programmpunkt" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.type(dialog.getByLabelText("Beginn"), "2026-02-15T10:00");
    await user.clear(dialog.getByLabelText(/Dauer/));
    await user.type(dialog.getByLabelText(/Dauer/), "1.5");
    await user.type(dialog.getByLabelText(/Aktion/), "Standplatzbau");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).not.toBeNull());
    expect(patched).toMatchObject({ activity: "Knotenkunde" });
    expect(created).toMatchObject({ activity: "Standplatzbau", duration: "1.5" });

    // Then remove the server-side row.
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));
    await user.click((await screen.findAllByRole("button", { name: "Entfernen" }))[0]);
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("shows the schedule read-only outside edit mode", async () => {
    detailReturns({}, {
      ...LJP,
      interventions: [
        { id: 7, date_start: "2026-02-14T09:00:00Z", duration: 2, activity: "" },
      ],
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "LJP-Antrag" }));

    // A schedule entry without an activity reads as an em dash.
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("says so when the proposal has no schedule yet", async () => {
    detailReturns({}, LJP);
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "LJP-Antrag" }));
    expect(await screen.findByText("Keine Programmpunkte.")).toBeInTheDocument();
  });

  it("surfaces a failing proposal lookup rather than swallowing it", async () => {
    server.use(
      http.get(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.get(api("/api/members/excursions/3/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/excursions/3/ljp-proposal"), () =>
        new HttpResponse(null, { status: 500 }),
      ),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
      http.get(api("/api/members/activity-categories"), () =>
        HttpResponse.json(ACTIVITY_CATEGORIES),
      ),
    );
    renderRoute("/kompass/excursions/3");
    // The page still renders; only the LJP section is missing its data.
    expect(await screen.findByText("Südtirol")).toBeInTheDocument();
  });
});

/** A complete StatementOut; the Abrechnung tab stays mounted on every tab. */
const FULL_STATEMENT = {
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

describe("activities — Ausfahrt Abrechnung: remaining paths", () => {
  it("edits every statement field on the excursion's own tab", async () => {
    detailReturns({ statement_id: 1 });
    server.use(
      http.get(api("/api/finance/statements/1"), () =>
        HttpResponse.json({
          ...FULL_STATEMENT,
          short_description: null,
          explanation: null,
          night_cost: null,
          subsidy_to: { id: 42, name: "Anna Ärmel" },
          ljp_to: { id: 42, name: "Anna Ärmel" },
          allowance_to: [{ id: 42, name: "Anna Ärmel" }],
        }),
      ),
    );
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_STATEMENT);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Abrechnung" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    // Clearing the optional recipient selects sends null, not 0.
    expect(patched).toMatchObject({ subsidy_to_id: null, ljp_to_id: null, night_cost: 3 });
  });

  it("names the statement after the excursion's code when it has no name", async () => {
    detailReturns({ name: "" });
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_STATEMENT);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));
    await user.click(await screen.findByRole("button", { name: "Abrechnung anlegen" }));
    await waitFor(() => expect(body).toMatchObject({ short_description: "F26-01" }));
  });

  it("shows an em dash for a statement with no recipients", async () => {
    detailReturns({ statement_id: 1 });
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(FULL_STATEMENT)),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("marks a confirmed statement as paid", async () => {
    detailReturns({ statement_id: 1 });
    server.use(
      http.get(api("/api/finance/statements/1"), () =>
        HttpResponse.json({
          ...FULL_STATEMENT,
          submitted: true,
          confirmed: true,
          status_display: "Bezahlt",
        }),
      ),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));
    expect(await screen.findByText("Bezahlt")).toBeInTheDocument();
  });
});

describe("activities — Ausfahrt Abrechnung", () => {
  const STATEMENT = FULL_STATEMENT;

  function withStatement(overrides: Record<string, unknown> = {}) {
    detailReturns({ statement_id: 1 });
    server.use(
      http.get(api("/api/finance/statements/1"), () =>
        HttpResponse.json({ ...STATEMENT, ...overrides }),
      ),
    );
  }

  it("offers to create a statement when there is none", async () => {
    detailReturns();
    let created = false;
    server.use(
      http.post(api("/api/finance/statements"), async ({ request }) => {
        const body = (await request.json()) as { excursion_id: number };
        expect(body.excursion_id).toBe(3);
        created = true;
        return HttpResponse.json(STATEMENT);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));

    expect(await screen.findByText("Diese Ausfahrt hat noch keine Abrechnung.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Abrechnung anlegen" }));
    await waitFor(() => expect(created).toBe(true));
    expect(await screen.findByText("Abrechnung angelegt.")).toBeInTheDocument();
  });

  it("reports a refused statement creation", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/finance/statements"), () =>
        HttpResponse.json({ detail: "finance.add_global_statement" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));
    await user.click(await screen.findByRole("button", { name: "Abrechnung anlegen" }));
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("links the statement and edits its recipients on the excursion's Save", async () => {
    withStatement();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/finance/statements/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(STATEMENT);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));

    expect(await screen.findByRole("link", { name: "F26-01 Skifreizeit" })).toHaveAttribute(
      "href",
      "/kompass/finance/statements/1",
    );

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Abrechnung" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getByRole("button", { name: "+ Auswählen…" }));
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      allowance_to_ids: [42],
      subsidy_to_id: null,
      ljp_to_id: null,
      night_cost: 11,
    });
  });

  it("freezes a submitted statement", async () => {
    withStatement({ submitted: true, status: 1, status_display: "Eingereicht" });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "Abrechnung" }));

    expect(
      await screen.findByText(
        "Die Abrechnung wurde eingereicht und kann nicht mehr geändert werden.",
      ),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Abrechnung" }));
    // No editable field appears even in edit mode.
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    expect(panel.querySelector("input")).toBeNull();
  });
});

describe("activities — Finanzübersicht", () => {
  const OVERVIEW = {
    statement_id: 1,
    excursion_name: "Skifreizeit",
    submitted: false,
    bills: [
      {
        short_description: "Verpflegung",
        explanation: "Einkauf",
        amount: 40,
        paid_by_name: "Anna Ärmel",
        paid_by_iban_valid: true,
      },
    ],
    total_bills_theoretic: 40,
    staff_count: 2,
    nights: 2,
    price_per_night: 11,
    nights_per_yl: 22,
    duration: 3,
    allowance_per_day: 10,
    allowance_per_yl: 30,
    kilometers_traveled: 420,
    means_of_transport: "Fahrgemeinschaften",
    euro_per_km: 0.3,
    transportation_per_yl: 126,
    allowances_paid: 60,
    real_staff_count: 2,
    allowance_to: [{ id: 42, name: "Anna Ärmel", iban_valid: true }],
    allowance_to_valid: true,
    subsidy_to: { id: 42, name: "Anna Ärmel", iban_valid: true },
    total_subsidies: 148,
    total_org_fee: 30,
    total_org_fee_theoretical: 30,
    org_fee: 5,
    old_participant_count: 2,
    ljp_to: { id: 42, name: "Anna Ärmel", iban_valid: true },
    ljp_contributions: 90,
    total_seminar_days: 3,
    ljp_participant_count: 8,
    theoretic_ljp_participant_count: 8,
    seminar_days: [{ day: "14.02.2026", total_duration: 6, sum_days: 1 }],
    total_relative_costs: -168,
  };

  function overviewReturns(overrides: Record<string, unknown> = {}) {
    detailReturns({ statement_id: 1 });
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(FULL_STATEMENT)),
      http.get(api("/api/finance/statements/1/overview"), () =>
        HttpResponse.json({ ...OVERVIEW, ...overrides }),
      ),
    );
  }

  it("estimates the costs and contributions", async () => {
    overviewReturns();
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Verpflegung")).toBeInTheDocument();
    expect(dialog.getByText(/Erwartete Gesamtausgaben/)).toBeInTheDocument();
    // Once as a heading, once as a row in the summary table.
    expect(dialog.getAllByText("Organisationspauschale")).toHaveLength(2);
    expect(dialog.getByText(/Dokumentierte 3 Seminartage/)).toBeInTheDocument();
    expect(dialog.getByText("Zusammenfassung")).toBeInTheDocument();
  });

  it("shows an em dash for a bill nobody paid in the overview", async () => {
    overviewReturns({
      bills: [
        {
          short_description: "Verpflegung",
          explanation: "",
          amount: 40,
          paid_by_name: null,
          paid_by_iban_valid: false,
        },
      ],
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getAllByText("—").length).toBeGreaterThan(0);
    // The IBAN column reads as a tick or a cross, never as true/false.
    expect(dialog.getAllByText("✗").length).toBeGreaterThan(0);
  });

  it("names the gaps when nobody is set to receive the money", async () => {
    overviewReturns({
      allowances_paid: 0,
      allowance_to: [],
      allowance_to_valid: false,
      subsidy_to: null,
      ljp_to: null,
      total_org_fee: 0,
      theoretic_ljp_participant_count: 3,
      seminar_days: [],
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(
      dialog.getByText("Keine Empfänger*innen der Aufwandsentschädigung."),
    ).toBeInTheDocument();
    expect(
      dialog.getByText(/Empfänger\*innen der Aufwandsentschädigung entsprechen nicht den/),
    ).toBeInTheDocument();
    expect(dialog.getByText("Keine Empfänger*in des Zuschusses.")).toBeInTheDocument();
    expect(dialog.getByText(/bislang keine\s+Empfänger\*in festgelegt/)).toBeInTheDocument();
    expect(dialog.getByText(/nur ab 5 Teilnehmenden möglich/)).toBeInTheDocument();
    // Only the summary row remains; the explanatory section is dropped.
    expect(dialog.getAllByText("Organisationspauschale")).toHaveLength(1);
  });

  it("submits the statement after asking, and then freezes it", async () => {
    overviewReturns();
    let submitted = false;
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () => {
        submitted = true;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Einreichen" }),
    );
    // The confirmation opens on top of the overview, so take the newest dialog.
    const confirmDialog = (await screen.findAllByRole("dialog")).slice(-1)[0];
    await user.click(within(confirmDialog).getByRole("button", { name: "Einreichen" }));

    await waitFor(() => expect(submitted).toBe(true));
    expect(await screen.findByText("Abrechnung eingereicht.")).toBeInTheDocument();
  });

  it("offers no submit for an already submitted statement, and closes", async () => {
    overviewReturns({ submitted: true });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.queryByRole("button", { name: "Einreichen" })).not.toBeInTheDocument();

    const closers = dialog.getAllByRole("button", { name: "Schließen" });
    await user.click(closers[closers.length - 1]);
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reports a refused submission", async () => {
    overviewReturns();
    server.use(
      http.post(api("/api/finance/statements/1/submit"), () =>
        HttpResponse.json({ detail: "Es fehlen Belege." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Finanzübersicht" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Einreichen" }),
    );
    const confirmDialog = (await screen.findAllByRole("dialog")).slice(-1)[0];
    await user.click(within(confirmDialog).getByRole("button", { name: "Einreichen" }));
    expect(await screen.findByText("Es fehlen Belege.")).toBeInTheDocument();
  });

  it("offers no finance overview without a statement", async () => {
    detailReturns();
    renderRoute("/kompass/excursions/3");
    await screen.findByText("Südtirol");
    expect(screen.queryByRole("button", { name: "Finanzübersicht" })).not.toBeInTheDocument();
  });
});

describe("activities — Ausfahrt: remaining paths", () => {
  it("opens an excursion from its row and closes the create modal with ×", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/kompass/excursions");

    await user.click(await screen.findByRole("button", { name: "Neue Ausfahrt" }));
    const dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText("Bis"), "2026-02-16T18:00");
    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Skifreizeit"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("passes an unparseable date through in the list", async () => {
    listReturns([{ ...BRIEF, date: "irgendwann" }]);
    renderRoute("/kompass/excursions");
    await screen.findByText("F26-01");
    expect(screen.getByText("irgendwann")).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    detailReturns({
      name: null,
      place: null,
      postcode: null,
      destination: null,
      description: null,
      date: null,
      end: null,
      kilometers_traveled: null,
      approval_comments: null,
      approved: null,
      difficulty_str: "",
      tour_type_str: "",
      tour_approach_str: "",
      approved_extra_youth_leader_count: null,
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("sends null for the optional text fields cleared during an edit", async () => {
    detailReturns({ postcode: "39030", description: "Drei Tage im Schnee." });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue("39030"));
    const description = screen
      .getAllByRole("textbox")
      .find((el) => (el as HTMLTextAreaElement).value === "Drei Tage im Schnee.");
    if (description) await user.clear(description);
    await user.click(screen.getByRole("tab", { name: "Genehmigung" }));
    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.type(panel.getAllByRole("textbox")[0], "x");
    await user.clear(panel.getAllByRole("textbox")[0]);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ postcode: null, description: null });
  });

  it("names a nameless excursion by its code when deleting", async () => {
    useMe({ permissions: ["members.delete_global_freizeit"] });
    detailReturns({ name: "" });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    expect(
      within(await screen.findByRole("dialog")).getByText(/„F26-01“ wirklich löschen\?/),
    ).toBeInTheDocument();
  });

  it("closes the schedule dialog with × and with Abbrechen", async () => {
    detailReturns({}, {
      id: 4,
      excursion_id: 3,
      title: "Sportklettern",
      category: 2,
      category_display: "",
      goal: 1,
      goal_display: "",
      not_bw_reason: null,
      not_bw_reason_display: null,
      goal_strategy: "",
      interventions: [],
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));

    await user.click(await screen.findByRole("button", { name: "+ Programmpunkt" }));
    let dialog = await screen.findByRole("dialog");
    await user.type(within(dialog).getByLabelText(/Dauer/), "2");
    await user.click(within(dialog).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "+ Programmpunkt" }));
    dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("edits a schedule entry's start and duration in the table", async () => {
    detailReturns({}, {
      id: 4,
      excursion_id: 3,
      title: "Sportklettern",
      category: 2,
      category_display: "",
      goal: 1,
      goal_display: "",
      not_bw_reason: null,
      not_bw_reason_display: null,
      goal_strategy: "",
      interventions: [
        { id: 7, date_start: "2026-02-14T09:00:00Z", duration: 2, activity: "Materialkunde" },
      ],
    });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), () => HttpResponse.json(EXCURSION)),
      http.patch(api("/api/members/ljp-proposals/4"), () => HttpResponse.json({ id: 4 })),
      http.patch(api("/api/members/interventions/7"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 7 });
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "LJP-Antrag" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    const start = panel.getByDisplayValue(/2026-02-14T/);
    await user.clear(start);
    await user.type(start, "2026-02-15T08:00");
    const duration = panel.getByDisplayValue("2");
    await user.clear(duration);
    await user.type(duration, "4");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ duration: "4" });
  });

  it("shows an em dash for a schedule entry with no start time", async () => {
    detailReturns({}, {
      id: 4,
      excursion_id: 3,
      title: "",
      category: 2,
      category_display: "",
      goal: 1,
      goal_display: "",
      not_bw_reason: null,
      not_bw_reason_display: null,
      goal_strategy: "",
      interventions: [{ id: 7, date_start: null, duration: 2, activity: "" }],
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("tab", { name: "LJP-Antrag" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });
});

describe("activities — Ausfahrt: every field", () => {
  const LJP_FULL = {
    id: 4,
    excursion_id: 3,
    title: "Sportklettern",
    category: 2,
    category_display: "Themenorientierte Bildungsmaßnahme",
    goal: 1,
    goal_display: "Qualifizierung",
    goal_strategy: "Übungen am Fels",
    not_bw_reason: 1,
    not_bw_reason_display: "aufgrund der Lehrgangsinhalte",
    interventions: [],
  };

  it("carries every edited field into the PATCH", async () => {
    detailReturns({}, LJP_FULL);
    let patched: Record<string, unknown> | null = null;
    let ljpPatched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/excursions/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(EXCURSION);
      }),
      http.patch(api("/api/members/ljp-proposals/4"), async ({ request }) => {
        ljpPatched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(LJP_FULL);
      }),
    );
    const { user } = renderRoute("/kompass/excursions/3");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    for (const tab of ["Allgemein", "Genehmigung", "LJP-Antrag"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await fillEveryField(user, panel);
      await pickEverySelect(user, panel);
    }
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      name: "Text",
      place: "Text",
      postcode: "Text",
      destination: "Text",
      description: "Text",
      kilometers_traveled: 3,
      approval_comments: "Text",
      approved_extra_youth_leader_count: 3,
    });
    await waitFor(() => expect(ljpPatched).not.toBeNull());
    expect(ljpPatched).toMatchObject({ title: "Text", goal_strategy: "Text" });
  });

  it("shows an em dash for every optional field left empty", async () => {
    detailReturns({
      name: "",
      place: "",
      postcode: "",
      destination: "",
      description: "",
      date: null,
      end: null,
      groups: [],
      jugendleiter: [],
      activity: [],
      kilometers_traveled: null,
      approval_comments: "",
      approved: null,
    });
    const { user } = renderRoute("/kompass/excursions/3");
    await screen.findByRole("button", { name: "Bearbeiten" });

    for (const tab of ["Allgemein", "Genehmigung"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      expect(panel.textContent).toContain("—");
    }
  });
});
