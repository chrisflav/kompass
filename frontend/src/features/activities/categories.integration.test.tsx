import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import {
  currentSearch,
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

/**
 * The tab you are actually looking at. Both panels of the Kategorien page stay
 * mounted (only the inactive one is `hidden`), so an assertion about "the list"
 * has to say which list, or it matches the one behind the tab too.
 */
const visiblePanel = () =>
  within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);

const ACTIVITY = {
  id: 1,
  name: "Klettern",
  ljp_category: "Klettern",
  ljp_category_display: "Klettern",
  description: "Am Fels und in der Halle",
};

const TRAINING_CAT = { id: 2, name: "Grundkurs", permission_needed: true };

/** Both lists load together, so a test that renders the page answers both. */
function categoriesReturn({
  activity = [ACTIVITY] as unknown[],
  training = [TRAINING_CAT] as unknown[],
} = {}) {
  server.use(
    http.get(api("/api/members/activity-categories"), () => HttpResponse.json(activity)),
    http.get(api("/api/members/training-categories"), () => HttpResponse.json(training)),
  );
}

/* --- Aktivitätskategorien ------------------------------------------------- */

describe("activities — Aktivitätskategorien", () => {
  function listReturns(rows: unknown[] = [ACTIVITY]) {
    categoriesReturn({ activity: rows, training: [] });
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/activity-categories/1"), () =>
        HttpResponse.json({ ...ACTIVITY, ...overrides }),
      ),
    );
  }

  it("lists the categories with their LJP mapping", async () => {
    listReturns();
    renderRoute("/kompass/categories");
    expect(await screen.findByText("Am Fels und in der Halle")).toBeInTheDocument();
    expect(screen.getByText("1 Aktivitätskategorien")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/kompass/categories");
    await waitFor(() => expect(visiblePanel().getByText("Keine Kategorien.")).toBeInTheDocument());
  });

  it("shows an em dash for a category without a description", async () => {
    listReturns([{ ...ACTIVITY, description: "", ljp_category: "", ljp_category_display: "" }]);
    renderRoute("/kompass/categories");
    await screen.findByText("Klettern");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/categories");
    await screen.findAllByText("Klettern");
    expect(screen.queryByRole("button", { name: "Neue Kategorie" })).not.toBeInTheDocument();
  });

  it("switches to the Ausbildungen tab and records it in the URL", async () => {
    categoriesReturn();
    const { user } = renderRoute("/kompass/categories");
    await screen.findByText("Am Fels und in der Halle");

    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    expect(visiblePanel().getByText("Grundkurs")).toBeInTheDocument();
    // The open tab is a bookmark, not just component state.
    expect(currentSearch()).toBe("?type=training");
  });

  it("creates a category with its LJP mapping", async () => {
    useMe({ permissions: ["members.add_activitycategory"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/members/activity-categories"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(ACTIVITY);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/categories");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Klettern");
    await user.click(dialog.getByRole("button", { name: "LJP-Kategorie" }));
    await user.click(dropdown().getByRole("button", { name: "Bergsteigen" }));
    await user.type(dialog.getByLabelText("Beschreibung"), "Am Fels");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      name: "Klettern",
      ljp_category: "Bergsteigen",
      description: "Am Fels",
    });
    expect(await screen.findByText("Kategorie angelegt.")).toBeInTheDocument();
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    useMe({ permissions: ["members.add_activitycategory"] });
    listReturns();
    server.use(
      http.post(api("/api/members/activity-categories"), () =>
        djangoValidation({
          name: ["Diese Kategorie gibt es schon."],
          ljp_category: ["Unbekannte LJP-Kategorie."],
          description: ["Zu lang."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/categories");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Klettern");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Diese Kategorie gibt es schon.")).not.toHaveLength(0);
    expect(screen.getByText("Unbekannte LJP-Kategorie.")).toBeInTheDocument();
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("fills every field of the create form", async () => {
    useMe({ permissions: ["members.add_activitycategory"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/activity-categories"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/kompass/categories");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ name: "Text", description: "Text", ljp_category: "Winter" });
  });

  it("carries every edited field into the PATCH", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/activity-categories/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(ACTIVITY);
      }),
    );
    const { user } = renderRoute("/kompass/categories/activity/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ name: "Text", description: "Text", ljp_category: "Winter" });
  });

  it("edits a category and reports a rejected save", async () => {
    detailReturns();
    let attempt = 0;
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/activity-categories/1"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ name: ["Der Name fehlt."] });
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(ACTIVITY);
      }),
    );
    const { user } = renderRoute("/kompass/categories/activity/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    const name = screen.getByDisplayValue("Klettern");
    await user.clear(name);
    await user.type(name, "Sportklettern");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ name: "Sportklettern" });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/categories/activity/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Klettern")).not.toBeInTheDocument();
  });

  it("deletes a category once confirmed, and reports a refusal", async () => {
    detailReturns();
    let attempt = 0;
    server.use(
      http.get(api("/api/members/activity-categories"), () => HttpResponse.json([])),
      http.delete(api("/api/members/activity-categories/1"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "Noch Ausfahrten zugeordnet." }, { status: 409 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/categories/activity/1");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Noch Ausfahrten zugeordnet.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Gelöscht.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/categories/activity/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Ausbildungskategorien ------------------------------------------------ */

describe("activities — Ausbildungskategorien", () => {
  function listReturns(rows: unknown[] = [TRAINING_CAT]) {
    categoriesReturn({ activity: [], training: rows });
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/training-categories/2"), () =>
        HttpResponse.json({ ...TRAINING_CAT, ...overrides }),
      ),
    );
  }

  it("marks which categories need a permission", async () => {
    listReturns([TRAINING_CAT, { id: 3, name: "Aufbaukurs", permission_needed: false }]);
    renderRoute("/kompass/categories?type=training");
    expect(await screen.findByText("Grundkurs")).toBeInTheDocument();
    expect(screen.getByText("Ja")).toBeInTheDocument();
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/kompass/categories?type=training");
    await waitFor(() => expect(visiblePanel().getByText("Keine Kategorien.")).toBeInTheDocument());
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/categories?type=training");
    await screen.findByText("Grundkurs");
    expect(screen.queryByRole("button", { name: "Neue Kategorie" })).not.toBeInTheDocument();
  });

  it("opens on the tab the URL names, and drops the param going back", async () => {
    categoriesReturn();
    const { user } = renderRoute("/kompass/categories?type=training");
    await waitFor(() => expect(visiblePanel().getByText("Grundkurs")).toBeInTheDocument());

    await user.click(screen.getByRole("tab", { name: "Aktivitäten" }));
    expect(visiblePanel().getByText("Am Fels und in der Halle")).toBeInTheDocument();
    // The default tab is the bare URL, so it never accumulates a redundant param.
    expect(currentSearch()).toBe("");
  });

  it("creates a category, carrying the permission flag", async () => {
    useMe({ permissions: ["members.add_trainingcategory"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/members/training-categories"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(TRAINING_CAT);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/categories?type=training");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Grundkurs");
    await user.click(dialog.getByLabelText("Berechtigung erforderlich"));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() =>
      expect(body).toEqual({ name: "Grundkurs", permission_needed: true }),
    );
    expect(await screen.findByText("Kategorie angelegt.")).toBeInTheDocument();
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    useMe({ permissions: ["members.add_trainingcategory"] });
    listReturns();
    server.use(
      http.post(api("/api/members/training-categories"), () =>
        djangoValidation({
          name: ["Diese Kategorie gibt es schon."],
          permission_needed: ["Ungültig."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/categories?type=training");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Grundkurs");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Diese Kategorie gibt es schon.")).not.toHaveLength(0);
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("edits a category and reports a rejected save", async () => {
    detailReturns();
    let attempt = 0;
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/training-categories/2"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ name: ["Der Name fehlt."] });
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRAINING_CAT);
      }),
    );
    const { user } = renderRoute("/kompass/categories/training/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ name: "Grundkurs", permission_needed: false });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/categories/training/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Grundkurs")).not.toBeInTheDocument();
  });

  it("deletes a category once confirmed, and reports a refusal", async () => {
    detailReturns();
    let attempt = 0;
    server.use(
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
      http.delete(api("/api/members/training-categories/2"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "Noch Ausbildungen zugeordnet." }, { status: 409 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/categories/training/2");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Noch Ausbildungen zugeordnet.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Gelöscht.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/categories/training/2");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Notizlisten ---------------------------------------------------------- */

const NOTELIST: Record<string, unknown> = { id: 8, title: "Gruppenabend", date: "2026-04-01" };

describe("activities — Notizlisten: remaining paths", () => {
  it("opens a note list from its row and closes the create modal with ×", async () => {
    server.use(
      http.get(api("/api/members/note-lists"), () => HttpResponse.json([NOTELIST])),
      http.get(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([{ id: 42, name: "Anna Ärmel" }])),
    );
    const { user } = renderRoute("/kompass/notelists");

    await user.click(await screen.findByRole("button", { name: "Neue Notizliste" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Gruppenabend"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("copes with a note list whose title and date are null", async () => {
    server.use(
      http.get(api("/api/members/note-lists/8"), () =>
        HttpResponse.json({ ...NOTELIST, title: null, date: null }),
      ),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("closes the participant dialog with ×", async () => {
    server.use(
      http.get(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([{ id: 42, name: "Anna Ärmel" }])),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Teilnehmende" }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reports a refused delete", async () => {
    useMe({ permissions: ["members.delete_membernotelist"] });
    server.use(
      http.get(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
      http.delete(api("/api/members/note-lists/8"), () =>
        HttpResponse.json({ detail: "members.delete_membernotelist" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("reports a rejected save whose body is not JSON", async () => {
    server.use(
      http.get(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
      http.patch(api("/api/members/note-lists/8"), () =>
        new HttpResponse("<html>500</html>", { status: 500 }),
      ),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });
});

describe("activities — Kategorien: remaining paths", () => {
  it("opens an activity category from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["members.add_activitycategory"] });
    server.use(
      http.get(api("/api/members/activity-categories"), () => HttpResponse.json([ACTIVITY])),
      http.get(api("/api/members/activity-categories/1"), () => HttpResponse.json(ACTIVITY)),
    );
    const { user } = renderRoute("/kompass/categories");

    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getAllByText("Klettern")[0]);
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("opens a training category from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["members.add_trainingcategory"] });
    server.use(
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([TRAINING_CAT])),
      http.get(api("/api/members/training-categories/2"), () => HttpResponse.json(TRAINING_CAT)),
    );
    const { user } = renderRoute("/kompass/categories?type=training");

    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Grundkurs"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("falls back to the raw LJP value when the API sends no label", async () => {
    server.use(
      http.get(api("/api/members/activity-categories/1"), () =>
        HttpResponse.json({ ...ACTIVITY, ljp_category_display: "" }),
      ),
    );
    renderRoute("/kompass/categories/activity/1");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("Klettern").length).toBeGreaterThan(0);
  });

  it("marks a training category that needs no permission", async () => {
    server.use(
      http.get(api("/api/members/training-categories/2"), () =>
        HttpResponse.json({ ...TRAINING_CAT, permission_needed: false }),
      ),
    );
    renderRoute("/kompass/categories/training/2");
    expect(await screen.findByText("Nein")).toBeInTheDocument();
  });

  it("copes with a category whose description is null", async () => {
    server.use(
      http.get(api("/api/members/activity-categories/1"), () =>
        HttpResponse.json({ ...ACTIVITY, description: null, ljp_category: null }),
      ),
    );
    const { user } = renderRoute("/kompass/categories/activity/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });
});

describe("activities — Notizlisten", () => {
  function listReturns(rows = [NOTELIST]) {
    server.use(http.get(api("/api/members/note-lists"), () => HttpResponse.json(rows)));
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/note-lists/8"), () =>
        HttpResponse.json({ ...NOTELIST, ...overrides }),
      ),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () =>
        HttpResponse.json([
          { id: 42, name: "Anna Ärmel" },
          { id: 43, name: "Mila Nowak" },
        ]),
      ),
    );
  }

  it("lists the note lists", async () => {
    listReturns();
    renderRoute("/kompass/notelists");
    expect(await screen.findByText("Gruppenabend")).toBeInTheDocument();
    expect(screen.getByText("1.4.2026")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/kompass/notelists");
    expect(await screen.findByText("Keine Notizlisten sichtbar.")).toBeInTheDocument();
  });

  it("shows an em dash for a list without a title", async () => {
    listReturns([{ ...NOTELIST, title: "", date: null }]);
    renderRoute("/kompass/notelists");
    expect((await screen.findAllByText("—")).length).toBeGreaterThan(0);
  });

  it("searches by title and passes an unparseable date through", async () => {
    listReturns([
      { ...NOTELIST, date: "irgendwann" },
      { id: 9, title: "Wochenende", date: null },
    ]);
    const { user } = renderRoute("/kompass/notelists");
    await screen.findByText("Gruppenabend");
    expect(screen.getByText("irgendwann")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Suchen…"), "wochen");
    await waitFor(() => expect(screen.queryByText("Gruppenabend")).not.toBeInTheDocument());
  });

  it("shows a rejected date on the create form", async () => {
    listReturns();
    server.use(
      http.post(api("/api/members/note-lists"), () =>
        djangoValidation({ date: ["Ungültiges Datum."] }),
      ),
    );
    const { user } = renderRoute("/kompass/notelists");
    await user.click(await screen.findByRole("button", { name: "Neue Notizliste" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Titel"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Ungültiges Datum.")).not.toHaveLength(0);
  });

  it("names an untitled note list when deleting it", async () => {
    useMe({ permissions: ["members.delete_membernotelist"] });
    server.use(
      http.get(api("/api/members/note-lists/8"), () =>
        HttpResponse.json({ ...NOTELIST, title: "" }),
      ),
      http.get(api("/api/members/note-lists/8/participants"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    expect(
      within(await screen.findByRole("dialog")).getByText(/„Notizliste“ wirklich löschen\?/),
    ).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([NOTELIST, { id: 9, title: "", date: null }]);
    const { user } = renderRoute("/kompass/notelists");
    await screen.findByText("Gruppenabend");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/notelists");
    await screen.findByText("Gruppenabend");
    expect(screen.queryByRole("button", { name: "Neue Notizliste" })).not.toBeInTheDocument();
  });

  it("creates a note list, sending an empty date as null", async () => {
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/members/note-lists"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(NOTELIST);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/kompass/notelists");
    await user.click(await screen.findByRole("button", { name: "Neue Notizliste" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Titel"), "Gruppenabend");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ title: "Gruppenabend", date: null }));
    expect(await screen.findByText("Notizliste angelegt.")).toBeInTheDocument();
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    listReturns();
    server.use(
      http.post(api("/api/members/note-lists"), () =>
        djangoValidation({ title: ["Der Titel fehlt."] }),
      ),
    );
    const { user } = renderRoute("/kompass/notelists");
    await user.click(await screen.findByRole("button", { name: "Neue Notizliste" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Titel"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("fills every field of the create form", async () => {
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/note-lists"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ title: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/kompass/notelists");
    await user.click(await screen.findByRole("button", { name: "Neue Notizliste" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ title: "Text", date: "2026-03-04" }));
  });

  it("edits a note list and reports a rejected save", async () => {
    detailReturns();
    let attempt = 0;
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/note-lists/8"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ title: ["Der Titel fehlt."] });
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(NOTELIST);
      }),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);

    const date = screen.getByDisplayValue("2026-04-01");
    await user.clear(date);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ title: "Gruppenabend", date: null });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Gruppenabend")).not.toBeInTheDocument();
  });

  it("stages a new participant and creates it on save", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.post(api("/api/members/note-lists/8/participants"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 20 });
      }),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Teilnehmende" }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.type(dialog.getByLabelText("Kommentar"), "kommt später");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    // Staged only.
    expect(created).toBeNull();
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).toEqual({ member_id: 42, comments: "kommt später" }));
  });

  it("edits an existing participant's comment on save", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/note-lists/8/participants"), () =>
        HttpResponse.json([
          { id: 20, member: { id: 42, name: "Anna Ärmel" }, comments: "kommt später" },
        ]),
      ),
      http.patch(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.patch(api("/api/members/participants/20"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 20 });
      }),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Teilnehmende" }));

    const comment = await screen.findByDisplayValue("kommt später");
    await user.clear(comment);
    await user.type(comment, "kommt pünktlich");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).toEqual({ comments: "kommt pünktlich" }));
  });

  it("removes a participant on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/note-lists/8/participants"), () =>
        HttpResponse.json([
          { id: 20, member: { id: 42, name: "Anna Ärmel" }, comments: "" },
        ]),
      ),
      http.patch(api("/api/members/note-lists/8"), () => HttpResponse.json(NOTELIST)),
      http.delete(api("/api/members/participants/20"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Teilnehmende" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("shows the participants read-only outside edit mode", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/note-lists/8/participants"), () =>
        HttpResponse.json([{ id: 20, member: { id: 42, name: "Anna Ärmel" }, comments: null }]),
      ),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("tab", { name: "Teilnehmende" }));

    expect(await screen.findByText("Anna Ärmel")).toBeInTheDocument();
    // A missing comment reads as an em dash, not as a blank cell.
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("closes the participant dialog on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Teilnehmende" }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("deletes a note list once confirmed", async () => {
    useMe({ permissions: ["members.delete_membernotelist"] });
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/note-lists"), () => HttpResponse.json([])),
      http.delete(api("/api/members/note-lists/8"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Notizliste gelöscht.")).toBeInTheDocument();
  });

  it("hides the delete button without the permission", async () => {
    useMe({ permissions: [] });
    detailReturns();
    renderRoute("/kompass/notelists/8");
    await screen.findAllByText("Gruppenabend");
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/notelists/8");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});
