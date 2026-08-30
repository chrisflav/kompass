import { screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { api, djangoValidation, http, HttpResponse, server, useMe } from "../../test/server";
import {
  fillEveryField,
  pickEverySelect,
  renderRoute,
  sortByEveryColumn,
} from "../../test/utils";
import { dateBucket } from "./Klettertreff";

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);

const GROUPS = [
  { id: 5, name: "Klettergruppe" },
  { id: 6, name: "Bouldergruppe" },
];

const MEMBERS = [
  { id: 42, name: "Anna Ärmel" },
  { id: 43, name: "Mila Nowak" },
];

/** An ISO date `days` before today, so the date-bucket filters are testable. */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(
    d.getDate(),
  ).padStart(2, "0")}`;
}

const TODAY = isoDaysAgo(0);

// The list carries leader names as plain strings; the detail carries objects.
const KT_BRIEF = {
  id: 9,
  group: { id: 5, name: "Klettergruppe" },
  date: TODAY,
  location: "Kletterhalle",
  topic: "Vorstieg",
  jugendleiter: ["Anna Ärmel"],
};

const KT = {
  ...KT_BRIEF,
  jugendleiter: [{ id: 42, name: "Anna Ärmel" }],
  attendees: [],
  jugendleiter_ids: [42],
};

function listReturns(rows: unknown[] = [KT_BRIEF]) {
  server.use(
    http.get(api("/api/members/klettertreff"), () => HttpResponse.json(rows)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
  );
}

function detailReturns(overrides: Record<string, unknown> = {}) {
  server.use(
    http.get(api("/api/members/klettertreff/9"), () => HttpResponse.json({ ...KT, ...overrides })),
    http.get(api("/api/members/klettertreff/9/attendees"), () => HttpResponse.json([])),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    http.get(api("/api/members/"), () => HttpResponse.json(MEMBERS)),
  );
}

describe("activities — Klettertreff list", () => {
  it("lists the dates with group, place, topic and leaders", async () => {
    listReturns();
    renderRoute("/app/klettertreff");
    expect(await screen.findByText("Kletterhalle")).toBeInTheDocument();
    expect(screen.getByText("Vorstieg")).toBeInTheDocument();
    expect(screen.getByText("Klettergruppe")).toBeInTheDocument();
    expect(screen.getByText("Anna Ärmel")).toBeInTheDocument();
  });

  it("says so when there are none", async () => {
    listReturns([]);
    renderRoute("/app/klettertreff");
    expect(await screen.findByText("Keine Klettertreff-Termine sichtbar.")).toBeInTheDocument();
  });

  it("shows an em dash for missing place, topic and leaders", async () => {
    listReturns([{ ...KT_BRIEF, location: "", topic: "", jugendleiter: [], date: null }]);
    renderRoute("/app/klettertreff");
    await screen.findByText("Klettergruppe");
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("searches over date, place, topic and group", async () => {
    listReturns([KT_BRIEF, { ...KT_BRIEF, id: 10, location: "Fels", topic: "Sichern" }]);
    const { user } = renderRoute("/app/klettertreff");
    await screen.findByText("Kletterhalle");

    await user.type(screen.getByPlaceholderText("Suchen…"), "fels");
    await waitFor(() => expect(screen.queryByText("Kletterhalle")).not.toBeInTheDocument());
    expect(screen.getByText("Fels")).toBeInTheDocument();
  });

  it("filters by group and by each date bucket", async () => {
    listReturns([
      KT_BRIEF,
      { ...KT_BRIEF, id: 10, group: { id: 6, name: "Bouldergruppe" }, date: isoDaysAgo(3) },
      { ...KT_BRIEF, id: 11, date: isoDaysAgo(200), location: "Alt" },
      { ...KT_BRIEF, id: 12, date: null, location: "Datumslos" },
      { ...KT_BRIEF, id: 13, date: "irgendwann", location: "Kaputt" },
    ]);
    const { user } = renderRoute("/app/klettertreff");
    await screen.findAllByText("Kletterhalle");

    const pickDate = async (label: string) => {
      await user.click(screen.getByRole("button", { name: /Datum:/ }));
      await user.click(dropdown().getByRole("button", { name: label }));
    };

    await pickDate("Heute");
    await waitFor(() => expect(screen.getByText("1 / 5")).toBeInTheDocument());

    await pickDate("Letzte 7 Tage");
    await waitFor(() => expect(screen.getByText("2 / 5")).toBeInTheDocument());

    await pickDate("Ohne Datum");
    // A date that cannot be parsed is not "without a date"; only the null one is.
    await waitFor(() => expect(screen.getByText("1 / 5")).toBeInTheDocument());
    expect(screen.getByText("Datumslos")).toBeInTheDocument();

    await pickDate("Dieses Jahr");
    await waitFor(() => expect(screen.queryByText("Datumslos")).not.toBeInTheDocument());

    await pickDate("Dieser Monat");
    await waitFor(() => expect(screen.getAllByText("Kletterhalle").length).toBeGreaterThan(0));

    await user.click(screen.getByRole("button", { name: "Filter zurücksetzen" }));
    await user.click(await screen.findByRole("button", { name: /Gruppe:/ }));
    await user.click(dropdown().getByRole("button", { name: "Bouldergruppe" }));
    await waitFor(() => expect(screen.getByText("1 / 5")).toBeInTheDocument());
  });

  it("sorts by every column in both directions", async () => {
    listReturns([KT_BRIEF, { ...KT_BRIEF, id: 10, location: "", topic: "", date: null }]);
    const { user } = renderRoute("/app/klettertreff");
    await screen.findByText("Kletterhalle");
    await sortByEveryColumn(user);
    expect(screen.getAllByRole("row")).toHaveLength(3);
  });

  it("hides the create button without the permission", async () => {
    useMe({ permissions: [] });
    listReturns();
    renderRoute("/app/klettertreff");
    await screen.findByText("Kletterhalle");
    expect(screen.queryByRole("button", { name: "Neuer Klettertreff" })).not.toBeInTheDocument();
  });

  it("creates a date, requiring a group and sending an empty date as null", async () => {
    useMe({ permissions: ["members.add_klettertreff"] });
    listReturns();
    let body: unknown = null;
    server.use(
      http.post(api("/api/members/klettertreff"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(KT);
      }),
    );
    detailReturns();
    const { user } = renderRoute("/app/klettertreff");
    await user.click(await screen.findByRole("button", { name: "Neuer Klettertreff" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Anlegen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: "Gruppe" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.type(dialog.getByLabelText("Ort"), "Kletterhalle");
    await user.type(dialog.getByLabelText("Thema"), "Vorstieg");
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    await waitFor(() =>
      expect(body).toEqual({
        group_id: 5,
        date: null,
        location: "Kletterhalle",
        topic: "Vorstieg",
        jugendleiter_ids: [],
      }),
    );
    expect(await screen.findByText("Klettertreff angelegt.")).toBeInTheDocument();
  });

  it("fills every field of the create form", async () => {
    useMe({ permissions: ["members.add_klettertreff"] });
    listReturns();
    let body: Record<string, unknown> | null = null;
    server.use(
      http.post(api("/api/members/klettertreff"), async ({ request }) => {
        body = (await request.json()) as Record<string, unknown>;
        return djangoValidation({ topic: ["Stop."] });
      }),
    );
    const { user } = renderRoute("/app/klettertreff");
    await user.click(await screen.findByRole("button", { name: "Neuer Klettertreff" }));

    const dialog = await screen.findByRole("dialog");
    await fillEveryField(user, dialog);
    await pickEverySelect(user, dialog);
    await user.click(within(dialog).getByRole("button", { name: "Anlegen" }));

    await waitFor(() => expect(body).not.toBeNull());
    expect(body).toMatchObject({
      group_id: 5,
      date: "2026-03-04",
      location: "Text",
      topic: "Text",
    });
  });

  it("shows every server field error on the create form", async () => {
    useMe({ permissions: ["members.add_klettertreff"] });
    listReturns();
    server.use(
      http.post(api("/api/members/klettertreff"), () =>
        djangoValidation({
          group_id: ["Unbekannte Gruppe."],
          date: ["Ungültiges Datum."],
          location: ["Zu lang."],
          topic: ["Zu lang."],
        }),
      ),
    );
    const { user } = renderRoute("/app/klettertreff");
    await user.click(await screen.findByRole("button", { name: "Neuer Klettertreff" }));

    const dialog = within(screen.getByRole("dialog"));
    await user.click(dialog.getByRole("button", { name: "Gruppe" }));
    await user.click(dropdown().getByRole("button", { name: "Klettergruppe" }));
    await user.click(dialog.getByRole("button", { name: "Anlegen" }));

    expect(await screen.findAllByText("Unbekannte Gruppe.")).not.toHaveLength(0);
    expect(screen.getByText("Ungültiges Datum.")).toBeInTheDocument();
    expect(screen.getAllByText("Zu lang.")).toHaveLength(2);

    await user.click(dialog.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });
});

describe("activities — Klettertreff detail", () => {
  it("shows the date and its leaders", async () => {
    detailReturns();
    renderRoute("/app/klettertreff/9");
    expect(await screen.findByText("Kletterhalle")).toBeInTheDocument();
    expect(screen.getByText("Anna Ärmel")).toBeInTheDocument();
  });

  it("shows an em dash for missing place, topic and leaders", async () => {
    detailReturns({ location: "", topic: "", jugendleiter: [], jugendleiter_ids: [] });
    renderRoute("/app/klettertreff/9");
    await screen.findByRole("button", { name: "Bearbeiten" });
    expect(screen.getAllByText("—").length).toBeGreaterThanOrEqual(3);
  });

  it("saves an inline edit with the group and leaders as ids", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/klettertreff/9"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(KT);
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const topic = screen.getByDisplayValue("Vorstieg");
    await user.clear(topic);
    await user.type(topic, "Nachstieg");
    await user.click(screen.getByRole("button", { name: /Klettergruppe/ }));
    await user.click(dropdown().getByRole("button", { name: "Bouldergruppe" }));
    await user.click(screen.getByRole("button", { name: "+ Auswählen…" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      topic: "Nachstieg",
      group_id: 6,
      jugendleiter_ids: [42, 43],
    });
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });

  it("reports a rejected save and leaves edit mode on Abbrechen", async () => {
    detailReturns();
    server.use(
      http.patch(api("/api/members/klettertreff/9"), () =>
        djangoValidation({ topic: ["Das Thema fehlt."] }),
      ),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findAllByText("Das Thema fehlt.")).not.toHaveLength(0);

    await user.click(screen.getByRole("button", { name: "Abbrechen" }));
    expect(screen.queryByDisplayValue("Vorstieg")).not.toBeInTheDocument();
  });

  it("stages an attendee and creates it on save", async () => {
    detailReturns();
    let created: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/klettertreff/9"), () => HttpResponse.json(KT)),
      http.post(api("/api/members/klettertreff/9/attendees"), async ({ request }) => {
        created = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 30 });
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));

    const dialog = within(await screen.findByRole("dialog"));
    expect(dialog.getByRole("button", { name: "Hinzufügen" })).toBeDisabled();
    await user.click(dialog.getByRole("button", { name: "Teilnehmende" }));
    await user.click(dropdown().getByRole("button", { name: "Mila Nowak" }));
    await user.click(dialog.getByRole("button", { name: "Hinzufügen" }));

    expect(created).toBeNull();
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(created).toMatchObject({ member_id: 43 }));
  });

  it("removes an attendee on save", async () => {
    detailReturns();
    let deleted = false;
    server.use(
      http.get(api("/api/members/klettertreff/9/attendees"), () =>
        HttpResponse.json([{ id: 30, member: { id: 43, name: "Mila Nowak" } }]),
      ),
      http.patch(api("/api/members/klettertreff/9"), () => HttpResponse.json(KT)),
      http.delete(api("/api/members/attendees/30"), () => {
        deleted = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));

    expect(await screen.findByText("Mila Nowak")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Entfernen" }));
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("closes the attendee dialog on Abbrechen", async () => {
    detailReturns();
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Abbrechen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("deletes a date once confirmed, and reports a refusal", async () => {
    useMe({ permissions: ["members.delete_klettertreff", "members.change_klettertreff"] });
    detailReturns();
    let attempt = 0;
    server.use(
      http.get(api("/api/members/klettertreff"), () => HttpResponse.json([])),
      http.delete(api("/api/members/klettertreff/9"), () => {
        attempt += 1;
        if (attempt === 1) {
          return HttpResponse.json({ detail: "members.delete_klettertreff" }, { status: 403 });
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");

    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Dazu fehlt dir die Berechtigung.")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Löschen" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Löschen" }),
    );
    expect(await screen.findByText("Klettertreff gelöscht.")).toBeInTheDocument();
  });

  it("hides the delete button without the permission", async () => {
    useMe({ permissions: [] });
    detailReturns();
    renderRoute("/app/klettertreff/9");
    await screen.findByText("Kletterhalle");
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("goes back through the browser history", async () => {
    detailReturns();
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Zurück" }));
    expect(screen.getByRole("button", { name: "Zurück" })).toBeInTheDocument();
  });
});

describe("dateBucket", () => {
  const iso = (days: number) => {
    const d = new Date();
    d.setDate(d.getDate() - days);
    return d.toISOString();
  };

  it("matches only rows without a date for 'none'", () => {
    expect(dateBucket(null, "none")).toBe(true);
    expect(dateBucket("", "none")).toBe(true);
    expect(dateBucket(iso(0), "none")).toBe(false);
  });

  it("rejects a missing or unparseable date for every dated bucket", () => {
    expect(dateBucket(null, "today")).toBe(false);
    expect(dateBucket("irgendwann", "today")).toBe(false);
  });

  it("matches today, the last seven days, the month and the year", () => {
    expect(dateBucket(iso(0), "today")).toBe(true);
    expect(dateBucket(iso(3), "today")).toBe(false);
    expect(dateBucket(iso(3), "7days")).toBe(true);
    expect(dateBucket(iso(30), "7days")).toBe(false);
    // A future date is not "the last seven days".
    expect(dateBucket(iso(-2), "7days")).toBe(false);
    expect(dateBucket(iso(0), "month")).toBe(true);
    expect(dateBucket(iso(0), "year")).toBe(true);
    expect(dateBucket("2000-01-01", "year")).toBe(false);
  });

  it("keeps every row for a bucket it does not know", () => {
    expect(dateBucket(iso(0), "quatsch")).toBe(true);
  });
});

describe("activities — Klettertreff: remaining paths", () => {
  it("opens a date from its row and closes the create modal with ×", async () => {
    useMe({ permissions: ["members.add_klettertreff"] });
    listReturns();
    detailReturns();
    const { user } = renderRoute("/app/klettertreff");

    await user.click(await screen.findByRole("button", { name: "Neuer Klettertreff" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("Kletterhalle"));
    expect(await screen.findByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
  });

  it("names a date by its group when it has no topic", async () => {
    useMe({ permissions: ["members.delete_klettertreff"] });
    detailReturns({ topic: "" });
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Löschen" }));
    expect(
      within(await screen.findByRole("dialog")).getByText(/„Klettergruppe“ wirklich löschen\?/),
    ).toBeInTheDocument();
  });

  it("copes with an API that sends null for every optional field", async () => {
    detailReturns({ date: null, location: null, topic: null, jugendleiter: [] });
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    expect(screen.getAllByDisplayValue("").length).toBeGreaterThan(0);
  });

  it("sends an empty date as null when saving", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/klettertreff/9"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(KT);
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue(TODAY));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toMatchObject({ date: null }));
  });

  it("closes the attendee dialog with ×", async () => {
    detailReturns();
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));
    await user.click(screen.getByRole("tab", { name: /Teilnehmer/ }));
    await user.click(await screen.findByRole("button", { name: "+ Teilnehmende" }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Schließen" }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
  });

  it("says so when there are no attendees, and shows an em dash for a nameless one", async () => {
    detailReturns();
    server.use(
      http.get(api("/api/members/klettertreff/9/attendees"), () =>
        HttpResponse.json([{ id: 30, member: { id: 43, name: "" } }]),
      ),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("tab", { name: /Teilnehmer/ }));
    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await waitFor(() => expect(panel.textContent).toContain("—"));
  });
});

describe("activities — Klettertreff: every field", () => {
  it("carries every edited field into the PATCH", async () => {
    detailReturns();
    let patched: Record<string, unknown> | null = null;
    server.use(
      http.patch(api("/api/members/klettertreff/9"), async ({ request }) => {
        patched = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(KT);
      }),
    );
    const { user } = renderRoute("/app/klettertreff/9");
    await user.click(await screen.findByRole("button", { name: "Bearbeiten" }));

    const panel = document.querySelector(".tab-panel:not([hidden])") as HTMLElement;
    await fillEveryField(user, panel);
    await pickEverySelect(user, panel);
    await user.click(screen.getByRole("button", { name: "Speichern" }));

    await waitFor(() => expect(patched).not.toBeNull());
    expect(patched).toMatchObject({
      date: "2026-03-04",
      location: "Text",
      topic: "Text",
      group_id: 5,
    });
  });
});
