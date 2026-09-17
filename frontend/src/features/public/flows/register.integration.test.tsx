import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, ninjaValidation, server } from "../../../test/server";
import { renderWithApp } from "../../../test/utils";
import { RegisterFlow } from "./Register";
import { WaitingListFlow } from "./WaitingList";
import { UploadFormFlow } from "./UploadForm";

/** Fill a labelled input; `which` picks between the member and contact copies. */
async function fill(
  user: ReturnType<typeof renderWithApp>["user"],
  label: RegExp,
  value: string,
  which: "first" | "last" = "first",
) {
  const fields = screen.getAllByLabelText(label);
  await user.clear(fields[which === "first" ? 0 : fields.length - 1]);
  await user.type(fields[which === "first" ? 0 : fields.length - 1], value);
}

/** Fill every required field of the registration form and its first contact. */
async function fillRegisterForm(user: ReturnType<typeof renderWithApp>["user"]) {
  await fill(user, /^Vorname/, "Neu");
  await fill(user, /^Nachname/, "Person");
  await fill(user, /^E-Mail$/, "neu@example.org");
  await fill(user, /^Straße/, "Weg 1");
  await fill(user, /^PLZ/, "71634");
  await fill(user, /^Ort/, "Ludwigsburg");
  await fill(user, /^Vorname/, "Mutter", "last");
  await fill(user, /^Nachname/, "Person", "last");
  await fill(user, /^Telefon/, "0711 1", "last");
}

describe("public registration", () => {
  it("asks for the group password first", () => {
    renderWithApp(<RegisterFlow />, { authenticated: false });
    expect(screen.getByText(/Anmeldepasswort deiner Gruppe/)).toBeInTheDocument();
  });

  it("reports a wrong password without advancing", async () => {
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ detail: ["Das eingegebene Passwort ist falsch."] }, { status: 422 }),
      ),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });

    await user.type(screen.getByLabelText(/Passwort/), "falsch");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    expect(await screen.findByText("Das eingegebene Passwort ist falsch.")).toBeInTheDocument();
    expect(screen.queryByLabelText(/Vorname/)).not.toBeInTheDocument();
  });

  it("shows the form for the verified group", async () => {
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ group: { id: 5, name: "Jugendleiter" } }),
      ),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/Passwort/), "juleiti");
    await user.click(screen.getByRole("button", { name: "Weiter" }));

    // The name sits in its own <strong>, so match on the element that holds it.
    expect(await screen.findByText("Jugendleiter")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anmeldung absenden" })).toBeInTheDocument();
  });

  it("renders a ninja validation error as readable text, not [object Object]", async () => {
    // The exact payload the backend sends when the required fields are blank.
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ group: { id: 5, name: "Jugendleiter" } }),
      ),
      http.post(api("/api/members/public/register"), () =>
        ninjaValidation([
          {
            type: "string_too_short",
            loc: ["body", "payload", "prename"],
            msg: "String should have at least 1 character",
          },
          {
            type: "string_too_short",
            loc: ["body", "payload", "town"],
            msg: "String should have at least 1 character",
          },
        ]),
      ),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/Passwort/), "juleiti");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await screen.findByRole("button", { name: "Anmeldung absenden" });

    // The required attributes stop a truly empty submit in the browser, so fill
    // the form and let the server reject it — which is how a ninja 422 actually
    // reaches this screen.
    await fillRegisterForm(user);
    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));

    const error = await screen.findByRole("alert");
    expect(error).not.toHaveTextContent("[object Object]");
    expect(error).toHaveTextContent(/prename/);
    expect(error).toHaveTextContent(/Dieses Feld darf nicht leer sein/);
    expect(error).toHaveTextContent(/town/);
  });

  it("submits the filled form and offers the next step", async () => {
    let submitted: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ group: { id: 5, name: "Jugendleiter" } }),
      ),
      http.post(api("/api/members/public/register"), async ({ request }) => {
        submitted = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ name: "Neu", upload_registration_form_key: "KEY" });
      }),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/Passwort/), "juleiti");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await screen.findByRole("button", { name: "Anmeldung absenden" });

    await fillRegisterForm(user);

    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));

    expect(await screen.findByText(/Vielen Dank, Neu!/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Anmeldebogen jetzt hochladen/ }),
    ).toHaveAttribute("href", "/anmeldebogen?key=KEY");
    expect(submitted).toMatchObject({ prename: "Neu", town: "Ludwigsburg" });
  });

  it("drops an emergency contact row the user never filled in", async () => {
    let submitted: { emergency_contacts: unknown[] } | null = null;
    server.use(
      http.post(api("/api/members/public/register/verify"), () =>
        HttpResponse.json({ group: { id: 5, name: "Jugendleiter" } }),
      ),
      http.post(api("/api/members/public/register"), async ({ request }) => {
        submitted = (await request.json()) as { emergency_contacts: unknown[] };
        return HttpResponse.json({ name: "Neu", upload_registration_form_key: "KEY" });
      }),
    );
    const { user } = renderWithApp(<RegisterFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/Passwort/), "juleiti");
    await user.click(screen.getByRole("button", { name: "Weiter" }));
    await screen.findByRole("button", { name: "Anmeldung absenden" });

    await fillRegisterForm(user);

    // A second contact block the user opens but leaves untouched.
    await user.click(screen.getByRole("button", { name: /Weiteren Kontakt hinzufügen/ }));
    await user.click(screen.getByRole("button", { name: "Anmeldung absenden" }));

    await waitFor(() => expect(submitted).not.toBeNull());
    expect(submitted!.emergency_contacts).toHaveLength(1);
  });
});

describe("waiting-list flow", () => {
  it("renders a validation error readably", async () => {
    server.use(
      http.post(api("/api/members/public/waiting-list"), () =>
        ninjaValidation([
          {
            type: "string_too_short",
            loc: ["body", "payload", "prename"],
            msg: "String should have at least 1 character",
          },
        ]),
      ),
    );
    const { user } = renderWithApp(<WaitingListFlow />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "Eintragen" }));

    const error = await screen.findByRole("alert");
    expect(error).not.toHaveTextContent("[object Object]");
    expect(error).toHaveTextContent(/Dieses Feld darf nicht leer sein/);
  });

  it("confirms the sign-up and tells the applicant to check their mail", async () => {
    server.use(
      http.post(api("/api/members/public/waiting-list"), () =>
        HttpResponse.json({ name: "Warte Kandidat" }),
      ),
    );
    const { user } = renderWithApp(<WaitingListFlow />, { authenticated: false });
    await user.type(screen.getByLabelText(/^Vorname/), "Warte");
    await user.type(screen.getByLabelText(/^Nachname/), "Kandidat");
    await user.type(screen.getByLabelText(/^E-Mail/), "w@example.org");
    await user.click(screen.getByRole("button", { name: "Eintragen" }));

    expect(await screen.findByText(/Danke, Warte Kandidat!/)).toBeInTheDocument();
  });
});

describe("registration-form upload flow", () => {
  it("refuses to do anything without a key", () => {
    renderWithApp(<UploadFormFlow />, { route: "/anmeldebogen", authenticated: false });
    expect(screen.getByText(/kein Schlüssel angegeben/)).toBeInTheDocument();
  });

  it("walks the applicant through download, sign and upload", async () => {
    server.use(
      http.get(api("/api/members/public/upload-registration-form/:key"), () =>
        HttpResponse.json({ name: "Clara", has_registration_form: false }),
      ),
    );
    renderWithApp(<UploadFormFlow />, {
      route: "/anmeldebogen?key=KEY",
      authenticated: false,
    });

    // The download step is the part that had gone missing: without it nobody
    // knows what they are supposed to upload.
    expect(
      await screen.findByRole("button", { name: /Anmeldebogen herunterladen/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/erziehungsberechtigte Person unterschreiben/)).toBeInTheDocument();
    expect(screen.getByLabelText(/Datei/)).toBeInTheDocument();
  });

  it("says so when a form is already on file", async () => {
    server.use(
      http.get(api("/api/members/public/upload-registration-form/:key"), () =>
        HttpResponse.json({ name: "Clara", has_registration_form: true }),
      ),
    );
    renderWithApp(<UploadFormFlow />, {
      route: "/anmeldebogen?key=KEY",
      authenticated: false,
    });
    expect(await screen.findByText(/Es liegt bereits ein Anmeldebogen vor/)).toBeInTheDocument();
  });
});
