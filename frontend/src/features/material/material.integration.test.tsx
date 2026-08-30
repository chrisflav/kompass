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

const CATEGORIES = [
  { id: 1, name: "Seile" },
  { id: 2, name: "Gurte" },
];

/* --- Materialkategorien --------------------------------------------------- */

describe("material — Kategorien", () => {
  function listReturns(rows = CATEGORIES) {
    server.use(http.get(api("/api/material/categories"), () => HttpResponse.json(rows)));
  }

  it("lists the categories", async () => {
    listReturns();
    renderRoute("/app/material/categories");
    expect(await screen.findByText("Seile")).toBeInTheDocument();
    expect(screen.getByText("2 / 2")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/material/categories");
    expect(await screen.findByText("Keine Kategorien vorhanden.")).toBeInTheDocument();
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/material/categories");
    await screen.findByText("Seile");
    expect(screen.queryByRole("button", { name: "Neue Kategorie" })).not.toBeInTheDocument();
  });

  it("creates a category and opens it", async () => {
    useMe({ permissions: ["material.add_materialcategory"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/material/categories"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 3, name: "Karabiner", material_parts: [] });
      }),
      http.get(api("/api/material/categories/3"), () =>
        HttpResponse.json({ id: 3, name: "Karabiner", material_parts: [] }),
      ),
    );
    const { user } = renderRoute("/app/material/categories");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Karabiner");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ name: "Karabiner" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("shows a rejected create on the form and closes on Abbrechen", async () => {
    useMe({ permissions: ["material.add_materialcategory"] });
    listReturns();
    server.use(
      http.post(api("/api/material/categories"), () =>
        djangoValidation({ name: ["Diese Kategorie gibt es schon."] }),
      ),
    );
    const { user } = renderRoute("/app/material/categories");
    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Seile");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Diese Kategorie gibt es schon.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("lists the category's material and opens a part from it", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({
          id: 1,
          name: "Seile",
          material_parts: [{ id: 4, name: "Halbseil 60m" }],
        }),
      ),
    );
    renderRoute("/app/material/categories/1");
    expect(await screen.findByText("Halbseil 60m")).toBeInTheDocument();
  });

  it("opens a part from the category's own list", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({
          id: 1,
          name: "Seile",
          material_parts: [{ id: 4, name: "Halbseil 60m" }],
        }),
      ),
      http.get(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
      http.get(api("/api/material/ownerships"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/material/categories/1");
    await user.click(await screen.findByText("Halbseil 60m"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("says so when the category holds no material", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
    );
    renderRoute("/app/material/categories/1");
    expect(await screen.findByText("Kein Material in dieser Kategorie.")).toBeInTheDocument();
  });

  it("edits a category, and keeps edit mode when the save is rejected", async () => {
    let put: unknown = null;
    let attempt = 0;
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
      http.put(api("/api/material/categories/1"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ name: ["Name fehlt."] });
        put = await request.json();
        return HttpResponse.json({ id: 1, name: "Seile & Reepschnüre", material_parts: [] });
      }),
    );
    const { user } = renderRoute("/app/material/categories/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Name fehlt.")).not.toHaveLength(0);

    const name = screen.getByDisplayValue("Seile");
    await user.clear(name);
    await user.type(name, "Seile & Reepschnüre");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(put).toEqual({ name: "Seile & Reepschnüre" }));
  });

  it("leaves edit mode on Abbrechen", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
    );
    const { user } = renderRoute("/app/material/categories/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Seile")).not.toBeInTheDocument();
  });

  it("deletes a category once confirmed, and reports a refusal", async () => {
    let attempt = 0;
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
      http.get(api("/api/material/categories"), () => HttpResponse.json([])),
      http.delete(api("/api/material/categories/1"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "Noch Material zugeordnet." }, { status: 409 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/material/categories/1");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Noch Material zugeordnet.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Kategorie gelöscht.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
    );
    const { user } = renderRoute("/app/material/categories/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Material ------------------------------------------------------------- */

const PART_BRIEF = {
  id: 4,
  name: "Halbseil 60m",
  description: "Rot",
  quantity: 2,
  quantity_real: "2 / 2",
  buy_date: "2024-03-01",
  lifetime: "10.0",
  not_too_old: true,
  owners: [{ owner_name: "Mila Nowak", count: 2 }],
};

const PART = {
  id: 4,
  name: "Halbseil 60m",
  description: "Rot",
  quantity: 2,
  quantity_real: "2 / 2",
  buy_date: "2024-03-01",
  lifetime: "10.0",
  not_too_old: true,
  owners: [{ owner_name: "Mila Nowak", count: 2 }],
  categories: [{ id: 1, name: "Seile" }],
  photo: null,
};

describe("material — Material", () => {
  function listReturns(rows = [PART_BRIEF]) {
    server.use(
      http.get(api("/api/material/parts"), () => HttpResponse.json(rows)),
      http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/material/parts/4"), () => HttpResponse.json({ ...PART, ...overrides })),
      http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
      http.get(api("/api/material/ownerships"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () =>
        HttpResponse.json([
          { id: 7, name: "Hannah Beckers" },
          { id: 9, name: "Tobias Werner" },
        ]),
      ),
    );
  }

  it("lists the parts with their owners and condition", async () => {
    listReturns();
    renderRoute("/app/material");
    expect(await screen.findByText("Halbseil 60m")).toBeInTheDocument();
    expect(screen.getByText("In Ordnung")).toBeInTheDocument();
    expect(screen.getByText(/Mila Nowak/)).toBeInTheDocument();
  });

  it("says so when there is none", async () => {
    listReturns([]);
    renderRoute("/app/material");
    expect(await screen.findByText("Kein Material vorhanden.")).toBeInTheDocument();
  });

  it("searches by name and description", async () => {
    listReturns([PART_BRIEF, { ...PART_BRIEF, id: 5, name: "Klettergurt", description: "Blau" }]);
    const { user } = renderRoute("/app/material");
    await screen.findByText("Halbseil 60m");
    await user.type(screen.getByPlaceholderText("Suchen…"), "blau");
    await waitFor(() => expect(screen.queryByText("Halbseil 60m")).not.toBeInTheDocument());
    expect(screen.getByText("Klettergurt")).toBeInTheDocument();
  });

  it("filters by condition and by owner", async () => {
    listReturns([
      PART_BRIEF,
      {
        ...PART_BRIEF,
        id: 5,
        name: "Altes Seil",
        not_too_old: false,
        owners: [{ owner_name: "Tobias Werner", count: 1 }],
      },
    ]);
    const { user } = renderRoute("/app/material");
    await screen.findByText("Halbseil 60m");

    await user.click(screen.getByRole("button", { name: /Zustand:/ }));
    await user.click(dropdown().getByRole("button", { name: "Zu alt" }));
    await waitFor(() => expect(screen.queryByText("Halbseil 60m")).not.toBeInTheDocument());
    expect(screen.getByText("Altes Seil")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(screen.getByRole("button", { name: /Besitzer:/ }));
    await user.click(dropdown().getByRole("button", { name: "Tobias Werner" }));
    await waitFor(() => expect(screen.queryByText("Halbseil 60m")).not.toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([
      PART_BRIEF,
      { ...PART_BRIEF, id: 5, name: "Klettergurt", description: "", owners: [] },
    ]);
    const { user } = renderRoute("/app/material");
    await screen.findByText("Halbseil 60m");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/material");
    await screen.findByText("Halbseil 60m");
    expect(screen.queryByRole("button", { name: "Neues Material" })).not.toBeInTheDocument();
  });

  it("creates a part as multipart, with its categories and photo", async () => {
    useMe({ permissions: ["material.add_materialpart"] });
    listReturns();
    let fields: Record<string, string> = {};
    let files: string[] = [];
    server.use(
      http.post(api("/api/material/parts"), async ({ request }) => {
        const clone = request.clone();
        files = await multipartFilenames(request);
        fields = await multipartFields(clone);
        return HttpResponse.json(PART);
      }),
      http.get(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.get(api("/api/material/ownerships"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/material");
    await user.click(await screen.findByRole("button", { name: "Neues Material" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Halbseil 60m");
    await user.type(dialog.getByLabelText("Beschreibung"), "Rot");
    await user.clear(dialog.getByLabelText("Anzahl"));
    await user.type(dialog.getByLabelText("Anzahl"), "2");
    await user.type(dialog.getByLabelText("Kaufdatum"), "2024-03-01");
    await user.clear(dialog.getByLabelText(/Lebenszeit/));
    await user.type(dialog.getByLabelText(/Lebenszeit/), "10");
    await user.click(dialog.getByRole("button", { name: "Kategorien" }));
    await user.click(dropdown().getByRole("button", { name: "Seile" }));
    await user.upload(
      dialog.getByLabelText(/Foto/),
      new File(["x"], "seil.png", { type: "image/png" }),
    );
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(files).toEqual(["seil.png"]));
    expect(fields).toMatchObject({
      name: "Halbseil 60m",
      description: "Rot",
      quantity: "2",
      buy_date: "2024-03-01",
      lifetime: "10",
      material_cat: "1",
    });
    expect(await screen.findByText("Material angelegt.")).toBeInTheDocument();
  });

  it("creates a part without a photo", async () => {
    useMe({ permissions: ["material.add_materialpart"] });
    listReturns();
    let files: string[] = ["unset"];
    server.use(
      http.post(api("/api/material/parts"), async ({ request }) => {
        files = await multipartFilenames(request);
        return HttpResponse.json(PART);
      }),
      http.get(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.get(api("/api/material/ownerships"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/material");
    await user.click(await screen.findByRole("button", { name: "Neues Material" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "Seil");
    await user.type(dialog.getByLabelText("Kaufdatum"), "2024-03-01");
    await user.type(dialog.getByLabelText(/Lebenszeit/), "10");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(files).toEqual([]));
  });

  it("shows server field errors on the create form and closes on Abbrechen", async () => {
    useMe({ permissions: ["material.add_materialpart"] });
    listReturns();
    server.use(
      http.post(api("/api/material/parts"), () =>
        djangoValidation({
          name: ["Der Name fehlt."],
          description: ["Zu lang."],
          quantity: ["Muss positiv sein."],
          buy_date: ["Ungültiges Datum."],
          lifetime: ["Ungültig."],
          material_cat: ["Unbekannte Kategorie."],
        }),
      ),
    );
    const { user } = renderRoute("/app/material");
    await user.click(await screen.findByRole("button", { name: "Neues Material" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Name"), "x");
    await user.type(dialog.getByLabelText("Kaufdatum"), "2024-03-01");
    await user.type(dialog.getByLabelText(/Lebenszeit/), "10");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Zu lang.")).toBeInTheDocument();
    expect(screen.getByText("Muss positiv sein.")).toBeInTheDocument();
    expect(screen.getByText("Ungültiges Datum.")).toBeInTheDocument();
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();
    expect(screen.getByText("Unbekannte Kategorie.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows the part with its categories and condition", async () => {
    detailReturns();
    renderRoute("/app/material/4");
    // The name appears in the breadcrumb and in the Name row.
    expect(await screen.findAllByText("Halbseil 60m")).toHaveLength(2);
    expect(screen.getByText("Seile")).toBeInTheDocument();
    expect(screen.getByText("In Ordnung")).toBeInTheDocument();
    expect(screen.getByText("Kein Foto hinterlegt.")).toBeInTheDocument();
  });

  it("marks an expired part as too old", async () => {
    detailReturns({ not_too_old: false });
    renderRoute("/app/material/4");
    expect(await screen.findByText("Zu alt")).toBeInTheDocument();
  });

  it("links an existing photo", async () => {
    detailReturns({ photo: "/media/seil.png" });
    renderRoute("/app/material/4");
    expect(await screen.findByRole("link", { name: "Foto ansehen" })).toHaveAttribute(
      "href",
      "http://localhost:8000/media/seil.png",
    );
    expect(screen.getByRole("link", { name: "Aktuelles Foto ansehen" })).toBeInTheDocument();
  });

  it("saves an inline edit as JSON, without the photo", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/material/parts/4"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(PART);
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const name = screen.getByDisplayValue("Halbseil 60m");
    await user.clear(name);
    await user.type(name, "Halbseil 70m");
    await user.click(screen.getByRole("button", { name: "+ Kategorie hinzufügen" }));
    await user.click(dropdown().getByRole("button", { name: "Gurte" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ name: "Halbseil 70m", material_cat: [1, 2] });
    expect(patched).not.toHaveProperty("photo");
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save without leaving edit mode", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/material/parts/4"), () =>
        djangoValidation({ name: ["Der Name fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Halbseil 60m")).not.toBeInTheDocument();
  });

  it("uploads a photo through its own endpoint as soon as one is picked", async () => {
    detailReturns();
    let uploaded: string | undefined;
    server.use(
      http.post(api("/api/material/parts/4/photo"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ ...PART, photo: "/media/seil.png" });
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "seil.png", { type: "image/png" }),
    );
    await waitFor(() => expect(uploaded).toBe("seil.png"));
    expect(await screen.findByText("Foto gespeichert.")).toBeInTheDocument();
  });

  it("reports a refused photo upload", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/material/parts/4/photo"), () =>
        HttpResponse.json({ detail: "Die Datei ist zu groß." }, { status: 413 }),
      ),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.upload(
      document.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "gross.png", { type: "image/png" }),
    );
    expect(await screen.findByText("Die Datei ist zu groß.")).toBeInTheDocument();
  });

  it("stages a new responsible person and creates it on save", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.post(api("/api/material/ownerships"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 30 });
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Verantwortliche" }));

    expect(await screen.findByText("Keine Verantwortlichen eingetragen.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "+ Verantwortliche:r" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: "Besitzer" }));
    await user.click(dropdown().getByRole("button", { name: "Tobias Werner" }));
    await user.clear(dialog.getByLabelText("Anzahl"));
    await user.type(dialog.getByLabelText("Anzahl"), "3");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    expect(created).toBeNull();
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toEqual({ material: 4, owner: 9, count: 3 });
  });

  it("edits and removes an existing responsible person on save", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.get(api("/api/material/ownerships"), () =>
        HttpResponse.json([
          { id: 30, material: { id: 4 }, owner: { id: 11, name: "Mila Nowak" }, count: 2 },
          { id: 31, material: { id: 99 }, owner: { id: 9, name: "Fremd" }, count: 1 },
        ]),
      ),
      http.patch(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.patch(api("/api/material/ownerships/30"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 30 });
      }),
      http.delete(api("/api/material/ownerships/30"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Verantwortliche" }));

    // Only this part's ownership is listed.
    expect(await screen.findByText("Mila Nowak")).toBeInTheDocument();
    expect(screen.queryByText("Fremd")).not.toBeInTheDocument();

    // The part's own "Anzahl" field also holds 2; take the inline table's.
    const count = within(screen.getByRole("table")).getByDisplayValue("2");
    await user.clear(count);
    await user.type(count, "5");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toEqual({ count: 5 }));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Verantwortliche" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("reports a failed inline flush without losing the drafts", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/material/parts/4"), () => HttpResponse.json(PART)),
      http.post(api("/api/material/ownerships"), () =>
        djangoValidation({ count: ["Mehr als vorhanden."] }),
      ),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Verantwortliche" }));
    await user.click(await screen.findByRole("button", { name: "+ Verantwortliche:r" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Besitzer" }));
    await user.click(dropdown().getByRole("button", { name: "Hannah Beckers" }));
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(
      await screen.findByText(/Ein verknüpfter Eintrag konnte nicht gespeichert werden/),
    ).toBeInTheDocument();
    // Still in edit mode with the staged row intact.
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("deletes a part once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/material/parts"), () => HttpResponse.json([])),
      http.delete(api("/api/material/parts/4"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Material gelöscht.")).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/material/parts/4"), () =>
        HttpResponse.json({ detail: "material.delete_materialpart" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

/** Stub the part list and detail for the exhaustive passes below. */
function partListReturns(rows: unknown[] = [PART_BRIEF]) {
  server.use(
    http.get(api("/api/material/parts"), () => HttpResponse.json(rows)),
    http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
  );
}

function partDetailReturns(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get(api("/api/material/parts/4"), () => HttpResponse.json({ ...PART, ...overrides })),
    http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
    http.get(api("/api/material/ownerships"), () => HttpResponse.json([])),
    http.get(api("/api/members/"), () =>
      HttpResponse.json([
        { id: 7, name: "Hannah Beckers" },
        { id: 9, name: "Tobias Werner" },
      ]),
    ),
  );
}

describe("material — remaining paths", () => {
  it("opens a part from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["material.add_materialpart"] });
    partListReturns();
    partDetailReturns();
    const { user } = renderRoute("/app/material");

    await user.click(await screen.findByRole("button", { name: "Neues Material" }));
    const dialog = await screen.findByRole("dialog");
    const file = within(dialog).getByLabelText(/Foto/);
    await user.upload(file, new File(["x"], "p.png", { type: "image/png" }));
    await user.upload(file, []);
    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Halbseil 60m"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("copes with an API that sends null for the optional fields", async () => {
    partDetailReturns({ description: null, buy_date: null, lifetime: null, categories: [] });
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("closes the responsible-person dialog with ×", async () => {
    partDetailReturns();
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Verantwortliche" }));
    await user.click(await screen.findByRole("button", { name: "+ Verantwortliche:r" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows an em dash for a responsible person with no name", async () => {
    partDetailReturns();
    server.use(
      http.get(api("/api/material/ownerships"), () =>
        HttpResponse.json([
          { id: 30, material: { id: 4 }, owner: { id: 11, name: "" }, count: 1 },
        ]),
      ),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("tab", { name: "Verantwortliche" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("opens a category from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["material.add_materialcategory"] });
    server.use(
      http.get(api("/api/material/categories"), () => HttpResponse.json(CATEGORIES)),
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
    );
    const { user } = renderRoute("/app/material/categories");

    await user.click(await screen.findByRole("button", { name: "Neue Kategorie" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Seile"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });
});

describe("material — every field", () => {
  it("Material: carries every edited field into the PATCH", async () => {
    partDetailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/material/parts/4"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(PART);
      }),
    );
    const { user } = renderRoute("/app/material/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      name: "Text",
      description: "Text",
      quantity: 3,
      buy_date: "2026-03-04",
      lifetime: "3",
    });
  });

  it("Material: shows an em dash for the optional fields left empty", async () => {
    partDetailReturns({
      description: "",
      buy_date: null,
      categories: [],
      owners: [],
      photo: null,
    });
    renderRoute("/app/material/4");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect((document.querySelector("form") as HTMLElement).textContent).toContain("—");
  });

  it("Material: fills every field of the create form", async () => {
    useMe({ permissions: ["material.add_materialpart"] });
    partListReturns();
    let fields: Record<string, string> = {};
    server.use(
      http.post(api("/api/material/parts"), async ({ request }) => {
        fields = await multipartFields(request);
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/material");
    await user.click(await screen.findByRole("button", { name: "Neues Material" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(Object.keys(fields).length).toBeGreaterThan(0));
    expect(fields).toMatchObject({
      name: "Text",
      description: "Text",
      quantity: "3",
      buy_date: "2026-03-04",
      lifetime: "3",
    });
  });

  it("Kategorie: carries the edited name into the PUT", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Seile", material_parts: [] }),
      ),
    );
    let put: unknown = null;
    server.use(
      http.put(api("/api/material/categories/1"), async ({ request }) => {
        put = await request.json();
        return HttpResponse.json({ id: 1, name: "Text", material_parts: [] });
      }),
    );
    const { user } = renderRoute("/app/material/categories/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await fillEveryField(user, document.querySelector("form") as HTMLElement);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).toEqual({ name: "Text" }));
  });
});
