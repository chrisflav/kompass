import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute } from "../../test/utils";

const HANNAH = { id: 7, name: "Hannah Beckers" };
const MILA = { id: 9, name: "Mila Nowak" };

/** One frozen approval constraint, with the fields `/approval` always sends. */
function constraint(overrides: Record<string, unknown> = {}) {
  return {
    name: "kassenwart",
    description: "Die Kassenwartin gibt die Auszahlung frei.",
    applicable: true,
    required: 1,
    satisfied: false,
    overridden: false,
    open: true,
    missing: 1,
    state_display: "Offen",
    eligible: [HANNAH],
    signed_by: [],
    excluded: [],
    overridden_by: null,
    override_reason: "",
    ...overrides,
  };
}

function approvalReturns(overrides: Record<string, unknown> = {}) {
  const payload = {
    statement_id: 1,
    approved: false,
    may_approve: false,
    constraints: [constraint()],
    signatures: [],
    ...overrides,
  };
  server.use(
    http.get(api("/api/finance/statements/1/approval"), () => HttpResponse.json(payload)),
  );
  return payload;
}

const APPROVAL = "/kompass/finance/statements/1/approval";

describe("statement approval — the record", () => {
  it("names the constraint, its state, who may sign and who did", async () => {
    approvalReturns({
      constraints: [
        constraint({
          required: 2,
          missing: 1,
          eligible: [HANNAH, MILA],
          signed_by: [MILA],
        }),
      ],
      signatures: [{ member: MILA, at: "2026-05-02T10:00:00Z", note: "geprüft" }],
    });
    renderRoute(APPROVAL);

    expect(await screen.findByText("Die Kassenwartin gibt die Auszahlung frei."))
      .toBeInTheDocument();
    expect(screen.getByText("Offen")).toBeInTheDocument();
    expect(screen.getByText("2 Unterschriften, noch 1 offen")).toBeInTheDocument();
    expect(screen.getByText("Hannah Beckers, Mila Nowak")).toBeInTheDocument();
    // Who actually signed, which is the thing no interface showed at all.
    expect(screen.getByText(/Mila Nowak · .* · geprüft/)).toBeInTheDocument();
  });

  it("gives an excluded signer the reason they were excluded", async () => {
    approvalReturns({
      constraints: [
        constraint({
          excluded: [{ member: MILA, forbid: "bekommt Geld aus dieser Abrechnung" }],
        }),
      ],
    });
    renderRoute(APPROVAL);

    expect(
      await screen.findByText("Mila Nowak (bekommt Geld aus dieser Abrechnung)"),
    ).toBeInTheDocument();
  });

  it("keeps an overridden step in the list with who did it and why", async () => {
    approvalReturns({
      approved: true,
      constraints: [
        constraint({
          satisfied: true,
          overridden: true,
          open: false,
          missing: 0,
          state_display: "Übergangen",
          overridden_by: HANNAH,
          override_reason: "Vorstand per Mail zugestimmt",
        }),
      ],
    });
    renderRoute(APPROVAL);

    expect(await screen.findByText("Übergangen")).toBeInTheDocument();
    expect(screen.getByText("Hannah Beckers · Vorstand per Mail zugestimmt")).toBeInTheDocument();
    expect(screen.getByText("Alle Freigaben liegen vor.")).toBeInTheDocument();
  });

  it("marks a signed step as signed", async () => {
    approvalReturns({
      approved: true,
      constraints: [
        constraint({
          satisfied: true,
          open: false,
          missing: 0,
          state_display: "Unterschrieben",
          signed_by: [HANNAH],
        }),
      ],
    });
    renderRoute(APPROVAL);

    expect(await screen.findByText("Unterschrieben")).toBeInTheDocument();
    expect(screen.getByText("1 Unterschrift")).toBeInTheDocument();
  });

  it("says a step does not apply rather than calling it unsigned", async () => {
    approvalReturns({
      constraints: [
        constraint({
          applicable: false,
          open: false,
          satisfied: true,
          state_display: "Gilt nicht",
          eligible: [],
        }),
      ],
    });
    renderRoute(APPROVAL);

    expect(await screen.findByText("gilt für diese Abrechnung nicht")).toBeInTheDocument();
    expect(screen.getByText("niemand")).toBeInTheDocument();
  });

  it("says so when the rules ask for no separate approval", async () => {
    approvalReturns({ constraints: [], approved: true });
    renderRoute(APPROVAL);
    expect(
      await screen.findByText("Für diese Abrechnung verlangen die Regeln keine gesonderte Freigabe."),
    ).toBeInTheDocument();
  });

  it("names an unattributable signature rather than dropping it", async () => {
    approvalReturns({ signatures: [{ member: null, at: "2026-05-02T10:00:00Z", note: "" }] });
    renderRoute(APPROVAL);
    expect(await screen.findByText(/unbekannte Person/)).toBeInTheDocument();
  });

  it("says when nobody has signed yet", async () => {
    approvalReturns();
    renderRoute(APPROVAL);
    expect(await screen.findByText("Noch niemand.")).toBeInTheDocument();
  });

  it("surfaces a refusal to load the record", async () => {
    server.use(
      http.get(api("/api/finance/statements/1/approval"), () =>
        HttpResponse.json({ detail: "Nicht gefunden." }, { status: 404 }),
      ),
    );
    renderRoute(APPROVAL);
    expect(await screen.findByRole("alert")).toHaveTextContent("Nicht gefunden.");
  });
});

describe("statement approval — the actions", () => {
  it("offers the signature only to somebody the rules still leave something to sign", async () => {
    approvalReturns({ may_approve: false });
    renderRoute(APPROVAL);
    await screen.findByText("Offen");
    expect(screen.queryByRole("button", { name: "Jetzt freigeben" })).not.toBeInTheDocument();
  });

  it("signs the statement off", async () => {
    approvalReturns({ may_approve: true });
    let signed = false;
    server.use(
      http.post(api("/api/finance/statements/1/approve"), () => {
        signed = true;
        return HttpResponse.json(approvalReturns({ approved: true }));
      }),
    );
    const { user } = renderRoute(APPROVAL);

    await user.click(await screen.findByRole("button", { name: "Jetzt freigeben" }));
    await waitFor(() => expect(signed).toBe(true));
    expect(await screen.findByText("Freigabe erteilt.")).toBeInTheDocument();
  });

  it("reports a refused signature", async () => {
    approvalReturns({ may_approve: true });
    server.use(
      http.post(api("/api/finance/statements/1/approve"), () =>
        HttpResponse.json({ detail: "Du hast hier schon unterschrieben." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute(APPROVAL);
    await user.click(await screen.findByRole("button", { name: "Jetzt freigeben" }));
    expect(await screen.findByText("Du hast hier schon unterschrieben.")).toBeInTheDocument();
  });

  it("offers an override only with the treasurer's permission", async () => {
    approvalReturns();
    renderRoute(APPROVAL);
    await screen.findByText("Offen");
    expect(
      screen.queryByRole("button", { name: "Ohne Unterschrift freigeben" }),
    ).not.toBeInTheDocument();
  });

  it("overrides a step with a reason on the record", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    approvalReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(approvalReturns({ approved: true }));
      }),
    );
    const { user } = renderRoute(APPROVAL);

    await user.click(
      await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }),
    );
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox"), "Vorstand per Mail zugestimmt");
    await user.click(dialog.getByRole("button", { name: "Übergehen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ name: "kassenwart", reason: "Vorstand per Mail zugestimmt" });
    expect(await screen.findByText("Schritt übergangen und vermerkt.")).toBeInTheDocument();
  });

  it("keeps the dialog open and says why a refused override was refused", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    approvalReturns();
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), () =>
        djangoValidation({ __all__: ["Die Regeln schließen dich von diesem Schritt aus."] }),
      ),
    );
    const { user } = renderRoute(APPROVAL);

    await user.click(
      await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }),
    );
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox"), "weil");
    await user.click(dialog.getByRole("button", { name: "Übergehen" }));

    // In the dialog, under the reason — not only as a toast that outlives it.
    const message = await within(screen.getByRole("dialog")).findByText(
      /schließen dich von diesem Schritt aus/,
    );
    expect(message).toHaveClass("field-error");
  });

  it("falls back to the generic message when a refusal names no field", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    approvalReturns();
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), () =>
        HttpResponse.json({ detail: "Schon bezahlt." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute(APPROVAL);

    await user.click(
      await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }),
    );
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox"), "weil");
    await user.click(dialog.getByRole("button", { name: "Übergehen" }));

    expect(await screen.findAllByText("Schon bezahlt.")).not.toHaveLength(0);
  });

  it("closes the override dialog on Abbrechen", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    approvalReturns();
    const { user } = renderRoute(APPROVAL);

    await user.click(
      await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }),
    );
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("goes back through the browser history", async () => {
    approvalReturns();
    const { user } = renderRoute(APPROVAL);
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});
