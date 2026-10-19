import { screen, waitFor, within } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { api, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute } from "../../test/utils";

const CREATE = "logindata.create_personalaccesstoken";
const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

const TOKEN = {
  id: 1,
  name: "Feedback abholen",
  read_only: true,
  created: "2026-10-19T20:00:00Z",
  expires: "2099-11-18T20:00:00Z",
  user: { id: 2, username: "hannah.becker" },
  created_by: { id: 2, username: "hannah.becker" },
};

function listReturns(rows: unknown[] = [TOKEN]) {
  server.use(http.get(api("/api/logindata/tokens"), () => HttpResponse.json(rows)));
}

// The workspace is a lazily loaded chunk; load it once up front so its cold
// import does not eat into the first test's budget for finding the page.
beforeAll(async () => {
  await import("../../kompassRoutes");
});

describe("access tokens", () => {
  it("lists one's tokens with their rights and expiry", async () => {
    listReturns([
      TOKEN,
      { ...TOKEN, id: 2, name: "Altes Skript", read_only: false, expires: "2020-01-01T00:00:00Z" },
    ]);
    renderRoute("/kompass/tokens");
    expect(await screen.findByText("Feedback abholen")).toBeInTheDocument();
    expect(screen.getByText("nur lesen")).toBeInTheDocument();
    expect(screen.getByText("lesen und schreiben")).toBeInTheDocument();
    expect(screen.getByText("abgelaufen")).toBeInTheDocument();
  });

  it("says so when there are none, and offers no creation without the permission", async () => {
    listReturns([]);
    renderRoute("/kompass/tokens");
    expect(await screen.findByText("Du hast keine Zugangstokens.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neues Token" })).toBeNull();
  });

  it("creates a token and shows it once, ready to copy", async () => {
    useMe({ permissions: [CREATE] });
    listReturns([]);
    let body: unknown = null;
    server.use(
      http.post(api("/api/logindata/tokens"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(
          { ...TOKEN, id: 3, name: "Claude", read_only: false, token: "kompass_pat_geheim" },
          { status: 201 },
        );
      }),
    );
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: "Neues Token" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Erstellen" })).toBeDisabled();
    await user.type(dialog.getByLabelText(/Name/), "Claude");
    await user.click(dialog.getByRole("button", { name: /^Rechte/ }));
    await user.click(dropdown().getByRole("button", { name: "Lesen und schreiben" }));
    await user.click(dialog.getByRole("button", { name: /^Gültigkeit/ }));
    await user.click(dropdown().getByRole("button", { name: "90 Tage" }));
    await user.click(dialog.getByRole("button", { name: "Erstellen" }));

    await waitFor(() =>
      expect(body).toEqual({ name: "Claude", read_only: false, days: 90, user_id: null }),
    );
    const shown = within(await screen.findByRole("dialog", { name: "Token erstellt" }));
    expect(shown.getByText("kompass_pat_geheim")).toBeInTheDocument();
    expect(shown.getByText(/Authorization: Bearer kompass_pat_geheim/)).toBeInTheDocument();

    const copy = vi.spyOn(navigator.clipboard, "writeText");
    await user.click(shown.getByRole("button", { name: "Kopieren" }));
    expect(copy).toHaveBeenCalledWith("kompass_pat_geheim");
    expect(await screen.findByText("Token kopiert.")).toBeInTheDocument();

    // Without clipboard access (an insecure origin, a refused permission) the
    // token stays on screen to be selected by hand.
    copy.mockRejectedValueOnce(new Error("denied"));
    await user.click(shown.getByRole("button", { name: "Kopieren" }));
    expect(await screen.findByText(/Kopieren nicht möglich/)).toBeInTheDocument();

    await user.click(shown.getByRole("button", { name: "Fertig" }));
    expect(screen.queryByText("kompass_pat_geheim")).toBeNull();
  });

  it("creates a token that never expires", async () => {
    useMe({ permissions: [CREATE] });
    listReturns([{ ...TOKEN, expires: null }]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/logindata/tokens"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ ...TOKEN, expires: null, token: "kompass_pat_ewig" }, { status: 201 });
      }),
    );
    const { user } = renderRoute("/kompass/tokens");
    // Listed without an expiry.
    expect(await screen.findByText("unbegrenzt")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Neues Token" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Name/), "Skript");
    await user.click(dialog.getByRole("button", { name: /^Gültigkeit/ }));
    await user.click(dropdown().getByRole("button", { name: "Unbegrenzt" }));
    expect(dialog.getByText(/Läuft nie ab/)).toBeInTheDocument();
    // Only a superuser picks the account.
    expect(dialog.queryByRole("button", { name: /^Konto/ })).toBeNull();
    await user.click(dialog.getByRole("button", { name: "Erstellen" }));
    await waitFor(() => expect(body).toMatchObject({ days: null, user_id: null }));
  });

  it("lets a superuser create a token for a bot account and see every account's", async () => {
    useMe({ is_superuser: true });
    listReturns([TOKEN, { ...TOKEN, id: 4, name: "Bot", user: { id: 9, username: "feedback-bot" } }]);
    let body: Record<string, unknown> | null = null;
    server.use(
      http.get(api("/api/logindata/users"), () =>
        HttpResponse.json([
          { id: 2, username: "hannah.becker", is_active: true, is_staff: true, is_superuser: true },
          { id: 9, username: "feedback-bot", is_active: true, is_staff: false, is_superuser: false },
        ]),
      ),
      http.post(api("/api/logindata/tokens"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          { ...TOKEN, id: 5, user: { id: 9, username: "feedback-bot" }, token: "kompass_pat_bot" },
          { status: 201 },
        );
      }),
    );
    const { user } = renderRoute("/kompass/tokens");
    expect(await screen.findByRole("columnheader", { name: "Konto" })).toBeInTheDocument();
    expect(screen.getByText("feedback-bot")).toBeInTheDocument();
    // Who made a token for another account is on record; one's own needs no note.
    expect(screen.getAllByText("erstellt von hannah.becker")).toHaveLength(1);

    await user.click(screen.getByRole("button", { name: "Neues Token" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Name/), "Feedback-Bot");
    await user.click(dialog.getByRole("button", { name: /^Konto/ }));
    // One's own account is the default, not a choice in the list.
    expect(dropdown().queryByRole("button", { name: "hannah.becker" })).toBeNull();
    await user.click(await dropdown().findByRole("button", { name: "feedback-bot" }));
    await user.click(dialog.getByRole("button", { name: "Erstellen" }));

    await waitFor(() => expect(body).toMatchObject({ user_id: 9 }));
    const shown = within(await screen.findByRole("dialog", { name: "Token erstellt" }));
    expect(shown.getByText("feedback-bot")).toBeInTheDocument();
  });

  it("shows the reason a token was refused on its field", async () => {
    useMe({ permissions: [CREATE] });
    listReturns([]);
    server.use(
      http.post(api("/api/logindata/tokens"), () =>
        HttpResponse.json(
          { detail: ["Gib dem Token einen Namen."], errors: { name: ["Gib dem Token einen Namen."] } },
          { status: 422 },
        ),
      ),
    );
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: "Neues Token" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText(/Name/), "x");
    await user.click(dialog.getByRole("button", { name: "Erstellen" }));
    expect(await dialog.findByText("Gib dem Token einen Namen.")).toHaveClass("field-error");

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("revokes a token after asking", async () => {
    listReturns();
    let revoked = false;
    server.use(
      http.delete(api("/api/logindata/tokens/1"), () => {
        revoked = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: "Widerrufen" }));
    const confirm = within(await screen.findByRole("dialog"));
    expect(confirm.getByText(/Feedback abholen/)).toBeInTheDocument();
    await user.click(confirm.getByRole("button", { name: "Widerrufen" }));
    await waitFor(() => expect(revoked).toBe(true));
    expect(await screen.findByText("Token widerrufen.")).toBeInTheDocument();
  });

  it("is in the user menu for those who may create tokens", async () => {
    useMe({ permissions: [CREATE] });
    listReturns();
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: /Hannah Beckers/ }));
    expect(await screen.findByRole("link", { name: "Zugangstokens" })).toHaveAttribute(
      "href",
      "/kompass/tokens",
    );
  });

  it("is not in the user menu for anyone else", async () => {
    listReturns();
    const { user } = renderRoute("/kompass/tokens");
    await user.click(await screen.findByRole("button", { name: /Hannah Beckers/ }));
    expect(await screen.findByText("Abmelden")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Zugangstokens" })).toBeNull();
  });
});
