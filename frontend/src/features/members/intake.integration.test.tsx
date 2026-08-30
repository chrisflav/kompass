import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

const ENUMS = {
  gender: [
    { value: 0, label: "Männlich" },
    { value: 1, label: "Weiblich" },
  ],
};

const GROUPS = [
  { id: 5, name: "Klettergruppe", invitation_text_template: "Hallo! Komm vorbei." },
  { id: 6, name: "Bouldergruppe", invitation_text_template: "" },
];

/* --- Registrierungen ------------------------------------------------------ */

const REGISTRATION_BRIEF: Record<string, unknown> = {
  id: 50,
  name: "Nils Neu",
  birth_date: "2012-03-01",
  age: 14,
  groups: ["Klettergruppe"],
  confirmed_mail: true,
  confirmed_alternative_mail: false,
  registration_form_uploaded: true,
};

const REGISTRATION = {
  ...REGISTRATION_BRIEF,
  registration_form: "/media/bogen.pdf",
  image: null,
  skills: [],
  activities: [],
  user_id: null,
  iban_valid: false,
  place: "71634 Ludwigsburg",
  address: "Weg 2",
  gender_str: "männlich",
  activity_score: 0,
  ticket_no: "",
  may_cancel_appointment_independently: null,
  gets_newsletter: true,
  active: true,
  prename: "Nils",
  lastname: "Neu",
  email: "nils@example.org",
  alternative_email: null,
  phone_number: "0711 3",
  gender: 0,
  gender_display: "Männlich",
  groups: [{ id: 5, name: "Klettergruppe" }],
  join_date: "2026-01-01",
  leave_date: null,
  comments: "",
  legal_guardians: "",
  dav_badge_no: "",
  echoed: false,
  user_display: "",
  confirmed: false,
  created: "2026-01-01T09:00:00Z",
  street: "Weg 2",
  plz: "71634",
  town: "Ludwigsburg",
  address_extra: "",
  country: "Deutschland",
  iban: null,
  swimming_badge: true,
  climbing_badge: "",
  alpine_experience: "",
  allergies: "",
  tetanus_vaccination: null,
  medication: "",
  photos_may_be_taken: true,
  good_conduct_certificate_presented_date: null,
  good_conduct_certificate_valid: false,
  has_key: false,
  has_free_ticket_gym: false,
};

describe("Registrierungen", () => {
  function listReturns(rows = [REGISTRATION_BRIEF]) {
    server.use(
      http.get(api("/api/members/registrations"), () => HttpResponse.json(rows)),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/registrations/50"), () =>
        HttpResponse.json({ ...REGISTRATION, ...overrides }),
      ),
      http.get(api("/api/members/registrations/50/emergency-contacts"), () =>
        HttpResponse.json([]),
      ),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    );
  }

  it("lists the open registrations with their confirmation state", async () => {
    listReturns();
    renderRoute("/app/registrations");
    expect(await screen.findByText("Nils Neu")).toBeInTheDocument();
    expect(screen.getByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByText("1.3.2012")).toBeInTheDocument();
  });

  it("says so when there are none open", async () => {
    listReturns([]);
    renderRoute("/app/registrations");
    expect(await screen.findByText("Keine offenen Registrierungen.")).toBeInTheDocument();
  });

  it("copes with a registration missing age, groups and form", async () => {
    listReturns([
      {
        ...REGISTRATION_BRIEF,
        age: null,
        groups: [],
        registration_form_uploaded: false,
        confirmed_mail: false,
      },
    ]);
    renderRoute("/app/registrations");
    await screen.findByText("Nils Neu");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("filters by group, mail confirmation and registration form", async () => {
    listReturns([
      REGISTRATION_BRIEF,
      {
        ...REGISTRATION_BRIEF,
        id: 51,
        name: "Ohne Alles",
        groups: [],
        confirmed_mail: false,
        confirmed_alternative_mail: true,
        registration_form_uploaded: false,
      },
    ]);
    const { user } = renderRoute("/app/registrations");
    await screen.findByText("Nils Neu");

    await user.click(screen.getByRole("button", { name: /Anmeldeformular:/ }));
    await user.click(dropdown().getByRole("button", { name: "Fehlt" }));
    await waitFor(() => expect(screen.queryByText("Nils Neu")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /^E-Mail bestätigt:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(screen.queryByText("Ohne Alles")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Alt\. E-Mail bestätigt:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    await waitFor(() => expect(screen.queryByText("Nils Neu")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("searches by name, first name, surname and e-mail", async () => {
    listReturns([
      REGISTRATION_BRIEF,
      { ...REGISTRATION_BRIEF, id: 51, name: "Ohne Alles", email: "sonst@example.org" },
    ]);
    const { user } = renderRoute("/app/registrations");
    await screen.findByText("Nils Neu");
    await user.type(screen.getByPlaceholderText("Suchen…"), "sonst@");
    await waitFor(() => expect(screen.queryByText("Nils Neu")).not.toBeInTheDocument());
  });

  it("shows an em dash for a registration without an alternative address", async () => {
    listReturns([{ ...REGISTRATION_BRIEF, alternative_email: null, birth_date: "irgendwann" }]);
    renderRoute("/app/registrations");
    await screen.findByText("Nils Neu");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    // An unparseable date is passed through rather than shown as "Invalid Date".
    expect(screen.getByText("irgendwann")).toBeInTheDocument();
  });

  it("sorts by every column in both directions", async () => {
    listReturns([
      REGISTRATION_BRIEF,
      { ...REGISTRATION_BRIEF, id: 51, name: "Ohne Alles", age: null, birth_date: null },
    ]);
    const { user } = renderRoute("/app/registrations");
    await screen.findByText("Nils Neu");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("shows a registration across its tabs and its emergency contacts", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/registrations/50/emergency-contacts"), () =>
        HttpResponse.json([
          { id: 1, prename: "Ute", lastname: "Neu", email: "", phone_number: "0711 4" },
        ]),
      ),
    );
    const { user } = renderRoute("/app/registrations/50");

    expect(await screen.findAllByText("Nils Neu")).toHaveLength(2);
    await user.click(screen.getByRole("tab", { name: "Kontaktdaten" }));
    expect(screen.getByText("Weg 2")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));
    expect(await screen.findByText("Ute")).toBeInTheDocument();
  });

  it("says so when no emergency contact is on file", async () => {
    detailReturns();
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("tab", { name: "Notfallkontakte" }));
    expect(await screen.findByText("Keine Notfallkontakte hinterlegt.")).toBeInTheDocument();
  });

  it("edits a registration, sending the gender as a number", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/registrations/50"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(REGISTRATION);
      }),
    );
    useMe({ permissions: ["members.change_memberunconfirmedproxy"] });
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const prename = screen.getByDisplayValue("Nils");
    await user.clear(prename);
    await user.type(prename, "Niels");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ prename: "Niels", gender: 0 });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/registrations/50"), () =>
        djangoValidation({ email: ["Keine gültige Adresse."] }),
      ),
    );
    useMe({ permissions: ["members.change_memberunconfirmedproxy"] });
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Keine gültige Adresse.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Nils")).not.toBeInTheDocument();
  });

  it("confirms a registration into a full membership", async () => {
    detailReturns();
    let confirmed = false;
    server.use(
      http.post(api("/api/members/50/confirm"), () => {
        confirmed = true;
        return HttpResponse.json({ id: 50 });
      }),
      http.get(api("/api/members/50"), () =>
        HttpResponse.json({ ...REGISTRATION, skills: [], activities: [], image: null }),
      ),
      http.get(api("/api/members/50/emergency-contacts"), () => HttpResponse.json([])),
      http.get(api("/api/members/50/documents"), () => HttpResponse.json([])),
      http.get(api("/api/members/50/permission-members"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Bestätigen" }),
    );

    await waitFor(() => expect(confirmed).toBe(true));
    expect(await screen.findByText("Registrierung bestätigt.")).toBeInTheDocument();
  });

  it("re-requests the mail confirmation and the registration form", async () => {
    detailReturns();
    const called: string[] = [];
    server.use(
      http.post(api("/api/members/50/request-mail-confirmation"), () => {
        called.push("mail");
        return HttpResponse.json({});
      }),
      http.post(api("/api/members/50/request-registration-form"), () => {
        called.push("form");
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/app/registrations/50");

    // The two mail-confirmation variants fire straight away; the form request
    // asks first.
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Bestätigungsmail an alle Adressen senden" }));
    expect(await screen.findByText("E-Mail-Bestätigung angefordert.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Anmeldebogen anfordern" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Senden" }),
    );
    await waitFor(() => expect(called).toEqual(["mail", "form"]));

    // …and the "only open addresses" variant fires too.
    await user.click(screen.getByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Bestätigungsmail nur an offene Adressen" }));
    await waitFor(() => expect(called).toEqual(["mail", "form", "mail"]));
  });

  it("demotes a registration back to the waiting list", async () => {
    detailReturns();
    let demoted = false;
    server.use(
      http.post(api("/api/members/50/demote-to-waiter"), () => {
        demoted = true;
        return HttpResponse.json({ id: 60 });
      }),
      http.get(api("/api/members/waiters"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: /Aktionen/ }));
    await user.click(screen.getByRole("button", { name: "Auf Warteliste zurückstufen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Zurückstufen" }),
    );

    await waitFor(() => expect(demoted).toBe(true));
    expect(await screen.findByText("Auf die Warteliste zurückgestuft.")).toBeInTheDocument();
  });

  it("hides the edit action without the permission", async () => {
    useMe({ permissions: [] });
    detailReturns();
    renderRoute("/app/registrations/50");
    await screen.findAllByText("Nils Neu");
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
  });

  it("opens a registration from its row", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/registrations");
    await user.click(await screen.findByText("Nils Neu"));
    expect(await screen.findByRole("button", { name: /Aktionen/ })).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    detailReturns({
      prename: null,
      lastname: null,
      email: null,
      alternative_email: null,
      phone_number: null,
      birth_date: null,
      gender: null,
      comments: null,
      legal_guardians: null,
      street: null,
      plz: null,
      town: null,
      address_extra: null,
      allergies: null,
      medication: null,
      photos_may_be_taken: null,
    });
    server.use(
      http.get(api("/api/members/registrations/50/emergency-contacts"), () =>
        HttpResponse.json([
          { id: 1, prename: null, lastname: null, email: null, phone_number: null },
        ]),
      ),
    );
    useMe({ permissions: ["members.change_memberunconfirmedproxy"] });
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);

    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Warteliste ----------------------------------------------------------- */

const WAITER_BRIEF: Record<string, unknown> = {
  id: 60,
  name: "Wanda Wartend",
  prename: "Wanda",
  lastname: "Wartend",
  email: "wanda@example.org",
  birth_date: "2011-09-09",
  age: 14,
  gender: 1,
  gender_str: "weiblich",
  application_date: "2026-01-15",
  latest_group_invitation: null,
  confirmed_mail: true,
  waiting_confirmed: null,
  sent_reminders: 0,
};

const WAITER = {
  ...WAITER_BRIEF,
  application_text: "Ich klettere gern.",
  comments: "",
  invitations: [],
};

describe("Warteliste", () => {
  function listReturns(rows = [WAITER_BRIEF]) {
    server.use(
      http.get(api("/api/members/waiters"), () => HttpResponse.json(rows)),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/waiters/60"), () =>
        HttpResponse.json({ ...WAITER, ...overrides }),
      ),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
    );
  }

  it("searches by name and e-mail, and shows an em dash for an unknown age", async () => {
    listReturns([
      { ...WAITER_BRIEF, age: null, birth_date: "irgendwann" },
      { ...WAITER_BRIEF, id: 61, name: "Bea Berg", email: "bea@example.org" },
    ]);
    const { user } = renderRoute("/app/waiters");
    await screen.findByText("Wanda Wartend");
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    expect(screen.getByText("irgendwann")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Suchen…"), "bea@");
    await waitFor(() => expect(screen.queryByText("Wanda Wartend")).not.toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([WAITER_BRIEF, { ...WAITER_BRIEF, id: 61, name: "Bea Berg", lastname: "Berg" }]);
    const { user } = renderRoute("/app/waiters");
    await screen.findByText("Wanda Wartend");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("lists the applications with their waiting status", async () => {
    listReturns();
    renderRoute("/app/waiters");
    expect(await screen.findByText("Wanda Wartend")).toBeInTheDocument();
    // A null waiting status is "pending", not a yes/no.
    expect(screen.getByText("Ausstehend")).toBeInTheDocument();
    expect(screen.getByText("15.1.2026")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/waiters");
    expect(await screen.findByText("Keine Wartelisten-Bewerbungen sichtbar.")).toBeInTheDocument();
  });

  it("filters by mail confirmation, gender, age and waiting status", async () => {
    listReturns([
      WAITER_BRIEF,
      {
        ...WAITER_BRIEF,
        id: 61,
        name: "Bea Bestätigt",
        gender: 0,
        gender_str: "männlich",
        age: 16,
        confirmed_mail: false,
        waiting_confirmed: true,
        latest_group_invitation: "Klettergruppe",
      },
    ]);
    const { user } = renderRoute("/app/waiters");
    await screen.findByText("Wanda Wartend");

    await user.click(screen.getByRole("button", { name: /Wartestatus:/ }));
    await user.click(dropdown().getByRole("button", { name: "Bestätigt" }));
    await waitFor(() => expect(screen.queryByText("Wanda Wartend")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Wartestatus:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ausstehend" }));
    await waitFor(() => expect(screen.queryByText("Bea Bestätigt")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Geschlecht:/ }));
    await user.click(dropdown().getByRole("button", { name: "Männlich" }));
    await waitFor(() => expect(screen.queryByText("Wanda Wartend")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Alter:/ }));
    await user.click(dropdown().getByRole("button", { name: "16" }));
    await waitFor(() => expect(screen.queryByText("Wanda Wartend")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /E-Mail bestätigt:/ }));
    await user.click(dropdown().getByRole("button", { name: "Nein" }));
    expect(screen.getByText("1 / 2")).toBeInTheDocument();
  });

  it("shows an expired waiting status as such", async () => {
    listReturns([{ ...WAITER_BRIEF, waiting_confirmed: false }]);
    renderRoute("/app/waiters");
    await screen.findByText("Wanda Wartend");
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);
  });

  it("marks an unconfirmed e-mail address on the detail", async () => {
    detailReturns({ confirmed_mail: false });
    renderRoute("/app/waiters/60");
    await screen.findAllByText("Wanda Wartend");
    expect(screen.getAllByText("Nein").length).toBeGreaterThan(0);
  });

  it("edits an application, sending the gender as a number", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/waiters/60"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(WAITER);
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const comments = screen.getAllByRole("textbox").slice(-1)[0];
    await user.type(comments, "Rückruf offen");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ gender: 1, comments: "Rückruf offen" });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("sends an empty birth date and gender as null", async () => {
    detailReturns({ birth_date: null, gender: null, gender_str: "—" });
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/waiters/60"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(WAITER);
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ birth_date: null, gender: null });
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/waiters/60"), () =>
        djangoValidation({ email: ["Keine gültige Adresse."] }),
      ),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Keine gültige Adresse.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Wanda")).not.toBeInTheDocument();
  });

  it("invites the applicant into a group, prefilling the group's text", async () => {
    detailReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.post(api("/api/members/waiters/60/invite"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(WAITER);
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "In Gruppe einladen" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(await dialog.findByRole("button", { name: "Gruppe" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));

    // The group's stored template becomes the editable invitation text.
    expect(dialog.getByLabelText(/Einladungstext/)).toHaveValue("Hallo! Komm vorbei.");
    await user.click(dialog.getByRole("button", { name: "Einladen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ group_id: 5, text: "Hallo! Komm vorbei." });
    expect(await screen.findByText("Einladung versendet.")).toBeInTheDocument();
  });

  it("sends a null text for a group without a template", async () => {
    detailReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.post(api("/api/members/waiters/60/invite"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(WAITER);
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "In Gruppe einladen" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(await dialog.findByRole("button", { name: "Gruppe" }));
    await user.click(dropdown().getByRole("button", { name: "Bouldergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Einladen" }));

    await waitFor(() => expect(body).toEqual({ group_id: 6, text: null }));
  });

  it("says so when no group is available to invite into", async () => {
    detailReturns();
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json([])));
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "In Gruppe einladen" }));
    expect(await screen.findByText("Keine Gruppen verfügbar.")).toBeInTheDocument();
  });

  it("closes the invitation dialog again", async () => {
    detailReturns();
    server.use(http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)));
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "In Gruppe einladen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("offers the three reminder mails, each behind a confirmation", async () => {
    detailReturns();
    const called: string[] = [];
    server.use(
      http.post(api("/api/members/waiters/60/request-wait-confirmation"), () => {
        called.push("wait");
        return HttpResponse.json({});
      }),
      http.post(api("/api/members/waiters/60/request-mail-confirmation"), ({ request }) => {
        called.push(`mail:${new URL(request.url).searchParams.get("rerequest")}`);
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/app/waiters/60");

    for (const label of [
      "Wartebestätigung anfordern",
      "Bestätigungsmail an alle Adressen",
      "Bestätigungsmail nur an offene Adressen",
    ]) {
      await user.click(await screen.findByRole("button", { name: /Erinnerungen/ }));
      await user.click(screen.getByRole("button", { name: label }));
      await user.click(
        within(await screen.findByRole("dialog")).getByRole("button", { name: "Senden" }),
      );
    }

    await waitFor(() => expect(called).toHaveLength(3));
    expect(called).toEqual(["wait", "mail:true", "mail:false"]);
  });

  it("hides the reminders from an account without the permission", async () => {
    useMe({ permissions: [] });
    detailReturns();
    renderRoute("/app/waiters/60");
    await screen.findAllByText("Wanda Wartend");
    expect(screen.queryByRole("button", { name: /Erinnerungen/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("deletes an application once confirmed", async () => {
    useMe({ permissions: ["members.delete_global_memberwaitinglist"] });
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/waiters"), () => HttpResponse.json([])),
      http.delete(api("/api/members/waiters/60"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Bewerbung gelöscht.")).toBeInTheDocument();
  });

  it("opens an application from its row", async () => {
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/waiters");
    await user.click(await screen.findByText("Wanda Wartend"));
    expect(await screen.findByRole("button", { name: "In Gruppe einladen" })).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    detailReturns({
      prename: null,
      lastname: null,
      email: null,
      birth_date: null,
      gender: null,
      application_text: null,
      comments: null,
      invitations: [],
    });
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("lists the invitation history and says so when it is empty", async () => {
    detailReturns({
      invitations: [
        { id: 1, group: { id: 5, name: "Klettergruppe" }, status: "offen", date: "2026-02-01" },
      ],
    });
    renderRoute("/app/waiters/60");
    expect(await screen.findByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByText("offen")).toBeInTheDocument();
  });

  it("reports a refused reminder mail", async () => {
    detailReturns();
    server.use(
      http.post(api("/api/members/waiters/60/request-wait-confirmation"), () =>
        HttpResponse.json({ detail: "Keine E-Mail hinterlegt." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: /Erinnerungen/ }));
    await user.click(screen.getByRole("button", { name: "Wartebestätigung anfordern" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Senden" }),
    );
    expect(await screen.findByText("Keine E-Mail hinterlegt.")).toBeInTheDocument();
  });

  it("reports a refused invitation and closes the dialog with ×", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
      http.post(api("/api/members/waiters/60/invite"), () =>
        HttpResponse.json({ detail: "Gruppe ist voll." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "In Gruppe einladen" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(await dialog.findByRole("button", { name: "Gruppe" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Einladen" }));
    expect(await screen.findByText("Gruppe ist voll.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Schließen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- Ausbildungen --------------------------------------------------------- */

const TRAINING_BRIEF: Record<string, unknown> = {
  id: 70,
  title: "Trainer C",
  member_id: 42,
  member_name: "Anna Ärmel",
  date: "2026-03-01",
  category_name: "Grundkurs",
  category_id: 1,
  activities: ["Klettern"],
  participated: true,
  passed: false,
  certificate: "/media/nachweis.pdf",
};

const TRAINING = {
  ...TRAINING_BRIEF,
  member: { id: 42, name: "Anna Ärmel" },
  comments: "",
  activity_ids: [1],
};

describe("Ausbildungen", () => {
  function listReturns(rows = [TRAINING_BRIEF]) {
    server.use(
      http.get(api("/api/members/trainings"), () => HttpResponse.json(rows)),
      http.get(api("/api/members/"), () => HttpResponse.json([{ id: 42, name: "Anna Ärmel" }])),
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
    );
  }

  function detailReturns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/trainings/70"), () =>
        HttpResponse.json({ ...TRAINING, ...overrides }),
      ),
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
      http.get(api("/api/members/activity-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Klettern" }]),
      ),
    );
  }

  it("lists the trainings with their certificate link", async () => {
    listReturns();
    renderRoute("/app/trainings");
    expect(await screen.findByText("Trainer C")).toBeInTheDocument();
    expect(screen.getByText("Anna Ärmel")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Öffnen" })).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/trainings");
    expect(await screen.findByText("Keine Ausbildungen sichtbar.")).toBeInTheDocument();
  });

  it("filters by category, member and passed status", async () => {
    listReturns([
      TRAINING_BRIEF,
      {
        ...TRAINING_BRIEF,
        id: 71,
        title: "Trainer B",
        member_id: 43,
        member_name: "Bea Berg",
        category_name: "Aufbaukurs",
        category_id: 2,
        activities: [],
        passed: true,
        certificate: null,
      },
    ]);
    const { user } = renderRoute("/app/trainings");
    await screen.findByText("Trainer C");

    await user.click(screen.getByRole("button", { name: /Kategorie:/ }));
    await user.click(dropdown().getByRole("button", { name: "Aufbaukurs" }));
    await waitFor(() => expect(screen.queryByText("Trainer C")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Teilnehmende:/ }));
    await user.click(dropdown().getByRole("button", { name: "Bea Berg" }));
    await waitFor(() => expect(screen.queryByText("Trainer C")).not.toBeInTheDocument());

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Bestanden:/ }));
    await user.click(dropdown().getByRole("button", { name: "Ja" }));
    expect(screen.getByText("1 / 2")).toBeInTheDocument();

    // "Unbekannt" is its own bucket: neither passed nor failed.
    await user.click(screen.getByRole("button", { name: /Bestanden:/ }));
    await user.click(dropdown().getByRole("button", { name: "Unbekannt" }));
    await waitFor(() => expect(screen.getByText("0 / 2")).toBeInTheDocument());
  });

  it("searches by title and filters by activity", async () => {
    listReturns([
      { ...TRAINING_BRIEF, date: "irgendwann" },
      { ...TRAINING_BRIEF, id: 71, title: "Trainer B", activities: ["Bouldern"] },
    ]);
    const { user } = renderRoute("/app/trainings");
    await screen.findByText("Trainer C");
    expect(screen.getByText("irgendwann")).toBeInTheDocument();

    await user.type(screen.getByPlaceholderText("Suchen…"), "trainer b");
    await waitFor(() => expect(screen.queryByText("Trainer C")).not.toBeInTheDocument());
    await user.clear(screen.getByPlaceholderText("Suchen…"));

    await user.click(await screen.findByRole("button", { name: /Tätigkeit:/ }));
    await user.click(dropdown().getByRole("button", { name: "Bouldern" }));
    await waitFor(() => expect(screen.queryByText("Trainer C")).not.toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([TRAINING_BRIEF, { ...TRAINING_BRIEF, id: 71, title: "Trainer B", date: null }]);
    const { user } = renderRoute("/app/trainings");
    await screen.findByText("Trainer C");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/trainings");
    await screen.findByText("Trainer C");
    expect(screen.queryByRole("button", { name: "Neue Ausbildung" })).not.toBeInTheDocument();
  });

  it("creates a training for a chosen member and category", async () => {
    useMe({ permissions: ["members.add_global_membertraining"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/trainings"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRAINING);
      }),
      http.get(api("/api/members/activity-categories"), () => HttpResponse.json([])),
      http.get(api("/api/members/trainings/70"), () => HttpResponse.json(TRAINING)),
    );
    const { user } = renderRoute("/app/trainings");
    await user.click(await screen.findByRole("button", { name: "Neue Ausbildung" }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.type(dialog.getByLabelText("Titel"), "Trainer C");
    await user.click(dialog.getByRole("button", { name: "Kategorie" }));
    await user.click(dropdown().getByRole("button", { name: /Grundkurs/ }));
    await user.type(dialog.getByLabelText("Datum"), "2026-03-01");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      member_id: 42,
      title: "Trainer C",
      category_id: 1,
      date: "2026-03-01",
    });
    expect(await screen.findByText("Ausbildung angelegt.")).toBeInTheDocument();
  });

  it("reports a rejected create and closes on Abbrechen", async () => {
    useMe({ permissions: ["members.add_global_membertraining"] });
    listReturns();
    server.use(
      http.post(api("/api/members/trainings"), () =>
        djangoValidation({
          title: ["Der Titel fehlt."],
          member_id: ["Unbekannte Person."],
          category_id: ["Unbekannte Kategorie."],
          date: ["Ungültiges Datum."],
        }),
      ),
    );
    const { user } = renderRoute("/app/trainings");
    await user.click(await screen.findByRole("button", { name: "Neue Ausbildung" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Anna Ärmel" }));
    await user.click(dialog.getByRole("button", { name: "Kategorie" }));
    await user.click(dropdown().getByRole("button", { name: /Grundkurs/ }));
    await user.type(dialog.getByLabelText("Titel"), "x");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));
    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);
    expect(screen.getByText("Unbekannte Person.")).toBeInTheDocument();
    expect(screen.getByText("Unbekannte Kategorie.")).toBeInTheDocument();
    expect(screen.getByText("Ungültiges Datum.")).toBeInTheDocument();

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("edits a training, sending ids and a null date when cleared", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/trainings/70"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRAINING);
      }),
    );
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.clear(screen.getByDisplayValue("2026-03-01"));
    const [participated, passed] = screen.getAllByRole("checkbox");
    await user.click(participated);
    await user.click(passed);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      title: "Trainer C",
      date: null,
      category_id: 1,
      activity_ids: [1],
      participated: false,
      passed: true,
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("shows an em dash for a training without activities or a certificate", async () => {
    detailReturns({ activities: [], activity_ids: [], certificate: null, comments: "" });
    renderRoute("/app/trainings/70");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/trainings/70"), () =>
        djangoValidation({ title: ["Der Titel fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Der Titel fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Trainer C")).not.toBeInTheDocument();
  });

  it("deletes a training once confirmed", async () => {
    useMe({ permissions: ["members.delete_global_membertraining"] });
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
      http.get(api("/api/members/"), () => HttpResponse.json([])),
      http.delete(api("/api/members/trainings/70"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Ausbildung gelöscht.")).toBeInTheDocument();
  });

  it("opens a training from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["members.add_global_membertraining"] });
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/trainings");

    await user.click(await screen.findByRole("button", { name: "Neue Ausbildung" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Trainer C"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    detailReturns({
      title: null,
      date: null,
      comments: null,
      participated: null,
      passed: null,
      category: null,
      category_id: null,
      activities: [],
      activity_ids: [],
      certificate: null,
    });
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("reports a refused delete", async () => {
    useMe({ permissions: ["members.delete_global_membertraining"] });
    detailReturns();
    server.use(
      http.delete(api("/api/members/trainings/70"), () =>
        HttpResponse.json({ detail: "members.delete_global_membertraining" }, { status: 403 }),
      ),
    );
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

describe("Registrierung — every field", () => {
  const DETAIL = {
    ...REGISTRATION,
  };

  function returns(overrides: Record<string, unknown> = {}) {
    server.use(
      http.get(api("/api/members/registrations/50"), () =>
        HttpResponse.json({ ...DETAIL, ...overrides }),
      ),
      http.get(api("/api/members/registrations/50/emergency-contacts"), () =>
        HttpResponse.json([]),
      ),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
      http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    );
  }

  it("carries every edited field into the PATCH", async () => {
    useMe({ permissions: ["members.change_memberunconfirmedproxy"] });
    returns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/registrations/50"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(DETAIL);
      }),
    );
    const { user } = renderRoute("/app/registrations/50");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    for (const tab of ["Stammdaten", "Kontaktdaten", "Fähigkeiten", "Sonstiges", "Organisatorisch"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      await fillEveryField(user, panel);
      await pickEverySelect(user, panel);
    }
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({ prename: "Text", lastname: "Text" });
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
      join_date: null,
      leave_date: null,
      comments: "",
      legal_guardians: "",
      dav_badge_no: "",
      user_display: "",
      street: "",
      plz: "",
      town: "",
      address_extra: "",
      country: "",
      iban: null,
      climbing_badge: "",
      alpine_experience: "",
      allergies: "",
      tetanus_vaccination: null,
      medication: "",
      good_conduct_certificate_presented_date: null,
      created: null,
    });
    const { user } = renderRoute("/app/registrations/50");
    await screen.findAllByText("Nils Neu");

    for (const tab of ["Stammdaten", "Kontaktdaten", "Fähigkeiten", "Sonstiges", "Organisatorisch"]) {
      await user.click(screen.getByRole("tab", { name: tab }));
      const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
      expect(panel.textContent).toContain("—");
    }
  });
});

describe("Warteliste — every field", () => {
  it("carries every edited field into the PATCH", async () => {
    server.use(
      http.get(api("/api/members/waiters/60"), () => HttpResponse.json(WAITER)),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
    );
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/waiters/60"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(WAITER);
      }),
    );
    const { user } = renderRoute("/app/waiters/60");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      prename: "Text",
      lastname: "Text",
      email: "Text",
      birth_date: "2026-03-04",
      application_text: "Text",
      comments: "Text",
      // The gender select has no clear entry, so its first option is a value.
      gender: 0,
    });
  });

  it("shows an em dash for every optional field left empty", async () => {
    server.use(
      http.get(api("/api/members/waiters/60"), () =>
        HttpResponse.json({
          ...WAITER,
          email: "",
          birth_date: null,
          age: null,
          gender_str: "",
          application_text: "",
          application_date: null,
          comments: "",
          latest_group_invitation: null,
        }),
      ),
      http.get(api("/api/members/enums"), () => HttpResponse.json(ENUMS)),
    );
    renderRoute("/app/waiters/60");
    await screen.findAllByText("Wanda Wartend");
    expect((document.querySelector("form") as HTMLElement).textContent).toContain("—");
  });
});

describe("Ausbildung — every field", () => {
  it("carries every edited field into the PATCH", async () => {
    server.use(
      http.get(api("/api/members/trainings/70"), () => HttpResponse.json(TRAINING)),
      http.get(api("/api/members/training-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Grundkurs" }]),
      ),
      http.get(api("/api/members/activity-categories"), () =>
        HttpResponse.json([{ id: 1, name: "Klettern" }]),
      ),
    );
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/trainings/70"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(TRAINING);
      }),
    );
    const { user } = renderRoute("/app/trainings/70");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      title: "Text",
      comments: "Text",
      date: "2026-03-04",
      participated: false,
      passed: true,
    });
  });
});
