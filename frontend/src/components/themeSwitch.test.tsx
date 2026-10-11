import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { api, http, HttpResponse, server } from "../test/server";
import { renderWithApp } from "../test/utils";
import { setThemeChoice, THEME_STORAGE_KEY } from "../theme";
import { SiteHeader } from "./SiteHeader";

const root = document.documentElement;

function navReturns() {
  server.use(
    http.get(api("/api/startpage/public/navigation"), () =>
      HttpResponse.json({ root_section: null, sections: [], groups: [] }),
    ),
  );
}

afterEach(() => {
  act(() => setThemeChoice("system"));
  delete root.dataset.theme;
});

describe("theme switch", () => {
  it("is in the public chrome for a visitor who is not signed in", () => {
    navReturns();
    renderWithApp(<SiteHeader variant="public" />, { route: "/", authenticated: false });
    expect(screen.getByRole("button", { name: "Darstellung: System" })).toBeInTheDocument();
  });

  it("offers System, Hell and Dunkel, with the current one picked and focused", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    const trigger = screen.getByRole("button", { name: "Darstellung: System" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");

    await user.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    const group = screen.getByRole("group", { name: "Darstellung" });
    const options = within(group).getAllByRole("radio");
    expect(options.map((o) => o.closest("label")!.textContent)).toEqual([
      "System",
      "Hell",
      "Dunkel",
    ]);
    const system = within(group).getByRole("radio", { name: "System" });
    expect(system).toBeChecked();
    await waitFor(() => expect(system).toHaveFocus());
  });

  it("applies and remembers a choice, and the button says what is chosen", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    await user.click(screen.getByRole("button", { name: "Darstellung: System" }));

    await user.click(screen.getByRole("radio", { name: "Dunkel" }));
    expect(root.dataset.theme).toBe("dark");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("dark");
    expect(screen.getByRole("button", { name: "Darstellung: Dunkel" })).toBeInTheDocument();

    await user.click(screen.getByRole("radio", { name: "Hell" }));
    expect(root.dataset.theme).toBe("light");
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe("light");

    // Back to System forgets the choice rather than storing "system".
    await user.click(screen.getByRole("radio", { name: "System" }));
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBeNull();
  });

  it("is driven from the keyboard: arrows pick, Escape closes back onto the button", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    const trigger = screen.getByRole("button", { name: "Darstellung: System" });
    trigger.focus();
    await user.keyboard("{Enter}");
    await waitFor(() => expect(screen.getByRole("radio", { name: "System" })).toHaveFocus());

    await user.keyboard("{ArrowDown}");
    expect(screen.getByRole("radio", { name: "Hell" })).toBeChecked();
    expect(root.dataset.theme).toBe("light");

    await user.keyboard("{Escape}");
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
    expect(trigger).toHaveFocus();
    expect(screen.queryByRole("group", { name: "Darstellung" })).not.toBeInTheDocument();
  });

  it("closes on a click outside without moving focus", async () => {
    const { user } = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    const trigger = screen.getByRole("button", { name: "Darstellung: System" });
    await user.click(trigger);
    await user.click(document.body);
    await waitFor(() => expect(trigger).toHaveAttribute("aria-expanded", "false"));
    expect(trigger).not.toHaveFocus();
  });

  it("is in the mobile drawer too, in step with the button", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, {
      route: "/",
      authenticated: false,
    });
    await user.click(screen.getByRole("button", { name: "Menü" }));
    const group = screen.getByRole("group", { name: "Darstellung" });
    await user.click(within(group).getByRole("radio", { name: "Dunkel" }));
    expect(root.dataset.theme).toBe("dark");
    expect(screen.getByRole("button", { name: "Darstellung: Dunkel" })).toBeInTheDocument();
  });

  it("shows a choice made before it mounted", () => {
    setThemeChoice("dark");
    renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(screen.getByRole("button", { name: "Darstellung: Dunkel" })).toBeInTheDocument();
  });
});
