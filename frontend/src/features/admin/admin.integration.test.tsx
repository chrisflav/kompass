import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

const USERS = [
  {
    id: 1,
    username: "jdav_admin",
    is_active: true,
    is_staff: true,
    is_superuser: true,
    last_login: "2026-07-12T09:00:00Z",
    groups: [],
    member_name: "Tobias Werner",
  },
  {
    id: 2,
    username: "hannah.becker",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    last_login: null,
    groups: ["Standard"],
    member_name: "Hannah Beckers",
  },
];

const GROUPS = [{ id: 1, name: "Standard", permission_count: 15, user_count: 5 }];

describe("users list", () => {
  it("lists accounts with their linked member and rights", async () => {
    server.use(http.get(api("/api/logindata/users"), () => HttpResponse.json(USERS)));
    renderRoute("/kompass/users");

    expect(await screen.findByText("jdav_admin")).toBeInTheDocument();
    expect(screen.getByText("Tobias Werner")).toBeInTheDocument();
    expect(screen.getByText("Standard")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Neuer Benutzer" })).toBeInTheDocument();
  });

  it("explains a 403 without leaking the permission codename", async () => {
    useMe({ permissions: [] });
    server.use(
      http.get(api("/api/logindata/users"), () =>
        HttpResponse.json({ detail: "auth.view_user" }, { status: 403 }),
      ),
    );
    renderRoute("/kompass/users");

    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
    expect(screen.queryByText(/auth\.view_user/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neuer Benutzer" })).not.toBeInTheDocument();
  });

  it("surfaces Django's own password rules on create", async () => {
    server.use(
      http.get(api("/api/logindata/users"), () => HttpResponse.json(USERS)),
      http.post(api("/api/logindata/users"), () =>
        djangoValidation({ password2: ["Die beiden Passwörter stimmen nicht überein."] }),
      ),
    );
    const { user } = renderRoute("/kompass/users");
    await screen.findByText("jdav_admin");
    await user.click(screen.getByRole("button", { name: "Neuer Benutzer" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Benutzername/), "neu");
    await user.type(dialog.getByLabelText(/^Passwort \*/), "abc");
    await user.type(dialog.getByLabelText(/Passwort wiederholen/), "xyz");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(
      await screen.findAllByText("Die beiden Passwörter stimmen nicht überein."),
    ).not.toHaveLength(0);
  });
});

describe("users list — search, filter and create", () => {
  function listReturns(rows = USERS) {
    server.use(http.get(api("/api/logindata/users"), () => HttpResponse.json(rows)));
  }

  it("searches by username and by linked member", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/users");
    await screen.findByText("jdav_admin");

    await user.type(screen.getByPlaceholderText("Suchen…"), "hannah");
    await waitFor(() => expect(screen.queryByText("jdav_admin")).not.toBeInTheDocument());
    expect(screen.getByText("hannah.becker")).toBeInTheDocument();
  });

  it("searches by username, member and rights group, and filters by the flags", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/users");
    await screen.findByText("jdav_admin");

    await user.type(screen.getByPlaceholderText("Suchen…"), "standard");
    await waitFor(() => expect(screen.queryByText("jdav_admin")).not.toBeInTheDocument());
    await user.clear(screen.getByPlaceholderText("Suchen…"));

    await user.click(await screen.findByRole("button", { name: /Aktiv:/ }));
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: "Nein",
      }),
    );
    await waitFor(() => expect(screen.getByText("0 / 2")).toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Kompass-Zugang:/ }));
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: "Nein",
      }),
    );
    await waitFor(() => expect(screen.getByText("0 / 2")).toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/users");
    await screen.findByText("jdav_admin");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: ["auth.view_user"] });
    listReturns();
    renderRoute("/kompass/users");
    await screen.findByText("jdav_admin");
    expect(screen.queryByRole("button", { name: "Neuer Benutzer" })).not.toBeInTheDocument();
  });

  it("says so when no account is visible", async () => {
    listReturns([]);
    renderRoute("/kompass/users");
    expect(await screen.findByText("Keine Benutzer sichtbar.")).toBeInTheDocument();
  });

  it("creates an account and opens it", async () => {
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/users"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...USERS[1], id: 3, username: "neu" });
      }),
      http.get(api("/api/logindata/users/3"), () =>
        HttpResponse.json({
          id: 3,
          username: "neu",
          is_active: true,
          is_staff: true,
          is_superuser: false,
          last_login: null,
          date_joined: "2026-08-01T00:00:00Z",
          groups: [],
          member_id: null,
          member_name: null,
        }),
      ),
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json(GROUPS)),
    );
    const { user } = renderRoute("/kompass/users");
    await user.click(await screen.findByRole("button", { name: "Neuer Benutzer" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Benutzername/), "neu");
    await user.type(dialog.getByLabelText(/^Passwort \*/), "Sup3rSecret!");
    await user.type(dialog.getByLabelText(/Passwort wiederholen/), "Sup3rSecret!");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() =>
      expect(body).toEqual({
        username: "neu",
        password1: "Sup3rSecret!",
        password2: "Sup3rSecret!",
      }),
    );
    expect(await screen.findByText("Benutzer angelegt.")).toBeInTheDocument();
    // An account with no linked member shows an em dash, not a broken link.
    expect(await screen.findAllByText("—")).not.toHaveLength(0);
  });

  it("shows a rejected username on the create form and closes on Abbrechen", async () => {
    listReturns();
    server.use(
      http.post(api("/api/logindata/users"), () =>
        djangoValidation({
          username: ["Diesen Benutzernamen gibt es schon."],
          password1: ["Zu kurz."],
        }),
      ),
    );
    const { user } = renderRoute("/kompass/users");
    await user.click(await screen.findByRole("button", { name: "Neuer Benutzer" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText(/Benutzername/), "jdav_admin");
    await user.type(dialog.getByLabelText(/^Passwort \*/), "x");
    await user.type(dialog.getByLabelText(/Passwort wiederholen/), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Diesen Benutzernamen gibt es schon.")).not.toHaveLength(0);
    expect(screen.getByText("Zu kurz.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("users list — remaining paths", () => {
  it("closes the create modal with ×", async () => {
    server.use(http.get(api("/api/logindata/users"), () => HttpResponse.json(USERS)));
    const { user } = renderRoute("/kompass/users");
    await user.click(await screen.findByRole("button", { name: "Neuer Benutzer" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("shows an em dash for an account that never signed in", async () => {
    server.use(
      http.get(api("/api/logindata/users"), () =>
        HttpResponse.json([{ ...USERS[1], last_login: null, member_name: null, groups: [] }]),
      ),
    );
    renderRoute("/kompass/users");
    await screen.findByText("hannah.becker");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });
});

describe("user detail", () => {
  const DETAIL = {
    id: 2,
    username: "hannah.becker",
    is_active: true,
    is_staff: true,
    is_superuser: false,
    last_login: null,
    date_joined: "2026-01-05T08:00:00Z",
    groups: [{ id: 1, name: "Standard", permission_count: 15, user_count: 5 }],
    member_id: 7,
    member_name: "Hannah Beckers",
  };

  function detailReturns() {
    server.use(
      http.get(api("/api/logindata/users/2"), () => HttpResponse.json(DETAIL)),
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json(GROUPS)),
      // Refetched after a mutation invalidates the list.
      http.get(api("/api/logindata/users"), () => HttpResponse.json(USERS)),
    );
  }

  it("links the account to its member profile", async () => {
    detailReturns();
    renderRoute("/kompass/users/2");
    expect(await screen.findByRole("link", { name: "Hannah Beckers" })).toHaveAttribute(
      "href",
      "/kompass/members/7",
    );
  });

  it("shows an em dash for an account with no member profile", async () => {
    server.use(
      http.get(api("/api/logindata/users/2"), () =>
        HttpResponse.json({ ...DETAIL, member_id: null, member_name: null }),
      ),
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json(GROUPS)),
    );
    renderRoute("/kompass/users/2");
    await screen.findByRole("button", { name: "Passwort setzen" });
    expect(screen.queryByRole("link", { name: /Beckers/ })).not.toBeInTheDocument();
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("never displays a password hash", async () => {
    detailReturns();
    renderRoute("/kompass/users/2");
    await screen.findByRole("button", { name: "Passwort setzen" });
    // Django's admin shows the encoded hash; this surface must not.
    expect(document.body.textContent).not.toMatch(/pbkdf2|argon2|bcrypt/i);
  });

  it("sets a password through its own dialog", async () => {
    detailReturns();
    let body: Record<string, unknown> | null = null;
    let savedUser = false;
    server.use(
      http.patch(api("/api/logindata/users/2"), () => {
        savedUser = true;
        return HttpResponse.json(DETAIL);
      }),
      http.post(api("/api/logindata/users/2/set-password"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(DETAIL);
      }),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Passwort setzen" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Neues Passwort/), "Sup3rSecret!x");
    await user.type(dialog.getByLabelText(/Passwort wiederholen/), "Sup3rSecret!x");
    await user.click(dialog.getByRole("button", { name: "Passwort setzen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      new_password1: "Sup3rSecret!x",
      new_password2: "Sup3rSecret!x",
    });
    expect(await screen.findByText("Passwort gesetzt.")).toBeInTheDocument();
    // The dialog is rendered from inside the detail page's <form>. Its submit
    // must not also save the account behind it.
    expect(savedUser).toBe(false);
  });

  it("edits an account's flags and rights groups", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/logindata/users/2"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(DETAIL);
      }),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const username = screen.getByDisplayValue("hannah.becker");
    await user.clear(username);
    await user.type(username, "hannah.b");
    // Aktiv / Mitarbeiter*in / Administrator, in that order.
    const [active] = screen.getAllByRole("checkbox");
    await user.click(active);
    await user.click(screen.getByRole("button", { name: "+ Rechtegruppe hinzufügen" }));
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: /Standard/,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ username: "hannah.b", is_active: false, group_ids: [] });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/logindata/users/2"), () =>
        djangoValidation({ username: ["Ungültiger Benutzername."] }),
      ),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Ungültiger Benutzername.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("hannah.becker")).not.toBeInTheDocument();
  });

  it("reports a rejected password change", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/logindata/users/2/set-password"), () =>
        djangoValidation({ new_password1: ["Zu kurz."], new_password2: ["Stimmt nicht überein."] }),
      ),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Passwort setzen" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Neues Passwort/), "x");
    await user.type(dialog.getByLabelText(/Passwort wiederholen/), "x");
    await user.click(dialog.getByRole("button", { name: "Passwort setzen" }));
    expect(await screen.findAllByText("Zu kurz.")).not.toHaveLength(0);
    expect(screen.getByText("Stimmt nicht überein.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("hides both edit actions from a read-only account", async () => {
    useMe({ permissions: ["auth.view_user"] });
    detailReturns();
    renderRoute("/kompass/users/2");
    // Breadcrumb plus the Benutzername row.
    await screen.findAllByText("hannah.becker");
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Passwort setzen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/logindata/users/2"), () =>
        HttpResponse.json({ detail: "auth.delete_user" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("warns what deleting an account means before doing it", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/logindata/users/2"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/users/2");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/„hannah.becker“ wirklich löschen\?/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Löschen" }));

    await waitFor(() => expect(deleted).toBe(true));
  });
});

describe("permission groups", () => {
  const DETAIL = {
    id: 1,
    name: "Standard",
    user_count: 5,
    permissions: [
      {
        id: 10,
        codename: "finance.add_global_statement",
        label: "Can add_global Statement",
        app_label: "finance",
      },
    ],
  };

  const ALL_PERMISSIONS = [
    {
      id: 10,
      codename: "finance.add_global_statement",
      label: "Can add_global Statement",
      app_label: "finance",
    },
    { id: 11, codename: "auth.view_user", label: "Can view user", app_label: "auth" },
  ];

  function listReturns(rows = GROUPS) {
    server.use(
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json(rows)),
      http.get(api("/api/logindata/permissions"), () => HttpResponse.json(ALL_PERMISSIONS)),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    // Editing and deleting a rights group are their own permissions.
    useMe({ permissions: ["auth.change_group", "auth.delete_group"] });
    server.use(
      http.get(api("/api/logindata/permission-groups/1"), () =>
        HttpResponse.json({ ...DETAIL, ...overrides }),
      ),
      http.get(api("/api/logindata/permissions"), () => HttpResponse.json(ALL_PERMISSIONS)),
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json(GROUPS)),
    );
  }

  it("shows how many rights and users a group carries", async () => {
    listReturns();
    renderRoute("/kompass/permission-groups");

    expect(await screen.findByText("Standard")).toBeInTheDocument();
    expect(screen.getByText("15")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([...GROUPS, { id: 2, name: "Kasse", permission_count: 2, user_count: 1 }]);
    const { user } = renderRoute("/kompass/permission-groups");
    await screen.findByText("Standard");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("searches by name and opens a group from its row", async () => {
    listReturns([...GROUPS, { id: 2, name: "Kasse", permission_count: 2, user_count: 1 }]);
    detailReturns();
    const { user } = renderRoute("/kompass/permission-groups");
    await screen.findByText("Standard");

    await user.type(screen.getByPlaceholderText("Suchen…"), "kasse");
    await waitFor(() => expect(screen.queryByText("Standard")).not.toBeInTheDocument());
    await user.clear(screen.getByPlaceholderText("Suchen…"));

    await user.click(await screen.findByText("Standard"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("closes the create modal with ×", async () => {
    useMe({ permissions: ["auth.add_group"] });
    listReturns();
    const { user } = renderRoute("/kompass/permission-groups");
    await user.click(await screen.findByRole("button", { name: "Neue Rechtegruppe" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("says so when none are visible", async () => {
    listReturns([]);
    renderRoute("/kompass/permission-groups");
    expect(await screen.findByText("Keine Rechtegruppen sichtbar.")).toBeInTheDocument();
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/permission-groups");
    await screen.findByText("Standard");
    expect(screen.queryByRole("button", { name: "Neue Rechtegruppe" })).not.toBeInTheDocument();
  });

  it("creates a group with the rights it should carry", async () => {
    useMe({ permissions: ["auth.add_group"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/permission-groups"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ ...DETAIL, id: 1 });
      }),
    );
    detailReturns();
    // detailReturns narrows the permissions; restore the create right.
    useMe({ permissions: ["auth.add_group", "auth.change_group"] });
    const { user } = renderRoute("/kompass/permission-groups");
    await user.click(await screen.findByRole("button", { name: "Neue Rechtegruppe" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();
    await user.type(dialog.getByLabelText(/^Name/), "Kassenwart");
    await user.click(dialog.getByRole("button", { name: "Rechte" }));
    // The codename is shown alongside the label so it is recognisable.
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: /finance\.add_global_statement/,
      }),
    );
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() =>
      expect(body).toEqual({ name: "Kassenwart", permission_ids: [10] }),
    );
    expect(await screen.findByText("Rechtegruppe angelegt.")).toBeInTheDocument();
  });

  it("shows a rejected create and closes on Abbrechen", async () => {
    useMe({ permissions: ["auth.add_group"] });
    listReturns();
    server.use(
      http.post(api("/api/logindata/permission-groups"), () =>
        djangoValidation({ name: ["Diese Gruppe gibt es schon."] }),
      ),
    );
    const { user } = renderRoute("/kompass/permission-groups");
    await user.click(await screen.findByRole("button", { name: "Neue Rechtegruppe" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name/), "Standard");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Diese Gruppe gibt es schon.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("lists a group's rights with their codenames", async () => {
    detailReturns();
    renderRoute("/kompass/permission-groups/1");
    // The codename is what an administrator recognises from the rules files.
    expect(await screen.findByText("finance.add_global_statement")).toBeInTheDocument();
    expect(screen.getByText("Can add_global Statement")).toBeInTheDocument();
  });

  it("shows an em dash for a group carrying no rights", async () => {
    detailReturns({ permissions: [] });
    renderRoute("/kompass/permission-groups/1");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("edits a group's name and rights", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/logindata/permission-groups/1"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(DETAIL);
      }),
    );
    const { user } = renderRoute("/kompass/permission-groups/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const name = screen.getByDisplayValue("Standard");
    await user.clear(name);
    await user.type(name, "Standard 2026");
    await user.click(screen.getByRole("button", { name: "+ Recht hinzufügen" }));
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: /auth\.view_user/,
      }),
    );
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toEqual({ name: "Standard 2026", permission_ids: [10, 11] });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/logindata/permission-groups/1"), () =>
        djangoValidation({ name: ["Der Name fehlt."] }),
      ),
    );
    const { user } = renderRoute("/kompass/permission-groups/1");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Name fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Standard")).not.toBeInTheDocument();
  });

  it("warns how many users a delete affects", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/logindata/permission-groups/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/permission-groups/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/5 Benutzer verlieren die darin enthaltenen Rechte/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Löschen" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Rechtegruppe gelöscht.")).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    detailReturns();
    server.use(
      http.delete(api("/api/logindata/permission-groups/1"), () =>
        HttpResponse.json({ detail: "auth.delete_group" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/permission-groups/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("hides both edit actions from a read-only account", async () => {
    detailReturns();
    useMe({ permissions: [] });
    renderRoute("/kompass/permission-groups/1");
    await screen.findByText("finance.add_global_statement");
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/permission-groups/1");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("registration passwords", () => {
  const ALL = ["logindata.add_registrationpassword", "logindata.change_registrationpassword", "logindata.delete_registrationpassword"];

  function listReturns(rows: unknown[] = [{ id: 1, password: "testtest" }]) {
    server.use(
      http.get(api("/api/logindata/registration-passwords"), () => HttpResponse.json(rows)),
    );
  }

  it("explains what the shared secret is for and lists it", async () => {
    listReturns();
    renderRoute("/kompass/registration-passwords");

    expect(await screen.findByText("testtest")).toBeInTheDocument();
    expect(screen.getByText(/Wer per E-Mail eingeladen wird/)).toBeInTheDocument();
  });

  it("says so when none are set", async () => {
    listReturns([]);
    renderRoute("/kompass/registration-passwords");
    expect(
      await screen.findByText("Kein Registrierungspasswort hinterlegt."),
    ).toBeInTheDocument();
  });

  it("creates a password", async () => {
    useMe({ permissions: ALL });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/registration-passwords"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 2, password: "neuneu" });
      }),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Neues Passwort" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Passwort/), "neuneu");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).toEqual({ password: "neuneu" }));
    expect(await screen.findByText("Passwort angelegt.")).toBeInTheDocument();
  });

  it("changes an existing password", async () => {
    useMe({ permissions: ALL });
    listReturns();
    let body: unknown = null;
    server.use(
      http.patch(api("/api/logindata/registration-passwords/1"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ id: 1, password: "anders" });
      }),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Ändern" }));

    const dialog = within(await screen.findByRole("dialog"));
    // The dialog opens prefilled with the current value.
    const input = dialog.getByLabelText(/Passwort/);
    expect(input).toHaveValue("testtest");
    await user.clear(input);
    await user.type(input, "anders");
    await user.click(dialog.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(body).toEqual({ password: "anders" }));
    expect(await screen.findByText("Passwort geändert.")).toBeInTheDocument();
  });

  it("fills the create form's only field", async () => {
    useMe({ permissions: ALL });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/registration-passwords"), async ({ request }) => {
        body = await request.json();
        return djangoValidation({ password: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Neues Passwort" }));
    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(body).toEqual({ password: "Text" }));
  });

  it("fills every field of the rights-group create form", async () => {
    useMe({ permissions: ["auth.add_group"] });
    server.use(
      http.get(api("/api/logindata/permission-groups"), () => HttpResponse.json([])),
      http.get(api("/api/logindata/permissions"), () =>
        HttpResponse.json([
          { id: 10, codename: "auth.view_user", label: "Can view user", app_label: "auth" },
        ]),
      ),
    );
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/permission-groups"), async ({ request }) => {
        body = await request.json();
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/kompass/permission-groups");
    await user.click(await screen.findByRole("button", { name: "Neue Rechtegruppe" }));
    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(body).toEqual({ name: "Text", permission_ids: [10] }));
  });

  it("shows a rejected password and closes on Abbrechen", async () => {
    useMe({ permissions: ALL });
    listReturns();
    server.use(
      http.post(api("/api/logindata/registration-passwords"), () =>
        djangoValidation({ password: ["Zu kurz."] }),
      ),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Neues Passwort" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText(/Passwort/), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Zu kurz.")).not.toHaveLength(0);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("warns that deleting one invalidates open invitations", async () => {
    useMe({ permissions: ALL });
    listReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/logindata/registration-passwords/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(
      dialog.getByText(/Offene Einladungen damit funktionieren dann nicht mehr/),
    ).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Löschen" }));

    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Passwort gelöscht.")).toBeInTheDocument();
  });

  it("does nothing when the delete is cancelled", async () => {
    useMe({ permissions: ALL });
    listReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/logindata/registration-passwords/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(deleted).toBe(false);
  });

  it("reports a refused delete", async () => {
    useMe({ permissions: ALL });
    listReturns();
    server.use(
      http.delete(api("/api/logindata/registration-passwords/1"), () =>
        HttpResponse.json({ detail: "logindata.delete_registrationpassword" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/kompass/registration-passwords");
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("hides every action from someone without the rights", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/kompass/registration-passwords");
    await screen.findByText("testtest");
    expect(screen.queryByRole("button", { name: "Neues Passwort" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ändern" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Entfernen" })).not.toBeInTheDocument();
  });
});
