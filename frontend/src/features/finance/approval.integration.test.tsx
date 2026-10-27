import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import { renderRoute } from "../../test/utils";

/**
 * The approval record where it now lives: the review pipeline's last leg.
 *
 * It used to be a route of its own, `/:id/approval`, beside a review pipeline
 * whose last leg paid the statement out — two doors into one room, and the
 * review's door was the one that looked as though it skipped the other. Both
 * posted a signature: `/confirm` and `/approve` are `Statement.approve`
 * underneath, which pays out on the signature that completes the quorum and
 * records one that does not.
 *
 * So these are tests about one surface offering whichever act is left: the
 * payout, with the acknowledgement that has always stood in front of it, or a
 * signature, which says what it did and what is still missing.
 */

const HANNAH = { id: 7, name: "Hannah Beckers" };
const MILA = { id: 9, name: "Mila Nowak" };

const REVIEW = "/kompass/finance/statements/1/review?stage=payout";

const TRANSACTION = {
  id: 20,
  amount: 42.5,
  confirmed: false,
  confirmed_date: null,
  confirmed_by: null,
  statement_id: 1,
  member: MILA,
  ledger: { id: 1, name: "Jugendetat" },
  code: "",
  iban: "DE02120300000000202051",
  iban_valid: true,
  reference: "Material",
  settlement_group: "",
};

/** Only what the review pipeline and the record view actually read. */
function statement(overrides: Record<string, unknown> = {}) {
  return {
    id: 1,
    title: "F26-02 Materialkauf",
    short_description: "Materialkauf",
    explanation: "",
    submitted: true,
    confirmed: false,
    status: 1,
    status_display: "Eingereicht",
    is_valid: true,
    validity: 0,
    validity_display: "Gültig",
    transaction_issues: [],
    // The rail reads them for the Erstattung leg, which the review shows now.
    transfers: [],
    excursion: null,
    created_by: MILA,
    submitted_by: MILA,
    confirmed_by: null,
    submitted_date: "2026-05-02",
    confirmed_date: null,
    allowance_to: [],
    subsidy_to: null,
    ljp_to: null,
    night_cost: 0,
    bills: [],
    total: 42.5,
    ...overrides,
  };
}

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

function approval(overrides: Record<string, unknown> = {}) {
  return {
    statement_id: 1,
    approved: false,
    may_approve: false,
    // Heidelberg's shape: one constraint, satisfied by one signature, so the
    // next click is the payout. A section that asks for more says `false` here
    // until the signature that completes it.
    completes_approval: true,
    constraints: [constraint()],
    signatures: [],
    ...overrides,
  };
}

/**
 * Open the review pipeline's last leg for a treasurer.
 *
 * Returns the mutable call log, so a test can say which endpoint the click
 * reached — the point of the whole change being that the signature short of a
 * quorum stopped going to `/confirm`.
 */
function openFreigabe(
  payload: Record<string, unknown> = approval(),
  overrides: Record<string, unknown> = {},
  transactions: unknown[] = [TRANSACTION],
) {
  useMe({ permissions: ["finance.process_statementsubmitted"] });
  const posted: string[] = [];
  let current = payload;
  server.use(
    http.get(api("/api/finance/statements/1"), () =>
      HttpResponse.json(statement(overrides)),
    ),
    http.get(api("/api/finance/statements/1/transactions"), () =>
      HttpResponse.json(transactions),
    ),
    http.get(api("/api/finance/statements/1/approval"), () => HttpResponse.json(current)),
    // The leg states the statement's own answers above the money now, so it
    // asks for the form as well. Heidelberg's shape: four questions, none of
    // which these tests are about — `signer.integration.test.tsx` is.
    http.get(api("/api/finance/statements/1/form"), () =>
      HttpResponse.json({
        statement_id: 1,
        inputs: [
          {
            key: "night_cost",
            label: "Preis pro Übernachtung",
            type: "money",
            required: false,
            help: "",
            max: null,
            options: [],
            choices: [],
            fields: [],
            step: "",
            derived: false,
          },
        ],
        steps: [{ label: "", keys: ["night_cost"] }],
        answers: { night_cost: "11.00" },
      }),
    ),
    http.post(api("/api/finance/statements/1/approve"), () => {
      posted.push("approve");
      return HttpResponse.json(current);
    }),
    http.post(api("/api/finance/statements/1/confirm"), () => {
      posted.push("confirm");
      return HttpResponse.json(statement({ ...overrides, confirmed: true, status: 2 }));
    }),
  );
  return {
    ...renderRoute(REVIEW),
    posted,
    /** What `/approval` and `/approve` answer from now on. */
    answers: (next: Record<string, unknown>) => {
      current = next;
    },
  };
}

describe("Freigabe — the record on the review's last leg", () => {
  it("names the constraint, its state, who may sign and who did", async () => {
    openFreigabe(
      approval({
        constraints: [
          constraint({ required: 2, missing: 1, eligible: [HANNAH, MILA], signed_by: [MILA] }),
        ],
        signatures: [{ member: MILA, at: "2026-05-02T10:00:00Z", note: "geprüft" }],
      }),
    );

    expect(
      await screen.findByText("Die Kassenwartin gibt die Auszahlung frei."),
    ).toBeInTheDocument();
    expect(screen.getByText("Offen")).toBeInTheDocument();
    expect(screen.getByText("2 Unterschriften, noch 1 offen")).toBeInTheDocument();
    expect(screen.getByText("Hannah Beckers, Mila Nowak")).toBeInTheDocument();
    // Who actually signed, which is the thing no interface showed at all.
    expect(screen.getByText(/Mila Nowak · .* · geprüft/)).toBeInTheDocument();
    // And the payout it is holding up is on the same screen.
    expect(screen.getByRole("heading", { name: "Auszahlung" })).toBeInTheDocument();
  });

  it("gives an excluded signer the reason they were excluded", async () => {
    openFreigabe(
      approval({
        constraints: [
          constraint({ excluded: [{ member: MILA, forbid: "bekommt Geld aus dieser Abrechnung" }] }),
        ],
      }),
    );

    expect(
      await screen.findByText("Mila Nowak (bekommt Geld aus dieser Abrechnung)"),
    ).toBeInTheDocument();
  });

  it("keeps an overridden step in the list with who did it and why", async () => {
    openFreigabe(
      approval({
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
      }),
    );

    expect(await screen.findByText("Übergangen")).toBeInTheDocument();
    expect(screen.getByText("Hannah Beckers · Vorstand per Mail zugestimmt")).toBeInTheDocument();
    expect(screen.getByText("Alle Freigaben liegen vor.")).toBeInTheDocument();
  });

  it("says a step does not apply rather than calling it unsigned", async () => {
    openFreigabe(
      approval({
        approved: true,
        constraints: [
          constraint({
            applicable: false,
            open: false,
            satisfied: true,
            state_display: "Gilt nicht",
            eligible: [],
          }),
        ],
      }),
    );

    expect(await screen.findByText("gilt für diese Abrechnung nicht")).toBeInTheDocument();
    expect(screen.getByText("niemand")).toBeInTheDocument();
  });

  it("says so when the rules ask for no separate approval", async () => {
    openFreigabe(approval({ constraints: [], approved: true }));
    expect(
      await screen.findByText(
        "Für diese Abrechnung verlangen die Regeln keine gesonderte Freigabe.",
      ),
    ).toBeInTheDocument();
    // And the payout is still offered: a ruleset that asks for no signature is
    // one that is happy with the capability check.
    expect(screen.getByRole("button", { name: "Nur bestätigen" })).toBeInTheDocument();
  });

  it("names an unattributable signature rather than dropping it", async () => {
    openFreigabe(approval({ signatures: [{ member: null, at: "2026-05-02T10:00:00Z", note: "" }] }));
    expect(await screen.findByText(/unbekannte Person/)).toBeInTheDocument();
  });

  it("says a step nobody may sign is stuck rather than waiting", async () => {
    openFreigabe(
      approval({
        completes_approval: false,
        constraints: [
          constraint({ eligible: [], state_display: "Niemand darf unterschreiben" }),
        ],
      }),
    );
    expect(
      await screen.findByText(/kommt nicht weiter: für Die Kassenwartin/),
    ).toBeInTheDocument();
  });
});

describe("Freigabe — the act, whichever one is left", () => {
  it("signs short of a quorum and says what is still missing", async () => {
    // The defect this whole change is about: the signature that does not
    // complete the quorum. "Prüfen & auszahlen" posted `/confirm`, which took
    // the signature and answered "Statement is not ready to be confirmed."
    const open = approval({
      completes_approval: false,
      may_approve: true,
      constraints: [
        constraint({ name: "kasse", description: "Kasse", satisfied: true, open: false, missing: 0, state_display: "Unterschrieben", signed_by: [HANNAH] }),
        constraint({ name: "vorstand", description: "Vorstand", eligible: [HANNAH, MILA] }),
      ],
    });
    const { user, posted } = openFreigabe(open);

    // The payout's acknowledgement is not asked for an act that pays nothing
    // out, and neither confirm button is on offer.
    expect(await screen.findByRole("button", { name: "Jetzt freigeben" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Überweisungen ausgeführt/)).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nur bestätigen" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Jetzt freigeben" }));

    await waitFor(() => expect(posted).toEqual(["approve"]));
    expect(
      await screen.findByText("Freigabe vermerkt. Es fehlt noch eine Unterschrift: Vorstand."),
    ).toBeInTheDocument();
  });

  it("counts every signature that is still missing, and names the steps", async () => {
    const { user } = openFreigabe(
      approval({
        completes_approval: false,
        may_approve: true,
        constraints: [
          constraint({ name: "kasse", description: "Kasse" }),
          constraint({
            name: "vorstand",
            description: "Vorstand",
            required: 2,
            missing: 2,
            eligible: [HANNAH, MILA],
          }),
        ],
      }),
    );

    // Said before the click as well as after it: this is where the statement
    // stands, not a message about one request.
    expect(
      await screen.findByText("Es fehlen noch 3 Unterschriften: Kasse, Vorstand."),
    ).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Jetzt freigeben" }));
    expect(
      await screen.findByText("Freigabe vermerkt. Es fehlen noch 3 Unterschriften: Kasse, Vorstand."),
    ).toBeInTheDocument();
  });

  it("says so when the signature turned out to be the last one", async () => {
    const { user, answers } = openFreigabe(
      approval({ completes_approval: false, may_approve: true }),
    );
    await screen.findByRole("button", { name: "Jetzt freigeben" });
    answers(approval({ approved: true, constraints: [constraint({ satisfied: true, open: false, missing: 0 })] }));
    await user.click(screen.getByRole("button", { name: "Jetzt freigeben" }));
    expect(
      await screen.findByText("Freigabe vermerkt. Alle Freigaben liegen jetzt vor."),
    ).toBeInTheDocument();
  });

  it("reports a refused signature", async () => {
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements/1/approval"), () =>
        HttpResponse.json(approval({ completes_approval: false, may_approve: true })),
      ),
      http.post(api("/api/finance/statements/1/approve"), () =>
        HttpResponse.json({ detail: "Du hast hier schon unterschrieben." }, { status: 422 }),
      ),
    );
    const { user } = renderRoute(REVIEW);

    await user.click(await screen.findByRole("button", { name: "Jetzt freigeben" }));
    expect(await screen.findByText("Du hast hier schon unterschrieben.")).toBeInTheDocument();
  });

  it("offers nothing to somebody the rules leave nothing to sign", async () => {
    openFreigabe(approval({ completes_approval: false, may_approve: false }));

    expect(
      await screen.findByText(/Für dich ist hier nichts mehr zu tun/),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Jetzt freigeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nur bestätigen" })).not.toBeInTheDocument();
  });

  it("pays out through confirm when the signature is the last one", async () => {
    const { user, posted } = openFreigabe();

    await user.click(await screen.findByLabelText(/Ich habe die aufgeführten Überweisungen/));
    await user.click(screen.getByRole("button", { name: "Nur bestätigen" }));

    await waitFor(() => expect(posted).toEqual(["confirm"]));
    expect(await screen.findByText("Abrechnung bestätigt.")).toBeInTheDocument();
  });

  it("falls back to the payout when the record cannot be loaded", async () => {
    // The record is what decides which act is on offer, so a record that is
    // missing must not take the act with it: `confirm` is what this leg always
    // posted, and it now names which of its two refusals applies.
    useMe({ permissions: ["finance.process_statementsubmitted"] });
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements/1/approval"), () =>
        HttpResponse.json({ detail: "Nicht gefunden." }, { status: 404 }),
      ),
    );
    renderRoute(REVIEW);

    expect(await screen.findByText("Nicht gefunden.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Nur bestätigen" })).toBeInTheDocument();
  });
});

describe("Freigabe — going ahead without a signature", () => {
  it("overrides a step with a reason on the record", async () => {
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(approval({ approved: true }));
      }),
    );
    const { user } = openFreigabe();

    await user.click(await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox"), "Vorstand per Mail zugestimmt");
    await user.click(dialog.getByRole("button", { name: "Übergehen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toEqual({ name: "kassenwart", reason: "Vorstand per Mail zugestimmt" });
    expect(await screen.findByText("Schritt übergangen und vermerkt.")).toBeInTheDocument();
  });

  it("keeps the dialog open and says why a refused override was refused", async () => {
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), () =>
        djangoValidation({ __all__: ["Die Regeln schließen dich von diesem Schritt aus."] }),
      ),
    );
    const { user } = openFreigabe();

    await user.click(await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }));
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
    server.use(
      http.post(api("/api/finance/statements/1/override-approval"), () =>
        HttpResponse.json({ detail: "Schon bezahlt." }, { status: 422 }),
      ),
    );
    const { user } = openFreigabe();

    await user.click(await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }));
    const dialog = within(await screen.findByRole("dialog"));
    await user.type(dialog.getByRole("textbox"), "weil");
    await user.click(dialog.getByRole("button", { name: "Übergehen" }));

    expect(await screen.findAllByText("Schon bezahlt.")).not.toHaveLength(0);
  });

  it("closes the override dialog on Abbrechen", async () => {
    const { user } = openFreigabe();

    await user.click(await screen.findByRole("button", { name: "Ohne Unterschrift freigeben" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("offers an override only with the treasurer's permission", async () => {
    useMe({ permissions: [] });
    server.use(
      http.get(api("/api/finance/statements/1"), () => HttpResponse.json(statement())),
      http.get(api("/api/finance/statements/1/transactions"), () => HttpResponse.json([])),
      http.get(api("/api/finance/statements/1/approval"), () => HttpResponse.json(approval())),
    );
    renderRoute(REVIEW);

    await screen.findByText("Offen");
    expect(
      screen.queryByRole("button", { name: "Ohne Unterschrift freigeben" }),
    ).not.toBeInTheDocument();
  });
});
