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
const SOON = () => new Date(Date.now() + 10 * 60 * 1000).toISOString();

type Factor = Omit<typeof APP, "last_used"> & { last_used: string | null };

/** The status: confirmed (``elevated``) or not, with these factors. */
function status(factors: Factor[], elevated = true, extra: Record<string, unknown> = {}) {
  return {
    available: true,
    enabled: factors.length > 0,
    has_totp: factors.some((f) => f.kind === "totp"),
    has_webauthn: factors.some((f) => f.kind === "webauthn"),
    elevated_until: elevated ? SOON() : null,
    factors: elevated ? factors : [],
    recovery_codes_remaining: elevated && factors.length ? 8 : 0,
    ...extra,
  };
}

function statusReturns(factors: Factor[] = [], elevated = true, extra: Record<string, unknown> = {}) {
  server.use(http.get(api(BASE), () => HttpResponse.json(status(factors, elevated, extra))));
}

const refused = (field: string, message: string) =>
  HttpResponse.json({ detail: [message], errors: { [field]: [message] } }, { status: 422 });

const bytes = (s: string) => new TextEncoder().encode(s).buffer;

function stubWebAuthn(methods: Record<string, unknown>) {
  vi.stubGlobal("PublicKeyCredential", function PublicKeyCredential() {});
  Object.defineProperty(navigator, "credentials", { value: methods, configurable: true });
}

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

  it("says who manages the factors where an identity provider signs in", async () => {
    statusReturns([], false, { available: false });
    renderRoute("/kompass/security");
    expect(await screen.findByText(/verwaltet euer Identitätsanbieter/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Faktor hinzufügen" })).toBeNull();
    expect(screen.queryByLabelText(/Dein Passwort/)).toBeNull();
  });
});

describe("confirming who is there", () => {
  it("asks for the password while there is no factor", async () => {
    let confirmed = false;
    let body: unknown = null;
    server.use(
      http.get(api(BASE), () => HttpResponse.json(status([], confirmed))),
      http.post(api(`${BASE}/confirm`), async ({ request }) => {
        body = await request.json();
        confirmed = true;
        return HttpResponse.json({ elevated_until: SOON() });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await user.type(await screen.findByLabelText(/Dein Passwort/), "geheim");
    // Nothing to change before.
    expect(screen.queryByRole("button", { name: "Faktor hinzufügen" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    await waitFor(() => expect(body).toEqual({ password: "geheim" }));
    expect(await screen.findByRole("button", { name: "Faktor hinzufügen" })).toBeInTheDocument();
    expect(screen.getByText("Du hast noch keinen zweiten Faktor eingerichtet.")).toBeInTheDocument();
  });

  it("asks for a second factor, not the password, once there is one", async () => {
    let confirmed = false;
    const bodies: unknown[] = [];
    server.use(
      http.get(api(BASE), () => HttpResponse.json(status([APP], confirmed))),
      http.post(api(`${BASE}/confirm`), async ({ request }) => {
        bodies.push(await request.json());
        if (bodies.length === 1) return refused("__all__", "Das hat nicht geklappt.");
        confirmed = true;
        return HttpResponse.json({ elevated_until: SOON() });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await user.type(await screen.findByLabelText(/Code aus deiner Authenticator-App/), "000000");
    expect(screen.queryByLabelText(/Dein Passwort/)).toBeNull();
    // No security key to offer.
    expect(screen.queryByRole("button", { name: "Mit Sicherheitsschlüssel bestätigen" })).toBeNull();
    await user.click(screen.getByRole("button", { name: "Bestätigen" }));
    expect(await screen.findByText("Das hat nicht geklappt.")).toBeInTheDocument();

    await user.click(screen.getByText("Wiederherstellungscode verwenden"));
    await user.type(screen.getByLabelText(/^Wiederherstellungscode/), "abcd-efgh");
    await user.click(screen.getByRole("button", { name: "Mit Code bestätigen" }));
    expect(await screen.findByText("Handy")).toBeInTheDocument();
    expect(bodies).toEqual([{ code: "000000" }, { recovery_code: "abcd-efgh" }]);
  });

  it("confirms with a security key", async () => {
    let confirmed = false;
    let body: Record<string, unknown> | null = null;
    const get = vi.fn().mockResolvedValue({
      id: "a2V5",
      rawId: bytes("key"),
      type: "public-key",
      response: {
        clientDataJSON: bytes("client"),
        authenticatorData: bytes("auth"),
        signature: bytes("sig"),
        userHandle: bytes("2"),
      },
      getClientExtensionResults: () => ({}),
    });
    stubWebAuthn({ get });
    server.use(
      http.get(api(BASE), () => HttpResponse.json(status([PASSKEY], confirmed))),
      http.post(api(`${BASE}/confirm/options`), () =>
        HttpResponse.json({
          options: { challenge: "Y2hhbGxlbmdl", allowCredentials: [{ id: "a2V5", type: "public-key" }] },
          state: "confirm-state",
        }),
      ),
      http.post(api(`${BASE}/confirm`), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        confirmed = true;
        return HttpResponse.json({ elevated_until: SOON() });
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Mit Sicherheitsschlüssel bestätigen" }));
    expect(await screen.findByText("YubiKey")).toBeInTheDocument();
    const publicKey = get.mock.calls[0][0].publicKey;
    expect(new TextDecoder().decode(publicKey.challenge)).toBe("challenge");
    expect(new TextDecoder().decode(publicKey.allowCredentials[0].id)).toBe("key");
    expect(body).toEqual({
      state: "confirm-state",
      credential: {
        id: "a2V5",
        rawId: "a2V5",
        type: "public-key",
        response: {
          clientDataJSON: "Y2xpZW50",
          authenticatorData: "YXV0aA",
          signature: "c2ln",
          userHandle: "Mg",
        },
        clientExtensionResults: {},
      },
    });
  });

  it("says so when the key does not answer", async () => {
    stubWebAuthn({ get: vi.fn().mockResolvedValue(null) });
    statusReturns([PASSKEY], false);
    server.use(
      http.post(api(`${BASE}/confirm/options`), () =>
        HttpResponse.json({ options: { challenge: "Y2hhbGxlbmdl" }, state: "s" }),
      ),
    );
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Mit Sicherheitsschlüssel bestätigen" }));
    expect(await screen.findByText("Der Sicherheitsschlüssel hat nicht geantwortet.")).toBeInTheDocument();
  });

  it("asks again once the confirmation ran out", async () => {
    statusReturns([APP], true, { elevated_until: new Date(Date.now() - 1000).toISOString() });
    renderRoute("/kompass/security");
    expect(await screen.findByLabelText(/Code aus deiner Authenticator-App/)).toBeInTheDocument();
    expect(screen.queryByText("Handy")).toBeNull();
  });

  it("asks again when a change is refused for want of one", async () => {
    let confirmed = true;
    server.use(
      http.get(api(BASE), () => HttpResponse.json(status([APP], confirmed))),
      http.post(api(`${BASE}/totp/1/remove`), () => {
        confirmed = false;
        return HttpResponse.json(
          { detail: "Bitte bestätige zuerst, dass du es bist.", displayable: true },
          { status: 403 },
        );
      }),
    );
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Entfernen" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Entfernen" }));
    expect(await screen.findByLabelText(/Code aus deiner Authenticator-App/)).toBeInTheDocument();
  });
});

describe("managing factors once confirmed", () => {
  it("offers a security key only where the browser can use one", async () => {
    statusReturns();
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Faktor hinzufügen" }));
    const dialog = within(await screen.findByRole("dialog", { name: "Faktor hinzufügen" }));
    expect(dialog.getByRole("button", { name: "Authenticator-App" })).toBeInTheDocument();
    expect(dialog.queryByRole("button", { name: "Sicherheitsschlüssel" })).toBeNull();
  });

  it("adds an authenticator app and shows the recovery codes once", async () => {
    statusReturns();
    let started = false;
    let confirmBody: unknown = null;
    server.use(
      http.post(api(`${BASE}/totp/setup`), () => {
        started = true;
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
    expect(dialog.queryByLabelText(/Passwort/)).toBeNull();
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "Handy");
    await user.click(dialog.getByRole("button", { name: "Weiter" }));
    await waitFor(() => expect(started).toBe(true));

    expect(await dialog.findByText("JBSWY3DPEHPK3PXP")).toBeInTheDocument();
    expect(dialog.getByLabelText("QR-Code für die Authenticator-App")).toBeInTheDocument();
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

  it("shows a wrong code on its field", async () => {
    statusReturns();
    server.use(
      http.post(api(`${BASE}/totp/setup`), () =>
        HttpResponse.json({ secret: "JBSWY3DPEHPK3PXP", uri: "otpauth://totp/x", state: "s" }),
      ),
      http.post(api(`${BASE}/totp`), () => refused("code", "Der Code ist nicht korrekt.")),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Authenticator-App");
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Weiter" }));
    await user.type(await dialog.findByLabelText(/Code aus der App/), "000000");
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    expect(await dialog.findByText("Der Code ist nicht korrekt.")).toBeInTheDocument();
  });

  it("registers a security key through the browser", async () => {
    statusReturns([APP]);
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
    stubWebAuthn({ create });
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
    expect(dialog.queryByLabelText(/Passwort/)).toBeNull();
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "YubiKey");
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

  it("says so when the key does not answer at registration", async () => {
    statusReturns();
    stubWebAuthn({ create: vi.fn().mockResolvedValue(null) });
    server.use(
      http.post(api(`${BASE}/webauthn/setup`), () =>
        HttpResponse.json({ options: { user: { id: "Mg" }, challenge: "Y2hhbGxlbmdl" }, state: "s" }),
      ),
    );
    const { user } = renderRoute("/kompass/security");
    await chooseFactor(user, "Sicherheitsschlüssel");
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));
    expect(await screen.findByText("Der Sicherheitsschlüssel hat nicht geantwortet.")).toBeInTheDocument();
  });

  it("lists, renames and removes factors", async () => {
    statusReturns([APP, PASSKEY]);
    let renamed: unknown = null;
    let removed = false;
    server.use(
      http.patch(api(`${BASE}/webauthn/4`), async ({ request }) => {
        renamed = await request.json();
        return HttpResponse.json({ ...PASSKEY, name: "Schlüsselbund" });
      }),
      http.post(api(`${BASE}/totp/1/remove`), () => {
        removed = true;
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
    const dialog = within(await screen.findByRole("dialog"));
    await user.clear(dialog.getByLabelText(/Name/));
    await user.type(dialog.getByLabelText(/Name/), "Schlüsselbund");
    await user.click(dialog.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(renamed).toEqual({ name: "Schlüsselbund" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());

    const appRow = within(screen.getByText("Handy").closest("tr") as HTMLElement);
    await user.click(appRow.getByRole("button", { name: "Entfernen" }));
    const confirm = within(await screen.findByRole("dialog"));
    expect(confirm.getByText(/„Handy“ entfernen\?/)).toBeInTheDocument();
    await user.click(confirm.getByRole("button", { name: "Entfernen" }));
    await waitFor(() => expect(removed).toBe(true));
    expect(await screen.findByText("Entfernt.")).toBeInTheDocument();
  });

  it("shows a rename that was refused", async () => {
    statusReturns([APP]);
    server.use(http.patch(api(`${BASE}/totp/1`), () => refused("name", "Gib einen Namen an.")));
    const { user } = renderRoute("/kompass/security");
    await user.click(await screen.findByRole("button", { name: "Umbenennen" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Speichern" }));
    expect(await dialog.findByText("Gib einen Namen an.")).toBeInTheDocument();
  });

  it("replaces the recovery codes", async () => {
    statusReturns([APP]);
    server.use(http.post(api(`${BASE}/recovery-codes`), () => HttpResponse.json({ codes: CODES })));
    const { user } = renderRoute("/kompass/security");
    expect(await screen.findByText("8")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Neue Codes erzeugen" }));
    const confirm = within(await screen.findByRole("dialog"));
    await user.click(confirm.getByRole("button", { name: "Erzeugen" }));
    const shown = within(await screen.findByRole("dialog", { name: "Deine Wiederherstellungscodes" }));
    expect(shown.getByText(CODES[9])).toBeInTheDocument();
  });
});
