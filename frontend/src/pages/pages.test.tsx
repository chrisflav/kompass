import { screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server } from "../test/server";
import { renderRoute, renderWithApp } from "../test/utils";
import { Dashboard } from "./Dashboard";
import { Login } from "./Login";

describe("Login", () => {
  it("asks for credentials and titles the tab", () => {
    renderWithApp(<Login />, { authenticated: false });
    expect(screen.getByRole("heading", { name: "Kompass" })).toBeInTheDocument();
    expect(screen.getByLabelText("Benutzername")).toHaveFocus();
    expect(document.title).toBe("Anmelden · Kompass");
  });

  it("sends the user straight on when a token already exists", () => {
    renderWithApp(
      <>
        <Login />
      </>,
      { route: "/login" },
    );
    // <Navigate> renders nothing; the form is simply gone.
    expect(screen.queryByRole("heading", { name: "Kompass" })).not.toBeInTheDocument();
  });

  it("signs in and lands on the dashboard", async () => {
    server.use(
      http.post(api("/o/token/"), () => HttpResponse.json({ access_token: "neues-token" })),
      http.get(api("/api/members/groups"), () => HttpResponse.json([])),
      http.get(api("/api/members/excursions"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements"), () => HttpResponse.json([])),
      http.get(api("/api/startpage/links"), () => HttpResponse.json([])),
    );
    const { user } = renderRoute("/login", { authenticated: false });

    await user.type(screen.getByLabelText("Benutzername"), "hannah");
    await user.type(screen.getByLabelText("Passwort"), "geheim");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(await screen.findByText(/Kompass · Verwaltung der JDAV Ludwigsburg/)).toBeInTheDocument();
    expect(localStorage.getItem("kompass_token")).toBe("neues-token");
  });

  it("shows the rejection inline and stays on the form", async () => {
    server.use(
      http.post(api("/o/token/"), () =>
        HttpResponse.json({ error: "invalid_grant" }, { status: 400 }),
      ),
    );
    const { user } = renderWithApp(<Login />, { authenticated: false });

    await user.type(screen.getByLabelText("Benutzername"), "hannah");
    await user.type(screen.getByLabelText("Passwort"), "falsch");
    await user.click(screen.getByRole("button", { name: "Anmelden" }));

    expect(
      await screen.findByText("Benutzername oder Passwort ist falsch."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Anmelden" })).toBeEnabled();
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
  { id: 1, title: "JL-Wiki", url: "https://wiki.example.org", visible: true },
  { id: 2, title: "", url: "https://intern.example.org", visible: true },
  { id: 3, title: "Versteckt", url: "https://nope.example.org", visible: false },
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

  it("shows only visible links, titled by their URL when unnamed", async () => {
    dashboardReturns();
    renderWithApp(<Dashboard />, { route: "/kompass" });

    expect(await screen.findByRole("link", { name: /JL-Wiki/ })).toHaveAttribute(
      "href",
      "https://wiki.example.org",
    );
    expect(screen.getAllByText("https://intern.example.org").length).toBeGreaterThan(0);
    expect(screen.queryByText("Versteckt")).not.toBeInTheDocument();
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
