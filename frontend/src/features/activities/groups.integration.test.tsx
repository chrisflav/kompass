import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  api,
  djangoValidation,
  http,
  HttpResponse,
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
  { id: 42, name: "Anna Ärmel" },
  { id: 43, name: "Mila Nowak" },
];
const EMAILS = [{ id: 2, name: "jugend", email: "jugend@example.org" }];

const GROUP: Record<string, unknown> = {
  id: 7,
  name: "Klettergruppe",
  description: "Beschreibung",
  weekday_display: "Sonntag",
  time_info: "",
  age_info: "Jahrgang 2010 bis 2013",
  leiters: [],
  year_from: 2010,
  year_to: 2013,
  show_website: true,
  show_website_ages: false,
  show_website_contact_email: false,
  show_website_weekday: false,
  show_website_time: false,
  contact_email: null,
  contact_email_display: null,
  weekday: null,
  time_from: null,
  time_to: null,
  invitation_text_template: "",
};

function groupsReturn(rows = [GROUP]) {
  server.use(http.get(api("/api/members/groups"), () => HttpResponse.json(rows)));
}

describe("groups list", () => {
  it("lists the groups with their document actions", async () => {
    groupsReturn();
    renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Neue Gruppe" })).toBeInTheDocument();
  });

  it("hides the document downloads from someone who may not view groups", async () => {
    useMe({ permissions: [] });
    groupsReturn();
    renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    expect(screen.queryByRole("button", { name: /Übersicht \(xlsx\)/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Checkliste \(pdf\)/ })).not.toBeInTheDocument();
  });
});

describe("group create modal", () => {
  it("keeps the submit disabled until the required fields are filled", async () => {
    groupsReturn();
    const { user } = renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Neue Gruppe" }));

    const dialog = within(await screen.findByRole("dialog"));
    // Both year fields are NOT NULL on the model; leaving them blank used to
    // produce "Dieses Feld darf nicht null sein." naming no field at all.
    expect(dialog.getByLabelText(/Ab Jahrgang \*/)).toBeRequired();
    expect(dialog.getByLabelText(/Bis Jahrgang \*/)).toBeRequired();
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();

    await user.type(dialog.getByLabelText(/^Name \*/), "Neue Gruppe");
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();

    await user.type(dialog.getByLabelText(/Ab Jahrgang \*/), "2012");
    await user.type(dialog.getByLabelText(/Bis Jahrgang \*/), "2015");
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeEnabled();
  });

  it("sends the years as numbers and lands on the new group", async () => {
    groupsReturn();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/groups"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...GROUP, id: 9, name: "Neue Gruppe" }, { status: 201 });
      }),
      http.get(api("/api/members/groups/9"), () =>
        HttpResponse.json({ ...GROUP, id: 9, name: "Neue Gruppe" }),
      ),
      http.get(api("/api/members/groups/9/registration-passwords"), () => HttpResponse.json([])),
      http.get(api("/api/members/groups/9/permission-groups"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
      http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([])),
    );

    const { user } = renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Neue Gruppe" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name \*/), "Neue Gruppe");
    await user.type(dialog.getByLabelText(/Ab Jahrgang \*/), "2012");
    await user.type(dialog.getByLabelText(/Bis Jahrgang \*/), "2015");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ name: "Neue Gruppe", year_from: 2012, year_to: 2015 });
    expect(await screen.findByText("Gruppe angelegt.")).toBeInTheDocument();
  });

  it("fills every field of the create form", async () => {
    groupsReturn();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/groups"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Neue Gruppe" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      name: "Text",
      description: "Text",
      year_from: 3,
      year_to: 3,
    });
  });

  it("shows a server-side field error on the field it belongs to", async () => {
    groupsReturn();
    server.use(
      http.post(api("/api/members/groups"), () =>
        djangoValidation({ name: ["Eine Gruppe mit diesem Namen gibt es bereits."] }),
      ),
    );
    const { user } = renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Neue Gruppe" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name \*/), "Klettergruppe");
    await user.type(dialog.getByLabelText(/Ab Jahrgang \*/), "2012");
    await user.type(dialog.getByLabelText(/Bis Jahrgang \*/), "2015");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    // Shown twice on purpose: inline under the offending field, and as a toast
    // for the case where the field is on a tab the user is not looking at.
    const shown = await screen.findAllByText("Eine Gruppe mit diesem Namen gibt es bereits.");
    expect(shown).toHaveLength(2);
    expect(shown.some((el) => el.classList.contains("field-error"))).toBe(true);
    expect(shown.some((el) => el.closest(".toast"))).toBe(true);
  });

  it("puts every rejected field's message under its own field", async () => {
    groupsReturn();
    server.use(
      http.post(api("/api/members/groups"), () =>
        djangoValidation({
          description: ["Zu lang."],
          year_from: ["Ungültiger Jahrgang."],
          year_to: ["Zu spät."],
        }),
      ),
    );
    const { user } = renderRoute("/app/groups");
    await waitFor(() => expect(screen.getByText("Klettergruppe")).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: "Neue Gruppe" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name \*/), "Neue Gruppe");
    await user.type(dialog.getByLabelText(/Ab Jahrgang \*/), "2012");
    await user.type(dialog.getByLabelText(/Bis Jahrgang \*/), "2015");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Zu lang.")).not.toHaveLength(0);
    expect(screen.getByText("Ungültiger Jahrgang.")).toBeInTheDocument();
    expect(screen.getByText("Zu spät.")).toBeInTheDocument();
  });
});

describe("group detail — delete", () => {
  function detailReturns() {
    server.use(
      http.get(api("/api/members/groups/7"), () => HttpResponse.json(GROUP)),
      http.get(api("/api/members/groups/7/registration-passwords"), () => HttpResponse.json([])),
      http.get(api("/api/members/groups/7/permission-groups"), () => HttpResponse.json([])),
      http.get(api("/api/members/groups"), () => HttpResponse.json([GROUP])),
      http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
      http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json(EMAILS)),
    );
  }

  it("asks before deleting, and does nothing when cancelled", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/members/groups/7"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/„Klettergruppe“ wirklich löschen\?/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));

    expect(deleted).toBe(false);
  });

  it("deletes once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/members/groups/7"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Löschen" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Gruppe gelöscht.")).toBeInTheDocument();
  });

  it("offers no delete button without the permission", async () => {
    useMe({ permissions: ["members.view_group"] });
    detailReturns();
    renderRoute("/app/groups/7");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });
});

/* --- list documents ------------------------------------------------------- */

describe("group list — documents", () => {
  it("downloads the overview and the checklist", async () => {
    groupsReturn();
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

    useMe({ permissions: ["members.view_group"] });
    const requested: string[] = [];
    server.use(
      http.post(api("/api/members/documents/groups/overview"), () => {
        requested.push("overview");
        return HttpResponse.json({});
      }),
      http.post(api("/api/members/documents/groups/checklist"), () => {
        requested.push("checklist");
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/app/groups");

    await user.click(await screen.findByRole("button", { name: /Übersicht \(xlsx\)/ }));
    await user.click(screen.getByRole("button", { name: /Checkliste \(pdf\)/ }));
    await waitFor(() => expect(requested).toEqual(["overview", "checklist"]));
  });

  it("sorts by every column in both directions", async () => {
    groupsReturn([GROUP, { ...GROUP, id: 8, name: "Bouldergruppe", weekday_display: "" }]);
    const { user } = renderRoute("/app/groups");
    await screen.findByText("Klettergruppe");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("says so when no group is visible", async () => {
    groupsReturn([]);
    renderRoute("/app/groups");
    expect(await screen.findByText("Keine Gruppen sichtbar.")).toBeInTheDocument();
  });
});

/* --- detail --------------------------------------------------------------- */

const FULL_GROUP = {
  ...GROUP,
  leiters: [{ id: 42, name: "Anna Ärmel" }],
  contact_email: 2,
  contact_email_display: "jugend@example.org",
  weekday: 6,
  weekday_display: "Sonntag",
  start_time: "18:00",
  end_time: "20:00",
  time_info: "18:00–20:00",
};

function fullDetailReturns(overrides: Record<string, unknown> = {}, extra: Parameters<typeof server.use> = []) {
  server.use(
    // `extra` comes first: among the handlers of one call, the earlier wins.
    ...extra,
    http.get(api("/api/members/groups/7"), () =>
      HttpResponse.json({ ...FULL_GROUP, ...overrides }),
    ),
    http.get(api("/api/members/groups/7/registration-passwords"), () => HttpResponse.json([])),
    http.get(api("/api/members/groups/7/permission-groups"), () => HttpResponse.json([])),
    http.get(api("/api/members/groups"), () => HttpResponse.json([FULL_GROUP])),
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json(EMAILS)),
  );
}

describe("group detail — general", () => {
  it("shows the group with its website flags", async () => {
    fullDetailReturns();
    renderRoute("/app/groups/7");
    expect(await screen.findByText("jugend@example.org")).toBeInTheDocument();
    expect(screen.getByText("Sonntag")).toBeInTheDocument();
    expect(screen.getByText("18:00–20:00")).toBeInTheDocument();
    expect(screen.getAllByText("Ja").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);
  });

  it("shows an em dash for the optional fields when unset", async () => {
    fullDetailReturns({
      description: "",
      leiters: [],
      contact_email: null,
      contact_email_display: null,
      weekday: null,
      weekday_display: null,
      time_info: "",
      age_info: "",
    });
    renderRoute("/app/groups/7");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(5);
  });

  it("saves an inline edit with ids, numbers and nulls", async () => {
    fullDetailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/groups/7"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_GROUP);
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const name = screen.getByDisplayValue("Klettergruppe");
    await user.clear(name);
    await user.type(name, "Kletterkids");
    await user.click(screen.getByRole("button", { name: "+ Auswählen…" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      name: "Kletterkids",
      year_from: 2010,
      year_to: 2013,
      weekday: 6,
      contact_email_id: 2,
      leiter_ids: [42, 43],
      start_time: "18:00",
      end_time: "20:00",
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("sends null for a cleared weekday, time and contact address", async () => {
    fullDetailReturns({
      weekday: null,
      weekday_display: null,
      start_time: null,
      end_time: null,
      contact_email: null,
      contact_email_display: null,
    });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/groups/7"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_GROUP);
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      weekday: null,
      start_time: null,
      end_time: null,
      contact_email_id: null,
    });
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    fullDetailReturns();
    server.use(
      http.patch(api("/api/members/groups/7"), () =>
        djangoValidation({ name: ["Der Name fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Klettergruppe")).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    fullDetailReturns();
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("group detail — Registrierungspasswörter", () => {
  it("stages a new password and creates it on save", async () => {
    fullDetailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/groups/7"), () => HttpResponse.json(FULL_GROUP)),
      http.post(api("/api/members/groups/7/registration-passwords"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 12, password: "kletter26" });
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));
    await user.click(await screen.findByRole("button", { name: "+ Passwort" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.type(dialog.getByLabelText("Passwort"), "kletter26");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    expect(created).toBeNull();
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).toEqual({ password: "kletter26" }));
  });

  it("edits and removes an existing password on save", async () => {
    fullDetailReturns({}, [
      http.get(api("/api/members/groups/7/registration-passwords"), () =>
        HttpResponse.json([{ id: 12, password: "kletter25" }]),
      ),
    ]);
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.patch(api("/api/members/groups/7"), () => HttpResponse.json(FULL_GROUP)),
      http.patch(api("/api/members/registration-passwords/12"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 12 });
      }),
      http.delete(api("/api/members/registration-passwords/12"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));

    const input = await screen.findByDisplayValue("kletter25");
    await user.clear(input);
    await user.type(input, "kletter26");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toEqual({ password: "kletter26" }));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("shows the passwords read-only outside edit mode", async () => {
    fullDetailReturns({}, [
      http.get(api("/api/members/groups/7/registration-passwords"), () =>
        HttpResponse.json([{ id: 12, password: "" }]),
      ),
    ]);
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("tab", { name: "Registrierungspasswörter" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("closes the password dialog on Abbrechen", async () => {
    fullDetailReturns();
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));
    await user.click(await screen.findByRole("button", { name: "+ Passwort" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("group detail — Gruppenberechtigungen", () => {
  it("says so when there are none, differently in edit mode", async () => {
    fullDetailReturns();
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("tab", { name: "Gruppenberechtigungen" }));
    expect(await screen.findByText("Keine Berechtigungen.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Gruppenberechtigungen" }));
    expect(
      await screen.findByText("Keine Berechtigungen – oben anlegen."),
    ).toBeInTheDocument();
  });

  it("adds a permission set and creates it on save", async () => {
    fullDetailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/groups/7"), () => HttpResponse.json(FULL_GROUP)),
      http.post(api("/api/members/groups/7/permission-groups"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 15 });
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Gruppenberechtigungen" }));
    await user.click(await screen.findByRole("button", { name: "+ Berechtigungen" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getAllByRole("button", { name: "+ Auswählen…" })[0]);
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toMatchObject({ list_member_ids: [42] });
  });

  it("edits and removes an existing permission set on save", async () => {
    fullDetailReturns({}, [
      http.get(api("/api/members/groups/7/permission-groups"), () =>
        HttpResponse.json([
          {
            id: 15,
            list_member_ids: [42],
            view_member_ids: [],
            change_member_ids: [],
            delete_member_ids: [],
            list_group_ids: [7],
            view_group_ids: [999],
            change_group_ids: [],
            delete_group_ids: [],
          },
        ]),
      ),
    ]);
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.patch(api("/api/members/groups/7"), () => HttpResponse.json(FULL_GROUP)),
      http.patch(api("/api/members/permission-groups/15"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 15 });
      }),
      http.delete(api("/api/members/permission-groups/15"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/groups/7");

    // Read-only first: ids resolve to names, unknown ones stay as "#id".
    await user.click(await screen.findByRole("tab", { name: "Gruppenberechtigungen" }));
    const panelEl = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panelEl.textContent).toContain("Anna Ärmel"));
    expect(panelEl.textContent).toContain("#999");

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Gruppenberechtigungen" }));
    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getAllByRole("button", { name: "+ Auswählen…" })[1]);
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ list_member_ids: [42], view_member_ids: [43] });

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Gruppenberechtigungen" }));
    // The MultiSelect badges have their own remove buttons; take the row's.
    const rowRemove = (
      document.querySelector(".tab-panel:not([hidden]) td.inline-actions button") as HTMLElement
    );
    await user.click(rowRemove);
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("offers only one permission set per group", async () => {
    fullDetailReturns({}, [
      http.get(api("/api/members/groups/7/permission-groups"), () =>
        HttpResponse.json([
          {
            id: 15,
            list_member_ids: [],
            view_member_ids: [],
            change_member_ids: [],
            delete_member_ids: [],
            list_group_ids: [],
            view_group_ids: [],
            change_group_ids: [],
            delete_group_ids: [],
          },
        ]),
      ),
    ]);
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Gruppenberechtigungen" }));
    await screen.findByRole("button", { name: "Entfernen" });
    expect(screen.queryByRole("button", { name: "+ Berechtigungen" })).not.toBeInTheDocument();
  });
});

describe("group list — remaining paths", () => {
  it("searches by name and filters by weekday", async () => {
    groupsReturn([
      GROUP,
      {
        ...GROUP,
        id: 8,
        name: "Bouldergruppe",
        weekday: 0,
        weekday_display: "Montag",
        age_info: "",
        time_info: "",
      },
    ]);
    const { user } = renderRoute("/app/groups");
    await screen.findByText("Klettergruppe");

    await user.type(screen.getByPlaceholderText("Suchen…"), "boulder");
    await waitFor(() => expect(screen.queryByText("Klettergruppe")).not.toBeInTheDocument());
    await user.clear(screen.getByPlaceholderText("Suchen…"));

    await user.click(await screen.findByRole("button", { name: /Webseite:/ }));
    await user.click(dropdown().getByRole("button", { name: "Nein" }));
    await waitFor(() => expect(screen.getByText("0 / 2")).toBeInTheDocument());
  });

  it("opens a group's members from its row and closes the create modal with ×", async () => {
    groupsReturn();
    server.use(
      http.get(api("/api/members/groups/7"), () => HttpResponse.json(GROUP)),
      http.get(api("/api/members/"), () =>
        HttpResponse.json([{ id: 42, name: "Anna Ärmel", groups: ["Klettergruppe"] }]),
      ),
    );
    const { user } = renderRoute("/app/groups");

    await user.click(await screen.findByRole("button", { name: "Neue Gruppe" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Klettergruppe"));
    // The row opens the group's own member list.
    expect(await screen.findByText("Anna Ärmel")).toBeInTheDocument();
  });

  it("marks a group that is hidden from the website", async () => {
    groupsReturn([{ ...GROUP, show_website: false }]);
    renderRoute("/app/groups");
    await screen.findByText("Klettergruppe");
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("shows an em dash for a group with no meeting time", async () => {
    groupsReturn([{ ...GROUP, weekday_display: "", time_info: "", age_info: "" }]);
    renderRoute("/app/groups");
    await screen.findByText("Klettergruppe");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("group detail — remaining paths", () => {
  it("copes with an API that sends null for every optional field", async () => {
    fullDetailReturns({
      description: null,
      leiters: [],
      contact_email: null,
      contact_email_display: null,
      weekday: null,
      weekday_display: null,
      start_time: null,
      end_time: null,
      time_info: "",
      age_info: "",
      invitation_text_template: null,
    });
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("reports a refused delete and a rejected inline flush", async () => {
    fullDetailReturns();
    server.use(
      http.delete(api("/api/members/groups/7"), () =>
        HttpResponse.json({ detail: "members.delete_group" }, { status: 403 }),
      ),
      http.patch(api("/api/members/groups/7"), () => HttpResponse.json(FULL_GROUP)),
      http.post(api("/api/members/groups/7/registration-passwords"), () =>
        djangoValidation({ password: ["Zu kurz."] }),
      ),
    );
    const { user } = renderRoute("/app/groups/7");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));
    await user.click(await screen.findByRole("button", { name: "+ Passwort" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Passwort"), "x");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText(/Ein verknüpfter Eintrag konnte nicht gespeichert werden/),
    ).toBeInTheDocument();
  });

  it("closes the password dialog with ×", async () => {
    fullDetailReturns();
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Registrierungspasswörter" }));
    await user.click(await screen.findByRole("button", { name: "+ Passwort" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("group detail — every field", () => {
  it("carries every edited field into the PATCH", async () => {
    fullDetailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/groups/7"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(FULL_GROUP);
      }),
    );
    const { user } = renderRoute("/app/groups/7");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({
      name: "Text",
      description: "Text",
      year_from: 3,
      year_to: 3,
      start_time: "17:30",
      end_time: "17:30",
      // Every checkbox flipped from its stored value.
      show_website: false,
      show_website_year: true,
      show_website_weekday: true,
      show_website_time: true,
      show_website_contact_email: true,
      // Taking the first option of an optional select means "clear it", and the
      // leaders MultiSelect toggles the one selected name back off.
      weekday: null,
      contact_email_id: null,
      leiter_ids: [],
    });
  });
});
