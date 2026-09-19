import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, http, HttpResponse, server, useMe } from "../test/server";
import { renderRoute, renderWithApp } from "../test/utils";
import { SiteHeader } from "./SiteHeader";

const anon = { authenticated: false as const, route: "/" };

function navReturns() {
  server.use(
    http.get(api("/api/startpage/public/navigation"), () =>
      HttpResponse.json({ root_section: null, sections: [], groups: [] }),
    ),
  );
}

describe("feedback button", () => {
  it("is in the chrome of the public site and of Kompass alike", async () => {
    navReturns();
    renderWithApp(<SiteHeader variant="public" />, anon);
    expect(await screen.findByRole("button", { name: /Feedback/ })).toBeInTheDocument();

    const app = renderWithApp(<SiteHeader variant="app" />, { route: "/kompass" });
    expect(
      await within(app.container).findByRole("button", { name: /Feedback/ }),
    ).toBeInTheDocument();
  });

  it("sends a note with the current page and reports back", async () => {
    navReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/feedback"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, message: "x", created: "2026-09-14T10:00:00Z" });
      }),
    );
    const { user } = renderWithApp(<SiteHeader variant="public" />, {
      ...anon,
      route: "/gruppen?x=1",
    });

    await user.click(await screen.findByRole("button", { name: /Feedback/ }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Dein Feedback"), "Der Button klemmt.");
    await user.click(dialog.getByRole("button", { name: "Absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    const sent = body as unknown as { message: string; page_url: string; user_agent: string };
    expect(sent.message).toBe("Der Button klemmt.");
    // Context is on by default, and it is the page the sender was actually on.
    expect(sent.page_url).toContain("/gruppen?x=1");
    expect(sent.user_agent).not.toBe("");
    expect(await screen.findByText("Danke für dein Feedback!")).toBeInTheDocument();
  });

  it("sends nothing about the page when the context is unticked", async () => {
    navReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/feedback"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1, message: "x", created: "2026-09-14T10:00:00Z" });
      }),
    );
    const { user } = renderWithApp(<SiteHeader variant="public" />, anon);

    await user.click(await screen.findByRole("button", { name: /Feedback/ }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Dein Feedback"), "Nur ein Lob.");
    await user.click(dialog.getByLabelText(/Aktuelle Seite mitsenden/));
    await user.click(dialog.getByRole("button", { name: "Absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ page_url: "", user_agent: "" });
  });

  it("shows what would be sent, so the checkbox is an informed choice", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, {
      ...anon,
      route: "/impressum",
    });
    await user.click(await screen.findByRole("button", { name: /Feedback/ }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByText(/\/impressum/)).toBeInTheDocument();
  });

  it("will not send an empty note", async () => {
    navReturns();
    const { user } = renderWithApp(<SiteHeader variant="public" />, anon);
    await user.click(await screen.findByRole("button", { name: /Feedback/ }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Absenden" })).toBeDisabled();
    await user.type(dialog.getByLabelText("Dein Feedback"), "  ");
    expect(dialog.getByRole("button", { name: "Absenden" })).toBeDisabled();
  });

  it("keeps the note when the server refuses it", async () => {
    navReturns();
    server.use(
      http.post(api("/api/feedback"), () =>
        HttpResponse.json({ detail: "Zu lang." }, { status: 422 }),
      ),
    );
    const { user } = renderWithApp(<SiteHeader variant="public" />, anon);
    await user.click(await screen.findByRole("button", { name: /Feedback/ }));

    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Dein Feedback"), "Ein Hinweis.");
    await user.click(dialog.getByRole("button", { name: "Absenden" }));

    expect(await screen.findByText("Zu lang.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("Ein Hinweis.")).toBeInTheDocument();
  });
});

describe("feedback inbox", () => {
  const ROWS = [
    {
      id: 2,
      message: "Der Kalender lädt nicht.\nZweite Zeile",
      created: "2026-09-14T10:30:00Z",
      submitted_by: { id: 7, name: "Hannah Beckers" },
      page_url: "http://localhost/kompass/events",
      has_context: true,
    },
    {
      id: 1,
      message: "Schöne Seite!",
      created: "2026-09-13T08:00:00Z",
      submitted_by: null,
      page_url: "",
      has_context: false,
    },
  ];

  function listReturns(rows: unknown[] = ROWS) {
    server.use(http.get(api("/api/feedback"), () => HttpResponse.json(rows)));
  }

  it("lists what came in, naming anonymous senders as such", async () => {
    listReturns();
    renderRoute("/kompass/feedback");

    await screen.findByText(/Der Kalender lädt nicht\./);
    // Scoped to the table: the signed-in user's own name is also in the chrome.
    const table = within(document.querySelector(".data-table") as HTMLElement);
    expect(table.getByText("Hannah Beckers")).toBeInTheDocument();
    expect(table.getByText("ohne Konto")).toBeInTheDocument();
    expect(table.getByText("mitgesendet")).toBeInTheDocument();
  });

  it("says so when nothing has come in", async () => {
    listReturns([]);
    renderRoute("/kompass/feedback");
    expect(await screen.findByText("Noch kein Feedback eingegangen.")).toBeInTheDocument();
  });

  it("opens one and shows the context it carried", async () => {
    listReturns();
    server.use(
      http.get(api("/api/feedback/2"), () =>
        HttpResponse.json({ ...ROWS[0], user_agent: "Mozilla/5.0" }),
      ),
    );
    const { user } = renderRoute("/kompass/feedback");
    await user.click(await screen.findByText(/Der Kalender lädt nicht\./));

    expect(await screen.findByText(/Zweite Zeile/)).toBeInTheDocument();
    expect(screen.getByText("http://localhost/kompass/events")).toBeInTheDocument();
    expect(screen.getByText("Mozilla/5.0")).toBeInTheDocument();
  });

  it("hides the delete action without the permission", async () => {
    listReturns();
    server.use(
      http.get(api("/api/feedback/1"), () => HttpResponse.json({ ...ROWS[1], user_agent: "" })),
    );
    renderRoute("/kompass/feedback/1");
    await screen.findByText("Schöne Seite!");
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("deletes once confirmed", async () => {
    useMe({ permissions: ["feedback.delete_feedback"] });
    listReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/feedback/1"), () => HttpResponse.json({ ...ROWS[1], user_agent: "" })),
      http.delete(api("/api/feedback/1"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/kompass/feedback/1");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });
});
