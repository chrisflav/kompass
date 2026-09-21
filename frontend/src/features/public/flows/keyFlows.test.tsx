import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  api,
  http,
  HttpResponse,
  multipartFilenames,
  ninjaValidation,
  server,
} from "../../../test/server";
import { fillEveryField, pickEverySelect, renderWithApp } from "../../../test/utils";
import { ConfirmInvitationFlow } from "./ConfirmInvitation";
import { ConfirmMailFlow } from "./ConfirmMail";
import { ConfirmWaitingFlow } from "./ConfirmWaiting";
import { EchoFlow } from "./Echo";
import { InvitedRegistrationFlow } from "./InvitedRegistration";
import { LeaveWaitingListFlow } from "./LeaveWaitingList";
import { PasswordFlow } from "./Password";
import { RejectInvitationFlow } from "./RejectInvitation";
import { SubmitTerminFlow } from "./SubmitTermin";
import { UnsubscribeFlow } from "./Unsubscribe";
import { UploadFormFlow } from "./UploadForm";
import { RegisterFlow } from "./Register";
import { WaitingListFlow } from "./WaitingList";

const KEY = "GEHEIM";

/** Mount a key-driven flow at `?key=GEHEIM` (or without a key). */
function renderFlow(ui: React.ReactElement, { key = KEY }: { key?: string | null } = {}) {
  return renderWithApp(ui, {
    route: key === null ? "/flow" : `/flow?key=${key}`,
    authenticated: false,
  });
}

/**
 * Every key flow refuses to act without a key. They are separate components, so
 * assert it once per flow rather than trusting a shared helper by inspection.
 */
describe("a missing key", () => {
  const flows: [string, React.ReactElement][] = [
    ["E-Mail bestätigen", <ConfirmMailFlow key="a" />],
    ["Warteliste bestätigen", <ConfirmWaitingFlow key="b" />],
    ["Warteliste verlassen", <LeaveWaitingListFlow key="c" />],
    ["Einladung annehmen", <ConfirmInvitationFlow key="d" />],
    ["Einladung ablehnen", <RejectInvitationFlow key="e" />],
    ["Newsletter abbestellen", <UnsubscribeFlow key="f" />],
    ["Passwort setzen", <PasswordFlow key="g" />],
    ["Daten aktualisieren", <EchoFlow key="h" />],
    ["Einladung annehmen", <InvitedRegistrationFlow key="i" />],
    ["Anmeldebogen hochladen", <UploadFormFlow key="j" />],
  ];

  it.each(flows)("%s says the link is invalid", (title, ui) => {
    renderFlow(ui, { key: null });
    expect(screen.getByRole("heading", { name: title })).toBeInTheDocument();
    expect(
      screen.getByText("Dieser Link ist ungültig (kein Schlüssel angegeben)."),
    ).toBeInTheDocument();
  });
});

describe("confirm mail", () => {
  it("confirms the address on request", async () => {
    server.use(
      http.post(api(`/api/members/public/confirm-mail/${KEY}`), () =>
        HttpResponse.json({ name: "Anna", email: "anna@example.org" }),
      ),
    );
    const { user } = renderFlow(<ConfirmMailFlow />);

    await user.click(screen.getByRole("button", { name: "E-Mail bestätigen" }));
    expect(
      await screen.findByText(/Danke, Anna! Die Adresse anna@example.org wurde bestätigt./),
    ).toBeInTheDocument();
  });

  it("reports an expired key without pretending it worked", async () => {
    server.use(
      http.post(api(`/api/members/public/confirm-mail/${KEY}`), () =>
        HttpResponse.json({ detail: "No Member matches the given query" }, { status: 404 }),
      ),
    );
    const { user } = renderFlow(<ConfirmMailFlow />);

    await user.click(screen.getByRole("button", { name: "E-Mail bestätigen" }));
    // Django's own 404 text is developer-facing, so a 404 always reads the same.
    expect(await screen.findByText("Nicht gefunden.")).toBeInTheDocument();
    // Still on the action screen, so a retry is possible.
    expect(screen.getByRole("button", { name: "E-Mail bestätigen" })).toBeInTheDocument();
  });
});

describe("confirm waiting", () => {
  it("confirms the applicant stays on the list", async () => {
    server.use(
      http.post(api(`/api/members/public/confirm-waiting/${KEY}`), () =>
        HttpResponse.json({ prename: "Bea", already_confirmed: false }),
      ),
    );
    const { user } = renderFlow(<ConfirmWaitingFlow />);
    await user.click(screen.getByRole("button", { name: "Warteliste bestätigen" }));
    expect(
      await screen.findByText("Danke, Bea! Du stehst weiterhin auf der Warteliste."),
    ).toBeInTheDocument();
  });

  it("says so when the confirmation was already on file", async () => {
    server.use(
      http.post(api(`/api/members/public/confirm-waiting/${KEY}`), () =>
        HttpResponse.json({ prename: "Bea", already_confirmed: true }),
      ),
    );
    const { user } = renderFlow(<ConfirmWaitingFlow />);
    await user.click(screen.getByRole("button", { name: "Warteliste bestätigen" }));
    expect(
      await screen.findByText("Danke, Bea! Deine Wartelisten-Bestätigung lag bereits vor."),
    ).toBeInTheDocument();
  });

  it("surfaces a rejected confirmation", async () => {
    server.use(
      http.post(api(`/api/members/public/confirm-waiting/${KEY}`), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    const { user } = renderFlow(<ConfirmWaitingFlow />);
    await user.click(screen.getByRole("button", { name: "Warteliste bestätigen" }));
    expect(await screen.findByText("Nicht gefunden.")).toBeInTheDocument();
  });
});

describe("leave the waiting list", () => {
  it("names the person before the irreversible step, then removes them", async () => {
    server.use(
      http.get(api(`/api/members/public/leave-waitinglist/${KEY}`), () =>
        HttpResponse.json({ name: "Cara Klein" }),
      ),
      http.post(api(`/api/members/public/leave-waitinglist/${KEY}`), () =>
        HttpResponse.json({ name: "Cara Klein" }),
      ),
    );
    const { user } = renderFlow(<LeaveWaitingListFlow />);

    expect(await screen.findByText("Cara Klein")).toBeInTheDocument();
    expect(screen.getByText(/kann nicht rückgängig gemacht werden/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Warteliste verlassen" }));
    expect(
      await screen.findByText(/Cara Klein, du wurdest von der Warteliste entfernt/),
    ).toBeInTheDocument();
  });

  it("shows the lookup failure instead of an empty confirmation", async () => {
    server.use(
      http.get(api(`/api/members/public/leave-waitinglist/${KEY}`), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    renderFlow(<LeaveWaitingListFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });

  it("reports a failed removal", async () => {
    server.use(
      http.get(api(`/api/members/public/leave-waitinglist/${KEY}`), () =>
        HttpResponse.json({ name: "Cara Klein" }),
      ),
      http.post(api(`/api/members/public/leave-waitinglist/${KEY}`), () =>
        HttpResponse.json({ detail: "Schon entfernt." }, { status: 409 }),
      ),
    );
    const { user } = renderFlow(<LeaveWaitingListFlow />);
    await user.click(await screen.findByRole("button", { name: "Warteliste verlassen" }));
    expect(await screen.findByText("Schon entfernt.")).toBeInTheDocument();
  });
});

describe("accept an invitation", () => {
  const DETAIL = {
    groupname: "Klettergruppe",
    timeinfo: "montags 18:00",
    contact_email: "kletter@example.org",
  };

  it("shows what is being accepted, then accepts it", async () => {
    server.use(
      http.get(api(`/api/members/public/confirm-invitation/${KEY}`), () =>
        HttpResponse.json(DETAIL),
      ),
      http.post(api(`/api/members/public/confirm-invitation/${KEY}`), () =>
        HttpResponse.json({ groupname: "Klettergruppe" }),
      ),
    );
    const { user } = renderFlow(<ConfirmInvitationFlow />);

    expect(await screen.findByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByText("montags 18:00")).toBeInTheDocument();
    expect(screen.getByText("kletter@example.org")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Einladung annehmen" }));
    expect(await screen.findByText(/Wir\s+freuen uns auf dich!/)).toBeInTheDocument();
  });

  it("omits the contact row when the group publishes no address", async () => {
    server.use(
      http.get(api(`/api/members/public/confirm-invitation/${KEY}`), () =>
        HttpResponse.json({ ...DETAIL, contact_email: null }),
      ),
    );
    renderFlow(<ConfirmInvitationFlow />);
    await screen.findByText("Klettergruppe");
    expect(screen.queryByText("Kontakt")).not.toBeInTheDocument();
  });

  it("reports a failed acceptance", async () => {
    server.use(
      http.get(api(`/api/members/public/confirm-invitation/${KEY}`), () =>
        HttpResponse.json(DETAIL),
      ),
      http.post(api(`/api/members/public/confirm-invitation/${KEY}`), () =>
        HttpResponse.json({ detail: "Die Einladung ist abgelaufen." }, { status: 410 }),
      ),
    );
    const { user } = renderFlow(<ConfirmInvitationFlow />);
    await user.click(await screen.findByRole("button", { name: "Einladung annehmen" }));
    expect(await screen.findByText("Die Einladung ist abgelaufen.")).toBeInTheDocument();
  });
});

describe("reject an invitation", () => {
  const DETAIL = {
    groupname: "Klettergruppe",
    timeinfo: "montags 18:00",
    contact_email: null,
  };

  function rejectReturns(left: boolean) {
    server.use(
      http.get(api(`/api/members/public/reject-invitation/${KEY}`), () =>
        HttpResponse.json(DETAIL),
      ),
      http.post(api(`/api/members/public/reject-invitation/${KEY}`), async ({ request }) => {
        const body = (await request.json()) as { action: string };
        return HttpResponse.json({
          groupname: "Klettergruppe",
          left_waitinglist: body.action === "leave",
        });
      }),
    );
    return left;
  }

  it("can decline but stay on the waiting list", async () => {
    rejectReturns(false);
    const { user } = renderFlow(<RejectInvitationFlow />);
    await user.click(
      await screen.findByRole("button", { name: "Nur ablehnen (Warteliste behalten)" }),
    );
    expect(
      await screen.findByText(/Du bleibst weiterhin auf der Warteliste\./),
    ).toBeInTheDocument();
  });

  it("can decline and leave the waiting list in one step", async () => {
    rejectReturns(true);
    const { user } = renderFlow(<RejectInvitationFlow />);
    await user.click(
      await screen.findByRole("button", { name: "Ablehnen und Warteliste verlassen" }),
    );
    expect(
      await screen.findByText(/Du wurdest außerdem von der Warteliste entfernt\./),
    ).toBeInTheDocument();
  });

  it("shows the contact when the group published one", async () => {
    server.use(
      http.get(api(`/api/members/public/reject-invitation/${KEY}`), () =>
        HttpResponse.json({ ...DETAIL, contact_email: "kletter@example.org" }),
      ),
    );
    renderFlow(<RejectInvitationFlow />);
    expect(await screen.findByText("kletter@example.org")).toBeInTheDocument();
  });

  it("reports a failed rejection", async () => {
    server.use(
      http.get(api(`/api/members/public/reject-invitation/${KEY}`), () =>
        HttpResponse.json(DETAIL),
      ),
      http.post(api(`/api/members/public/reject-invitation/${KEY}`), () =>
        HttpResponse.json({ detail: "Nicht mehr möglich." }, { status: 409 }),
      ),
    );
    const { user } = renderFlow(<RejectInvitationFlow />);
    await user.click(await screen.findByRole("button", { name: /Nur ablehnen/ }));
    expect(await screen.findByText("Nicht mehr möglich.")).toBeInTheDocument();
  });
});

describe("newsletter unsubscribe", () => {
  it("names the address before unsubscribing it", async () => {
    server.use(
      http.get(api("/api/mailer/public/unsubscribe"), () =>
        HttpResponse.json({ name: "Dana", email: "dana@example.org" }),
      ),
      http.post(api("/api/mailer/public/unsubscribe"), () =>
        HttpResponse.json({ name: "Dana", email: "dana@example.org" }),
      ),
    );
    const { user } = renderFlow(<UnsubscribeFlow />);

    expect(await screen.findByText("dana@example.org")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Newsletter abbestellen" }));
    expect(
      await screen.findByText(/Dana, die Adresse dana@example.org erhält keine Newsletter mehr\./),
    ).toBeInTheDocument();
  });

  it("reports a failed unsubscribe", async () => {
    server.use(
      http.get(api("/api/mailer/public/unsubscribe"), () =>
        HttpResponse.json({ name: "Dana", email: "dana@example.org" }),
      ),
      http.post(api("/api/mailer/public/unsubscribe"), () =>
        HttpResponse.json({ detail: "Schlüssel abgelaufen." }, { status: 410 }),
      ),
    );
    const { user } = renderFlow(<UnsubscribeFlow />);
    await user.click(await screen.findByRole("button", { name: "Newsletter abbestellen" }));
    expect(await screen.findByText("Schlüssel abgelaufen.")).toBeInTheDocument();
  });
});

describe("set a password", () => {
  it("creates a new account, asking for a username", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/logindata/register"), () =>
        HttpResponse.json({
          name: "Emil Ernst",
          suggested_username: "emil.ernst",
          is_reset_mode: false,
        }),
      ),
      http.post(api("/api/logindata/register"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ is_reset_mode: false });
      }),
    );
    const { user } = renderFlow(<PasswordFlow />);

    expect(await screen.findByText(/richte hier deinen Zugang ein/)).toBeInTheDocument();
    // The suggested username is prefilled but editable.
    expect(screen.getByLabelText("Benutzername")).toHaveValue("emil.ernst");

    await user.type(screen.getByLabelText(/Anmeldepasswort/), "testtest");
    await user.type(screen.getByLabelText("Neues Passwort"), "Sup3rSecret!");
    await user.type(screen.getByLabelText("Passwort wiederholen"), "Sup3rSecret!");
    await user.click(screen.getByRole("button", { name: "Passwort speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({
      key: KEY,
      registration_password: "testtest",
      new_password1: "Sup3rSecret!",
      new_password2: "Sup3rSecret!",
      username: "emil.ernst",
    });
    expect(await screen.findByText("Dein Konto wurde erstellt.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Anmeldung" })).toHaveAttribute("href", "/login");
  });

  it("resets an existing password without touching the username", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/logindata/register"), () =>
        HttpResponse.json({
          name: "Emil Ernst",
          suggested_username: "emil.ernst",
          is_reset_mode: true,
        }),
      ),
      http.post(api("/api/logindata/register"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ is_reset_mode: true });
      }),
    );
    const { user } = renderFlow(<PasswordFlow />);

    expect(await screen.findByText(/setze hier ein neues Passwort/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Benutzername")).not.toBeInTheDocument();

    await user.type(screen.getByLabelText(/Anmeldepasswort/), "testtest");
    await user.type(screen.getByLabelText("Neues Passwort"), "Sup3rSecret!");
    await user.type(screen.getByLabelText("Passwort wiederholen"), "Sup3rSecret!");
    await user.click(screen.getByRole("button", { name: "Passwort speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ username: null });
    expect(await screen.findByText("Dein Passwort wurde geändert.")).toBeInTheDocument();
  });

  it("shows Django's password rules when the server rejects the choice", async () => {
    server.use(
      http.get(api("/api/logindata/register"), () =>
        HttpResponse.json({ name: "Emil", suggested_username: "emil", is_reset_mode: true }),
      ),
      http.post(api("/api/logindata/register"), () =>
        HttpResponse.json({ detail: "Das Passwort ist zu kurz." }, { status: 422 }),
      ),
    );
    const { user } = renderFlow(<PasswordFlow />);
    await user.click(await screen.findByRole("button", { name: "Passwort speichern" }));
    expect(await screen.findByText("Das Passwort ist zu kurz.")).toBeInTheDocument();
  });

  it("reports an invalid key from the lookup", async () => {
    server.use(
      http.get(api("/api/logindata/register"), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    renderFlow(<PasswordFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});

describe("echo (data refresh)", () => {
  const PREFILL = {
    member: {
      prename: "Frida",
      lastname: "Fuchs",
      gender: 1,
      street: "Weg 1",
      plz: "71634",
      town: "Ludwigsburg",
      address_extra: "",
      phone_number: "0711 1",
      dav_badge_no: "",
      photos_may_be_taken: true,
    },
    emergency_contacts: [
      { prename: "Erika", lastname: "Fuchs", phone_number: "0711 2", email: "e@example.org" },
    ],
  };

  function echoReturns(prefill: Record<string, unknown> = PREFILL) {
    server.use(
      http.get(api(`/api/members/public/echo/${KEY}`), () => HttpResponse.json({ name: "Frida" })),
      http.post(api(`/api/members/public/echo/${KEY}/prefill`), () => HttpResponse.json(prefill)),
    );
  }

  it("gates the form behind the password from the e-mail", async () => {
    echoReturns();
    const { user } = renderFlow(<EchoFlow />);

    expect(
      await screen.findByText(/Bitte gib das Passwort aus der E-Mail ein/),
    ).toBeInTheDocument();
    await user.type(screen.getByLabelText("Passwort"), "geheim");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    expect(await screen.findByDisplayValue("Frida")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Erika")).toBeInTheDocument();
  });

  it("reports a wrong password without showing any data", async () => {
    server.use(
      http.get(api(`/api/members/public/echo/${KEY}`), () => HttpResponse.json({ name: "Frida" })),
      http.post(api(`/api/members/public/echo/${KEY}/prefill`), () =>
        HttpResponse.json({ detail: "Das Passwort ist falsch." }, { status: 403 }),
      ),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));

    // A 403 body can carry internals, so the status decides the wording.
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Frida")).not.toBeInTheDocument();
  });

  it("starts with one blank contact when none are on file", async () => {
    echoReturns({ ...PREFILL, emergency_contacts: [] });
    const { user } = renderFlow(<EchoFlow />);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));

    await screen.findByDisplayValue("Frida");
    // One editable, empty contact block rather than none at all.
    expect(screen.getByRole("button", { name: /Weiteren Kontakt hinzufügen/ })).toBeInTheDocument();
    expect(screen.queryByDisplayValue("Erika")).not.toBeInTheDocument();
  });

  it("submits the edited data and offers the registration-form upload", async () => {
    let body: Record<string, unknown> | null = null;
    echoReturns();
    server.use(
      http.post(api(`/api/members/public/echo/${KEY}`), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          name: "Frida",
          needs_registration_form_upload: true,
          upload_registration_form_key: "UPKEY",
        });
      }),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.type(await screen.findByLabelText("Passwort"), "geheim");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    const town = await screen.findByDisplayValue("Ludwigsburg");
    await user.clear(town);
    await user.type(town, "Stuttgart");
    await user.click(screen.getByLabelText("Fotos dürfen gemacht werden"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      town: "Stuttgart",
      password: "geheim",
      photos_may_be_taken: false,
    });
    expect(await screen.findByText(/Vielen Dank, Frida!/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Jetzt Anmeldebogen hochladen" })).toHaveAttribute(
      "href",
      "/anmeldebogen?key=UPKEY",
    );
  });

  it("does not offer an upload link when none is needed", async () => {
    echoReturns();
    server.use(
      http.post(api(`/api/members/public/echo/${KEY}`), () =>
        HttpResponse.json({
          name: "Frida",
          needs_registration_form_upload: false,
          upload_registration_form_key: null,
        }),
      ),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));
    await user.click(await screen.findByRole("button", { name: "Speichern" }));

    expect(await screen.findByText(/Vielen Dank, Frida!/)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Anmeldebogen/ })).not.toBeInTheDocument();
  });

  it("reports a rejected save on the form", async () => {
    echoReturns();
    server.use(
      http.post(api(`/api/members/public/echo/${KEY}`), () =>
        ninjaValidation([
          { type: "string_too_short", loc: ["body", "payload", "plz"], msg: "too short" },
        ]),
      ),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));
    await user.click(await screen.findByRole("button", { name: "Speichern" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(/plz/);
    expect(error).not.toHaveTextContent("[object Object]");
  });

  it("lets the user change their gender through the select", async () => {
    let body: Record<string, unknown> | null = null;
    echoReturns();
    server.use(
      http.post(api(`/api/members/public/echo/${KEY}`), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ name: "Frida", needs_registration_form_upload: false });
      }),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.click(await screen.findByRole("button", { name: "Weiter" }));

    await screen.findByDisplayValue("Frida");
    const genderTrigger = screen
      .getByText("Geschlecht")
      .closest(".field")!
      .querySelector(".ss-trigger") as HTMLElement;
    await user.click(genderTrigger);
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: "Divers",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    // The select yields strings; the API wants the enum number.
    expect(body).toMatchObject({ gender: 2 });
  });

  it("reports an invalid echo key from the lookup", async () => {
    server.use(
      http.get(api(`/api/members/public/echo/${KEY}`), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    renderFlow(<EchoFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});

describe("invited registration", () => {
  const PREFILL = {
    group: { id: 5, name: "Klettergruppe" },
    member: {
      prename: "Greta",
      lastname: "Groß",
      email: "greta@example.org",
      birth_date: "2011-05-04",
      gender: 1,
      street: "Weg 1",
      plz: "71634",
      town: "Ludwigsburg",
      address_extra: "",
      phone_number: "0711 1",
      dav_badge_no: "",
      photos_may_be_taken: true,
      legal_guardians: "",
    },
  };

  it("names the group and submits the completed registration", async () => {
    let body: { emergency_contacts: unknown[]; prename: string } | null = null;
    server.use(
      http.get(api(`/api/members/public/invited-registration/${KEY}`), () =>
        HttpResponse.json(PREFILL),
      ),
      http.post(api(`/api/members/public/invited-registration/${KEY}`), async ({ request }) => {
        body = (await request.json()) as { emergency_contacts: unknown[]; prename: string };
        return HttpResponse.json({ name: "Greta", upload_registration_form_key: "UPKEY" });
      }),
    );
    const { user } = renderFlow(<InvitedRegistrationFlow />);

    expect(await screen.findByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Greta")).toBeInTheDocument();

    await user.type(screen.getAllByLabelText(/^Vorname/).slice(-1)[0], "Erika");
    await user.type(screen.getAllByLabelText(/^Nachname/).slice(-1)[0], "Groß");
    await user.type(screen.getAllByLabelText(/^Telefon/).slice(-1)[0], "0711 2");
    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body!.prename).toBe("Greta");
    expect(body!.emergency_contacts).toHaveLength(1);
    expect(await screen.findByText(/Vielen Dank, Greta!/)).toBeInTheDocument();
  });

  it("reports a rejected submission", async () => {
    server.use(
      http.get(api(`/api/members/public/invited-registration/${KEY}`), () =>
        HttpResponse.json(PREFILL),
      ),
      http.post(api(`/api/members/public/invited-registration/${KEY}`), () =>
        HttpResponse.json({ detail: "Die Einladung ist abgelaufen." }, { status: 410 }),
      ),
    );
    const { user } = renderFlow(<InvitedRegistrationFlow />);
    await screen.findByDisplayValue("Greta");
    await user.type(screen.getAllByLabelText(/^Vorname/).slice(-1)[0], "Erika");
    await user.type(screen.getAllByLabelText(/^Nachname/).slice(-1)[0], "Groß");
    await user.type(screen.getAllByLabelText(/^Telefon/).slice(-1)[0], "0711 2");
    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));
    expect(await screen.findByText("Die Einladung ist abgelaufen.")).toBeInTheDocument();
  });

  it("reports an invalid invitation key", async () => {
    server.use(
      http.get(api(`/api/members/public/invited-registration/${KEY}`), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    renderFlow(<InvitedRegistrationFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});

describe("upload the registration form", () => {
  function verifyReturns(hasForm = false) {
    server.use(
      http.get(api(`/api/members/public/upload-registration-form/${KEY}`), () =>
        HttpResponse.json({ name: "Hanna", has_registration_form: hasForm }),
      ),
    );
  }

  it("keeps upload disabled until a file is chosen, then uploads it", async () => {
    verifyReturns();
    let uploaded: string | undefined;
    server.use(
      http.post(api(`/api/members/public/upload-registration-form/${KEY}`), async ({ request }) => {
        [uploaded] = await multipartFilenames(request);
        return HttpResponse.json({ name: "Hanna" });
      }),
    );
    const { user } = renderFlow(<UploadFormFlow />);

    expect(await screen.findByRole("button", { name: "Hochladen" })).toBeDisabled();

    const file = new File(["%PDF"], "Anmeldebogen.pdf", { type: "application/pdf" });
    await user.upload(screen.getByLabelText("Datei"), file);
    expect(screen.getByRole("button", { name: "Hochladen" })).toBeEnabled();

    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    await waitFor(() => expect(uploaded).toBe("Anmeldebogen.pdf"));
    expect(
      await screen.findByText(/Danke, Hanna! Dein Anmeldebogen wurde hochgeladen\./),
    ).toBeInTheDocument();
  });

  it("reports a rejected upload", async () => {
    verifyReturns();
    server.use(
      http.post(api(`/api/members/public/upload-registration-form/${KEY}`), () =>
        HttpResponse.json({ detail: "Die Datei ist zu groß." }, { status: 413 }),
      ),
    );
    const { user } = renderFlow(<UploadFormFlow />);
    await user.upload(
      await screen.findByLabelText("Datei"),
      new File(["x"], "gross.pdf", { type: "application/pdf" }),
    );
    await user.click(screen.getByRole("button", { name: "Hochladen" }));
    expect(await screen.findByText("Die Datei ist zu groß.")).toBeInTheDocument();
  });

  it("reports an invalid upload key", async () => {
    server.use(
      http.get(api(`/api/members/public/upload-registration-form/${KEY}`), () =>
        HttpResponse.json({ detail: "Unbekannter Schlüssel." }, { status: 404 }),
      ),
    );
    renderFlow(<UploadFormFlow />);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});

describe("submit an event proposal", () => {
  it("sends the filled proposal with numbers where the API wants numbers", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/public/termine"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderWithApp(<SubmitTerminFlow />, { authenticated: false });

    // The selects are built from `/public/enums`, so the form arrives async.
    await user.type(await screen.findByLabelText("Titel"), "Klettersteig Allgäu");
    await user.type(screen.getByLabelText("Untertitel"), "für Fortgeschrittene");
    await user.type(screen.getByLabelText("Von"), "2026-07-04");
    await user.type(screen.getByLabelText("Bis"), "2026-07-05");
    await user.clear(screen.getByLabelText("Höhenmeter"));
    await user.type(screen.getByLabelText("Höhenmeter"), "1200");
    await user.clear(screen.getByLabelText("Max. Teilnehmende"));
    await user.type(screen.getByLabelText("Max. Teilnehmende"), "8");
    await user.type(screen.getByLabelText("Beschreibung"), "Zwei Tage am Fels.");
    await user.type(screen.getByLabelText("Organisator:in"), "Ingo Iller");
    await user.type(screen.getByLabelText("E-Mail"), "ingo@example.org");
    await user.click(screen.getByRole("button", { name: "Termin einreichen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      title: "Klettersteig Allgäu",
      start_date: "2026-07-04",
      anforderung_hoehe: 1200,
      max_participants: 8,
      // Unedited selects keep their defaults from the model's choices.
      group: "ASG",
      category: "SON",
      klassifizierung: "Gemeinschaftstour",
    });
    expect(await screen.findByText(/Dein Terminvorschlag wurde eingereicht/)).toBeInTheDocument();
  });

  it("changes a choice through its dropdown", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/public/termine"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderWithApp(<SubmitTerminFlow />, { authenticated: false });

    const trigger = (await screen.findByText("Kategorie"))
      .closest(".field")!
      .querySelector(".ss-trigger") as HTMLElement;
    await user.click(trigger);
    await user.click(
      within(document.querySelector(".ms-dropdown") as HTMLElement).getByRole("button", {
        name: "Klettersteig",
      }),
    );
    await user.click(screen.getByRole("button", { name: "Termin einreichen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ category: "KST" });
  });

  it("keeps a half-filled form when the choice lists fail to refetch", async () => {
    // The lists never change, so `usePublicTerminEnums` pins `staleTime` to
    // Infinity. Without that a tab refocus refetches them, and because
    // `QueryBoundary` reads `error` before `data`, one failed request on flaky
    // mobile data would replace the form with an error state — throwing away
    // everything a volunteer had typed into a twenty-field form.
    const { user } = renderWithApp(<SubmitTerminFlow />, { authenticated: false });
    await user.type(await screen.findByLabelText("Titel"), "Klettersteig Allgäu");

    let refetched = false;
    server.use(
      http.get(api("/api/ludwigsburgalpin/public/enums"), () => {
        refetched = true;
        return HttpResponse.json({ detail: "kaputt" }, { status: 500 });
      }),
    );
    window.dispatchEvent(new Event("visibilitychange"));
    await waitFor(() => expect(screen.getByLabelText("Titel")).toHaveValue("Klettersteig Allgäu"));

    expect(refetched).toBe(false);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Termin einreichen" })).toBeInTheDocument();
  });

  it("reports a rejected proposal on the form", async () => {
    server.use(
      http.post(api("/api/ludwigsburgalpin/public/termine"), () =>
        ninjaValidation([
          { type: "string_too_short", loc: ["body", "payload", "title"], msg: "too short" },
        ]),
      ),
    );
    const { user } = renderWithApp(<SubmitTerminFlow />, { authenticated: false });
    await user.click(await screen.findByRole("button", { name: "Termin einreichen" }));

    const error = await screen.findByRole("alert");
    expect(error).toHaveTextContent(/title/);
    expect(error).not.toHaveTextContent("[object Object]");
  });
});

/* --- exhaustive field passes ---------------------------------------------- */

describe("public flows — every field", () => {
  it("Terminvorschlag: carries every field into the submission", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/ludwigsburgalpin/public/termine"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderWithApp(<SubmitTerminFlow />, { authenticated: false });

    await screen.findByLabelText("Titel");
    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Termin einreichen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      title: "Text",
      subtitle: "Text",
      start_date: "2026-03-04",
      end_date: "2026-03-04",
      description: "Text",
      equipment: "Text",
      voraussetzungen: "Text",
      responsible: "Text",
      phone: "Text",
      email: "test@example.org",
      anforderung_hoehe: 3,
      anforderung_strecke: 3,
      anforderung_dauer: 3,
      max_participants: 3,
      // Every choice resolved to its first option.
      group: "ASG",
      category: "WAN",
      condition: "gering",
      technik: "leicht",
      saison: "ganzjährig",
      eventart: "Einzeltermin",
      klassifizierung: "Gemeinschaftstour",
    });
  });

  it("Echo: carries every field into the submission", async () => {
    server.use(
      http.get(api(`/api/members/public/echo/${KEY}`), () => HttpResponse.json({ name: "Frida" })),
      http.post(api(`/api/members/public/echo/${KEY}/prefill`), () =>
        HttpResponse.json({
          member: {
            prename: "Frida",
            lastname: "Fuchs",
            gender: 1,
            street: "Weg 1",
            plz: "71634",
            town: "Ludwigsburg",
            address_extra: "",
            phone_number: "0711 1",
            dav_badge_no: "",
            photos_may_be_taken: true,
          },
          emergency_contacts: [],
        }),
      ),
    );
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api(`/api/members/public/echo/${KEY}`), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ name: "Frida", needs_registration_form_upload: false });
      }),
    );
    const { user } = renderFlow(<EchoFlow />);
    await user.type(await screen.findByLabelText("Passwort"), "geheim");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    const form = (await screen.findByDisplayValue("Frida")).closest("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      prename: "Text",
      lastname: "Text",
      street: "Text",
      plz: "Text",
      town: "Text",
      address_extra: "Text",
      phone_number: "Text",
      dav_badge_no: "Text",
      photos_may_be_taken: false,
      gender: 0,
    });
  });

  it("Warteliste: carries every field into the submission", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/public/waiting-list"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ name: "Warte Kandidat" });
      }),
    );
    const { user } = renderWithApp(<WaitingListFlow />, { authenticated: false });

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Eintragen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      prename: "Text",
      lastname: "Text",
      email: "test@example.org",
      birth_date: "2026-03-04",
      application_text: "Text",
      gender: 0,
    });
  });

  it("Einladung: carries every field into the submission", async () => {
    server.use(
      http.get(api(`/api/members/public/invited-registration/${KEY}`), () =>
        HttpResponse.json({
          group: { id: 5, name: "Klettergruppe" },
          member: {
            prename: "Greta",
            lastname: "Groß",
            email: "greta@example.org",
            birth_date: "2011-05-04",
            gender: 1,
            street: "Weg 1",
            plz: "71634",
            town: "Ludwigsburg",
            address_extra: "",
            phone_number: "0711 1",
            dav_badge_no: "",
            photos_may_be_taken: true,
            legal_guardians: "",
          },
        }),
      ),
    );
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api(`/api/members/public/invited-registration/${KEY}`), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ name: "Greta", upload_registration_form_key: "UPKEY" });
      }),
    );
    const { user } = renderFlow(<InvitedRegistrationFlow />);
    await screen.findByDisplayValue("Greta");

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await pickEverySelect(user, form);
    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      prename: "Text",
      lastname: "Text",
      email: "test@example.org",
      birth_date: "2026-03-04",
      photos_may_be_taken: false,
    });
  });

  it("Passwort setzen: carries every field into the submission", async () => {
    server.use(
      http.get(api("/api/logindata/register"), () =>
        HttpResponse.json({ name: "Emil", suggested_username: "emil", is_reset_mode: false }),
      ),
    );
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/logindata/register"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ is_reset_mode: false });
      }),
    );
    const { user } = renderFlow(<PasswordFlow />);
    await screen.findByLabelText("Benutzername");

    const form = document.querySelector("form") as HTMLElement;
    await fillEveryField(user, form);
    await user.click(screen.getByRole("button", { name: "Passwort speichern" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      key: KEY,
      registration_password: "Text",
      new_password1: "Text",
      new_password2: "Text",
      username: "Text",
    });
  });

  it("removes an added emergency contact again", async () => {
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ group: { id: 5, name: "Jugendleiter" } }),
      ),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/Passwort/), "juleiti");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await screen.findByRole("button", { name: "Anmeldung absenden" });

    // A second block gets its own remove button; the first never does.
    expect(screen.queryByRole("button", { name: "Kontakt entfernen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Weiteren Kontakt hinzufügen/ }));
    await user.click(screen.getAllByRole("button", { name: "Kontakt entfernen" })[0]);
    expect(screen.queryByRole("button", { name: "Kontakt entfernen" })).not.toBeInTheDocument();
  });
});
