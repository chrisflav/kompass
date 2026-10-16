import { screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server } from "../test/server";
import { renderRoute } from "../test/utils";

describe("FeedbackButton", () => {
  // The button lives in the site chrome; mock the page underneath it so the
  // route renders cleanly rather than leaving an unrelated query in error.
  beforeEach(() => {
    server.use(
      http.get(api("/api/finance/statements"), () => HttpResponse.json([])),
      http.get(api("/api/finance/enums"), () => HttpResponse.json({ status: [] })),
    );
  });

  it("opens the dialog and shows the page it will send", async () => {
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));

    expect(await screen.findByRole("dialog", { name: "Feedback geben" })).toBeInTheDocument();
    expect(screen.getByText(/\/kompass\/finance\/statements/)).toBeInTheDocument();
  });

  it("sends the message with the page context by default", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/feedback"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    await user.type(await screen.findByLabelText("Dein Feedback"), "Hilfe, ein Fehler.");
    await user.click(screen.getByRole("button", { name: "Absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ message: "Hilfe, ein Fehler." });
    expect(body!.page_url).toContain("/kompass/finance/statements");
    expect(body!.user_agent).not.toBe("");
    expect(await screen.findByText("Danke für dein Feedback!")).toBeInTheDocument();
  });

  it("drops the page context when the checkbox is unticked", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/feedback"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 1 });
      }),
    );
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    await user.type(await screen.findByLabelText("Dein Feedback"), "Ohne Kontext bitte.");
    await user.click(screen.getByRole("checkbox", { name: /Aktuelle Seite mitsenden/ }));
    await user.click(screen.getByRole("button", { name: "Absenden" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({ page_url: "", user_agent: "" });
  });

  it("counts down once the message nears the limit", async () => {
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    const textarea = await screen.findByLabelText("Dein Feedback");
    await user.click(textarea);
    await user.paste("a".repeat(4950));

    expect(await screen.findByText("Noch 50 Zeichen.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Absenden" })).toBeEnabled();
  });

  it("blocks sending once the message is over the limit", async () => {
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    const textarea = await screen.findByLabelText("Dein Feedback");
    await user.click(textarea);
    await user.paste("a".repeat(5010));

    expect(await screen.findByText("10 Zeichen zu viel.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Absenden" })).toBeDisabled();
  });

  it("shows a rejected message as a field error", async () => {
    server.use(
      http.post(api("/api/feedback"), () => djangoValidation({ message: ["Zu kurz."] })),
    );
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByLabelText("Dein Feedback"), "x");
    await user.click(dialog.getByRole("button", { name: "Absenden" }));

    expect(await dialog.findByText("Zu kurz.")).toBeInTheDocument();
  });

  it("closes without sending on Abbrechen", async () => {
    const { user } = renderRoute("/kompass/finance/statements");
    await user.click(screen.getByRole("button", { name: "Feedback" }));
    await user.type(await screen.findByLabelText("Dein Feedback"), "verworfen");
    await user.click(screen.getByRole("button", { name: "Abbrechen" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});
