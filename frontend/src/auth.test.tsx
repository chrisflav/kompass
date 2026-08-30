import { render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { AuthProvider, getToken, useAuth } from "./auth";
import { API_BASE } from "./api/client";
import { api, http, HttpResponse, server } from "./test/server";
import { renderRoute } from "./test/utils";

/** Minimal consumer that drives login/logout and shows the resulting error,
 *  standing in for the real `Login` page. */
function Harness({ password = "secret" }: { password?: string }) {
  const { token, login, logout } = useAuth();
  const [error, setError] = useState("");
  return (
    <div>
      <span data-testid="token">{token ?? "none"}</span>
      <button
        type="button"
        onClick={async () => {
          try {
            await login("hannah", password);
          } catch (e) {
            setError(e instanceof Error ? e.message : String(e));
          }
        }}
      >
        Anmelden
      </button>
      <button type="button" onClick={logout}>
        Abmelden
      </button>
      <p data-testid="err">{error}</p>
    </div>
  );
}

const renderAuth = (props: { password?: string } = {}) =>
  render(
    <AuthProvider>
      <Harness {...props} />
    </AuthProvider>,
  );

describe("AuthProvider login", () => {
  it("stores the access token on success", async () => {
    server.use(
      http.post(`${API_BASE}/o/token/`, () =>
        HttpResponse.json({ access_token: "abc123", token_type: "Bearer" }),
      ),
    );
    const user = userEvent.setup();
    renderAuth();
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    await waitFor(() => expect(screen.getByTestId("token")).toHaveTextContent("abc123"));
    expect(getToken()).toBe("abc123");
  });

  it("reports wrong credentials in German, without mentioning the OAuth app", async () => {
    server.use(
      http.post(`${API_BASE}/o/token/`, () =>
        HttpResponse.json({ error: "invalid_grant" }, { status: 400 }),
      ),
    );
    const user = userEvent.setup();
    renderAuth({ password: "wrong" });
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    await waitFor(() =>
      expect(screen.getByTestId("err")).toHaveTextContent(
        "Benutzername oder Passwort ist falsch.",
      ),
    );
    expect(screen.getByTestId("err")).not.toHaveTextContent(/OAuth/i);
    expect(getToken()).toBeNull();
  });

  it("distinguishes a server problem from wrong credentials", async () => {
    server.use(
      http.post(`${API_BASE}/o/token/`, () => HttpResponse.json({}, { status: 500 })),
    );
    const user = userEvent.setup();
    renderAuth();
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    await waitFor(() =>
      expect(screen.getByTestId("err")).toHaveTextContent(/Administration/),
    );
  });

  it("reports an unreachable server rather than throwing a network error at the user", async () => {
    server.use(http.post(`${API_BASE}/o/token/`, () => HttpResponse.error()));
    const user = userEvent.setup();
    renderAuth();
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    await waitFor(() =>
      expect(screen.getByTestId("err")).toHaveTextContent(/nicht erreichbar/i),
    );
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
    renderRoute("/app/groups");

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
    renderRoute("/app/groups");

    await waitFor(() => expect(localStorage.getItem("kompass_token")).toBeNull());
    const tokenRemovals = removeItem.mock.calls.filter(([k]) => k === "kompass_token");
    expect(tokenRemovals).toHaveLength(1);
  });
});
