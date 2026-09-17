import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, getToken, redirectUri, useAuth } from "./auth";
import { API_BASE } from "./api/client";
import { api, http, HttpResponse, server } from "./test/server";
import { captureNavigations, renderRoute, restoreNavigations } from "./test/utils";

/** `beginLogin` leaves the page; jsdom cannot, so the destination is captured. */
let assigned: string[] = [];

beforeEach(() => {
  assigned = captureNavigations();
});

afterEach(restoreNavigations);

/** Minimal consumer that drives the flow and shows the resulting error,
 *  standing in for the real `Login` / `AuthCallback` pages. */
function Harness({ code = "CODE", state }: { code?: string; state?: string }) {
  const { token, beginLogin, completeLogin, logout } = useAuth();
  const [error, setError] = useState("");
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <button type="button" onClick={() => beginLogin("/kompass/members")}>
        Anmelden
      </button>
      <button
        type="button"
        onClick={async () => {
          try {
            // Default to the state the provider really would echo back.
            await completeLogin(code, state ?? sessionStorage.getItem("kompass_pkce_state") ?? "");
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
      >
        Zurück
      </button>
      <button type="button" onClick={logout}>
        Abmelden
      </button>
      <p data-testid="err">{error}</p>
    </div>
  );
}

const renderAuth = (props: { code?: string; state?: string } = {}) =>
  render(
    <AuthProvider>
      <Harness {...props} />
    </AuthProvider>,
  );

/** Runs the redirect leg and returns the parsed authorize URL. */
async function startLogin(user: ReturnType<typeof userEvent.setup>) {
  await user.click(screen.getByRole("button", { name: "Anmelden" }));
  await waitFor(() => expect(assigned).toHaveLength(1));
  return new URL(assigned[0]);
}

describe("beginLogin — the redirect leg", () => {
  it("sends the user to the provider with a S256 challenge and never a password", async () => {
    const user = userEvent.setup();
    renderAuth();
    const url = await startLogin(user);

    expect(url.origin + url.pathname).toBe(`${API_BASE}/o/authorize/`);
    expect(url.searchParams.get("response_type")).toBe("code");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
    expect(url.searchParams.get("redirect_uri")).toBe(redirectUri());
    expect(url.searchParams.get("code_challenge")).toBeTruthy();
    // The verifier is the one secret that must stay in the browser.
    expect(url.toString()).not.toContain(sessionStorage.getItem("kompass_pkce_verifier")!);
  });

  it("derives the challenge from the stored verifier, per RFC 7636", async () => {
    const user = userEvent.setup();
    renderAuth();
    const url = await startLogin(user);

    const verifier = sessionStorage.getItem("kompass_pkce_verifier")!;
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier));
    const expected = btoa(String.fromCharCode(...new Uint8Array(digest)))
      .replace(/\+/g, "-")
      .replace(/\//g, "_")
      .replace(/=+$/, "");
    expect(url.searchParams.get("code_challenge")).toBe(expected);
  });

  it("keeps the verifier in sessionStorage, not localStorage", async () => {
    const user = userEvent.setup();
    renderAuth();
    await startLogin(user);

    expect(sessionStorage.getItem("kompass_pkce_verifier")).toBeTruthy();
    expect(localStorage.getItem("kompass_pkce_verifier")).toBeNull();
  });
});

describe("completeLogin — the exchange leg", () => {
  it("trades the code for a token and returns where the user was headed", async () => {
    let body: URLSearchParams | null = null;
    server.use(
      http.post(`${API_BASE}/o/token/`, async ({ request }) => {
        body = new URLSearchParams(await request.text());
        return HttpResponse.json({ access_token: "abc123", token_type: "Bearer" });
      }),
    );
    const user = userEvent.setup();
    renderAuth();
    await startLogin(user);
    const verifier = sessionStorage.getItem("kompass_pkce_verifier")!;

    await user.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("abc123"));

    expect(getToken()).toBe("abc123");
    expect(body!.get("grant_type")).toBe("authorization_code");
    expect(body!.get("code")).toBe("CODE");
    expect(body!.get("code_verifier")).toBe(verifier);
    // Single-use: the verifier must not survive the exchange.
    expect(sessionStorage.getItem("kompass_pkce_verifier")).toBeNull();
  });

  it("refuses a callback whose state does not match the one this tab sent", async () => {
    const exchange = vi.fn(() => HttpResponse.json({ access_token: "nope" }));
    server.use(http.post(`${API_BASE}/o/token/`, exchange));
    const user = userEvent.setup();
    renderAuth({ state: "forged" });
    await startLogin(user);

    await user.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.getByTestId("err")).toHaveTextContent(/nicht zugeordnet/));
    // The code is never presented at all — the mismatch is caught first.
    expect(exchange).not.toHaveBeenCalled();
    expect(getToken()).toBeNull();
  });

  it("refuses a callback that arrives without a flow having been started", async () => {
    const user = userEvent.setup();
    renderAuth({ state: "whatever" });

    await user.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.getByTestId("err")).toHaveTextContent(/nicht zugeordnet/));
    expect(getToken()).toBeNull();
  });

  it("reports a refused exchange without mentioning the OAuth app", async () => {
    server.use(
      http.post(`${API_BASE}/o/token/`, () =>
        HttpResponse.json({ error: "invalid_grant" }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderAuth();
    await startLogin(user);

    await user.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.getByTestId("err")).toHaveTextContent(/Administration/));
    expect(screen.getByTestId("err")).not.toHaveTextContent(/OAuth/i);
    expect(getToken()).toBeNull();
  });

  it("reports an unreachable server rather than throwing a network error at the user", async () => {
    server.use(http.post(`${API_BASE}/o/token/`, () => HttpResponse.error()));
    const user = userEvent.setup();
    renderAuth();
    await startLogin(user);

    await user.click(screen.getByRole("button", { name: "Zurück" }));
    await waitFor(() => expect(screen.getByTestId("err")).toHaveTextContent(/nicht erreichbar/i));
  });
});

describe("AuthProvider logout", () => {
  it("clears the stored token", async () => {
    localStorage.setItem("kompass_token", "abc123");
    const user = userEvent.setup();
    renderAuth();
    expect(screen.getByTestId("token")).toHaveTextContent("abc123");

    await user.click(screen.getByRole("button", { name: "Abmelden" }));
    expect(screen.getByTestId("token")).toHaveTextContent("none");
    expect(getToken()).toBeNull();
  });
});

describe("central 401 handling", () => {
  it("logs out and shows the login screen when a request comes back 401", async () => {
    server.use(
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json({ detail: "Unauthorized" }, { status: 401 }),
      ),
    );
    renderRoute("/kompass/groups");

    // The expired token is dropped once, centrally, and the route guard takes
    // over — rather than every page rendering its own "not authorised" state.
    await waitFor(() => expect(localStorage.getItem("kompass_token")).toBeNull());
    expect(await screen.findByRole("heading", { name: "Kompass" })).toBeInTheDocument();
  });

  it("does not try to log out again when there is no token left", async () => {
    const removeItem = vi.spyOn(Storage.prototype, "removeItem");
    server.use(
      // Two pages on the same route both 401; the logout must happen once.
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json({ detail: "Unauthorized" }, { status: 401 }),
      ),
      http.get(api("/api/members/me"), () =>
        HttpResponse.json({ detail: "Unauthorized" }, { status: 401 }),
      ),
    );
    renderRoute("/kompass/groups");

    await waitFor(() => expect(localStorage.getItem("kompass_token")).toBeNull());
    const tokenRemovals = removeItem.mock.calls.filter(([k]) => k === "kompass_token");
    expect(tokenRemovals).toHaveLength(1);
  });
});
