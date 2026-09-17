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

const TERMIN_BRIEF = {
  id: 6,
  title: "Klettersteig Allgäu",
  start_date: "2026-07-04",
  end_date: "2026-07-05",
  group: "JUG",
  group_display: "Jugend",
  category: "KST",
  category_display: "Klettersteig",
  responsible: "Ingo Iller",
};

const TERMIN = {
  ...TERMIN_BRIEF,
  subtitle: "für Fortgeschrittene",
  phone: "0711 5",
  email: "ingo@example.org",
  condition: "mittel",
  technik: "mittel",
  saison: "Sommer",
  eventart: "Wochenendevent",
  klassifizierung: "Gemeinschaftstour",
  equipment: "Klettersteigset",
  voraussetzungen: "Trittsicherheit",
  description: "Zwei Tage am Fels.",
  max_participants: 8,
  anforderung_hoehe: 1200,
  anforderung_strecke: 14,
  anforderung_dauer: 6,
};

function listReturns(rows = [TERMIN_BRIEF]) {
  server.use(http.get(api("/api/ludwigsburgalpin/termine"), () => HttpResponse.json(rows)));
}

function detailReturns(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get(api("/api/ludwigsburgalpin/termine/6"), () =>
      HttpResponse.json({ ...TERMIN, ...overrides }),
    ),
  );
}

/** Fill the required fields of the Termin form inside `scope`. */
async function fillRequired(
  user: ReturnType<typeof renderRoute>["user"],
  scope: ReturnType<typeof within>,
) {
  await user.type(scope.getByLabelText("Titel"), "Klettersteig Allgäu");
  await user.type(scope.getByLabelText("Von"), "2026-07-04");
  await user.type(scope.getByLabelText("Bis"), "2026-07-05");
  await user.type(scope.getByLabelText("Organisator:in"), "Ingo Iller");
  await user.type(scope.getByLabelText("E-Mail"), "ingo@example.org");
}

describe("events — Termine list", () => {
  it("lists the dates with their group and category", async () => {
    listReturns();
    renderRoute("/kompass/events");
    expect(await screen.findByText("Klettersteig Allgäu")).toBeInTheDocument();
    expect(screen.getByText("Jugend")).toBeInTheDocument();
    expect(screen.getByText("Klettersteig")).toBeInTheDocument();
    expect(screen.getByText("4.7.2026")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/kompass/events");
    expect(await screen.findByText("Keine Termine vorhanden.")).toBeInTheDocument();
  });

  it("opens a date from its row", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/kompass/events");
    await user.click(await screen.findByText("Klettersteig Allgäu"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("shows an em dash for a date without an organiser", async () => {
    listReturns([{ ...TERMIN_BRIEF, responsible: "" }]);
    renderRoute("/kompass/events");
    await screen.findByText("Klettersteig Allgäu");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("filters by group", async () => {
    listReturns([
      TERMIN_BRIEF,
      {
        ...TERMIN_BRIEF,
        id: 7,
        title: "Familienwanderung",
        group: "FAM",
        group_display: "Familie",
      },
    ]);
    const { user } = renderRoute("/kompass/events");
    await screen.findByText("Klettersteig Allgäu");

    await user.click(screen.getByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: "Familie" }));

    await waitFor(() =>
      expect(screen.queryByText("Klettersteig Allgäu")).not.toBeInTheDocument(),
    );
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([TERMIN_BRIEF, { ...TERMIN_BRIEF, id: 7, title: "Zweiter", responsible: "" }]);
    const { user } = renderRoute("/kompass/events");
    await screen.findByText("Klettersteig Allgäu");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the export and create actions without the permissions", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/events");
    await screen.findByText("Klettersteig Allgäu");
    expect(screen.queryByRole("button", { name: /Übersicht \(Excel\)/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neuer Termin" })).not.toBeInTheDocument();
  });

  it("exports the overview as a spreadsheet", async () => {
    useMe({ permissions: ["ludwigsburgalpin.view_termin"] });
    listReturns();
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

    let body: unknown = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/documents/termine/overview"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/kompass/events");
    await user.click(await screen.findByRole("button", { name: /Übersicht \(Excel\)/ }));
    // `null` means "every visible Termin", not a selection.
    await waitFor(() => expect(body).toEqual({ termin_ids: null }));
  });

  it("creates a date with its text and numeric fields", async () => {
    useMe({ permissions: ["ludwigsburgalpin.add_termin"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/termine"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TERMIN);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/events");
    await user.click(await screen.findByRole("button", { name: "Neuer Termin" }));

    const dialog = within(await screen.findByRole("dialog"));
    await fillRequired(user, dialog);
    await user.type(dialog.getByLabelText("Untertitel"), "für Fortgeschrittene");
    await user.type(dialog.getByLabelText("Telefonnummer"), "0711 5");
    await user.type(dialog.getByLabelText("Ausrüstung"), "Klettersteigset");
    await user.type(dialog.getByLabelText("Voraussetzungen"), "Trittsicherheit");
    await user.type(dialog.getByLabelText("Beschreibung"), "Zwei Tage am Fels.");
    await user.clear(dialog.getByLabelText("Max. Teilnehmerzahl"));
    await user.type(dialog.getByLabelText("Max. Teilnehmerzahl"), "8");
    await user.clear(dialog.getByLabelText(/Höhenmeter/));
    await user.type(dialog.getByLabelText(/Höhenmeter/), "1200");
    await user.clear(dialog.getByLabelText(/Strecke/));
    await user.type(dialog.getByLabelText(/Strecke/), "14");
    await user.clear(dialog.getByLabelText(/Etappendauer/));
    await user.type(dialog.getByLabelText(/Etappendauer/), "6");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      title: "Klettersteig Allgäu",
      subtitle: "für Fortgeschrittene",
      start_date: "2026-07-04",
      end_date: "2026-07-05",
      responsible: "Ingo Iller",
      phone: "0711 5",
      email: "ingo@example.org",
      equipment: "Klettersteigset",
      voraussetzungen: "Trittsicherheit",
      description: "Zwei Tage am Fels.",
      max_participants: 8,
      anforderung_hoehe: 1200,
      anforderung_strecke: 14,
      anforderung_dauer: 6,
      // Untouched selects keep the model's defaults.
      group: "ASG",
      category: "SON",
    });
    expect(await screen.findByText("Termin angelegt.")).toBeInTheDocument();
  });

  it("sends the code, not the label, for every choice field", async () => {
    useMe({ permissions: ["ludwigsburgalpin.add_termin"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/termine"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TERMIN);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/events");
    await user.click(await screen.findByRole("button", { name: "Neuer Termin" }));

    const dialog = within(await screen.findByRole("dialog"));
    await fillRequired(user, dialog);

    const pick = async (field: string, option: string) => {
      await user.click(dialog.getByRole("button", { name: field }));
      await user.click(dropdown().getByRole("button", { name: option }));
    };
    await pick("Gruppe", "Jugend");
    await pick("Kategorie", "Klettersteig");
    await pick("Kondition", "groß");
    await pick("Technik", "schwer");
    await pick("Saison", "Sommer");
    await pick("Eventart", "Wochenendevent");
    await pick("Klassifizierung", "Ausbildung");

    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      group: "JUG",
      category: "KST",
      condition: "groß",
      technik: "schwer",
      saison: "Sommer",
      eventart: "Wochenendevent",
      klassifizierung: "Ausbildung",
    });
  });

  it("shows every server field error on the create form", async () => {
    useMe({ permissions: ["ludwigsburgalpin.add_termin"] });
    listReturns();
    server.use(
      http.post(api("/api/ludwigsburgalpin/termine"), () =>
        djangoValidation({
          title: ["Der Titel fehlt."],
          subtitle: ["Zu lang."],
          start_date: ["Ungültig."],
          end_date: ["Liegt vor dem Start."],
          group: ["Unbekannte Gruppe."],
          responsible: ["Pflichtfeld."],
          phone: ["Keine Nummer."],
          email: ["Keine Adresse."],
          category: ["Unbekannt."],
          condition: ["Unbekannt."],
          technik: ["Unbekannt."],
          saison: ["Unbekannt."],
          eventart: ["Unbekannt."],
          klassifizierung: ["Unbekannt."],
          equipment: ["Zu lang."],
          voraussetzungen: ["Zu lang."],
          description: ["Zu lang."],
          max_participants: ["Muss positiv sein."],
          anforderung_hoehe: ["Muss positiv sein."],
          anforderung_strecke: ["Muss positiv sein."],
          anforderung_dauer: ["Muss positiv sein."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/events");
    await user.click(await screen.findByRole("button", { name: "Neuer Termin" }));

    const dialog = within(screen.getByRole("dialog"));
    await fillRequired(user, dialog);
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Liegt vor dem Start.")).toBeInTheDocument();
    expect(screen.getByText("Keine Adresse.")).toBeInTheDocument();
    expect(screen.getAllByText("Unbekannt.")).toHaveLength(6);
    expect(screen.getAllByText("Muss positiv sein.")).toHaveLength(4);
    expect(screen.getAllByText("Zu lang.")).toHaveLength(4);
  });

  it("closes the create modal on Abbrechen and on ×", async () => {
    useMe({ permissions: ["ludwigsburgalpin.add_termin"] });
    listReturns();
    const { user } = renderRoute("/kompass/events");

    await user.click(await screen.findByRole("button", { name: "Neuer Termin" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Neuer Termin" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("events — Termin detail", () => {
  it("shows the date across its three tabs", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/events/6");

    expect(await screen.findAllByText("Klettersteig Allgäu")).toHaveLength(2);
    expect(screen.getByText("Ingo Iller")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Anforderungen" }));
    expect(screen.getByText("1200")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Beschreibung" }));
    expect(screen.getByText("Zwei Tage am Fels.")).toBeInTheDocument();
  });

  it("copes with the optional fields being empty", async () => {
    detailReturns({
      subtitle: null,
      phone: null,
      equipment: null,
      voraussetzungen: null,
      description: null,
      anforderung_hoehe: null,
      anforderung_strecke: null,
      anforderung_dauer: null,
    });
    renderRoute("/kompass/events/6");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("saves an inline edit with numbers and choices", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/ludwigsburgalpin/termine/6"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TERMIN);
      }),
    );
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const title = screen.getByDisplayValue("Klettersteig Allgäu");
    await user.clear(title);
    await user.type(title, "Klettersteig Karwendel");

    await user.click(screen.getByRole("tab", { name: "Anforderungen" }));
    const hoehe = screen.getByDisplayValue("1200");
    await user.clear(hoehe);
    await user.type(hoehe, "1400");

    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      title: "Klettersteig Karwendel",
      anforderung_hoehe: 1400,
      group: "JUG",
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save without leaving edit mode", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/ludwigsburgalpin/termine/6"), () =>
        djangoValidation({ end_date: ["Liegt vor dem Start."] }),
      ),
    );
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Liegt vor dem Start.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Klettersteig Allgäu")).not.toBeInTheDocument();
  });

  it("deletes a date once confirmed, and does nothing when cancelled", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/ludwigsburgalpin/termine"), () => HttpResponse.json([])),
      http.delete(api("/api/ludwigsburgalpin/termine/6"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/events/6");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText("Diesen Termin wirklich löschen?")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Termin gelöscht.")).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/ludwigsburgalpin/termine/6"), () =>
        HttpResponse.json({ detail: "ludwigsburgalpin.delete_termin" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("events — every detail field", () => {
  it("carries every edited field into the PATCH", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/ludwigsburgalpin/termine/6"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TERMIN);
      }),
    );
    const { user } = renderRoute("/kompass/events/6");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    for (const tab of ["Allgemein", "Anforderungen", "Beschreibung"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await fillEveryField(user, panel);
      await pickEverySelect(user, panel);
    }
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      title: "Text",
      subtitle: "Text",
      responsible: "Text",
      phone: "Text",
      email: "test@example.org",
      equipment: "Text",
      voraussetzungen: "Text",
      description: "Text",
      start_date: "2026-03-04",
      end_date: "2026-03-04",
      max_participants: 3,
      anforderung_hoehe: 3,
      anforderung_strecke: 3,
      anforderung_dauer: 3,
      // Each select resolved to its first option's code.
      group: "ASG",
      category: "WAN",
      condition: "gering",
      technik: "leicht",
      saison: "ganzjährig",
      eventart: "Einzeltermin",
      klassifizierung: "Gemeinschaftstour",
    });
  });
});
