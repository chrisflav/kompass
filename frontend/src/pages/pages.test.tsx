import { screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE } from "../api/client";
import { api, http, HttpResponse, server, useMe } from "../test/server";
import {
  captureNavigations,
  renderRoute,
  renderWithApp,
  restoreNavigations,
} from "../test/utils";
import { Dashboard } from "./Dashboard";
import { AuthCallback, Login } from "./Login";

describe("Login", () => {
  let assigned: string[];

  beforeEach(() => {
    assigned = captureNavigations();
  });
  afterEach(restoreNavigations);

  it("offers a way in and titles the tab, asking for no password of its own", () => {
    renderWithApp(<Login />, { authenticated: false });
    expect(screen.getByRole("heading", { name: "Kompass" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anmelden" })).toBeInTheDocument();
    // Credentials belong on the provider's page, never on this one.
    expect(screen.queryByLabelText("Passwort")).not.toBeInTheDocument();
    expect(document.title).toBe("Anmelden · Kompass");
  });

  it("sends the user straight on when a token already exists", () => {
    renderWithApp(
      <>
        <Login />
      </>,
      { route: "/login" },
    );
    // <Navigate> renders nothing; the card is simply gone.
    expect(screen.queryByRole("heading", { name: "Kompass" })).not.toBeInTheDocument();
  });

  it("hands off to the provider when asked to sign in", async () => {
    const { user } = renderWithApp(<Login />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    await waitFor(() => expect(assigned).toHaveLength(1));
    const url = new URL(assigned[0]);
    expect(url.pathname).toBe("/o/authorize/");
    expect(url.searchParams.get("code_challenge_method")).toBe("S256");
  });

  it("goes straight to the provider from a protected page, back to that page", async () => {
    renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByText("Weiterleitung zur Anmeldung …")).toBeInTheDocument();
    // No card flashes up on the way out.
    expect(screen.queryByRole("button", { name: "Anmelden" })).not.toBeInTheDocument();
    await waitFor(() => expect(assigned).toHaveLength(1));
    expect(new URL(assigned[0]).pathname).toBe("/o/authorize/");
    expect(sessionStorage.getItem("kompass_pkce_return")).toBe("/kompass/members");
    expect(Number(sessionStorage.getItem("kompass_login_autostart"))).toBeGreaterThan(0);
  });

  it("goes straight to the provider from the header's login link", async () => {
    const { user } = renderRoute("/", { authenticated: false });
    await user.click(await screen.findByRole("link", { name: "Anmelden" }));

    await waitFor(() => expect(assigned).toHaveLength(1));
    expect(sessionStorage.getItem("kompass_pkce_return")).toBe("/kompass");
  });

  it("leaves for the provider once under StrictMode", async () => {
    renderWithApp(
      <StrictMode>
        <Routes>
          <Route path="/" element={<Navigate to="/login" state={{ from: "/kompass/groups" }} />} />
          <Route path="/login" element={<Login />} />
        </Routes>
      </StrictMode>,
      { authenticated: false },
    );

    await waitFor(() => expect(assigned).toHaveLength(1));
    // Give a replayed effect the chance to start a second time.
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(assigned).toHaveLength(1);
  });

  it("waits for a click when it was just sent off automatically", async () => {
    // A token rejected right after the login lands back here within seconds;
    // a second automatic start would loop forever with nothing on screen.
    sessionStorage.setItem("kompass_login_autostart", String(Date.now() - 5_000));
    const { user } = renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByText(/Anmeldung hat nicht geklappt/)).toBeInTheDocument();
    expect(assigned).toEqual([]);
    await user.click(screen.getByRole("button", { name: "Anmelden" }));
    await waitFor(() => expect(assigned).toHaveLength(1));
    expect(sessionStorage.getItem("kompass_pkce_return")).toBe("/kompass/members");
  });

  it("starts automatically again once the last start is long past", async () => {
    sessionStorage.setItem("kompass_login_autostart", String(Date.now() - 120_000));
    renderRoute("/kompass/members", { authenticated: false });
    await waitFor(() => expect(assigned).toHaveLength(1));
  });

  it("waits for a click after the callback reported a failure", async () => {
    sessionStorage.setItem("kompass_login_failed", "1");
    renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByText(/Anmeldung hat nicht geklappt/)).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });

  it("falls back to the button when sessionStorage is unavailable", async () => {
    // What a browser blocking site data does: touching the storage throws.
    const blocked = vi.spyOn(window, "sessionStorage", "get").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByRole("button", { name: "Anmelden" })).toBeInTheDocument();
    // Not a failed login, so no claim that one failed.
    expect(screen.queryByText(/Anmeldung hat nicht geklappt/)).not.toBeInTheDocument();
    expect(assigned).toEqual([]);
    // Before the shared teardown clears the storage.
    blocked.mockRestore();
  });

  it("falls back to the button when the start cannot be recorded", async () => {
    // Spied on the prototype: an own property on a Storage would just be
    // stored as an item. localStorage, holding no token here, writes nothing.
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("full", "QuotaExceededError");
    });
    renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByRole("button", { name: "Anmelden" })).toBeInTheDocument();
    expect(assigned).toEqual([]);
  });

  it("says so, with the button, when an automatic start cannot build the challenge", async () => {
    vi.spyOn(crypto.subtle, "digest").mockRejectedValue(new Error("insecure context"));
    renderRoute("/kompass/members", { authenticated: false });

    expect(await screen.findByText(/Administration/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anmelden" })).toBeEnabled();
    expect(assigned).toEqual([]);
  });

  it("stays put and says so when the challenge cannot be built", async () => {
    // WebCrypto is unavailable outside a secure context, so a misconfigured
    // deployment (plain HTTP) lands here rather than on a blank redirect.
    vi.spyOn(crypto.subtle, "digest").mockRejectedValue(new Error("insecure context"));
    const { user } = renderWithApp(<Login />, { authenticated: false });
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText(/Administration/)).toBeInTheDocument();
    expect(assigned).toEqual([]);
    expect(screen.getByRole("button", { name: "Anmelden" })).toBeEnabled();
  });
});

describe("AuthCallback", () => {
  let assigned: string[];

  beforeEach(() => {
    assigned = captureNavigations();
  });
  afterEach(restoreNavigations);

  /** Puts the tab in the state `beginLogin` leaves behind. */
  function startedFlow(returnTo = "/kompass") {
    sessionStorage.setItem("kompass_login_autostart", String(Date.now()));
    sessionStorage.setItem("kompass_pkce_verifier", "verifier-xyz");
    sessionStorage.setItem("kompass_pkce_state", "state-abc");
    sessionStorage.setItem("kompass_pkce_return", returnTo);
  }

  it("trades the code for a token and lands where the user was headed", async () => {
    startedFlow("/kompass");
    server.use(
      http.post(api("/o/token/"), () => HttpResponse.json({ access_token: "neues-token" })),
      http.get(api("/api/members/groups"), () => HttpResponse.json([])),
      http.get(api("/api/members/excursions"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/links"), () => HttpResponse.json([])),
    );
    renderRoute("/callback?code=CODE&state=state-abc", { authenticated: false });

    expect(await screen.findByText(/Kompass · Verwaltung der JDAV Ludwigsburg/)).toBeInTheDocument();
    expect(localStorage.getItem("kompass_token")).toBe("neues-token");
    // The next expired session may start the login on its own again.
    expect(sessionStorage.getItem("kompass_login_autostart")).toBeNull();
    expect(sessionStorage.getItem("kompass_login_failed")).toBeNull();
  });

  it("says so when the user turned the authorisation down", async () => {
    renderWithApp(<AuthCallback />, {
      route: "/callback?error=access_denied",
      authenticated: false,
    });
    expect(await screen.findByText("Die Anmeldung wurde abgebrochen.")).toBeInTheDocument();
    expect(localStorage.getItem("kompass_token")).toBeNull();
    // So the login page waits for a click instead of starting over.
    expect(sessionStorage.getItem("kompass_login_failed")).toBe("1");
  });

  it("says so when the provider came back without a code", async () => {
    renderWithApp(<AuthCallback />, { route: "/callback", authenticated: false });
    expect(await screen.findByText(/unvollständig/)).toBeInTheDocument();
  });

  it("reports a StrictMode-rendered exchange as the success it was", async () => {
    // The app really does run inside StrictMode (see main.tsx), which invokes
    // the render function twice per pass. A guard held in render-phase state
    // does not survive that, so the exchange ran from both invocations: the
    // first spent the verifier and got a token, the second found sessionStorage
    // already emptied and rejected straight away. The rejection landed first,
    // so a login that had in fact succeeded was reported as unassignable.
    startedFlow();
    let exchanges = 0;
    server.use(
      http.post(api("/o/token/"), () => {
        exchanges += 1;
        return HttpResponse.json({ access_token: "einmaliges-token" });
      }),
    );
    renderWithApp(
      <StrictMode>
        <AuthCallback />
      </StrictMode>,
      { route: "/callback?code=CODE&state=state-abc", authenticated: false },
    );

    await waitFor(() => expect(localStorage.getItem("kompass_token")).toBe("einmaliges-token"));
    expect(screen.queryByText(/zugeordnet/)).not.toBeInTheDocument();
    // The second invocation never reached the provider even before the fix, so
    // this guards the code against being spent twice rather than reproducing
    // the bug; the assertion above is the one that fails without the fix.
    expect(exchanges).toBe(1);
  });

  it("reports a refusal even to a tab still holding a token", async () => {
    // The redirect for an already-signed-in visitor is decided on the first
    // paint. Judging the provider's answer one tick later, in an effect, sent
    // anyone with a stale token to the dashboard and swallowed the refusal.
    renderRoute("/callback?error=access_denied", { authenticated: true });
    expect(await screen.findByText("Die Anmeldung wurde abgebrochen.")).toBeInTheDocument();
  });

  it("reports a refused exchange and offers the way back to the login", async () => {
    startedFlow();
    server.use(
      http.post(api("/o/token/"), () =>
        HttpResponse.json({ error: "invalid_grant" }, { status: 400 }),
      ),
    );
    const { user } = renderWithApp(<AuthCallback />, {
      route: "/callback?code=CODE&state=state-abc",
      authenticated: false,
    });

    expect(await screen.findByText(/Administration/)).toBeInTheDocument();
    expect(sessionStorage.getItem("kompass_login_failed")).toBe("1");
    await user.click(screen.getByRole("button", { name: "Zurück zur Anmeldung" }));
    expect(assigned).toEqual(["/login"]);
  });
});

/* --- dashboard ----------------------------------------------------------- */

const GROUPS = [
  {
    id: 5,
    name: "Klettergruppe",
    time_info: "montags 18:00",
    age_info: "Jahrgang 2010–2013",
    leiters: [{ id: 7, name: "Hannah Beckers" }],
  },
  {
    id: 6,
    name: "Fremde Gruppe",
    time_info: "",
    age_info: "",
    leiters: [{ id: 99, name: "Wer anders" }],
  },
];

const EXCURSIONS = [
  { id: 3, code: "F26-01", name: "Skifreizeit", place: "Südtirol", date: "2026-02-14" },
  { id: 4, code: "F26-02", name: "", place: "", date: null },
];

const STATEMENTS = [
  {
    id: 1,
    title: "F26-01 Skifreizeit",
    status_display: "Entwurf",
    total_pretty: "240,50 €",
  },
];

const LINKS = [
  {
    id: 1,
    title: "JL-Wiki",
    description: "Protokolle, Vorlagen und Ausrüstungslisten",
    url: "https://wiki.example.org",
    icon: "/media/icons/wiki.png",
    visible: true,
  },
  {
    id: 2,
    title: "",
    description: "",
    url: "https://intern.example.org",
    icon: null,
    visible: true,
  },
  {
    id: 3,
    title: "Versteckt",
    description: "Nicht sichtbar",
    url: "https://nope.example.org",
    icon: null,
    visible: false,
  },
  {
    id: 4,
    title: "Bergwetter",
    description: "Vorhersage für die Alpen",
    url: "https://wetter.example.org/alpen",
    icon: null,
    visible: true,
  },
];

function dashboardReturns({
  groups = GROUPS,
  excursions = EXCURSIONS,
  statements = STATEMENTS,
  links = LINKS,
} = {}) {
  server.use(
    http.get(api("/api/members/groups"), () => HttpResponse.json(groups)),
    http.get(api("/api/members/excursions"), () => HttpResponse.json(excursions)),
    http.get(api("/api/finance/statements"), () => HttpResponse.json(statements)),
    http.get(api("/api/startpage/links"), () => HttpResponse.json(links)),
  );
}

describe("Dashboard", () => {
  it("greets the user by first name, linked to their own profile", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    const name = await screen.findByRole("link", { name: "Hannah" });
    expect(name).toHaveAttribute("href", "/kompass/members/7");
    expect(document.title).toBe("Übersicht · Kompass");
  });

  it("greets an account without a member profile without a dead link", async () => {
    server.use(
      http.get(api("/api/members/me"), () =>
        HttpResponse.json({
          user_id: 1,
          username: "admin",
          name: "Admin Person",
          member_id: null,
          is_staff: true,
          is_superuser: true,
          permissions: [],
        }),
      ),
    );
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByText("Willkommen, Admin")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Admin" })).not.toBeInTheDocument();
  });

  it("falls back to a neutral greeting before /me answers", () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });
    expect(screen.getByText("Willkommen zurück")).toBeInTheDocument();
  });

  it("lists only the groups the user actually leads", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByRole("link", { name: /Klettergruppe/ })).toHaveAttribute(
      "href",
      "/kompass/groups/5/members",
    );
    expect(screen.getByText("montags 18:00")).toBeInTheDocument();
    expect(screen.queryByText("Fremde Gruppe")).not.toBeInTheDocument();
  });

  it("lists the newest excursions, coping with missing names and dates", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByRole("link", { name: /Südtirol/ })).toHaveAttribute(
      "href",
      "/kompass/excursions/3",
    );
    expect(screen.getByText("14.2.2026")).toBeInTheDocument();
    // Falls back to the code, and shows an em dash rather than "Invalid Date".
    expect(screen.getByText("F26-02")).toBeInTheDocument();
    expect(screen.getByText("—")).toBeInTheDocument();
  });

  it("passes an unparseable date through unchanged", async () => {
    dashboardReturns({
      excursions: [{ id: 4, code: "F26-02", name: "Kaputt", place: "", date: "irgendwann" }],
    });
    renderWithApp(<Dashboard />, { route: "/kompass" });
    expect(await screen.findByText("irgendwann")).toBeInTheDocument();
  });

  it("lists the newest statements with their status", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });
    expect(await screen.findByText("Entwurf")).toBeInTheDocument();
    expect(screen.getByText("240,50 €")).toBeInTheDocument();
  });

  it("shows every visible link as icon, title and description, never its URL", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    const wiki = await screen.findByRole("link", { name: /JL-Wiki/ });
    expect(wiki).toHaveAttribute("href", "https://wiki.example.org");
    // The uploaded icon is served by the backend, so it needs the API origin.
    const icon = wiki.querySelector("img");
    expect(icon).toHaveAttribute("src", `${API_BASE}/media/icons/wiki.png`);
    expect(
      screen.getByText("Protokolle, Vorlagen und Ausrüstungslisten"),
    ).toBeInTheDocument();
    // The address itself is never on the dashboard, only behind the link.
    expect(screen.queryByText("https://wiki.example.org")).not.toBeInTheDocument();
    expect(screen.queryByText("Versteckt")).not.toBeInTheDocument();
    // One tile per visible link, and nothing padding the grid out: the columns
    // are chosen by the tiles themselves, so an "incomplete" row cannot occur.
    expect(document.querySelectorAll(".dash-link")).toHaveLength(3);
  });

  it("still labels a link whose URL carries no host", async () => {
    // URLField validation keeps this out of new rows, but a link stored before
    // the API enforced it must not render as a blank tile with a blank plate.
    dashboardReturns({
      links: [{ id: 9, title: "", description: "", url: "https://", icon: null, visible: true }],
    });
    renderWithApp(<Dashboard />, { route: "/kompass" });

    const bare = await screen.findByRole("link", { name: /Link/ });
    expect(bare.querySelector(".dash-link-title")).toHaveTextContent("Link");
    expect(bare.querySelector(".dash-link-mark")).toHaveTextContent("L");
  });

  it("labels a link without icon, title or description by host and initial", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    const bare = await screen.findByRole("link", { name: /intern\.example\.org/ });
    expect(bare).toHaveAttribute("href", "https://intern.example.org");
    // No uploaded icon: the plate carries the initial instead of an image.
    expect(bare.querySelector("img")).toBeNull();
    expect(bare.querySelector(".dash-link-mark")).toHaveTextContent("I");
    // …and an empty description leaves no blank second line behind.
    expect(bare.querySelector(".dash-link-desc")).toBeNull();
  });

  it("drops the links panel entirely when none are visible", async () => {
    dashboardReturns({ links: [] });
    renderWithApp(<Dashboard />, { route: "/kompass" });
    await screen.findByText("Willkommen zurück");
    expect(screen.queryByText("Nützliche Links")).not.toBeInTheDocument();
  });

  it("omits the optional row details the API left empty", async () => {
    dashboardReturns({
      groups: [{ ...GROUPS[0], time_info: "", age_info: "" }],
      excursions: [{ id: 4, code: "", name: "", place: "", date: null }],
      statements: [{ id: 1, title: "", status_display: "", total_pretty: "" }],
    });
    renderWithApp(<Dashboard />, { route: "/kompass" });

    // Every row falls back to a neutral label rather than rendering blanks.
    expect(await screen.findByText("Ausfahrt")).toBeInTheDocument();
    expect(screen.getByText("Abrechnung")).toBeInTheDocument();
  });

  it("says so for each empty panel rather than showing a blank card", async () => {
    dashboardReturns({ groups: [], excursions: [], statements: [] });
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByText("Du leitest aktuell keine Gruppe.")).toBeInTheDocument();
    expect(screen.getByText("Keine Ausfahrten.")).toBeInTheDocument();
    expect(screen.getByText("Keine Abrechnungen.")).toBeInTheDocument();
  });

  it("shows a loading state per panel while the queries are in flight", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });
    expect(screen.getAllByText("Lädt…").length).toBeGreaterThan(0);
    await waitFor(() => expect(screen.queryByText("Lädt…")).not.toBeInTheDocument());
  });

  it("offers the compose shortcut and a see-all link per section", async () => {
    useMe({ permissions: ["mailer.add_global_message"] });
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByRole("link", { name: /Nachricht senden/ })).toHaveAttribute(
      "href",
      "/kompass/mailer/messages/new",
    );
    expect(await screen.findByRole("link", { name: "Alle Gruppen →" })).toHaveAttribute(
      "href",
      "/kompass/groups",
    );
    expect(screen.getByRole("link", { name: "Alle Ausfahrten →" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alle Abrechnungen →" })).toBeInTheDocument();
  });

  it("hides the compose shortcut from someone who may not send messages", async () => {
    useMe({ permissions: [] });
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    // The greeting names the user, so /me (and with it the rights) is in.
    await screen.findByRole("link", { name: "Hannah" });
    expect(screen.queryByRole("link", { name: /Nachricht senden/ })).not.toBeInTheDocument();
  });
});
