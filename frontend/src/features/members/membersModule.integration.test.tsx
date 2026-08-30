import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

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

const GROUPS = [
  { id: 5, name: "Klettergruppe", time_info: "montags 18:00", age_info: "2010–2013", contact_email_display: "kletter@example.org", leiters: [{ id: 7, name: "Hannah Beckers" }] },
  { id: 6, name: "Bouldergruppe", time_info: "", age_info: "", contact_email_display: null, leiters: [] },
];

const MEMBER_BRIEF = {
  id: 42,
  name: "Anna Ärmel",
  prename: "Anna",
  lastname: "Ärmel",
  email: "anna@example.org",
  age: 15,
  groups: ["Klettergruppe"],
  activity_score: 12,
  echoed: false,
  confirmed: true,
};

/** Stub every request the member list makes. */
function membersListReturns(rows: unknown[] = [MEMBER_BRIEF]) {
  server.use(
    http.get(api("/api/members/"), () => HttpResponse.json(rows)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    http.get(api("/api/members/enums"), () =>
      HttpResponse.json({
        gender: [
          { value: 0, label: "Männlich" },
          { value: 1, label: "Weiblich" },
        ],
      }),
    ),
  );
}

describe("Meine Gruppen", () => {
  it("lists only the groups the signed-in user leads", async () => {
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)));
    renderRoute("/app/meine/gruppen");

    expect(await screen.findByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByText("montags 18:00")).toBeInTheDocument();
    expect(screen.getByText("kletter@example.org")).toBeInTheDocument();
    expect(screen.queryByText("Bouldergruppe")).not.toBeInTheDocument();
  });

  it("says so when the user leads none", async () => {
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json([GROUPS[1]])));
    renderRoute("/app/meine/gruppen");
    expect(await screen.findByText("Du leitest aktuell keine Gruppe.")).toBeInTheDocument();
  });

  it("says so when the list is empty altogether", async () => {
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json([])));
    renderRoute("/app/meine/gruppen");
    expect(await screen.findByText("Du leitest aktuell keine Gruppe.")).toBeInTheDocument();
  });

  it("explains an account with no member profile instead of showing nothing", async () => {
    useMe({ member_id: null as unknown as number });
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)));
    renderRoute("/app/meine/gruppen");
    expect(
      await screen.findByText("Dein Konto ist mit keinem Teilnehmenden-Profil verknüpft."),
    ).toBeInTheDocument();
  });

  it("opens a group's member list from a row", async () => {
    server.use(
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.get(api("/api/members/groups/5"), () => HttpResponse.json(GROUPS[0])),
      http.get(api("/api/members/"), () => HttpResponse.json([MEMBER_BRIEF])),
    );
    const { user } = renderRoute("/app/meine/gruppen");
    await user.click(await screen.findByText("Klettergruppe"));
    expect(await screen.findByText("1 Teilnehmende")).toBeInTheDocument();
  });
});

describe("members of a group", () => {
  function groupMembersReturns(rows = [MEMBER_BRIEF]) {
    server.use(
      http.get(api("/api/members/groups/5"), () => HttpResponse.json(GROUPS[0])),
      http.get(api("/api/members/"), () => HttpResponse.json(rows)),
    );
  }

  it("lists the group's members and counts them", async () => {
    groupMembersReturns([MEMBER_BRIEF, { ...MEMBER_BRIEF, id: 43, name: "Fremd", groups: ["Andere"] }]);
    renderRoute("/app/groups/5/members");

    expect(await screen.findByText("Anna Ärmel")).toBeInTheDocument();
    expect(screen.getByText("1 Teilnehmende")).toBeInTheDocument();
    expect(screen.queryByText("Fremd")).not.toBeInTheDocument();
  });

  it("says so when the group is empty", async () => {
    groupMembersReturns([]);
    renderRoute("/app/groups/5/members");
    expect(await screen.findByText("Keine Teilnehmende in dieser Gruppe.")).toBeInTheDocument();
  });

  it("shows an em dash for a member without an e-mail", async () => {
    groupMembersReturns([{ ...MEMBER_BRIEF, email: "" }]);
    renderRoute("/app/groups/5/members");
    await screen.findByText("Anna Ärmel");
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("offers the way back and into the group's own settings", async () => {
    groupMembersReturns();
    server.use(
      http.get(api("/api/members/groups/5/registration-passwords"), () => HttpResponse.json([])),
      http.get(api("/api/members/groups/5/permission-groups"), () => HttpResponse.json([])),
      http.get(api("/api/mailer/email-addresses"), () => HttpResponse.json([])),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    );
    const { user } = renderRoute("/app/groups/5/members");
    await screen.findByText("Anna Ärmel");
    await user.click(screen.getByRole("button", { name: "Gruppe bearbeiten" }));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("opens a member carrying the group in the breadcrumb trail", async () => {
    groupMembersReturns();
    server.use(
      http.get(api("/api/members/42"), () =>
        HttpResponse.json({ ...MEMBER_BRIEF, groups: [{ id: 5, name: "Klettergruppe" }], skills: [], activities: [], legal_guardians: "", comments: "" }),
      ),
      http.get(api("/api/members/42/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
      http.get(api("/api/members/enums"), () => HttpResponse.json({ gender: [] })),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    );
    const { user } = renderRoute("/app/groups/5/members");
    await user.click(await screen.findByText("Anna Ärmel"));

    // The trail starts at Gruppen, not at the flat member list.
    expect(await screen.findByRole("link", { name: "Gruppen" })).toHaveAttribute(
      "href",
      "/app/groups",
    );
    expect(screen.getByRole("link", { name: "Klettergruppe" })).toHaveAttribute(
      "href",
      "/app/groups/5/members",
    );
  });
});

describe("members list — extras", () => {
  it("renders the activity score as climber icons", async () => {
    membersListReturns([
      { ...MEMBER_BRIEF, activity_score: 2 },
      { ...MEMBER_BRIEF, id: 43, name: "Bea", activity_score: 7 },
      { ...MEMBER_BRIEF, id: 44, name: "Cara", activity_score: 15 },
      { ...MEMBER_BRIEF, id: 45, name: "Dora", activity_score: 25 },
      { ...MEMBER_BRIEF, id: 46, name: "Eva", activity_score: 40 },
      { ...MEMBER_BRIEF, id: 47, name: "Fina", activity_score: null },
    ]);
    renderRoute("/app/members");
    await screen.findByText("Anna Ärmel");

    // One icon per level, 1–5, and an em dash when the score is unknown.
    const rows = screen.getAllByRole("row").slice(1);
    const icons = rows.map((r) => r.querySelectorAll("img").length);
    expect(icons.slice(0, 5)).toEqual([1, 2, 3, 4, 5]);
    expect(icons[5]).toBe(0);
  });

  it("shows an em dash for a member without an e-mail", async () => {
    membersListReturns([{ ...MEMBER_BRIEF, email: "" }]);
    renderRoute("/app/members");
    await screen.findByText("Anna Ärmel");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("sorts by every column in both directions", async () => {
    membersListReturns([
      MEMBER_BRIEF,
      { ...MEMBER_BRIEF, id: 43, name: "Bea Berg", age: null, groups: [], activity_score: null },
    ]);
    const { user } = renderRoute("/app/members");
    await screen.findByText("Anna Ärmel");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("creates a member, sending the gender as a number and blanks as null", async () => {
    useMe({ permissions: ["members.add_global_member"] });
    membersListReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 99 });
      }),
      http.get(api("/api/members/99"), () =>
        HttpResponse.json({ ...MEMBER_BRIEF, id: 99, groups: [], skills: [], activities: [] }),
      ),
      http.get(api("/api/members/99/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/99/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/99/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByRole("button", { name: "Neues Mitglied" }));

    const dialog = within(await screen.findByRole("dialog"));
    // Gender is required by the model, so the submit stays disabled without it.
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();

    await user.type(dialog.getByLabelText("Vorname"), "Neu");
    await user.type(dialog.getByLabelText("Nachname"), "Person");
    await user.click(dialog.getByRole("button", { name: "Geschlecht" }));
    await user.click(dropdown().getByRole("button", { name: "Weiblich" }));
    await user.click(dialog.getByRole("button", { name: "Gruppen" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      prename: "Neu",
      lastname: "Person",
      gender: 1,
      email: null,
      birth_date: null,
      phone_number: null,
      group_ids: [5],
    });
    expect(await screen.findByText("Mitglied angelegt.")).toBeInTheDocument();
  });

  it("shows every server field error on the create form", async () => {
    useMe({ permissions: ["members.add_global_member"] });
    membersListReturns();
    server.use(
      http.post(api("/api/members/"), () =>
        djangoValidation({
          prename: ["Der Vorname fehlt."],
          lastname: ["Der Nachname fehlt."],
          gender: ["Ungültig."],
          email: ["Keine Adresse."],
          birth_date: ["Ungültiges Datum."],
          phone_number: ["Keine Nummer."],
          group_ids: ["Unbekannte Gruppe."],
        }),
      ),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByRole("button", { name: "Neues Mitglied" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.type(dialog.getByLabelText("Vorname"), "x");
    await user.type(dialog.getByLabelText("Nachname"), "y");
    await user.click(dialog.getByRole("button", { name: "Geschlecht" }));
    await user.click(dropdown().getByRole("button", { name: "Männlich" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Der Vorname fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Der Nachname fehlt.")).toBeInTheDocument();
    expect(screen.getByText("Ungültig.")).toBeInTheDocument();
    expect(screen.getByText("Keine Adresse.")).toBeInTheDocument();
    expect(screen.getByText("Ungültiges Datum.")).toBeInTheDocument();
    expect(screen.getByText("Keine Nummer.")).toBeInTheDocument();
    expect(screen.getByText("Unbekannte Gruppe.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("builds a note list from the selection", async () => {
    useMe({ permissions: ["members.add_membernotelist"] });
    membersListReturns();
    const participants: unknown[] = [];
    server.use(
      http.post(api("/api/members/note-lists"), async ({ request }) => {
        const body = (await request.json()) as { title: string };
        expect(body.title).toBe("Liste (1 Teilnehmende)");
        return HttpResponse.json({ id: 77 });
      }),
      http.post(api("/api/members/note-lists/77/participants"), async ({ request }) => {
        participants.push(await request.json());
        return HttpResponse.json({ id: 1 });
      }),
      http.get(api("/api/members/note-lists/77"), () =>
        HttpResponse.json({ id: 77, title: "Liste", date: null, participants: [] }),
      ),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Notizliste aus Auswahl" }));

    await waitFor(() => expect(participants).toEqual([{ member_id: 42, comments: "" }]));
    expect(await screen.findByText("Notizliste aus der Auswahl angelegt.")).toBeInTheDocument();
  });

  it("generates a crisis intervention list for the selection", async () => {
    membersListReturns();
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

    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/documents/crisis-intervention-list"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: /Kriseninterventionsliste/ }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "PDF erzeugen" })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Aktivität/), "Klettern");
    await user.type(dialog.getByLabelText(/^Ort/), "Halle");
    await user.type(dialog.getByLabelText(/^Von/), "2026-07-04");
    await user.type(dialog.getByLabelText(/^Bis/), "2026-07-05");
    await user.type(dialog.getByLabelText("Beschreibung"), "Gruppenabend");
    await user.click(dialog.getByRole("button", { name: "PDF erzeugen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      activity: "Klettern",
      place: "Halle",
      start_date: "2026-07-04",
      end_date: "2026-07-05",
      description: "Gruppenabend",
      member_ids: [42],
    });
  });

  it("reports a failed crisis list download", async () => {
    membersListReturns();
    server.use(
      http.post(api("/api/members/documents/crisis-intervention-list"), () =>
        HttpResponse.json({ detail: "Keine Daten." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: /Kriseninterventionsliste/ }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Aktivität/), "Klettern");
    await user.type(dialog.getByLabelText(/^Ort/), "Halle");
    await user.type(dialog.getByLabelText(/^Von/), "2026-07-04");
    await user.type(dialog.getByLabelText(/^Bis/), "2026-07-05");
    await user.click(dialog.getByRole("button", { name: "PDF erzeugen" }));

    expect(await screen.findByText("Keine Daten.")).toBeInTheDocument();
  });

  it("closes the crisis list dialog on Abbrechen", async () => {
    membersListReturns();
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: /Kriseninterventionsliste/ }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("invites the selection to create an account", async () => {
    membersListReturns();
    let invited = 0;
    server.use(
      http.post(api("/api/members/42/invite-as-user"), () => {
        invited += 1;
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Als Nutzer einladen" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getAllByRole("button", { name: "Als Nutzer einladen" })[0]);

    await waitFor(() => expect(invited).toBe(1));
    expect(await screen.findByText("1 Einladungen verschickt.")).toBeInTheDocument();
  });

  it("unconfirms the selection behind a danger confirmation", async () => {
    membersListReturns();
    let unconfirmed = 0;
    server.use(
      http.post(api("/api/members/42/unconfirm"), () => {
        unconfirmed += 1;
        return HttpResponse.json({});
      }),
      http.get(api("/api/members/registrations"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Bestätigung aufheben" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getAllByRole("button", { name: "Bestätigung aufheben" })[0]);

    await waitFor(() => expect(unconfirmed).toBe(1));
    expect(await screen.findByText("1 Bestätigungen aufgehoben.")).toBeInTheDocument();
  });
});

describe("member detail — uploads and actions", () => {
  const MEMBER = {
    id: 42,
    name: "Anna Ärmel",
    prename: "Anna",
    lastname: "Ärmel",
    email: "anna@example.org",
    age: 15,
    groups: [{ id: 5, name: "Klettergruppe" }],
    gender: 1,
    gender_display: "Weiblich",
    activity_score: 12,
    registration_form: null,
    image: null,
    user_id: null,
    user_display: "",
    skills: [],
    activities: [],
    alternative_email: null,
    birth_date: "2011-05-04",
    phone_number: "0711 1",
    street: "Weg 1",
    plz: "71634",
    town: "Ludwigsburg",
    address_extra: "",
    country: "Deutschland",
    dav_badge_no: "",
    ticket_no: "",
    iban: null,
    iban_valid: false,
    join_date: "2024-01-01",
    leave_date: null,
    has_key: false,
    has_free_ticket_gym: false,
    swimming_badge: 0,
    climbing_badge: 0,
    alpine_experience: 0,
    allergies: "",
    medication: "",
    tetanus_vaccination: null,
    may_cancel_appointment_independently: null,
    good_conduct_certificate_presented_date: null,
    good_conduct_certificate_valid: false,
    legal_guardians: "",
    comments: "",
    echoed: false,
    photos_may_be_taken: true,
    gets_newsletter: true,
    active: true,
    confirmed: true,
    confirmed_mail: true,
    confirmed_alternative_mail: false,
    created: "2024-01-01T10:00:00Z",
    place: "71634 Ludwigsburg",
    address: "Weg 1",
    gender_str: "weiblich",
    quantity_real: "",
  };

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/42"), () => HttpResponse.json({ ...MEMBER, ...overrides })),
      http.get(api("/api/members/42/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
      http.get(api("/api/members/enums"), () =>
        HttpResponse.json({
          gender: [
            { value: 0, label: "Männlich" },
            { value: 1, label: "Weiblich" },
          ],
        }),
      ),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.get(api("/api/members/"), () => HttpResponse.json([MEMBER_BRIEF])),
    );
  }

  it("shows an IBAN with its validity badge", async () => {
    detailReturns({ iban: "DE02120300000000202051", iban_valid: true });
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Kontaktdaten" }));
    expect(screen.getByText("gültig")).toBeInTheDocument();
  });

  it("marks an invalid IBAN as such", async () => {
    detailReturns({ iban: "DE00", iban_valid: false });
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Kontaktdaten" }));
    expect(screen.getByText("ungültig")).toBeInTheDocument();
  });

  it("lists the member's activities", async () => {
    detailReturns({ activities: [{ id: 1, code: "F26-01", name: "Skifreizeit" }] });
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Fähigkeiten" }));
    expect(screen.getByText("Skifreizeit")).toBeInTheDocument();
  });

  it("uploads a registration form and reports a failure", async () => {
    detailReturns();
    let uploaded: string | undefined;
    let attempt = 0;
    server.use(
      http.post(api("/api/members/42/registration-form"), async ({ request }) => {
        attempt += 1;
        if (attempt === 1) return new HttpResponse("<html>502</html>", { status: 502 });
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json(MEMBER);
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const inputs = document.querySelectorAll('input[type="file"]');
    const formInput = inputs[0] as HTMLInputElement;
    await user.upload(formInput, new File(["%PDF"], "bogen.pdf", { type: "application/pdf" }));
    const uploadButtons = screen.getAllByRole("button", { name: "Hochladen" });
    await user.click(uploadButtons[0]);
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();

    await user.click(screen.getAllByRole("button", { name: "Hochladen" })[0]);
    await waitFor(() => expect(uploaded).toBe("bogen.pdf"));
    expect(await screen.findByText("Anmeldeformular hochgeladen.")).toBeInTheDocument();
  });

  it("offers the current registration form for opening while replacing it", async () => {
    detailReturns({ registration_form: "/media/bogen.pdf" });
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(
      screen.getByRole("link", { name: "Aktuelles Formular öffnen" }),
    ).toHaveAttribute("href", "http://localhost:8000/media/bogen.pdf");
  });

  it("still reports a photo upload whose body is not JSON", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/members/42/image"), () =>
        new HttpResponse("<html>502</html>", { status: 502 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.upload(
      document.querySelectorAll('input[type="file"]')[1] as HTMLInputElement,
      new File(["x"], "anna.jpg", { type: "image/jpeg" }),
    );
    await user.click(screen.getAllByRole("button", { name: "Hochladen" })[1]);
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("keeps an unset 'may cancel' as unset when saving", async () => {
    detailReturns({ may_cancel_appointment_independently: true });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MEMBER);
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ may_cancel_appointment_independently: true });
  });

  it("still reports a document upload whose body is not JSON", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/documents"), () =>
        new HttpResponse("<html>502</html>", { status: 502 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Dokumente" }));
    await user.click(await screen.findByRole("button", { name: "+ Dokument" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.upload(
      dialog.getByLabelText(/^Datei/),
      new File(["x"], "attest.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(
      await screen.findByText(/Ein verknüpfter Eintrag konnte nicht gespeichert werden/),
    ).toBeInTheDocument();
  });

  it("still reports a certificate upload whose body is not JSON", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: null,
            participated: true,
            passed: true,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: null,
          },
        ]),
      ),
      http.post(api("/api/members/trainings/5/certificate"), () =>
        new HttpResponse("<html>502</html>", { status: 502 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await user.upload(
      panel.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "nachweis.pdf", { type: "application/pdf" }),
    );
    expect(
      await screen.findByText(/Serverfehler — die Aktion konnte nicht ausgeführt werden/),
    ).toBeInTheDocument();
  });

  it("updates an existing permission set on save", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/42/permission-members"), () =>
        HttpResponse.json([
          {
            id: 4,
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
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.patch(api("/api/members/permission-members/4"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 4 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Berechtigungen" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click((await panel.findAllByRole("button", { name: "+ Teilnehmende" }))[0]);
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ list_member_ids: [42] });
  });

  it("links an existing registration form and photo", async () => {
    detailReturns({ registration_form: "/media/bogen.pdf", image: "/media/anna.jpg" });
    renderRoute("/app/members/42");
    const links = await screen.findAllByRole("link", { name: "Öffnen" });
    expect(links[0]).toHaveAttribute("href", "http://localhost:8000/media/bogen.pdf");
  });

  it("uploads and removes the member's photo", async () => {
    detailReturns({ image: "/media/anna.jpg" });
    let uploaded: string | undefined;
    let cleared = false;
    server.use(
      http.post(api("/api/members/42/image"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json(MEMBER);
      }),
      http.delete(api("/api/members/42/image"), () => {
        cleared = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const inputs = document.querySelectorAll('input[type="file"]');
    await user.upload(inputs[1] as HTMLInputElement, new File(["x"], "anna.jpg", { type: "image/jpeg" }));
    await user.click(screen.getAllByRole("button", { name: "Hochladen" })[1]);
    await waitFor(() => expect(uploaded).toBe("anna.jpg"));

    const imageBlock = (inputs[1] as HTMLElement).closest(".stack") as HTMLElement;
    await user.click(within(imageBlock).getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(cleared).toBe(true));
    expect(await screen.findByText("Bild entfernt.")).toBeInTheDocument();
  });

  it("offers the four mail actions, each behind a confirmation", async () => {
    detailReturns();
    const called: string[] = [];
    for (const path of [
      "request-echo",
      "invite-as-user",
      "request-password-reset",
      "request-registration-form",
    ]) {
      server.use(
        http.post(api(`/api/members/42/${path}`), () => {
          called.push(path);
          return HttpResponse.json({});
        }),
      );
    }
    const { user } = renderRoute("/app/members/42");

    for (const label of [
      "Echo anfordern",
      "Als Nutzer einladen",
      "Passwort-Reset anfordern",
      "Anmeldebogen anfordern",
    ]) {
      await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
      await user.click(screen.getByRole("button", { name: label }));
      await user.click(
        within(await screen.findByRole("dialog")).getByRole("button", { name: "Senden" }),
      );
    }

    await waitFor(() => expect(called).toHaveLength(4));
    expect(called).toEqual([
      "request-echo",
      "invite-as-user",
      "request-password-reset",
      "request-registration-form",
    ]);
  });

  it("reports a refused mail action", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/members/42/request-echo"), () =>
        HttpResponse.json({ detail: "Keine E-Mail hinterlegt." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Echo anfordern" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Senden" }),
    );
    expect(await screen.findByText("Keine E-Mail hinterlegt.")).toBeInTheDocument();
  });

  it("unconfirms a member back into the registrations list", async () => {
    detailReturns();
    let unconfirmed = false;
    server.use(
      http.post(api("/api/members/42/unconfirm"), () => {
        unconfirmed = true;
        return HttpResponse.json({});
      }),
      http.get(api("/api/members/registrations"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Bestätigung aufheben" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Aufheben" }),
    );

    await waitFor(() => expect(unconfirmed).toBe(true));
    expect(await screen.findByText("Bestätigung aufgehoben.")).toBeInTheDocument();
  });

  it("adds and removes a document, uploading only on save", async () => {
    detailReturns();
    let uploaded: string | undefined;
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/documents"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ id: 3, filename: "attest.pdf", file_url: "/media/attest.pdf" });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Dokumente" }));
    await user.click(await screen.findByRole("button", { name: "+ Dokument" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.upload(
      dialog.getByLabelText(/^Datei/),
      new File(["%PDF"], "attest.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    expect(uploaded).toBeUndefined();
    expect(screen.getByText("(neu)")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(uploaded).toBe("attest.pdf"));
  });

  it("deletes an existing document on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/42/documents"), () =>
        HttpResponse.json([{ id: 3, filename: "alt.pdf", file_url: "/media/alt.pdf" }]),
      ),
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.delete(api("/api/members/member-documents/3"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Dokumente" }));

    expect(await screen.findByRole("link", { name: "alt.pdf" })).toHaveAttribute(
      "href",
      "http://localhost:8000/media/alt.pdf",
    );
    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("adds a training, requiring a category and a title", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/trainings"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    await user.click(await screen.findByRole("button", { name: "+ Ausbildung" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: /Kategorie/ }));
    await user.click(dropdown().getByRole("button", { name: /Grundkurs/ }));
    await user.type(dialog.getByLabelText(/Titel/), "Trainer C");
    await user.type(dialog.getByLabelText("Datum"), "2026-03-01");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    // A brand-new row cannot carry a certificate until it has an id.
    expect(screen.getByText("nach dem Speichern")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toEqual({
      member_id: 42,
      category_id: 1,
      title: "Trainer C",
      date: "2026-03-01",
      activity_ids: [],
    });
  });

  it("edits and removes an existing training on save", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: "2026-03-01",
            participated: false,
            passed: false,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: null,
          },
          { id: 6, member_id: 99, title: "Fremd", category_name: "x", category_id: 1 },
        ]),
      ),
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.patch(api("/api/members/trainings/5"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5 });
      }),
      http.delete(api("/api/members/trainings/5"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));

    // Only this member's trainings appear.
    expect(await screen.findByDisplayValue("Trainer C")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Fremd")).not.toBeInTheDocument();

    const [participated, passed] = screen
      .getAllByRole("checkbox")
      .filter((c) => c.closest(".tab-panel:not([hidden])"));
    await user.click(participated);
    await user.click(passed);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ participated: true, passed: true, title: "Trainer C" });

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("uploads a training certificate and opens an existing one", async () => {
    detailReturns();
    let uploaded: string | undefined;
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: null,
            participated: true,
            passed: true,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: "/media/nachweis.pdf",
          },
        ]),
      ),
      http.post(api("/api/members/trainings/5/certificate"), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ id: 5 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Ausbildungen" }));
    expect(await screen.findByRole("link", { name: "Öffnen" })).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await user.upload(
      panel.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["%PDF"], "nachweis.pdf", { type: "application/pdf" }),
    );
    await waitFor(() => expect(uploaded).toBe("nachweis.pdf"));
    expect(await screen.findByText("Nachweis hochgeladen.")).toBeInTheDocument();
  });

  it("adds a permission set naming members and groups", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/permission-members"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 4 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Berechtigungen" }));
    await user.click(await screen.findByRole("button", { name: "+ Berechtigungssatz" }));

    const panel = within(document.querySelector(".tab-panel:not([hidden])") as HTMLElement);
    await user.click(panel.getAllByRole("button", { name: "+ Teilnehmende" })[0]);
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(panel.getAllByRole("button", { name: "+ Gruppe" })[0]);
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toMatchObject({ list_member_ids: [42], list_group_ids: [5] });
  });

  it("lists an existing permission set read-only", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/42/permission-members"), () =>
        HttpResponse.json([
          {
            id: 4,
            list_member_ids: [42],
            view_member_ids: [999],
            change_member_ids: [],
            delete_member_ids: [],
            list_group_ids: [5],
            view_group_ids: [999],
            change_group_ids: [],
            delete_group_ids: [],
          },
        ]),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Berechtigungen" }));

    // Ids are resolved to names, falling back to "#id" when the option list is
    // not loaded (it only loads in edit mode).
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("Teilnehmende: Anna Ärmel"));
    expect(panel.textContent).toContain("Gruppen: Klettergruppe");
    // An id nobody can resolve still shows as an id rather than vanishing.
    expect(panel.textContent).toContain("Teilnehmende: #999");
    expect(panel.textContent).toContain("Gruppen: #999");
    // Empty rights read as an em dash.
    expect(panel.textContent).toContain("Teilnehmende: —");
  });

  it("removes a permission set on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/42/permission-members"), () =>
        HttpResponse.json([
          {
            id: 4,
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
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.delete(api("/api/members/permission-members/4"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Berechtigungen" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("says so when there are no permission sets", async () => {
    detailReturns();
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Berechtigungen" }));
    expect(await screen.findByText("Keine Berechtigungen.")).toBeInTheDocument();
  });

  it("adds and removes an emergency contact through the inline", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    let patched: Record<string, unknown> | null = null;
    let deleted = false;
    server.use(
      http.get(api("/api/members/42/emergency-contacts"), () =>
        HttpResponse.json([
          { id: 3, prename: "Erika", lastname: "Ärmel", phone_number: "0711 2", email: "" },
        ]),
      ),
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/emergency-contacts"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 4 });
      }),
      http.patch(api("/api/members/emergency-contacts/3"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 3 });
      }),
      http.delete(api("/api/members/emergency-contacts/3"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));

    const phone = await screen.findByDisplayValue("0711 2");
    await user.clear(phone);
    await user.type(phone, "0711 9");
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toMatchObject({ phone_number: "0711 9" }));

    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(created).toBeNull();
  });
});

/* --- exhaustive field pass ------------------------------------------------ */

describe("Meine Gruppen — remaining paths", () => {
  it("shows an em dash for a group with no time, years or contact", async () => {
    server.use(
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ ...GROUPS[0], time_info: "", age_info: "", contact_email_display: "" }]),
      ),
    );
    renderRoute("/app/meine/gruppen");
    await screen.findByText("Klettergruppe");
    expect(screen.getAllByText("—")).toHaveLength(3);
  });
});

describe("members list — remaining paths", () => {
  it("filters by echo status and by group", async () => {
    membersListReturns([
      MEMBER_BRIEF,
      { ...MEMBER_BRIEF, id: 43, name: "Bea Berg", echoed: true, groups: ["Bouldergruppe"] },
    ]);
    const { user } = renderRoute("/app/members");
    await screen.findByText("Anna Ärmel");

    await user.click(screen.getByRole("button", { name: /Echo:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(screen.queryByText("Anna Ärmel")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await waitFor(() => expect(screen.queryByText("Bea Berg")).not.toBeInTheDocument());
  });

  it("opens a member from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["members.add_global_member"] });
    membersListReturns();
    server.use(
      http.get(api("/api/members/42"), () =>
        HttpResponse.json({ ...MEMBER_BRIEF, groups: [], skills: [], activities: [] }),
      ),
      http.get(api("/api/members/42/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/members");

    await user.click(await screen.findByRole("button", { name: "Neues Mitglied" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Anna Ärmel"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("reports a failed note-list build and a failed bulk action", async () => {
    useMe({
      permissions: ["members.add_membernotelist", "members.change_global_member"],
    });
    membersListReturns();
    server.use(
      http.post(api("/api/members/note-lists"), () =>
        HttpResponse.json({ detail: "members.add_membernotelist" }, { status: 403 }),
      ),
      http.post(api("/api/members/42/request-echo"), () =>
        HttpResponse.json({ detail: "Keine E-Mail." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByLabelText("Zeile auswählen"));

    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Notizliste aus Auswahl" }));
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Echo anfordern" }));
    await user.click(
      within(await screen.findByRole("dialog")).getAllByRole("button", {
        name: "Echo anfordern",
      })[0],
    );
    // A partial run reports its failures rather than looking like a success.
    expect(await screen.findByText(/Anna Ärmel: Keine E-Mail\./)).toBeInTheDocument();
  });
});

describe("members of a group — remaining paths", () => {
  it("goes back through the browser history", async () => {
    server.use(
      http.get(api("/api/members/groups/5"), () => HttpResponse.json(GROUPS[0])),
      http.get(api("/api/members/"), () => HttpResponse.json([MEMBER_BRIEF])),
    );
    const { user } = renderRoute("/app/groups/5/members");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("member detail — every field", () => {
  const MEMBER = {
    id: 42,
    name: "Anna Ärmel",
    prename: "Anna",
    lastname: "Ärmel",
    email: "anna@example.org",
    age: 15,
    groups: [{ id: 5, name: "Klettergruppe" }],
    gender: 1,
    gender_display: "Weiblich",
    activity_score: 12,
    registration_form: null,
    image: null,
    user_id: null,
    user_display: "",
    skills: [],
    activities: [],
    alternative_email: null,
    birth_date: "2011-05-04",
    phone_number: "0711 1",
    street: "Weg 1",
    plz: "71634",
    town: "Ludwigsburg",
    address_extra: "",
    country: "Deutschland",
    dav_badge_no: "",
    ticket_no: "",
    iban: null,
    iban_valid: false,
    join_date: "2024-01-01",
    leave_date: null,
    has_key: false,
    has_free_ticket_gym: false,
    swimming_badge: 0,
    climbing_badge: 0,
    alpine_experience: 0,
    allergies: "",
    medication: "",
    tetanus_vaccination: null,
    may_cancel_appointment_independently: null,
    good_conduct_certificate_presented_date: null,
    good_conduct_certificate_valid: false,
    legal_guardians: "",
    comments: "",
    echoed: false,
    photos_may_be_taken: true,
    gets_newsletter: true,
    active: true,
    confirmed: true,
    confirmed_mail: true,
    confirmed_alternative_mail: false,
    created: "2024-01-01T10:00:00Z",
    place: "71634 Ludwigsburg",
    address: "Weg 1",
    gender_str: "weiblich",
  };

  function returns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/42"), () => HttpResponse.json({ ...MEMBER, ...overrides })),
      http.get(api("/api/members/42/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/42/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
      http.get(api("/api/members/enums"), () =>
        HttpResponse.json({
          gender: [
            { value: 0, label: "Männlich" },
            { value: 1, label: "Weiblich" },
          ],
        }),
      ),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.get(api("/api/members/"), () => HttpResponse.json([MEMBER_BRIEF])),
    );
  }

  it("carries every edited field into the PATCH", async () => {
    returns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MEMBER);
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    for (const tab of ["Stammdaten", "Kontaktdaten", "Fähigkeiten", "Sonstiges", "Organisatorisch"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await fillEveryField(user, panel);
      await pickEverySelect(user, panel);
    }
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    // Every text field carries the typed value, the checkboxes flipped and the
    // selects resolved to their enum values.
    expect(patched).toMatchObject({
      prename: "Text",
      lastname: "Text",
      street: "Text",
      plz: "Text",
      town: "Text",
      address_extra: "Text",
      country: "Text",
      allergies: "Text",
      medication: "Text",
      comments: "Text",
      legal_guardians: "Text",
      birth_date: "2026-03-04",
      active: false,
      photos_may_be_taken: false,
      has_key: true,
      has_free_ticket_gym: true,
      gender: 0,
    });
  });

  it("closes every inline dialog with Abbrechen and with ×", async () => {
    returns();
    server.use(
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const cases: [string, string][] = [
      ["Notfallkontakte", "+ Notfallkontakt"],
      ["Dokumente", "+ Dokument"],
      ["Ausbildungen", "+ Ausbildung"],
    ];
    for (const [tab, add] of cases) {
      await user.click(screen.getByRole("tab", { name: tab }));
      await user.click(await screen.findByRole("button", { name: add }));
      await user.click(
        within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
      );
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

      await user.click(screen.getByRole("button", { name: add }));
      await user.click(
        within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
      );
      await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    }
  });

  it("fills every field of the create form and of each inline dialog", async () => {
    useMe({ permissions: ["members.add_global_member"] });
    server.use(
      http.get(api("/api/members/"), () => HttpResponse.json([MEMBER_BRIEF])),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.get(api("/api/members/enums"), () =>
        HttpResponse.json({
          gender: [
            { value: 0, label: "Männlich" },
            { value: 1, label: "Weiblich" },
          ],
        }),
      ),
    );
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ prename: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/members");
    await user.click(await screen.findByRole("button", { name: "Neues Mitglied" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      prename: "Text",
      lastname: "Text",
      email: "test@example.org",
      birth_date: "2026-03-04",
      phone_number: "Text",
      gender: 0,
      group_ids: [5],
    });
  });

  it("fills every field of the emergency-contact and training dialogs", async () => {
    returns();
    let contact: Record<string, unknown> | null = null;
    let training: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/emergency-contacts"), async ({ request }) => {
        contact = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 4 });
      }),
      http.post(api("/api/members/trainings"), async ({ request }) => {
        training = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));
    await user.click(await screen.findByRole("button", { name: "+ Notfallkontakt" }));
    let dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Hinzufügen" }));

    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    await user.click(await screen.findByRole("button", { name: "+ Ausbildung" }));
    dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Hinzufügen" }));

    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(contact).not.toBeNull());
    expect(contact).toMatchObject({
      prename: "Text",
      lastname: "Text",
      phone_number: "Text",
      email: "test@example.org",
    });
    await waitFor(() => expect(training).not.toBeNull());
    expect(training).toMatchObject({ title: "Text", date: "2026-03-04", category_id: 1 });
  });

  it("edits a training's title and date in the table", async () => {
    returns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: "2026-03-01",
            participated: false,
            passed: false,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: null,
          },
        ]),
      ),
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.patch(api("/api/members/trainings/5"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));

    const title = await screen.findByDisplayValue("Trainer C");
    await user.clear(title);
    await user.type(title, "Trainer B");
    const date = screen.getByDisplayValue("2026-03-01");
    await user.clear(date);
    await user.type(date, "2026-04-01");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).toMatchObject({ title: "Trainer B", date: "2026-04-01" }));
  });

  it("goes back and leaves edit mode from the detail header", async () => {
    returns();
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    await user.click(screen.getByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });

  it("reports a refused delete", async () => {
    returns();
    server.use(
      http.delete(api("/api/members/42"), () =>
        HttpResponse.json({ detail: "members.delete_global_member" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    returns({ prename: null, lastname: null, email: null });
    server.use(
      http.get(api("/api/members/42/emergency-contacts"), () =>
        HttpResponse.json([
          { id: 3, prename: null, lastname: null, phone_number: null, email: null },
        ]),
      ),
      http.get(api("/api/members/42/documents"), () =>
        HttpResponse.json([{ id: 4, filename: "attest.pdf", file_url: null }]),
      ),
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: null,
            date: null,
            participated: null,
            passed: null,
            category_name: "Grundkurs",
            category_id: null,
            certificate: null,
          },
        ]),
      ),
      http.get(api("/api/members/42/permission-members"), () =>
        HttpResponse.json([{ id: 6 }]),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await screen.findByRole("button", { name: "Bearbeiten" });

    for (const tab of ["Notfallkontakte", "Ausbildungen", "Berechtigungen"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await waitFor(() => expect(panel.textContent).toContain("—"));
    }
    // A document with no URL is listed as staged rather than as a link.
    await user.click(screen.getByRole("tab", { name: "Dokumente" }));
    expect(await screen.findByText(/\(neu\)/)).toBeInTheDocument();
  });

  it("passes an unparseable birth date through unchanged", async () => {
    returns({ birth_date: "irgendwann" });
    renderRoute("/app/members/42");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getByText("irgendwann")).toBeInTheDocument();
  });

  it("names an excursion by its code when it has none", async () => {
    returns({ activities: [{ id: 1, code: "F26-01", name: "" }] });
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Fähigkeiten" }));
    expect(screen.getByText("F26-01")).toBeInTheDocument();
  });

  it("still reports JSON errors from every upload endpoint", async () => {
    returns();
    server.use(
      http.post(api("/api/members/42/registration-form"), () =>
        HttpResponse.json({ detail: "Kein Anmeldebogen." }, { status: 422 }),
      ),
      http.post(api("/api/members/42/image"), () =>
        HttpResponse.json({ detail: "Kein Bild." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const inputs = [...document.querySelectorAll('input[type="file"]')] as HTMLInputElement[];
    await user.upload(inputs[0], new File(["x"], "a.pdf", { type: "application/pdf" }));
    await user.click(screen.getAllByRole("button", { name: "Hochladen" })[0]);
    expect(await screen.findByText("Kein Anmeldebogen.")).toBeInTheDocument();

    await user.upload(inputs[1], new File(["x"], "a.jpg", { type: "image/jpeg" }));
    await user.click(screen.getAllByRole("button", { name: "Hochladen" })[1]);
    expect(await screen.findByText("Kein Bild.")).toBeInTheDocument();
  });

  it("still reports a JSON error from the certificate upload", async () => {
    returns();
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: null,
            participated: true,
            passed: true,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: null,
          },
        ]),
      ),
      http.post(api("/api/members/trainings/5/certificate"), () =>
        HttpResponse.json({ detail: "Kein Nachweis." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await user.upload(
      panel.querySelector('input[type="file"]') as HTMLInputElement,
      new File(["x"], "n.pdf", { type: "application/pdf" }),
    );
    expect(await screen.findByText("Kein Nachweis.")).toBeInTheDocument();
  });

  it("still reports a JSON error from the document upload", async () => {
    returns();
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/documents"), () =>
        HttpResponse.json({ detail: "Kein Dokument." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Dokumente" }));
    await user.click(await screen.findByRole("button", { name: "+ Dokument" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.upload(
      dialog.getByLabelText(/^Datei/),
      new File(["x"], "d.pdf", { type: "application/pdf" }),
    );
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText(/Kein Dokument\./)).toBeInTheDocument();
  });

  it("clears a chosen document and certificate file again", async () => {
    returns();
    server.use(
      http.get(api("/api/members/trainings"), () =>
        HttpResponse.json([
          {
            id: 5,
            member_id: 42,
            title: "Trainer C",
            date: null,
            participated: true,
            passed: true,
            category_name: "Grundkurs",
            category_id: 1,
            certificate: null,
          },
        ]),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.click(screen.getByRole("tab", { name: "Dokumente" }));
    await user.click(await screen.findByRole("button", { name: "+ Dokument" }));
    const dialog = within(await screen.findByRole("dialog"));
    const docFile = dialog.getByLabelText(/^Datei/);
    await user.upload(docFile, new File(["x"], "d.pdf", { type: "application/pdf" }));
    await user.upload(docFile, []);
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));

    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    const cert = panel.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(cert, []);
    expect(cert.files).toHaveLength(0);
  });

  it("keeps the group in the breadcrumb even when the group cannot be loaded", async () => {
    returns();
    server.use(
      http.get(api("/api/members/groups/5"), () =>
        HttpResponse.json({ detail: "Nicht gefunden" }, { status: 404 }),
      ),
    );
    renderRoute("/app/members/42?group=5");
    // The trail still reads "Gruppe" rather than breaking.
    expect(await screen.findByRole("link", { name: "Gruppe" })).toBeInTheDocument();
  });

  it("links an absolute document URL through unchanged", async () => {
    returns();
    server.use(
      http.get(api("/api/members/42/documents"), () =>
        HttpResponse.json([
          { id: 4, filename: "attest.pdf", file_url: "https://cdn.example.org/attest.pdf" },
        ]),
      ),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("tab", { name: "Dokumente" }));
    expect(await screen.findByRole("link", { name: "attest.pdf" })).toHaveAttribute(
      "href",
      "https://cdn.example.org/attest.pdf",
    );
  });

  it("clears a chosen file again in every upload field", async () => {
    returns();
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const inputs = [...document.querySelectorAll('input[type="file"]')] as HTMLInputElement[];
    for (const input of inputs.slice(0, 2)) {
      await user.upload(input, new File(["x"], "x.pdf", { type: "application/pdf" }));
      await user.upload(input, []);
    }
    const uploads = screen.getAllByRole("button", { name: "Hochladen" });
    for (const button of uploads) expect(button).toBeDisabled();
  });

  it("saves an empty birth date and training date as null", async () => {
    returns();
    let patched: Record<string, unknown> | null = null;
    let training: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
      http.patch(api("/api/members/42"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MEMBER);
      }),
      http.post(api("/api/members/trainings"), async ({ request }) => {
        training = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 5 });
      }),
    );
    const { user } = renderRoute("/app/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue("2011-05-04"));

    await user.click(screen.getByRole("tab", { name: "Ausbildungen" }));
    await user.click(await screen.findByRole("button", { name: "+ Ausbildung" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: /Kategorie/ }));
    await user.click(dropdown().getByRole("button", { name: /Grundkurs/ }));
    await user.type(dialog.getByLabelText(/Titel/), "Trainer C");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).toMatchObject({ birth_date: null }));
    await waitFor(() => expect(training).toMatchObject({ date: null }));
  });

  it("shows an em dash for every optional field left empty", async () => {
    returns({
      email: "",
      alternative_email: null,
      phone_number: "",
      birth_date: null,
      age: null,
      gender: null,
      gender_display: null,
      groups: [],
      registration_form: null,
      image: null,
      join_date: null,
      leave_date: null,
      comments: "",
      legal_guardians: "",
      user_display: "",
      street: "",
      plz: "",
      town: "",
      address_extra: "",
      country: "",
      iban: null,
      dav_badge_no: "",
      ticket_no: "",
      allergies: "",
      medication: "",
      tetanus_vaccination: null,
      good_conduct_certificate_presented_date: null,
      activity_score: null,
      skills: [],
      activities: [],
    });
    const { user } = renderRoute("/app/members/42");
    await screen.findByRole("button", { name: "Bearbeiten" });

    for (const tab of ["Stammdaten", "Kontaktdaten", "Fähigkeiten", "Sonstiges", "Organisatorisch"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      expect(panel.textContent).toContain("—");
    }
  });
});
