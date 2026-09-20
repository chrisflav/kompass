import { screen, waitFor } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { API_BASE } from "../api/client";
import { api, http, HttpResponse, server } from "../test/server";
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

  it("remembers the page the guard turned the user away from", async () => {
    const { user } = renderRoute("/kompass/members", { authenticated: false });
    await user.click(await screen.findByRole("button", { name: "Anmelden" }));

    await waitFor(() => expect(assigned).toHaveLength(1));
    expect(sessionStorage.getItem("kompass_pkce_return")).toBe("/kompass/members");
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
  });

  it("says so when the user turned the authorisation down", async () => {
    renderWithApp(<AuthCallback />, {
      route: "/callback?error=access_denied",
      authenticated: false,
    });
    expect(await screen.findByText("Die Anmeldung wurde abgebrochen.")).toBeInTheDocument();
    expect(localStorage.getItem("kompass_token")).toBeNull();
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
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(screen.getByRole("link", { name: /Nachricht senden/ })).toHaveAttribute(
      "href",
      "/kompass/mailer/messages?compose=1",
    );
    expect(await screen.findByRole("link", { name: "Alle Gruppen →" })).toHaveAttribute(
      "href",
      "/kompass/groups",
    );
    expect(screen.getByRole("link", { name: "Alle Ausfahrten →" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Alle Abrechnungen →" })).toBeInTheDocument();
  });
});
