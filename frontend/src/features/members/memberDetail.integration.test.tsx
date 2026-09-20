import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  api,
  DEFAULT_ME,
  djangoValidation,
  http,
  HttpResponse,
  server,
  useMe,
} from "../../test/server";
import { renderRoute } from "../../test/utils";

const MEMBER = {
  id: 42,
  name: "Anna Ärmel",
  age: 15,
  gender_str: "weiblich",
  place: "71634 Ludwigsburg",
  address: "Weg 1, 71634 Ludwigsburg",
  iban_valid: true,
  groups: [{ id: 5, name: "Klettergruppe" }],
  gender_display: "weiblich",
  good_conduct_certificate_valid: false,
  activity_score: 3,
  registration_form: null,
  image: null,
  user_id: null,
  user_display: "",
  skills: [],
  activities: [],
  prename: "Anna",
  lastname: "Ärmel",
  email: "anna@example.org",
  alternative_email: null,
  birth_date: "2011-05-04",
  gender: 1,
  phone_number: "0711 1",
  street: "Weg 1",
  plz: "71634",
  town: "Ludwigsburg",
  address_extra: "",
  country: "Deutschland",
  dav_badge_no: "",
  ticket_no: "",
  iban: null,
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
};

const CONTACT = {
  id: 3,
  prename: "Erika",
  lastname: "Ärmel",
  phone_number: "0711 2",
  email: "erika@example.org",
};

/** Every request the member detail page and its four inlines make. */
function detailReturns(overrides: Record<string, unknown> = {}, contacts = [CONTACT]) {
  server.use(
    http.get(api("/api/members/42"), () => HttpResponse.json({ ...MEMBER, ...overrides })),
    http.get(api("/api/members/42/emergency-contacts"), () => HttpResponse.json(contacts)),
    http.get(api("/api/members/42/documents"), () => HttpResponse.json([])),
    http.get(api("/api/members/42/permission-members"), () => HttpResponse.json([])),
    http.get(api("/api/members/trainings"), () => HttpResponse.json([])),
    http.get(api("/api/members/training-categories"), () => HttpResponse.json([])),
    // Refetched by the list after a mutation invalidates it.
    http.get(api("/api/members/"), () => HttpResponse.json([])),
    http.get(api("/api/members/enums"), () =>
      HttpResponse.json({
        gender: [
          { value: 1, label: "weiblich" },
          { value: 2, label: "männlich" },
        ],
        swimming_badge: [{ value: 0, label: "keins" }],
        climbing_badge: [{ value: 0, label: "keins" }],
        alpine_experience: [{ value: 0, label: "keine" }],
      }),
    ),
    http.get(api("/api/members/groups"), () =>
      HttpResponse.json([{ id: 5, name: "Klettergruppe" }]),
    ),
  );
}

describe("member detail", () => {
  it("shows the member across its tabs", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/members/42");

    // The name appears twice by design: in the breadcrumb and in the Name row.
    expect(await screen.findAllByText("Anna Ärmel")).toHaveLength(2);
    expect(screen.getByText("anna@example.org")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Kontaktdaten" }));
    expect(screen.getByText("Weg 1")).toBeInTheDocument();

    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));
    expect(await screen.findByText("Erika")).toBeInTheDocument();
  });

  it("stays read-only until Bearbeiten is pressed", async () => {
    detailReturns();
    const { user } = renderRoute("/kompass/members/42");
    await screen.findByText("anna@example.org");

    expect(screen.queryByDisplayValue("Anna")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    expect(screen.getByDisplayValue("Anna")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });

  it("sends the edited fields with the right types", async () => {
    detailReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...MEMBER, prename: "Anne" });
      }),
    );
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const prename = screen.getByDisplayValue("Anna");
    await user.clear(prename);
    await user.type(prename, "Anne");
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      prename: "Anne",
      lastname: "Ärmel",
      // The select yields a string; the API wants the enum's number.
      gender: 1,
      group_ids: [5],
      // Blank optional values go as null, not as "".
      alternative_email: null,
      iban: null,
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("keeps edit mode and shows the field error when the save is rejected", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/42"), () =>
        djangoValidation({ email: ["Gib eine gültige E-Mail-Adresse ein."] }),
      ),
    );
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    expect(
      (await screen.findAllByText("Gib eine gültige E-Mail-Adresse ein.")).length,
    ).toBeGreaterThan(0);
    // The form must not close, or the user loses everything they typed.
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
  });
});

describe("member detail — emergency contacts inline", () => {
  it("stages an added contact and only posts it on Save", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/42"), () => HttpResponse.json(MEMBER)),
      http.post(api("/api/members/42/emergency-contacts"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...CONTACT, id: 4, prename: "Neu" });
      }),
    );
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: "Notfallkontakte" }));

    await user.click(await screen.findByRole("button", { name: "+ Notfallkontakt" }));

    const dialog = within(await screen.findByRole("dialog"));
    // The add button stays disabled until the model's NOT NULL fields are there.
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Vorname/), "Neu");
    await user.type(dialog.getByLabelText(/Nachname/), "Kontakt");
    await user.type(dialog.getByLabelText(/Telefonnummer/), "0711 9");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    // Staged only — nothing has reached the server yet.
    expect(created).toBeNull();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).not.toBeNull());
    expect(created).toMatchObject({ prename: "Neu" });
  });
});

describe("member detail — actions and permissions", () => {
  it("offers deleting only with the permission, and asks first", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.delete(api("/api/members/42"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/„Anna Ärmel“ wirklich löschen\?/)).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("hides editing and deleting from a read-only account", async () => {
    useMe({ permissions: ["members.view_member"] });
    detailReturns();
    renderRoute("/kompass/members/42");
    await screen.findByText("anna@example.org");

    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });
});

/* The "Nutzer" row mirrors the admin's per-field permission: only a holder of
 * members.may_set_auth_user gets the select, and the PATCH carries the link
 * only when it actually changed (the backend refuses the field otherwise). */
describe("member detail — Nutzer (login account)", () => {
  const ACCOUNTS = [
    // 9 is this member's own account in the tests that start out linked.
    { id: 9, username: "anna.aermel", taken: true },
    { id: 10, username: "bernd.berg", taken: true },
    { id: 11, username: "frei.konto", taken: false },
  ];
  const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

  function mayLinkAccounts() {
    useMe({ permissions: [...DEFAULT_ME.permissions, "members.may_set_auth_user"] });
    server.use(http.get(api("/api/members/auth-users"), () => HttpResponse.json(ACCOUNTS)));
  }

  function patchCaptures() {
    const seen: { body: Record<string, unknown> | null } = { body: null };
    server.use(
      http.patch(api("/api/members/42"), async ({ request }) => {
        seen.body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(MEMBER);
      }),
    );
    return seen;
  }

  it("links an account with the permission, warning about the taken ones", async () => {
    mayLinkAccounts();
    detailReturns();
    const seen = patchCaptures();
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    await user.click(await screen.findByRole("button", { name: /Nutzerkonto wählen/ }));
    // An account linked elsewhere is offered as in the admin, but warns that
    // linking it would fail on the one-to-one relation. It never says to whom:
    // that name is one the API refuses this caller.
    expect(
      dropdown().getByRole("button", { name: "bernd.berg (bereits verknüpft)" }),
    ).toBeInTheDocument();
    await user.click(dropdown().getByRole("button", { name: "frei.konto" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(seen.body).not.toBeNull());
    expect(seen.body).toMatchObject({ user_id: 11 });
  });

  it("clears the link through the empty option", async () => {
    mayLinkAccounts();
    detailReturns({ user_id: 9, user_display: "anna.aermel" });
    const seen = patchCaptures();
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    // The member's own account is "taken" by this very member, so it carries no
    // warning — the trigger reads as the plain username.
    await user.click(await screen.findByRole("button", { name: "anna.aermel ▾" }));
    await user.click(dropdown().getByRole("button", { name: "Kein Nutzerkonto" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(seen.body).not.toBeNull());
    expect(seen.body).toMatchObject({ user_id: null });
  });

  it("stays read-only without the permission and leaves the field out of the PATCH", async () => {
    detailReturns({ user_id: 9, user_display: "anna.aermel" });
    const seen = patchCaptures();
    const { user } = renderRoute("/kompass/members/42");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    // No control — and no request for the options either, which the API would
    // refuse anyway (msw has no handler for it in this test).
    expect(screen.queryByRole("button", { name: /Nutzerkonto wählen/ })).not.toBeInTheDocument();
    expect(screen.getByText("anna.aermel")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(seen.body).not.toBeNull());
    expect(seen.body).not.toHaveProperty("user_id");
  });
});
