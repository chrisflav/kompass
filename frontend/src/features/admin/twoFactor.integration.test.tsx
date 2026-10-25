import { screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { api, http, HttpResponse, server } from "../../test/server";
import { renderRoute } from "../../test/utils";

const BASE = "/api/logindata/two-factor";

const APP = {
  id: 1,
  kind: "totp",
  name: "Handy",
  created: "2026-10-01T10:00:00Z",
  last_used: null,
  passwordless: false,
};
const PASSKEY = {
  id: 4,
  kind: "webauthn",
  name: "YubiKey",
  created: "2026-10-02T10:00:00Z",
  last_used: "2026-10-20T10:00:00Z",
  passwordless: true,
};
const CODES = Array.from({ length: 10 }, (_, i) => `abcd-efgh-ijkl-mn${i}${i}`);

function statusReturns(factors: unknown[] = [], extra: Record<string, unknown> = {}) {
  server.use(
    http.get(api(BASE), () =>
      HttpResponse.json({
        available: true,
        enabled: factors.length > 0,
        factors,
        recovery_codes_remaining: factors.length ? 8 : 0,
        ...extra,
      }),
    ),
  );
}

const wrongPassword = () =>
  HttpResponse.json(
    { detail: ["Das Passwort ist nicht korrekt."], errors: { password: ["Das Passwort ist nicht korrekt."] } },
    { status: 422 },
  );

/** The header's add action, then the kind of factor in its dialog. */
async function chooseFactor(user: ReturnType<typeof renderRoute>["user"], kind: string) {
  await user.click(await screen.findByRole("button", { name: "Faktor hinzufügen" }));
  const dialog = within(await screen.findByRole("dialog", { name: "Faktor hinzufügen" }));
  await user.click(dialog.getByRole("button", { name: kind }));
}

beforeAll(async () => {
  await import("../../kompassRoutes");
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("two-factor authentication", () => {
  it("is reachable from the user menu", async () => {
    statusReturns();
    server.use(http.get(api("/api/logindata/tokens"), () => HttpResponse.json([])));
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: /Hannah/ }));
    await user.click(await screen.findByRole("link", { name: "Zwei-Faktor-Authentifizierung" }));
    expect(await screen.findByText("Du hast noch keinen zweiten Faktor eingerichtet.")).toBeInTheDocument();
  });

  it("offers a security key only where the browser can use one", async () => {
    statusReturns();
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Faktor hinzufügen" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Faktor hinzufügen" }));
    expect(dialog.getByRole("button", { name: "Authenticator-App" })).toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "Sicherheitsschlüssel" })).toBeNull();
  });

  it("says who manages the factors where an identity provider signs in", async () => {
    statusReturns([], { available: false });
    renderRoute("/kompass/security");
    expect(await screen.findByText(/verwaltet euer Identitätsanbieter/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Faktor hinzufügen" })).toBeNull();
  });

  it("adds an authenticator app and shows the recovery codes once", async () => {
    statusReturns();
    let setupBody: unknown = null;
    let confirmBody: unknown = null;
    server.use(
      http.post(api(`${BASE}/totp/setup`), async ({ request }) => {
        setupBody = await request.json();
        return HttpResponse.json({
          secret: "JBSWY3DPEHPK3PXP",
          uri: "otpauth://totp/Kompass:hannah?secret=JBSWY3DPEHPK3PXP&issuer=Kompass",
          state: "signed-state",
        });
      }),
      http.post(api(`${BASE}/totp`), async ({ request }) => {
        confirmBody = await request.json();
        return HttpResponse.json({ factor: APP, recovery_codes: CODES }, { status: 201 });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Authenticator-App");

    let dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "geheim");
    await user.click(dialog.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(setupBody).toEqual({ password: "geheim" }));

    expect(await dialog.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    expect(dialog.getByLabelText("QR-Code für die Authenticator-App")).toBeInTheDocument();
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "Handy");
    await user.type(dialog.getByLabelText(/Code aus der App/), "123456");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    await waitFor(() =>
      expect(confirmBody).toEqual({ name: "Handy", code: "123456", state: "signed-state" }),
    );

    dialog = within(await screen.findByRole("dialog", { name: "Deine Wiederherstellungscodes" }));
    expect(dialog.getByText(CODES[0])).toBeInTheDocument();
    const copy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(dialog.getByRole("button", { name: "Kopieren" }));
    expect(copy).toHaveBeenCalledWith(CODES.join("\n"));
    await user.click(dialog.getByRole("button", { name: "Ich habe sie gespeichert" }));
    expect(screen.queryByText(CODES[0])).toBeNull();
  });

  it("shows a wrong password and a wrong code on their fields", async () => {
    statusReturns();
    let attempts = 0;
    server.use(
      http.post(api(`${BASE}/totp/setup`), () =>
        attempts++ === 0
          ? wrongPassword()
          : HttpResponse.json({ secret: "JBSWY3DPEHPK3PXP", uri: "otpauth://totp/x", state: "s" }),
      ),
      http.post(api(`${BASE}/totp`), () =>
        HttpResponse.json(
          { detail: ["Der Code ist nicht korrekt."], errors: { code: ["Der Code ist nicht korrekt."] } },
          { status: 422 },
        ),
      ),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Authenticator-App");
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "falsch");
    await user.click(dialog.getByRole("button", { name: "Weiter" }));
    expect(await dialog.findByText("Das Passwort ist nicht korrekt.")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Weiter" }));
    await user.type(await dialog.findByLabelText(/Code aus der App/), "000000");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    expect(await dialog.findByText("Der Code ist nicht korrekt.")).toBeInTheDocument();
  });

  it("registers a security key through the browser", async () => {
    statusReturns([APP]);
    const bytes = (s: string) => new TextEncoder().encode(s).buffer;
    const create = vi.fn().mockResolvedValue({
      id: "a2V5",
      rawId: bytes("key"),
      type: "public-key",
      response: {
        clientDataJSON: bytes("client"),
        attestationObject: bytes("attest"),
        getTransports: () => ["usb"],
      },
      getClientExtensionResults: () => ({ credProps: { rk: true } }),
    });
    vi.stubGlobal("PublicKeyCredential", function PublicKeyCredential() {});
    Object.defineProperty(navigator, "credentials", { value: { create }, configurable: true });
    let confirmBody: Record<string, unknown> | null = null;
    server.use(
      http.post(api(`${BASE}/webauthn/setup`), () =>
        HttpResponse.json({
          options: {
            rp: { id: "localhost", name: "Kompass" },
            user: { id: "Mg", name: "hannah", displayName: "Hannah" },
            challenge: "Y2hhbGxlbmdl",
            excludeCredentials: [{ id: "b2xk", type: "public-key" }],
          },
          state: "key-state",
        }),
      ),
      http.post(api(`${BASE}/webauthn`), async ({ request }) => {
        confirmBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ factor: PASSKEY, recovery_codes: [] }, { status: 201 });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Sicherheitsschlüssel");
    const dialog = within(await screen.findByRole("dialog"));
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "YubiKey");
    await user.type(dialog.getByLabelText(/Dein Passwort/), "geheim");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    await waitFor(() => expect(confirmBody).not.toBeNull());
    const publicKey = create.mock.calls[0][0].publicKey;
    expect(new TextDecoder().decode(publicKey.challenge)).toBe("challenge");
    expect(new TextDecoder().decode(publicKey.excludeCredentials[0].id)).toBe("old");
    expect(confirmBody).toEqual({
      name: "YubiKey",
      state: "key-state",
      credential: {
        id: "a2V5",
        rawId: "a2V5",
        type: "public-key",
        response: { clientDataJSON: "Y2xpZW50", attestationObject: "YXR0ZXN0", transports: ["usb"] },
        clientExtensionResults: { credProps: { rk: true } },
      },
    });
    expect(await screen.findByText("Sicherheitsschlüssel hinzugefügt.")).toBeInTheDocument();
    // Not the first factor: no recovery codes to show.
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("says so when the key does not answer", async () => {
    statusReturns();
    vi.stubGlobal("PublicKeyCredential", function PublicKeyCredential() {});
    Object.defineProperty(navigator, "credentials", {
      value: { create: vi.fn().mockResolvedValue(null) },
      configurable: true,
    });
    server.use(
      http.post(api(`${BASE}/webauthn/setup`), () =>
        HttpResponse.json({
          options: { user: { id: "Mg" }, challenge: "Y2hhbGxlbmdl" },
          state: "key-state",
        }),
      ),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Sicherheitsschlüssel");
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "geheim");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    expect(await screen.findByText("Der Sicherheitsschlüssel hat nicht geantwortet.")).toBeInTheDocument();
  });

  it("lists, renames and removes factors", async () => {
    statusReturns([APP, PASSKEY]);
    let renamed: unknown = null;
    let removed: unknown = null;
    server.use(
      http.patch(api(`${BASE}/webauthn/4`), async ({ request }) => {
        renamed = await request.json();
        return HttpResponse.json({ ...PASSKEY, name: "Schlüsselbund" });
      }),
      http.post(api(`${BASE}/totp/1/remove`), async ({ request }) => {
        removed = await request.json();
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    expect(await screen.findByText("YubiKey")).toBeInTheDocument();
    expect(screen.getByText("Passkey")).toBeInTheDocument();
    expect(screen.getByText("Authenticator-App")).toBeInTheDocument();
    expect(screen.getByText("nie")).toBeInTheDocument();

    const keyRow = within(screen.getByText("YubiKey").closest("tr") as HTMLElement);
    await user.click(keyRow.getByRole("button", { name: "Umbenennen" }));
    let dialog = within(await screen.findByRole("dialog"));
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "Schlüsselbund");
    await user.click(dialog.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(renamed).toEqual({ name: "Schlüsselbund" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const appRow = within(screen.getByText("Handy").closest("tr") as HTMLElement);
    await user.click(appRow.getByRole("button", { name: "Entfernen" }));
    dialog = within(await screen.findByRole("dialog", { name: "„Handy“ entfernen" }));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "geheim");
    await user.click(dialog.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(removed).toEqual({ password: "geheim" }));
    expect(await screen.findByText("Entfernt.")).toBeInTheDocument();
  });

  it("shows a rename or removal that was refused", async () => {
    statusReturns([APP]);
    server.use(
      http.patch(api(`${BASE}/totp/1`), () =>
        HttpResponse.json(
          { detail: ["Gib einen Namen an."], errors: { name: ["Gib einen Namen an."] } },
          { status: 422 },
        ),
      ),
      http.post(api(`${BASE}/totp/1/remove`), wrongPassword),
    );
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Umbenennen" }));
    let dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Speichern" }));
    expect(await dialog.findByText("Gib einen Namen an.")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Schließen" }));

    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "falsch");
    await user.click(dialog.getByRole("button", { name: "Entfernen" }));
    expect(await dialog.findByText("Das Passwort ist nicht korrekt.")).toBeInTheDocument();
  });

  it("replaces the recovery codes", async () => {
    statusReturns([APP]);
    let attempts = 0;
    server.use(
      http.post(api(`${BASE}/recovery-codes`), () =>
        attempts++ === 0 ? wrongPassword() : HttpResponse.json({ codes: CODES }),
      ),
    );
    const { user } = renderRoute("/kompass/security");
    expect(await screen.findByText("8")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Neue Codes erzeugen" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Dein Passwort/), "geheim");
    await user.click(dialog.getByRole("button", { name: "Erzeugen" }));
    expect(await dialog.findByText("Das Passwort ist nicht korrekt.")).toBeInTheDocument();
    await user.click(dialog.getByRole("button", { name: "Erzeugen" }));
    const shown = within(await screen.findByRole("dialog", { name: "Deine Wiederherstellungscodes" }));
    expect(shown.getByText(CODES[9])).toBeInTheDocument();
  });
});
