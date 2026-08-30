import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  api,
  djangoValidation,
  http,
  HttpResponse,
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
  { id: 9, name: "Tobias Werner" },
];
const GROUPS = [{ id: 5, name: "Klettergruppe" }];
const EXCURSIONS = [{ id: 3, code: "F26-01", name: "Skifreizeit" }];

/* --- E-Mail-Adressen ------------------------------------------------------ */

const ADDRESS_BRIEF = {
  id: 2,
  name: "jugend",
  email: "jugend@example.org",
  internal_only: true,
};

const ADDRESS = {
  ...ADDRESS_BRIEF,
  forwards: ["hannah@example.org"],
  to_members: [{ id: 7, name: "Hannah Beckers" }],
  to_groups: [{ id: 5, name: "Klettergruppe" }],
  allowed_senders: [],
};

function addressBase() {
  server.use(
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
  );
}

describe("mailer — E-Mail-Adressen", () => {
  function listReturns(rows = [ADDRESS_BRIEF]) {
    addressBase();
    server.use(http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json(rows)));
  }

  it("lists the managed addresses", async () => {
    listReturns();
    renderRoute("/app/mailer/addresses");
    expect(await screen.findByText("jugend@example.org")).toBeInTheDocument();
    expect(screen.getByText("1 / 1")).toBeInTheDocument();
  });

  it("marks an address that also accepts external senders", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () =>
        HttpResponse.json({ ...ADDRESS, internal_only: false }),
      ),
    );
    renderRoute("/app/mailer/addresses/2");
    await screen.findAllByText("jugend");
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/mailer/addresses");
    expect(await screen.findByText("Keine E-Mail-Adressen vorhanden.")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([ADDRESS_BRIEF, { ...ADDRESS_BRIEF, id: 3, name: "vorstand", internal_only: false }]);
    const { user } = renderRoute("/app/mailer/addresses");
    await screen.findByText("jugend");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/mailer/addresses");
    await screen.findByText("jugend@example.org");
    expect(screen.queryByRole("button", { name: "Neue Adresse" })).not.toBeInTheDocument();
  });

  it("creates an address with its forwarding targets", async () => {
    useMe({ permissions: ["mailer.add_emailaddress"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/mailer/email-addresses"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...ADDRESS, id: 9 });
      }),
      http.get(api("/api/mailer/email-addresses/9"), () =>
        HttpResponse.json({ ...ADDRESS, id: 9 }),
      ),
    );
    const { user } = renderRoute("/app/mailer/addresses");
    await user.click(await screen.findByRole("button", { name: "Neue Adresse" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name/), "vorstand");
    await user.click(dialog.getByLabelText(/Nur interne Absender/));
    await user.click(dialog.getByRole("button", { name: /Weiterleiten an Gruppen/ }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Weiterleiten an Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Tobias Werner" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      name: "vorstand",
      internal_only: true,
      to_groups: [5],
      to_members: [9],
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("shows the backend's 'group or member required' rule on the form", async () => {
    useMe({ permissions: ["mailer.add_emailaddress"] });
    listReturns();
    server.use(
      http.post(api("/api/mailer/email-addresses"), () =>
        djangoValidation({
          to_groups: ["Gruppe oder Teilnehmende sind erforderlich."],
          to_members: ["Gruppe oder Teilnehmende sind erforderlich."],
          allowed_senders: ["Ungültig."],
          name: ["Diesen Namen gibt es schon."],
        }),
      ),
    );
    const { user } = renderRoute("/app/mailer/addresses");
    await user.click(await screen.findByRole("button", { name: "Neue Adresse" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/^Name/), "jugend");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(
      await screen.findAllByText("Gruppe oder Teilnehmende sind erforderlich."),
    ).toHaveLength(2);
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();
    expect(screen.getByText("Diesen Namen gibt es schon.")).toBeInTheDocument();
  });

  it("closes the create modal on Abbrechen", async () => {
    useMe({ permissions: ["mailer.add_emailaddress"] });
    listReturns();
    const { user } = renderRoute("/app/mailer/addresses");
    await user.click(await screen.findByRole("button", { name: "Neue Adresse" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("marks an internal-only address in the list", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses"), () =>
        HttpResponse.json([ADDRESS_BRIEF, { ...ADDRESS_BRIEF, id: 3, internal_only: false }]),
      ),
    );
    renderRoute("/app/mailer/addresses");
    await screen.findAllByText("jugend@example.org");
    expect(screen.getByText("Ja")).toBeInTheDocument();
    expect(screen.getByText("Nein")).toBeInTheDocument();
  });

  it("edits every forwarding list of an address", async () => {
    addressBase();
    let put: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
      http.put(api("/api/mailer/email-addresses/2"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(ADDRESS);
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.click(screen.getByRole("checkbox"));
    await user.click(screen.getByRole("button", { name: "+ Teilnehmende hinzufügen" }));
    await user.click(dropdown().getByRole("button", { name: "Tobias Werner" }));
    // Two rows offer "+ Gruppe hinzufügen"; the second is "Erlaubte Absender".
    const groupPickers = screen.getAllByRole("button", { name: "+ Gruppe hinzufügen" });
    await user.click(groupPickers[groupPickers.length - 1]);
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({
      internal_only: false,
      to_members: [7, 9],
      allowed_senders: [5],
    });
  });

  it("shows the address read-only, with its recovered help text while editing", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");

    expect(await screen.findByText("hannah@example.org")).toBeInTheDocument();
    expect(screen.getByText("Klettergruppe")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    expect(screen.getByText(/Leite nur E-Mails weiter, die von einer der folgenden Domains/)).toBeInTheDocument();
  });

  it("saves an edit and reports a rejected one", async () => {
    addressBase();
    let put: Record<string, unknown> | null = null;
    let attempt = 0;
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
      http.put(api("/api/mailer/email-addresses/2"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return djangoValidation({ name: ["Ungültiger Name."] });
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(ADDRESS);
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Ungültiger Name.")).not.toHaveLength(0);

    // Still in edit mode, so a corrected second attempt is possible.
    const name = screen.getByDisplayValue("jugend");
    await user.clear(name);
    await user.type(name, "jugendreferat");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ name: "jugendreferat" });
  });

  it("leaves edit mode on Abbrechen", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("jugend")).not.toBeInTheDocument();
  });

  it("deletes an address once confirmed, and reports a refusal", async () => {
    addressBase();
    let attempt = 0;
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
      http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([])),
      http.delete(api("/api/mailer/email-addresses/2"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "mailer.delete_emailaddress" }, { status: 403 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Adresse gelöscht.")).toBeInTheDocument();
  });

  it("does nothing when the delete is cancelled", async () => {
    addressBase();
    let deleted = false;
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
      http.delete(api("/api/mailer/email-addresses/2"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    expect(deleted).toBe(false);
  });

  it("goes back through the browser history", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Nachrichten ---------------------------------------------------------- */

const MESSAGE_BRIEF: Record<string, unknown> = {
  id: 4,
  subject: "Sommerfahrt",
  sent: false,
  recipients: "Klettergruppe",
  created_by: { id: 7, name: "Hannah Beckers" },
  created: "2026-05-01T10:00:00Z",
};

const MESSAGE = {
  id: 4,
  subject: "Sommerfahrt",
  content: "Bitte anmelden.",
  sent: false,
  recipients: "Klettergruppe",
  created_by: { id: 7, name: "Hannah Beckers" },
  created: "2026-05-01T10:00:00Z",
  to_groups: [{ id: 5, name: "Klettergruppe" }],
  to_members: [],
  to_freizeit: null,
  reply_to: [],
  reply_to_email_address: [],
};

function messageBase() {
  server.use(
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    http.get(api("/api/members/excursions"), () => HttpResponse.json(EXCURSIONS)),
    http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([ADDRESS_BRIEF])),
  );
}

describe("mailer — Nachrichten", () => {
  function listReturns(rows = [MESSAGE_BRIEF]) {
    messageBase();
    server.use(http.get(api("/api/mailer/messages"), () => HttpResponse.json(rows)));
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    messageBase();
    server.use(
      http.get(api("/api/mailer/messages/4"), () =>
        HttpResponse.json({ ...MESSAGE, ...overrides }),
      ),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
  }

  it("lists messages and filters by sent status", async () => {
    listReturns([MESSAGE_BRIEF, { ...MESSAGE_BRIEF, id: 5, subject: "Alt", sent: true }]);
    const { user } = renderRoute("/app/mailer/messages");
    await screen.findByText("Sommerfahrt");

    await user.click(screen.getByRole("button", { name: /Status:/ }));
    await user.click(dropdown().getByRole("button", { name: "Gesendet" }));

    await waitFor(() => expect(screen.queryByText("Sommerfahrt")).not.toBeInTheDocument());
    expect(screen.getByText("Alt")).toBeInTheDocument();
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/mailer/messages");
    expect(await screen.findByText("Keine Nachrichten vorhanden.")).toBeInTheDocument();
  });

  it("searches by subject and names an untitled message", async () => {
    listReturns([{ ...MESSAGE_BRIEF, subject: "" }, { ...MESSAGE_BRIEF, id: 5, subject: "Alt" }]);
    const { user } = renderRoute("/app/mailer/messages");
    await screen.findByText("(ohne Betreff)");

    await user.type(screen.getByPlaceholderText("Suchen…"), "alt");
    await waitFor(() => expect(screen.queryByText("(ohne Betreff)")).not.toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([MESSAGE_BRIEF, { ...MESSAGE_BRIEF, id: 5, subject: "Alt", created_by: null }]);
    const { user } = renderRoute("/app/mailer/messages");
    await screen.findByText("Sommerfahrt");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the compose button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/mailer/messages");
    await screen.findByText("Sommerfahrt");
    expect(screen.queryByRole("button", { name: "Neue Nachricht" })).not.toBeInTheDocument();
  });

  it("opens the compose dialog straight from ?compose=1", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    renderRoute("/app/mailer/messages?compose=1");
    // The dashboard's "Nachricht senden" shortcut lands here.
    expect(await screen.findByRole("dialog", { name: "Neue Nachricht" })).toBeInTheDocument();
  });

  it("drops ?compose=1 from the URL when the dialog is closed", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    const { user } = renderRoute("/app/mailer/messages?compose=1");
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    // Reopening is then a deliberate click, not a leftover query parameter.
    expect(screen.getByRole("button", { name: "Neue Nachricht" })).toBeInTheDocument();
  });

  it("shows a rejected content on the compose form", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    server.use(
      http.post(api("/api/mailer/messages"), () =>
        djangoValidation({ content: ["Der Inhalt ist zu lang."] }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "S");
    await user.type(dialog.getByLabelText("Inhalt"), "I");
    await user.click(dialog.getByRole("button", { name: "Als Entwurf speichern" }));
    expect(await screen.findAllByText("Der Inhalt ist zu lang.")).not.toHaveLength(0);
  });

  it("names the linked excursion on the detail page", async () => {
    detailReturns({ to_freizeit: { id: 3, code: "F26-01", name: "Skifreizeit" } });
    renderRoute("/app/mailer/messages/4");
    expect(await screen.findByText("F26-01 · Skifreizeit")).toBeInTheDocument();
  });

  it("refuses to save a message without subject and content", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    let posted = false;
    server.use(
      http.post(api("/api/mailer/messages"), () => {
        posted = true;
        return HttpResponse.json(MESSAGE);
      }),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));
    await user.click(
      within(screen.getByRole("dialog")).getByRole("button", { name: "Als Entwurf speichern" }),
    );

    expect(await screen.findByText("Betreff und Inhalt sind erforderlich.")).toBeInTheDocument();
    expect(posted).toBe(false);
  });

  it("saves a draft and opens it", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/mailer/messages"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MESSAGE);
      }),
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "Sommerfahrt");
    await user.type(dialog.getByLabelText("Inhalt"), "Bitte anmelden.");
    await user.click(dialog.getByRole("button", { name: "Empfänger-Gruppen" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Freizeit-Teilnehmer" }));
    await user.click(dropdown().getByRole("button", { name: "F26-01 · Skifreizeit" }));
    await user.click(dialog.getByRole("button", { name: "Antwort an (E-Mail-Adressen)" }));
    await user.click(dropdown().getByRole("button", { name: "jugend@example.org" }));
    await user.click(dialog.getByRole("button", { name: "Als Entwurf speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      subject: "Sommerfahrt",
      content: "Bitte anmelden.",
      to_groups: [5],
      to_freizeit: 3,
      reply_to_email_address: [2],
    });
    expect(await screen.findByText("Als Entwurf gespeichert.")).toBeInTheDocument();
  });

  it("asks before sending, then creates and submits in one step", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    let submitted = false;
    server.use(
      http.post(api("/api/mailer/messages"), () => HttpResponse.json(MESSAGE)),
      http.post(api("/api/mailer/messages/4/submit"), () => {
        submitted = true;
        return HttpResponse.json({ ...MESSAGE, sent: true });
      }),
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json({ ...MESSAGE, sent: true })),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "Sommerfahrt");
    await user.type(dialog.getByLabelText("Inhalt"), "Bitte anmelden.");
    await user.click(dialog.getByRole("button", { name: "Senden" }));

    const confirmDialog = await screen.findByText(
      "Nachricht jetzt an alle Empfänger versenden?",
    );
    expect(confirmDialog).toBeInTheDocument();
    expect(submitted).toBe(false);

    await user.click(
      within(confirmDialog.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Bestätigen",
      }),
    );
    await waitFor(() => expect(submitted).toBe(true));
    expect(await screen.findByText("Nachricht versendet.")).toBeInTheDocument();
  });

  it("does not send when the confirmation is declined", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    let posted = false;
    server.use(
      http.post(api("/api/mailer/messages"), () => {
        posted = true;
        return HttpResponse.json(MESSAGE);
      }),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "S");
    await user.type(dialog.getByLabelText("Inhalt"), "I");
    await user.click(dialog.getByRole("button", { name: "Senden" }));

    const confirmText = await screen.findByText("Nachricht jetzt an alle Empfänger versenden?");
    await user.click(
      within(confirmText.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Abbrechen",
      }),
    );
    expect(posted).toBe(false);
  });

  it("asks before discarding an edited draft, and keeps it when declined", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "Angefangen");
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));

    const confirmText = await screen.findByText("Änderungen verwerfen?");
    await user.click(
      within(confirmText.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Abbrechen",
      }),
    );
    expect(screen.getByDisplayValue("Angefangen")).toBeInTheDocument();
  });

  it("closes an untouched compose dialog without asking", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reports a rejected create on the compose form", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    server.use(
      http.post(api("/api/mailer/messages"), () =>
        djangoValidation({ subject: ["Der Betreff ist zu lang."] }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "S");
    await user.type(dialog.getByLabelText("Inhalt"), "I");
    await user.click(dialog.getByRole("button", { name: "Als Entwurf speichern" }));

    expect(await screen.findAllByText("Der Betreff ist zu lang.")).not.toHaveLength(0);
  });

  it("reports a rejected send without closing the compose dialog", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    listReturns();
    server.use(
      http.post(api("/api/mailer/messages"), () =>
        djangoValidation({ subject: ["Der Betreff ist zu lang."] }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Betreff"), "S");
    await user.type(dialog.getByLabelText("Inhalt"), "I");
    await user.click(dialog.getByRole("button", { name: "Senden" }));

    const confirmText = await screen.findByText("Nachricht jetzt an alle Empfänger versenden?");
    await user.click(
      within(confirmText.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Bestätigen",
      }),
    );

    expect(await screen.findAllByText("Der Betreff ist zu lang.")).not.toHaveLength(0);
    expect(screen.getByDisplayValue("S")).toBeInTheDocument();
  });

  it("offers editing, sending and deleting on an unsent message", async () => {
    detailReturns();
    const { user } = renderRoute("/app/mailer/messages/4");

    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    expect(screen.getByRole("button", { name: "Versenden" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Löschen" })).toBeInTheDocument();
  });

  it("freezes a sent message", async () => {
    detailReturns({ sent: true });
    renderRoute("/app/mailer/messages/4");
    await screen.findByText("Bitte anmelden.");
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Aktionen/ })).not.toBeInTheDocument();
  });

  it("sends an existing draft after confirmation", async () => {
    detailReturns();
    let submitted = false;
    server.use(
      http.post(api("/api/mailer/messages/4/submit"), () => {
        submitted = true;
        return HttpResponse.json({ ...MESSAGE, sent: true });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Versenden" }));

    const confirmText = await screen.findByText("Nachricht jetzt an alle Empfänger versenden?");
    await user.click(
      within(confirmText.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Bestätigen",
      }),
    );
    await waitFor(() => expect(submitted).toBe(true));
    expect(await screen.findByText("Nachricht versendet.")).toBeInTheDocument();
  });

  it("reports a refused send", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/mailer/messages/4/submit"), () =>
        HttpResponse.json({ detail: "Es fehlen Empfänger." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Versenden" }));
    const confirmText = await screen.findByText("Nachricht jetzt an alle Empfänger versenden?");
    await user.click(
      within(confirmText.closest(".modal") as HTMLElement).getByRole("button", {
        name: "Bestätigen",
      }),
    );
    expect(await screen.findByText("Es fehlen Empfänger.")).toBeInTheDocument();
  });

  it("saves an inline edit of the message", async () => {
    detailReturns();
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/mailer/messages/4"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MESSAGE);
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const subject = screen.getByDisplayValue("Sommerfahrt");
    await user.clear(subject);
    await user.type(subject, "Sommerfahrt 2026");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ subject: "Sommerfahrt 2026", to_groups: [5] });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected inline save without leaving edit mode", async () => {
    detailReturns();
    server.use(
      http.put(api("/api/mailer/messages/4"), () =>
        djangoValidation({ content: ["Der Inhalt fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(await screen.findAllByText("Der Inhalt fehlt.")).not.toHaveLength(0);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("leaves edit mode on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Sommerfahrt")).not.toBeInTheDocument();
  });

  it("deletes a draft once confirmed", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/mailer/messages"), () => HttpResponse.json([])),
      http.delete(api("/api/mailer/messages/4"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Nachricht gelöscht.")).toBeInTheDocument();
  });

  it("lists existing attachments and links them", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/mailer/messages/4/attachments"), () =>
        HttpResponse.json([{ id: 8, filename: "Programm.pdf", url: "/media/programm.pdf" }]),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("tab", { name: "Anhänge" }));

    expect(await screen.findByRole("link", { name: "Programm.pdf" })).toHaveAttribute(
      "href",
      "http://localhost:8000/media/programm.pdf",
    );
  });

  it("says so when there are no attachments", async () => {
    detailReturns();
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("tab", { name: "Anhänge" }));
    expect(await screen.findByText("Keine Anhänge.")).toBeInTheDocument();
  });

  it("stages an attachment and uploads it only on save", async () => {
    detailReturns();
    let uploaded: string | undefined;
    server.use(
      http.put(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.post(api("/api/mailer/messages/4/attachments"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ id: 9, filename: "Programm.pdf", url: "/media/p.pdf" });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Anhänge" }));
    await user.click(await screen.findByRole("button", { name: "+ Anhang" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.upload(
      dialog.getByLabelText(/^Datei/),
      new File(["x"], "Programm.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    expect(uploaded).toBeUndefined();
    expect(screen.getByText("(neu)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(uploaded).toBe("Programm.pdf"));
  });

  it("drops a staged attachment again without uploading it", async () => {
    detailReturns();
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Anhänge" }));
    await user.click(await screen.findByRole("button", { name: "+ Anhang" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.upload(
      dialog.getByLabelText(/^Datei/),
      new File(["x"], "Falsch.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(screen.queryByText(/Falsch\.pdf/)).not.toBeInTheDocument();
  });

  it("removes an existing attachment on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/mailer/messages/4/attachments"), () =>
        HttpResponse.json([{ id: 8, filename: "Alt.pdf", url: "/media/alt.pdf" }]),
      ),
      http.put(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.delete(api("/api/mailer/attachments/8"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Anhänge" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

describe("mailer — remaining paths", () => {
  /** The message list, for the tests below that live outside its describe. */
  function messageListReturns(rows: unknown[] = [MESSAGE_BRIEF]) {
    messageBase();
    server.use(http.get(api("/api/mailer/messages"), () => HttpResponse.json(rows)));
  }

  it("opens a message from its row and shows an em dash for a missing author", async () => {
    messageListReturns();
    server.use(
      http.get(api("/api/mailer/messages/4"), () =>
        HttpResponse.json({ ...MESSAGE, created_by: null }),
      ),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByText("Sommerfahrt"));

    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
    // "Erstellt von" falls back to an em dash rather than showing "undefined".
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("closes the compose dialog with ×", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    messageListReturns();
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("reports a rejected save whose body is not JSON", async () => {
    messageBase();
    server.use(
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
      http.put(api("/api/mailer/messages/4"), () =>
        new HttpResponse("<html>500</html>", { status: 500 }),
      ),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("closes the attachment dialog with × and clears a chosen file", async () => {
    messageBase();
    server.use(
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Anhänge" }));
    await user.click(await screen.findByRole("button", { name: "+ Anhang" }));

    const dialog = await screen.findByRole("dialog");
    const file = within(dialog).getByLabelText(/^Datei/);
    await user.upload(file, new File(["x"], "a.pdf", { type: "application/pdf" }));
    await user.upload(file, []);
    expect(within(dialog).getByRole("button", { name: "Hinzufügen" })).toBeDisabled();

    await user.click(within(dialog).getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("saves without uploading when an attachment row carries no file", async () => {
    messageBase();
    let uploaded = false;
    server.use(
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.get(api("/api/mailer/messages/4/attachments"), () =>
        HttpResponse.json([{ id: 8, filename: "Alt.pdf", url: null }]),
      ),
      http.put(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.post(api("/api/mailer/messages/4/attachments"), () => {
        uploaded = true;
        return HttpResponse.json({ id: 9 });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Anhänge" }));
    // A row the API returned without a URL still renders as staged.
    expect(await screen.findByText(/\(neu\)/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument(),
    );
    expect(uploaded).toBe(false);
  });

  it("opens an address from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["mailer.add_emailaddress"] });
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([ADDRESS_BRIEF])),
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
    );
    const { user } = renderRoute("/app/mailer/addresses");

    await user.click(await screen.findByRole("button", { name: "Neue Adresse" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("jugend@example.org"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });
});

describe("mailer — every field", () => {
  it("Nachricht: carries every edited field into the PUT", async () => {
    messageBase();
    server.use(
      http.get(api("/api/mailer/messages/4"), () => HttpResponse.json(MESSAGE)),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/mailer/messages/4"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MESSAGE);
      }),
    );
    const { user } = renderRoute("/app/mailer/messages/4");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ subject: "Text", content: "Text" });
  });

  it("Nachricht: shows an em dash for the optional fields left empty", async () => {
    messageBase();
    server.use(
      http.get(api("/api/mailer/messages/4"), () =>
        HttpResponse.json({
          ...MESSAGE,
          content: "",
          recipients: "",
          created_by: null,
          to_groups: [],
          to_members: [],
          to_freizeit: null,
          reply_to: [],
          reply_to_email_address: [],
        }),
      ),
      http.get(api("/api/mailer/messages/4/attachments"), () => HttpResponse.json([])),
    );
    renderRoute("/app/mailer/messages/4");
    await screen.findAllByText("Sommerfahrt");
    expect((document.querySelector("form") as HTMLElement).textContent).toContain("—");
  });

  it("Nachricht: fills every field of the compose form", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    messageBase();
    server.use(http.get(api("/api/mailer/messages"), () => HttpResponse.json([])));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/mailer/messages"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ subject: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/mailer/messages");
    await user.click(await screen.findByRole("button", { name: "Neue Nachricht" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Als Entwurf speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      subject: "Text",
      content: "Text",
      to_groups: [5],
      to_members: [7],
    });
  });

  it("E-Mail-Adresse: carries every edited field into the PUT", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () => HttpResponse.json(ADDRESS)),
    );
    let put: Record<string, unknown> | null = null;
    server.use(
      http.put(api("/api/mailer/email-addresses/2"), async ({ request }) => {
        put = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(ADDRESS);
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses/2");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(put).not.toBeNull());
    expect(put).toMatchObject({ name: "Text", internal_only: false });
  });

  it("E-Mail-Adresse: shows an em dash for the optional lists left empty", async () => {
    addressBase();
    server.use(
      http.get(api("/api/mailer/email-addresses/2"), () =>
        HttpResponse.json({
          ...ADDRESS,
          forwards: [],
          to_members: [],
          to_groups: [],
          allowed_senders: [],
        }),
      ),
    );
    renderRoute("/app/mailer/addresses/2");
    await screen.findAllByText("jugend");
    expect((document.querySelector("form") as HTMLElement).textContent).toContain("—");
  });

  it("E-Mail-Adresse: fills every field of the create form", async () => {
    useMe({ permissions: ["mailer.add_emailaddress"] });
    addressBase();
    server.use(http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([])));
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/mailer/email-addresses"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ name: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/mailer/addresses");
    await user.click(await screen.findByRole("button", { name: "Neue Adresse" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ name: "Text", internal_only: true });
  });
});
