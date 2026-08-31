import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Route, Routes } from "react-router-dom";

import { api, http, HttpResponse, server } from "../test/server";
import { renderWithApp } from "../test/utils";
import { ContourField, KompassMark } from "./Contour";
import { AppLayout, ProtectedRoute, PublicLayout } from "./Layout";
import { NotFound, Placeholder } from "./Placeholder";
import { SiteHeader } from "./SiteHeader";

const NAV = {
  root_section: { id: 1, title: "Verein", urlname: "verein" },
  sections: [
    { id: 2, title: "Ausbildung", urlname: "ausbildung", show_in_navigation: true },
    { id: 3, title: "Intern", urlname: "intern", show_in_navigation: false },
    // The root section is already represented by the first dropdown; listing it
    // again would duplicate the entry.
    { id: 1, title: "Verein", urlname: "verein", show_in_navigation: true },
  ],
  groups: [{ id: 5, name: "Klettergruppe" }],
};

function navReturns(data: Record<string, unknown> = NAV) {
  server.use(http.get(api("/api/startpage/public/navigation"), () => HttpResponse.json(data)));
}

describe("Contour", () => {
  it("draws one decorative contour ring per requested level", () => {
    const { container } = renderWithApp(<ContourField rings={4} />, { authenticated: false });
    const svg = container.querySelector("svg")!;
    expect(svg).toHaveAttribute("aria-hidden", "true");
    expect(svg.querySelectorAll("path")).toHaveLength(4);
    // Deterministic geometry: no randomness, so the same props draw the same path.
    expect(svg.querySelector("path")!.getAttribute("d")).toMatch(/^M[\d.]+ [\d.]+L/);
  });

  it("defaults to the hero field", () => {
    const { container } = renderWithApp(<ContourField />, { authenticated: false });
    expect(container.querySelector("svg")).toHaveClass("hero-contour");
    expect(container.querySelectorAll("path")).toHaveLength(11);
  });

  it("renders the brand mark as decoration, never as content", () => {
    const { container } = renderWithApp(<KompassMark size={40} />, { authenticated: false });
    const img = container.querySelector("img")!;
    expect(img).toHaveAttribute("alt", "");
    expect(img).toHaveAttribute("aria-hidden", "true");
    expect(img).toHaveAttribute("width", "40");
  });
});

describe("Placeholder", () => {
  it("says plainly that a surface is not built yet", () => {
    renderWithApp(<Placeholder title="Statistik" />, { authenticated: false });
    expect(screen.getByRole("heading", { name: "Statistik" })).toBeInTheDocument();
    expect(screen.getByText("Noch nicht implementiert.")).toBeInTheDocument();
  });

  it("offers a way home from a 404", () => {
    renderWithApp(<NotFound />, { authenticated: false });
    expect(screen.getByRole("heading", { name: "404" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Zur Startseite" })).toHaveAttribute("href", "/");
  });
});

describe("ProtectedRoute", () => {
  it("lets a signed-in user through", () => {
    renderWithApp(
      <Routes>
        <Route
          path="/kompass"
          element={
            <ProtectedRoute>
              <p>Geheim</p>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<p>Anmeldung</p>} />
      </Routes>,
      { route: "/kompass" },
    );
    expect(screen.getByText("Geheim")).toBeInTheDocument();
  });

  it("sends a signed-out visitor to the login screen", () => {
    renderWithApp(
      <Routes>
        <Route
          path="/kompass"
          element={
            <ProtectedRoute>
              <p>Geheim</p>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<p>Anmeldung</p>} />
      </Routes>,
      { route: "/kompass", authenticated: false },
    );
    expect(screen.getByText("Anmeldung")).toBeInTheDocument();
    expect(screen.queryByText("Geheim")).not.toBeInTheDocument();
  });
});

describe("layouts", () => {
  it("wraps the workspace in the app chrome", async () => {
    renderWithApp(
      <Routes>
        <Route element={<AppLayout />}>
          <Route path="/kompass" element={<p>Inhalt</p>} />
        </Route>
      </Routes>,
      { route: "/kompass" },
    );
    expect(await screen.findByText("Inhalt")).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Hauptnavigation" })).toBeInTheDocument();
  });

  it("wraps the public site in the same shell plus a footer", async () => {
    navReturns();
    renderWithApp(
      <Routes>
        <Route element={<PublicLayout />}>
          <Route path="/" element={<p>Startseite</p>} />
        </Route>
      </Routes>,
      { route: "/", authenticated: false },
    );
    expect(await screen.findByText("Startseite")).toBeInTheDocument();
    expect(screen.getByText(/JDAV Ludwigsburg · Kompass/)).toBeInTheDocument();
  });
});

describe("SiteHeader — admin variant", () => {
  it("opens an area dropdown and closes it on a click outside", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass/members" });

    const trigger = screen.getByRole("button", { name: /Teilnehmende/ });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    // The area is highlighted because the current route lives inside it.
    expect(trigger).toHaveClass("active");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByRole("link", { name: "Warteliste" })).toHaveAttribute(
      "href",
      "/kompass/waiters",
    );

    await user.click(document.body);
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });

  it("closes an open dropdown on Escape", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    const trigger = screen.getByRole("button", { name: /Finanzen/ });
    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });

  it("selecting an item closes the dropdown again", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    const trigger = screen.getByRole("button", { name: /Website/ });
    await user.click(trigger);
    await user.click(screen.getByRole("link", { name: "Beiträge" }));
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
  });

  it("offers the profile and logout under the user's name", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });

    const menu = await screen.findByRole("button", { name: /Hannah Beckers/ });
    await user.click(menu);
    expect(screen.getByRole("link", { name: "Mein Profil" })).toHaveAttribute(
      "href",
      "/kompass/members/7",
    );

    await user.click(screen.getByRole("button", { name: "Abmelden" }));
    expect(localStorage.getItem("kompass_token")).toBeNull();
  });

  it("says so when the account has no member profile", async () => {
    server.use(
      http.get(api("/api/members/me"), () =>
        HttpResponse.json({
          user_id: 1,
          username: "admin",
          name: "Admin",
          member_id: null,
          is_staff: true,
          is_superuser: true,
          permissions: [],
        }),
      ),
    );
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    await user.click(await screen.findByRole("button", { name: /Admin/ }));
    expect(screen.getByText("Kein Teilnehmenden-Profil")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Mein Profil" })).not.toBeInTheDocument();
  });

  it("falls back to a neutral label before /me has answered", () => {
    renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(screen.getByRole("button", { name: /Konto/ })).toBeInTheDocument();
  });

  it("shows the public ↔ Kompass switch only while signed in", () => {
    renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(screen.getByRole("group", { name: "Bereich wechseln" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Anmelden" })).not.toBeInTheDocument();
  });

  it("offers a login link instead when signed out", () => {
    navReturns();
    renderWithApp(<SiteHeader variant="public" />, { route: "/", authenticated: false });
    expect(screen.getByRole("link", { name: "Anmelden" })).toHaveAttribute("href", "/login");
    expect(screen.queryByRole("group", { name: "Bereich wechseln" })).not.toBeInTheDocument();
  });

  it("points the brand at the dashboard in the app and at the site outside it", () => {
    const app = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(screen.getByRole("link", { name: /JDAV Ludwigsburg/ })).toHaveAttribute("href", "/kompass");
    app.unmount();

    navReturns();
    renderWithApp(<SiteHeader variant="public" />, { route: "/" });
    expect(screen.getByRole("link", { name: /JDAV Ludwigsburg/ })).toHaveAttribute("href", "/");
  });
});

describe("SiteHeader — public variant", () => {
  it("builds the navigation from the live startpage data", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, { route: "/" });

    // The root section names the first dropdown…
    const verein = await screen.findByRole("button", { name: /Verein/ });
    await user.click(verein);
    expect(screen.getByRole("link", { name: "Aktuelles" })).toHaveAttribute("href", "/aktuelles");

    // …every other opted-in section becomes a plain top-level link…
    expect(screen.getByRole("link", { name: "Ausbildung" })).toHaveAttribute(
      "href",
      "/bereich/ausbildung",
    );
    // …and one that opted out does not appear at all.
    expect(screen.queryByRole("link", { name: "Intern" })).not.toBeInTheDocument();
  });

  it("lists the public groups under Gruppen", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, { route: "/" });
    await user.click(await screen.findByRole("button", { name: /Gruppen/ }));

    expect(screen.getByRole("link", { name: "Alle Gruppen" })).toHaveAttribute("href", "/gruppen");
    expect(screen.getByRole("link", { name: "Klettergruppe" })).toHaveAttribute(
      "href",
      "/gruppe/Klettergruppe",
    );
    expect(screen.getByRole("link", { name: "FAQ" })).toHaveAttribute("href", "/gruppen/faq");
  });

  it("still renders a usable bar when the navigation endpoint gives nothing", async () => {
    navReturns({});
    renderWithApp(<SiteHeader variant="public" />, { route: "/" });
    // "Verein" is the fallback label for a site without a root section.
    expect(await screen.findByRole("button", { name: /Verein/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Impressum" })).toBeInTheDocument();
  });

  it("highlights the section link for the page being viewed", async () => {
    navReturns();
    renderWithApp(<SiteHeader variant="public" />, { route: "/impressum" });
    expect(await screen.findByRole("link", { name: "Ausbildung" })).not.toHaveClass("active");
    expect(screen.getByRole("link", { name: "Impressum" })).toHaveClass("nav-link", "active");
  });

  it("keeps the mode switch in the drawer on the public site", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, { route: "/" });
    await user.click(screen.getByRole("button", { name: "Menü" }));

    const inDrawer = within(document.querySelector(".drawer-switch") as HTMLElement);
    expect(inDrawer.getByRole("link", { name: "Website" })).toHaveClass("ctx", "active");
    expect(inDrawer.getByRole("link", { name: "Kompass" })).not.toHaveClass("active");
  });

  it("does not fetch the public navigation inside the app", () => {
    // No handler is registered: MSW is set to fail on any unhandled request, so
    // this passing at all proves the query stayed disabled.
    renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(screen.getByRole("button", { name: /Verwaltung/ })).toBeInTheDocument();
  });
});

describe("SiteHeader — mobile drawer", () => {
  it("expands the whole navigation and the account actions", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    await user.click(screen.getByRole("button", { name: "Menü" }));

    const drawer = document.querySelector(".topnav-drawer") as HTMLElement;
    const inDrawer = within(drawer);
    expect(inDrawer.getByText("Aktivitäten")).toBeInTheDocument();
    expect(inDrawer.getByRole("link", { name: "Ausfahrten" })).toBeInTheDocument();
    expect(inDrawer.getByRole("link", { name: "Website" })).toBeInTheDocument();

    await waitFor(() =>
      expect(inDrawer.getByRole("link", { name: "Mein Profil" })).toHaveAttribute(
        "href",
        "/kompass/members/7",
      ),
    );
    await user.click(inDrawer.getByRole("button", { name: "Abmelden" }));
    expect(localStorage.getItem("kompass_token")).toBeNull();
  });

  it("offers only a login link to a signed-out visitor", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, {
      route: "/",
      authenticated: false,
    });
    await user.click(screen.getByRole("button", { name: "Menü" }));

    const inDrawer = within(document.querySelector(".topnav-drawer") as HTMLElement);
    // A section link rendered as a leaf, not a group.
    expect(inDrawer.getByRole("link", { name: "Impressum" })).toBeInTheDocument();
    expect(inDrawer.getByRole("link", { name: "Anmelden" })).toBeInTheDocument();
    expect(inDrawer.queryByRole("button", { name: "Abmelden" })).not.toBeInTheDocument();
  });
});
