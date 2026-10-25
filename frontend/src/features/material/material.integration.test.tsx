import { focusManager } from "@tanstack/react-query";
import { act, screen, waitFor, within } from "@testing-library/react";
import { delay } from "msw";
import { beforeEach, describe, expect, it } from "vitest";

import {
  api,
  djangoValidation,
  http,
  HttpResponse,
  multipartFields,
  server,
  useMe,
} from "../../test/server";
import { currentUrl, renderRoute } from "../../test/utils";
import { cartStorageKey } from "./cart";
import { addDays, isoToday, shortDate } from "./shared";

const TODAY = isoToday();
const TOMORROW = addDays(TODAY, 1);

const dropdown = () => within(document.querySelector(".ms-dropdown") as HTMLElement);
const dialog = async () => within(await screen.findByRole("dialog"));

const TAGS = [
  { id: 1, name: "Hochtour" },
  { id: 2, name: "Höhle" },
];
const GROUPS = [{ id: 5, name: "Jugend", leiters: [] as { id: number; name: string }[] }];
/** The groups owning material; Jugend, a group the user leads, owns none. */
const OWNER_GROUPS = [{ id: 6, name: "Hochtour" }];
const MEMBERS = [
  { id: 7, name: "Hannah Beckers" },
  { id: 8, name: "Peter Lustig" },
];
const LOCATIONS = [{ id: 3, name: "Griffwerk", address: "", opening_hours: "Di 18–20" }];

const ref = (id: number, name: string) => ({ id, name });

function part(id: number, overrides: Record<string, unknown> = {}) {
  return {
    id,
    label: `S${id}`,
    product_type: ref(10, "Bandschlinge 120 cm"),
    psa_id: null,
    serial_number: "",
    group: null,
    holder: null,
    location: ref(3, "Griffwerk"),
    status: "active",
    lent_until: null,
    ...overrides,
  };
}

const CARD = {
  id: 10,
  name: "Bandschlinge 120 cm",
  manufacturer: "Edelrid",
  product_group: "Schlingen",
  is_psa: true,
  photo: null,
  tags: [TAGS[0]],
  total: 4,
  available: 3,
  available_direct: 2,
  groups: [
    { id: null, name: "", available: 2, needs_approval: false },
    { id: 5, name: "Jugend", available: 1, needs_approval: true },
  ],
  sizes: [],
  sets: null,
  set_entries: [] as unknown[],
};

const size = (id: number, name: string, overrides: Record<string, unknown> = {}) => ({
  id,
  name,
  product_type: ref(11, "Friends"),
  quantity: 2,
  per_set: 1,
  group: null,
  location: null,
  position: id,
  available: 2,
  ...overrides,
});

const FRIENDS = {
  ...CARD,
  id: 11,
  name: "Friends",
  manufacturer: "Black Diamond",
  is_psa: false,
  tags: [],
  total: 6,
  available: 5,
  available_direct: 5,
  groups: [],
  sizes: [size(1, "1"), size(2, "2", { quantity: 4, per_set: 2, available: 3 })],
  sets: 1,
};

const setEntry = (id: number, typeId: number, name: string, perSet: number, available: number) => ({
  id,
  product_type: ref(typeId, name),
  per_set: perSet,
  position: id,
  available,
});

/** A set of types whose pieces have IDs: one CAM 0.5 and two CAM 1. */
const CAM_SET = {
  ...CARD,
  id: 12,
  name: "Totem Satz",
  manufacturer: "Totem",
  is_psa: false,
  tags: [],
  total: 2,
  available: 1,
  available_direct: 1,
  groups: [],
  sets: 1,
  set_entries: [setEntry(1, 13, "CAM 0.5", 1, 1), setEntry(2, 14, "CAM 1", 2, 3)],
};

const TYPE = {
  ...CARD,
  description: "Genähte Schlinge",
  article_number: "A-1",
  manual: "/media/material/manuals/schlinge.pdf",
  usage_years: 10,
  inspection_interval_days: 365,
  daily_rate: "1.50",
  calendar: [
    { start: TOMORROW, end: TOMORROW, status: "confirmed", count: 2, borrower: ref(8, "Peter Lustig") },
  ],
  parts: [part(1), part(2, { holder: ref(8, "Peter Lustig"), location: null, lent_until: TOMORROW })],
  in_sets: [] as unknown[],
};

/** The detail of ``CAM_SET``: a set has no pieces or sizes of its own. */
const SET_TYPE = { ...TYPE, ...CAM_SET, calendar: [], parts: [], retired_parts: [] };

function partOut(overrides: Record<string, unknown> = {}) {
  return {
    ...part(1),
    psa_id: "E1351",
    label: "E1351",
    note: "",
    photo: null,
    manufactured_on: "2024-01-01",
    buy_date: null,
    home_location: ref(3, "Griffwerk"),
    parent: null,
    components: [],
    retired_on: null,
    next_inspection: "2020-01-01",
    past_usage_period: true,
    inspections: [
      { id: 1, date: "2025-01-01", result: "ok", inspector: ref(7, "Hannah Beckers"), comment: "", photo: null },
    ],
    custody: [
      { id: 1, kind: "transfer", at: "2025-01-01T10:00:00Z", from_name: null, to_name: "Griffwerk", by: null },
    ],
    history: { loans: 0, reservations: 0, inspections: 1, handovers: 0 },
    reservations: [{ id: 4, start: TOMORROW, end: TOMORROW, status: "confirmed", borrower: ref(8, "Peter Lustig") }],
    ...overrides,
  };
}

function reservation(overrides: Record<string, unknown> = {}) {
  return {
    id: 20,
    borrower: ref(7, "Hannah Beckers"),
    start: TODAY,
    end: TOMORROW,
    status: "confirmed",
    note: "Kurs",
    created_at: "2026-01-01T10:00:00Z",
    lines: [{ product_type: ref(10, "Bandschlinge 120 cm"), count: 2 }],
    parts: [part(1), part(2)],
    sizes: [],
    approvals: [],
    decidable_groups: [],
    ...overrides,
  };
}

/** An answer of the cart's availability check. */
const checked = (overrides: Record<string, unknown> = {}) =>
  HttpResponse.json({ ok: true, problems: [], parts: [], sizes: [], approval_groups: [], ...overrides });

/** The cart of the default test user (user 2). */
const CART_KEY = cartStorageKey(2);

beforeEach(() => {
  localStorage.removeItem(CART_KEY);
  server.use(
    http.get(api("/api/material/categories"), () => HttpResponse.json(TAGS)),
    http.get(api("/api/material/groups"), () => HttpResponse.json(OWNER_GROUPS)),
    http.get(api("/api/members/groups"), () => HttpResponse.json(GROUPS)),
    // Hand-overs pick from everyone, not only the members one may see.
    http.get(api("/api/material/recipients"), () => HttpResponse.json(MEMBERS)),
    http.get(api("/api/material/locations"), () => HttpResponse.json(LOCATIONS)),
    http.get(api("/api/material/types"), () => HttpResponse.json([CARD])),
    http.get(api("/api/material/types/10"), () => HttpResponse.json(TYPE)),
    http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut())),
    http.get(api("/api/material/parts/match"), () => HttpResponse.json([])),
    http.get(api("/api/material/reservations"), () => HttpResponse.json([])),
  );
});

/* --- catalogue and cart ----------------------------------------------------- */

describe("material — Materialbrowser", () => {
  it("shows what there is and how much is free", async () => {
    renderRoute("/kompass/material");
    expect(await screen.findByText("Bandschlinge 120 cm")).toBeInTheDocument();
    expect(screen.getByText("3 / 4 frei")).toBeInTheDocument();
    expect(screen.getByText("1 mit Freigabe")).toBeInTheDocument();
    expect(screen.getByText("PSA")).toBeInTheDocument();
  });

  it("asks the server with the search and the period", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get(api("/api/material/types"), ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json([]);
      }),
    );
    const { user } = renderRoute("/kompass/material");
    expect(await screen.findByText("Kein Material gefunden.")).toBeInTheDocument();
    await user.type(screen.getByLabelText("Material suchen"), "seil");
    await waitFor(() => expect(seen[seen.length - 1]?.get("q")).toBe("seil"));
    expect(seen[seen.length - 1]?.get("start")).toBe(TODAY);
  });

  it("filters by the groups that own material, and only by those", async () => {
    const seen: URLSearchParams[] = [];
    server.use(
      http.get(api("/api/material/types"), ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json([CARD]);
      }),
    );
    const { user } = renderRoute("/kompass/material");
    await screen.findByText("Bandschlinge 120 cm");
    await user.click(await screen.findByRole("button", { name: /^Gruppe:/ }));
    expect(screen.queryByRole("button", { name: "Jugend" })).toBeNull();
    await user.click(await screen.findByRole("button", { name: "Hochtour" }));
    await waitFor(() => expect(seen[seen.length - 1]?.get("group")).toBe("6"));
  });

  it("drops a chosen group that no longer owns material", async () => {
    let owners = OWNER_GROUPS;
    const seen: URLSearchParams[] = [];
    server.use(
      http.get(api("/api/material/groups"), () => HttpResponse.json(owners)),
      http.get(api("/api/material/types"), ({ request }) => {
        seen.push(new URL(request.url).searchParams);
        return HttpResponse.json([CARD]);
      }),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: /^Gruppe:/ }));
    await user.click(await screen.findByRole("button", { name: "Hochtour" }));
    await waitFor(() => expect(seen[seen.length - 1]?.get("group")).toBe("6"));

    // Hochtour's last piece is retired; the list is fetched again on focus.
    owners = [];
    act(() => {
      focusManager.setFocused(false);
      focusManager.setFocused(true);
    });
    await waitFor(() => expect(seen[seen.length - 1]?.get("group")).toBeNull());
    expect(screen.queryByRole("button", { name: /^Gruppe:/ })).toBeNull();
  });

  it("offers no group filter when no group owns material", async () => {
    let asked = false;
    server.use(
      http.get(api("/api/material/groups"), () => {
        asked = true;
        return HttpResponse.json([]);
      }),
    );
    renderRoute("/kompass/material");
    await screen.findByText("Bandschlinge 120 cm");
    await waitFor(() => expect(asked).toBe(true));
    // Let the empty answer render before looking for the filter.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.getByRole("button", { name: /^Tag:/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Gruppe:/ })).toBeNull();
  });

  it("reserves what is in the cart and goes to my material", async () => {
    let body: unknown = null;
    server.use(
      http.post(api("/api/material/reservations/check"), () =>
        HttpResponse.json({
          ok: false,
          problems: ["Nur 3 × Bandschlinge sind frei."],
          parts: [],
          approval_groups: [ref(5, "Jugend")],
        }),
      ),
      http.post(api("/api/material/reservations"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(reservation());
      }),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Bandschlinge 120 cm in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    await user.tripleClick(cart.getByLabelText("Anzahl Bandschlinge 120 cm"));
    await user.keyboard("5");
    // Whether it is free is checked on its own once the cart settles.
    expect(await cart.findByText("Nur 3 × Bandschlinge sind frei.")).toBeInTheDocument();
    expect(cart.getByText("Braucht die Freigabe von Jugend.")).toBeInTheDocument();

    await user.type(cart.getByPlaceholderText("z. B. Ausfahrt"), "Hochtour");
    await user.click(cart.getByRole("button", { name: "Reservieren" }));
    await waitFor(() =>
      expect(body).toEqual({
        start: TODAY,
        end: TOMORROW,
        note: "Hochtour",
        lines: [{ product_type: 10, quantity: 5 }],
      }),
    );
    expect(await screen.findByText("Reserviert.")).toBeInTheDocument();
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/mine"));
  });

  it("does not offer to take material along that needs another group's approval", async () => {
    server.use(
      http.post(api("/api/material/reservations/check"), () => checked({ approval_groups: [ref(5, "Jugend")] })),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Bandschlinge 120 cm in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    expect(await cart.findByText("Alles frei")).toBeInTheDocument();
    expect(cart.getByText("Braucht die Freigabe von Jugend.")).toBeInTheDocument();
    // It is reserved and approved first, then picked up.
    expect(cart.getByRole("button", { name: "Jetzt mitnehmen" })).toBeDisabled();
    expect(cart.getByText(/erst nach der Freigabe mit/)).toBeInTheDocument();
    expect(cart.getByRole("button", { name: "Reservieren" })).toBeEnabled();
  });

  it("says so when the check fails, rather than checking for ever", async () => {
    localStorage.setItem(
      CART_KEY,
      JSON.stringify({
        start: TODAY,
        end: TOMORROW,
        lines: [{ key: "s99", quantity: 1, size: { id: 99, name: "9", typeName: "Friends" } }],
      }),
    );
    server.use(
      http.post(api("/api/material/reservations/check"), () =>
        HttpResponse.json({ detail: "Not Found" }, { status: 404 }),
      ),
    );
    renderRoute("/kompass/material");
    const cart = within(await screen.findByRole("complementary", { name: "Korb" }));
    expect(await cart.findByText(/Etwas im Korb gibt es nicht mehr/)).toBeInTheDocument();
    expect(cart.queryByText("Prüft, ob alles frei ist…")).not.toBeInTheDocument();
  });

  it("shows the check of the cart as it is, not a slower one of before", async () => {
    const sent: number[] = [];
    server.use(
      http.post(api("/api/material/reservations/check"), async ({ request }) => {
        const { lines } = (await request.json()) as { lines: { quantity: number }[] };
        sent.push(lines[0].quantity);
        if (lines[0].quantity === 1) {
          await delay(1200);
          return checked({ ok: false, problems: ["Nur 0 × Bandschlinge sind frei."] });
        }
        return checked();
      }),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Bandschlinge 120 cm in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    await waitFor(() => expect(sent).toEqual([1]));
    await user.tripleClick(cart.getByLabelText("Anzahl Bandschlinge 120 cm"));
    await user.keyboard("2");
    expect(await cart.findByText("Alles frei")).toBeInTheDocument();
    // The answer for one piece comes in late, and is dropped.
    await new Promise((resolve) => setTimeout(resolve, 1200));
    expect(cart.queryByText("Nur 0 × Bandschlinge sind frei.")).not.toBeInTheDocument();
    expect(cart.getByText("Alles frei")).toBeInTheDocument();
  });

  it("starts a stored cart whose period has passed again from today, and keeps it per user", async () => {
    localStorage.setItem(
      CART_KEY,
      JSON.stringify({
        start: "2020-01-01",
        end: "2020-01-03",
        // An older cart kept the whole type.
        lines: [{ key: "t10", quantity: 2, productType: TYPE }],
      }),
    );
    localStorage.setItem(
      cartStorageKey(3),
      JSON.stringify({
        start: TODAY,
        end: TOMORROW,
        lines: [{ key: "p9", quantity: 1, part: { id: 9, label: "S9", typeName: "Seil" } }],
      }),
    );
    renderRoute("/kompass/material");
    const cart = within(await screen.findByRole("complementary", { name: "Korb" }));
    expect(await cart.findByLabelText("Anzahl Bandschlinge 120 cm")).toHaveValue(2);
    expect(cart.getByLabelText("Von")).toHaveValue(TODAY);
    expect(cart.getByLabelText("Bis")).toHaveValue(TOMORROW);
    // Another user's cart stays theirs.
    expect(cart.queryByText("S9")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(CART_KEY)!)).toEqual({
        start: TODAY,
        end: TOMORROW,
        lines: [{ key: "t10", quantity: 2, productType: { id: 10, name: "Bandschlinge 120 cm" } }],
      }),
    );
  });

  it("counts days in local dates", () => {
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
    expect(addDays("2026-03-29", 1)).toBe("2026-03-30");
    expect(addDays("2026-03-01", -1)).toBe("2026-02-28");
  });

  it("opens a piece when its ID is searched for", async () => {
    server.use(
      http.get(api("/api/material/parts/lookup"), ({ request }) =>
        new URL(request.url).searchParams.get("code") === "E1351"
          ? HttpResponse.json(partOut())
          : HttpResponse.json({ detail: ["Zu dieser ID gibt es kein Material."] }, { status: 422 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    const search = await screen.findByLabelText("Material suchen");
    await user.type(search, "nope{Enter}");
    // Not an ID: the search just filters, and no error gets in the way.
    expect(currentUrl()).toBe("/kompass/material");
    await user.clear(search);
    await user.type(search, "E1351{Enter}");
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/parts/1"));
  });

  it("offers the piece whose PSA ID is searched for (Feedback #33)", async () => {
    const codes: (string | null)[] = [];
    server.use(
      http.get(api("/api/material/parts/match"), ({ request }) => {
        const code = new URL(request.url).searchParams.get("code");
        codes.push(code);
        return HttpResponse.json(
          code?.toLowerCase() === "e1351" ? [part(1, { psa_id: "E1351", label: "E1351" })] : [],
        );
      }),
    );
    const { user } = renderRoute("/kompass/material");
    const search = await screen.findByLabelText("Material suchen");
    // Nothing is asked before there is a search.
    await screen.findByText("Bandschlinge 120 cm");
    expect(codes).toEqual([]);
    await user.type(search, "e135");
    await waitFor(() => expect(codes[codes.length - 1]).toBe("e135"));
    expect(screen.queryByRole("link", { name: /^Teil/ })).toBeNull();
    await user.type(search, "1");
    const hit = await screen.findByRole("link", { name: "Teil E1351 – Bandschlinge 120 cm" });
    await user.click(hit);
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/parts/1"));
  });

  it("puts a whole set of a type kept by size in the cart", async () => {
    server.use(http.get(api("/api/material/types"), () => HttpResponse.json([CARD, FRIENDS])));
    const { user } = renderRoute("/kompass/material");
    expect(await screen.findByText("1 Satz frei")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Satz Friends in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    expect(cart.getByLabelText("Anzahl Friends 1")).toHaveValue(1);
    expect(cart.getByLabelText("Anzahl Friends 2")).toHaveValue(2);
  });

  it("puts a set of types in the cart as its pieces and reserves them", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/types"), () => HttpResponse.json([CARD, CAM_SET])),
      http.post(api("/api/material/reservations/check"), () => checked()),
      http.post(api("/api/material/reservations"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(reservation());
      }),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    expect(await screen.findByText("1 Satz frei")).toBeInTheDocument();
    expect(screen.getByText("2 Sätze aus 2 Typen")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Satz Totem Satz in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    // The pieces are gathered under the set's name, each a line of its own type.
    expect(cart.getByText("Totem Satz")).toBeInTheDocument();
    expect(cart.getByLabelText("Anzahl CAM 0.5")).toHaveValue(1);
    expect(cart.getByLabelText("Anzahl CAM 1")).toHaveValue(2);
    expect(await cart.findByText("Alles frei")).toBeInTheDocument();
    await user.click(cart.getByRole("button", { name: "Reservieren" }));
    await waitFor(() =>
      expect(body).toEqual({
        start: TODAY,
        end: TOMORROW,
        note: "",
        lines: [
          { product_type: 13, quantity: 1 },
          { product_type: 14, quantity: 2 },
        ],
      }),
    );
  });

  it("keeps the set's name of a stored cart line", async () => {
    localStorage.setItem(
      CART_KEY,
      JSON.stringify({
        start: TODAY,
        end: TOMORROW,
        lines: [
          { key: "t13", quantity: 1, productType: ref(13, "CAM 0.5"), set: { name: "Totem Satz", perSet: 1 } },
          { key: "t10", quantity: 1, productType: ref(10, "Bandschlinge 120 cm") },
          { key: "t14", quantity: 2, productType: ref(14, "CAM 1"), set: { name: "Totem Satz", perSet: 2 } },
        ],
      }),
    );
    server.use(http.post(api("/api/material/reservations/check"), () => checked()));
    const { user } = renderRoute("/kompass/material");
    const cart = within(await screen.findByRole("complementary", { name: "Korb" }));
    // The lines of one set stay together under its name, wherever they are in the cart.
    expect(await cart.findAllByText("Totem Satz")).toHaveLength(1);
    const group = within(cart.getByText("Totem Satz").closest("li") as HTMLElement);
    expect(group.getByLabelText("Anzahl CAM 0.5")).toHaveValue(1);
    expect(group.getByLabelText("Anzahl CAM 1")).toHaveValue(2);
    expect(group.queryByLabelText("Anzahl Bandschlinge 120 cm")).not.toBeInTheDocument();
    await user.click(cart.getByRole("button", { name: "Satz Totem Satz entfernen" }));
    expect(cart.queryByLabelText("Anzahl CAM 1")).not.toBeInTheDocument();
    expect(cart.getByLabelText("Anzahl Bandschlinge 120 cm")).toHaveValue(1);
  });

  it("adds a set onto pieces already in the cart, and takes only the set out again", async () => {
    localStorage.setItem(
      CART_KEY,
      JSON.stringify({
        start: TODAY,
        end: TOMORROW,
        lines: [{ key: "t13", quantity: 1, productType: ref(13, "CAM 0.5") }],
      }),
    );
    server.use(
      http.get(api("/api/material/types"), () => HttpResponse.json([CAM_SET])),
      http.post(api("/api/material/reservations/check"), () => checked()),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Satz Totem Satz in den Korb" }));
    await user.click(screen.getByRole("button", { name: "Satz Totem Satz in den Korb" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    // The cam already there is not the set's alone: it shows on its own.
    const group = within(cart.getByText("Totem Satz").closest("li") as HTMLElement);
    expect(group.queryByLabelText("Anzahl CAM 0.5")).not.toBeInTheDocument();
    expect(cart.getByLabelText("Anzahl CAM 0.5")).toHaveValue(3);
    expect(group.getByLabelText("Anzahl CAM 1")).toHaveValue(4);
    await user.click(cart.getByRole("button", { name: "Satz Totem Satz entfernen" }));
    expect(cart.getByLabelText("Anzahl CAM 1")).toHaveValue(2);
    expect(cart.getByLabelText("Anzahl CAM 0.5")).toHaveValue(3);
  });

  it("says how many sets need another group's approval", async () => {
    server.use(
      http.get(api("/api/material/types"), () =>
        HttpResponse.json([{ ...CAM_SET, sets: 2, available: 2, available_direct: 0 }]),
      ),
    );
    renderRoute("/kompass/material");
    expect(await screen.findByText("2 Sätze frei")).toHaveClass("badge", "warning");
    expect(screen.getByText("2 mit Freigabe")).toBeInTheDocument();
  });

  it("takes sizes from the cart right away", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/types"), () => HttpResponse.json([FRIENDS])),
      http.post(api("/api/material/loans"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Satz Friends in den Korb" }));
    await user.click(screen.getByRole("button", { name: "Jetzt mitnehmen" }));
    const d = await dialog();
    expect(d.getByText(/3 Teile/)).toBeInTheDocument();
    // Counted sizes cannot be kept for good.
    expect(d.getByRole("radio", { name: "dauerhaft" })).toBeDisabled();
    await user.click(d.getByRole("button", { name: "Mitnehmen" }));
    await waitFor(() =>
      expect(body).toEqual({
        parts: [],
        sizes: [
          { size: 1, quantity: 1 },
          { size: 2, quantity: 2 },
        ],
        due: TOMORROW,
        borrower: null,
        permanent: false,
      }),
    );
  });

  it("takes any pieces of a type for good: reserves them, then picks them up", async () => {
    const calls: Record<string, unknown> = {};
    server.use(
      http.post(api("/api/material/reservations"), async ({ request }) => {
        calls.reservation = await request.json();
        return HttpResponse.json(reservation());
      }),
      http.post(api("/api/material/loans"), async ({ request }) => {
        calls.loans = await request.json();
        return HttpResponse.json(null);
      }),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Bandschlinge 120 cm in den Korb" }));
    await user.click(screen.getByRole("button", { name: "Jetzt mitnehmen" }));
    await waitFor(() => expect(calls.reservation).toMatchObject({ start: TODAY }));
    const d = await dialog();
    await user.click(d.getByLabelText(/dauerhaft behalten/));
    await user.click(d.getByRole("button", { name: "2 Teile ausgeben" }));
    await waitFor(() =>
      expect(calls.loans).toEqual({ parts: [1, 2], sizes: [], reservation: 20, borrower: null, permanent: true }),
    );
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/mine"));
  });

  it("says where to pick up what was reserved to take along, when not picked up now", async () => {
    server.use(
      http.post(api("/api/material/reservations"), () => HttpResponse.json(reservation())),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Bandschlinge 120 cm in den Korb" }));
    await user.click(screen.getByRole("button", { name: "Jetzt mitnehmen" }));
    await user.click((await dialog()).getByRole("button", { name: "Abbrechen" }));
    expect(await screen.findByText("Reserviert – abholen kannst du es unter Mein Material.")).toBeInTheDocument();
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/mine"));
  });

  it("reports a deficit", async () => {
    let body: unknown = null;
    server.use(
      http.post(api("/api/material/deficits"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/kompass/material");
    await user.click(await screen.findByRole("button", { name: "Defizit melden" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Was fehlt?"), "Seilsack");
    await user.click(d.getByRole("button", { name: "Melden" }));
    await waitFor(() =>
      expect(body).toEqual({
        product_type: null,
        text: "Seilsack",
        wanted_from: TODAY,
        wanted_to: TOMORROW,
        comment: "",
      }),
    );
  });
});

/* --- type detail ------------------------------------------------------------ */

describe("material — Materialtyp", () => {
  it("shows the type, its availability and its calendar", async () => {
    const { user } = renderRoute("/kompass/material/types/10");
    expect(await screen.findByText("Genähte Schlinge")).toBeInTheDocument();
    expect(screen.queryByLabelText("Foto hochladen")).not.toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Verfügbarkeit" }));
    expect(screen.getByText("mit Freigabe")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Belegung" }));
    expect(screen.getAllByText("Peter Lustig").length).toBeGreaterThan(0);
  });

  it("lists retired pieces apart and says they go with a deleted type", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let deleted = false;
    server.use(
      http.get(api("/api/material/types/10"), () =>
        HttpResponse.json({
          ...TYPE,
          parts: [],
          retired_parts: [part(7, { status: "retired", location: null }), part(8, { status: "retired" })],
        }),
      ),
      http.delete(api("/api/material/types/10"), () => {
        deleted = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/types/10?tab=parts");
    // An empty stock, but the retired pieces are on record.
    expect(await screen.findByText("Ausgesondert (2)")).toBeInTheDocument();
    expect(screen.getByText("Noch keine Teile.")).toBeInTheDocument();
    expect(screen.getByText("S7")).toBeInTheDocument();
    expect(screen.getAllByText("ausgesondert")).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    const confirmation = await screen.findByRole("dialog");
    expect(
      within(confirmation).getByText(/Die 2 ausgesonderten Teile werden mit ihm gelöscht/),
    ).toBeInTheDocument();
    await user.click(within(confirmation).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(deleted).toBe(true));
    expect(await screen.findByText("Materialtyp gelöscht.")).toBeInTheDocument();
  });

  it("names a single retired piece, and asks plainly when there is none", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(
      http.get(api("/api/material/types/10"), () =>
        HttpResponse.json({ ...TYPE, parts: [], retired_parts: [part(7, { status: "retired" })] }),
      ),
    );
    const { user, unmount } = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    expect(
      within(await screen.findByRole("dialog")).getByText(/Das ausgesonderte Teil wird/),
    ).toBeInTheDocument();
    unmount();

    server.use(http.get(api("/api/material/types/10"), () => HttpResponse.json(TYPE)));
    const second = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    await second.user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await second.user.click(screen.getByRole("button", { name: "Löschen" }));
    expect(
      within(await screen.findByRole("dialog")).getByText("Materialtyp löschen?"),
    ).toBeInTheDocument();
  });

  it("puts one in the cart, whose amount the cart changes", async () => {
    const { user } = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    expect(screen.queryByLabelText("Anzahl")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "In den Korb" }));
    const quantity = screen.getByLabelText("Anzahl Bandschlinge 120 cm");
    expect(quantity).toHaveValue(1);
    await user.tripleClick(quantity);
    await user.keyboard("3");
    expect(quantity).toHaveValue(3);
    // Only the type's ID and name are kept, not the whole type.
    await waitFor(() =>
      expect(JSON.parse(localStorage.getItem(CART_KEY)!).lines).toEqual([
        { key: "t10", quantity: 3, productType: { id: 10, name: "Bandschlinge 120 cm" } },
      ]),
    );
  });

  it("lets the amount in the cart be cleared and typed anew", async () => {
    const { user } = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    await user.click(screen.getByRole("button", { name: "In den Korb" }));
    const quantity = screen.getByLabelText("Anzahl Bandschlinge 120 cm");
    await user.clear(quantity);
    expect(quantity).toHaveValue(null);
    await user.type(quantity, "4");
    expect(quantity).toHaveValue(4);
    // Left empty, it goes back to the last amount.
    await user.clear(quantity);
    await user.tab();
    expect(quantity).toHaveValue(4);
  });

  it("offers no editing to those without the inventory's rights", async () => {
    server.use(
      http.get(api("/api/material/types/11"), () =>
        HttpResponse.json({ ...TYPE, ...FRIENDS, calendar: [], parts: [] }),
      ),
    );
    const { user } = renderRoute("/kompass/material/types/11");
    await user.click(await screen.findByRole("tab", { name: "Größen (2)" }));
    expect(screen.queryByRole("button", { name: "Größe hinzufügen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    expect(screen.getByRole("button", { name: "Defizit melden" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("edits and deletes a size", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const calls: Record<string, unknown> = {};
    server.use(
      http.get(api("/api/material/types/11"), () =>
        HttpResponse.json({ ...TYPE, ...FRIENDS, calendar: [], parts: [] }),
      ),
      http.patch(api("/api/material/sizes/2"), async ({ request }) => {
        calls.patch = await request.json();
        return HttpResponse.json(size(2, "2"));
      }),
      http.delete(api("/api/material/sizes/2"), () => {
        calls.delete = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/types/11");
    await user.click(await screen.findByRole("tab", { name: "Größen (2)" }));
    await user.click(screen.getByText("3 / 4"));
    let d = await dialog();
    const stock = d.getByLabelText("Bestand");
    await user.clear(stock);
    await user.type(stock, "5");
    await user.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.patch).toEqual({ name: "2", quantity: 5, per_set: 2, group: null, location: null }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByText("3 / 4"));
    d = await dialog();
    await user.click(d.getByRole("button", { name: "Löschen" }));
    const confirmation = screen.getAllByRole("dialog")[screen.getAllByRole("dialog").length - 1];
    await user.click(within(confirmation).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(calls.delete).toBe(true));
    expect(await screen.findByText("Größe gelöscht.")).toBeInTheDocument();
  });

  it("does not save the type when Enter is pressed in the cart", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let patched = false;
    server.use(
      http.post(api("/api/material/reservations/check"), () => checked()),
      http.patch(api("/api/material/types/10"), () => {
        patched = true;
        return HttpResponse.json(TYPE);
      }),
    );
    const { user } = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    await user.click(screen.getByRole("button", { name: "In den Korb" }));
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const cart = within(screen.getByRole("complementary", { name: "Korb" }));
    await user.type(cart.getByPlaceholderText("z. B. Ausfahrt"), "Hochtour{Enter}");
    expect(await cart.findByText("Alles frei")).toBeInTheDocument();
    expect(patched).toBe(false);
    expect(screen.getByRole("button", { name: "Speichern" })).toBeInTheDocument();
    // The page's own Speichern still saves it.
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(patched).toBe(true));
  });

  it("lists the sizes of a type kept by size and adds one", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let created: unknown = null;
    server.use(
      http.get(api("/api/material/types/11"), () =>
        HttpResponse.json({ ...TYPE, ...FRIENDS, calendar: [], parts: [] }),
      ),
      http.post(api("/api/material/types/11/sizes"), async ({ request }) => {
        created = await request.json();
        return HttpResponse.json(size(3, "3"));
      }),
    );
    const { user } = renderRoute("/kompass/material/types/11");
    await user.click(await screen.findByRole("tab", { name: "Größen (2)" }));
    expect(screen.getByText("3 / 4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Friends 2 in den Korb" }));
    expect(screen.getByLabelText("Anzahl Friends 2")).toHaveValue(1);
    await user.click(screen.getByRole("button", { name: "Satz in den Korb" }));
    expect(screen.getByLabelText("Anzahl Friends 2")).toHaveValue(3);

    await user.click(screen.getByRole("button", { name: "Größe hinzufügen" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Größe"), "3");
    await user.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(created).toEqual({ name: "3", quantity: 1, per_set: 1, group: null, location: null, position: 3 }),
    );
  });

  it("lists the types of a set and puts a set in the cart", async () => {
    server.use(http.get(api("/api/material/types/12"), () => HttpResponse.json(SET_TYPE)));
    const { user } = renderRoute("/kompass/material/types/12");
    await user.click(await screen.findByRole("tab", { name: "Satz (2)" }));
    expect(screen.getByRole("link", { name: "CAM 1" })).toHaveAttribute("href", "/kompass/material/types/14");
    expect(screen.queryByRole("tab", { name: /Größen/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /Teile/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Belegung" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Typ hinzufügen" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Satz in den Korb" }));
    expect(screen.getByLabelText("Anzahl CAM 1")).toHaveValue(2);
    await user.click(screen.getByRole("tab", { name: "Verfügbarkeit" }));
    expect(screen.getByText(/Sätzen frei/)).toBeInTheDocument();
  });

  it("names the sets a type belongs to, and offers it no set of its own", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(
      http.get(api("/api/material/types/10"), () =>
        HttpResponse.json({ ...TYPE, parts: [], in_sets: [ref(12, "Totem Satz")] }),
      ),
    );
    renderRoute("/kompass/material/types/10");
    expect(await screen.findByRole("link", { name: "Totem Satz" })).toHaveAttribute(
      "href",
      "/kompass/material/types/12",
    );
    expect(screen.queryByRole("tab", { name: /Satz/ })).not.toBeInTheDocument();
  });

  it("lets the inventory add, change and remove the types of a set", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const calls: Record<string, unknown> = {};
    server.use(
      http.get(api("/api/material/types/12"), () => HttpResponse.json(SET_TYPE)),
      http.get(api("/api/material/types"), () =>
        HttpResponse.json([CARD, CAM_SET, { ...CARD, id: 13, name: "CAM 0.5" }, FRIENDS]),
      ),
      http.post(api("/api/material/types/12/set-entries"), async ({ request }) => {
        calls.post = await request.json();
        return HttpResponse.json(setEntry(3, 10, "Bandschlinge 120 cm", 1, 3));
      }),
      http.patch(api("/api/material/set-entries/2"), async ({ request }) => {
        calls.patch = await request.json();
        return djangoValidation({ per_set: ["Höchstens so viele, wie es gibt."] });
      }),
      http.delete(api("/api/material/set-entries/2"), () => {
        calls.delete = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/types/12");
    await user.click(await screen.findByRole("tab", { name: "Satz (2)" }));
    await user.click(screen.getByRole("button", { name: "Typ hinzufügen" }));
    let d = await dialog();
    await user.click(d.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Wähle einen Typ.")).toBeInTheDocument();
    await user.click(document.querySelector('[role="dialog"] .ss-trigger') as HTMLElement);
    // The set itself and the types already in it are not offered.
    await waitFor(() => expect(dropdown().getByRole("button", { name: "Bandschlinge 120 cm" })).toBeInTheDocument());
    expect(dropdown().queryByRole("button", { name: "Totem Satz" })).not.toBeInTheDocument();
    expect(dropdown().queryByRole("button", { name: "CAM 0.5" })).not.toBeInTheDocument();
    // Nor a type kept by size: a set is reserved as pieces.
    expect(dropdown().queryByRole("button", { name: "Friends" })).not.toBeInTheDocument();
    await user.click(dropdown().getByRole("button", { name: "Bandschlinge 120 cm" }));
    await user.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.post).toEqual({ product_type: 10, per_set: 1, position: 3 }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    await user.click(screen.getByRole("cell", { name: "3" }));
    d = await dialog();
    const perSet = d.getByLabelText("Im Satz");
    await user.clear(perSet);
    await user.type(perSet, "3");
    await user.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() => expect(calls.patch).toEqual({ per_set: 3 }));
    expect(await d.findByText("Höchstens so viele, wie es gibt.")).toBeInTheDocument();
    await user.click(d.getByRole("button", { name: "Herausnehmen" }));
    const confirmation = screen.getAllByRole("dialog")[screen.getAllByRole("dialog").length - 1];
    await user.click(within(confirmation).getByRole("button", { name: "Herausnehmen" }));
    await waitFor(() => expect(calls.delete).toBe(true));
    expect(await screen.findByText("Aus dem Satz genommen.")).toBeInTheDocument();
  });

  it("offers an empty type to the inventory to become a set", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(http.get(api("/api/material/types/10"), () => HttpResponse.json({ ...TYPE, parts: [] })));
    const { user } = renderRoute("/kompass/material/types/10");
    await user.click(await screen.findByRole("tab", { name: "Satz (0)" }));
    expect(screen.getByText("Noch kein Satz: füge die Typen hinzu, aus denen er besteht.")).toBeInTheDocument();
  });

  it("lets the inventory edit the type, replace its photo and add pieces", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let patch: unknown = null;
    let created: unknown = null;
    let photo = false;
    server.use(
      http.patch(api("/api/material/types/10"), async ({ request }) => {
        patch = await request.json();
        return HttpResponse.json(TYPE);
      }),
      http.post(api("/api/material/types/10/photo"), async ({ request }) => {
        photo = (await request.formData()).has("photo");
        return HttpResponse.json(TYPE);
      }),
      http.post(api("/api/material/parts"), async ({ request }) => {
        created = await request.json();
        return HttpResponse.json([part(9)]);
      }),
    );
    const { user } = renderRoute("/kompass/material/types/10");
    await screen.findByText("Genähte Schlinge");
    await user.click(screen.getByRole("tab", { name: "Teile (2)" }));
    expect(screen.getByText(`an Peter Lustig verliehen bis ${shortDate(TOMORROW)}`)).toBeInTheDocument();
    expect(screen.getByText("Griffwerk")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    const name = screen.getByDisplayValue("Bandschlinge 120 cm");
    await user.clear(name);
    await user.type(name, "Schlinge");
    await user.upload(screen.getByLabelText("Foto hochladen"), new File(["x"], "a.png", { type: "image/png" }));
    await waitFor(() => expect(photo).toBe(true));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(patch).toMatchObject({ name: "Schlinge", usage_years: 10, daily_rate: "1.50", tags: [1] }),
    );

    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Teile hinzufügen" }));
    const d = await dialog();
    await user.type(d.getByLabelText("PSA-ID"), "E2");
    await user.click(d.getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(created).toMatchObject({ product_type: 10, psa_id: "E2", count: 1 }));
    expect(await screen.findByText("Teil angelegt.")).toBeInTheDocument();
  });
});

/* --- part detail ------------------------------------------------------------ */

describe("material — Teil", () => {
  it("enlarges the photo of a piece, and changes it only in edit mode", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(
      http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ photo: "/media/images/s.png" }))),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Foto vergrößern" }));
    expect((await dialog()).getByRole("img", { name: "Bandschlinge 120 cm E1351" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Schließen" }));
    expect(screen.queryByLabelText("Foto ändern")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    expect(screen.getByLabelText("Foto ändern")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Foto vergrößern" })).not.toBeInTheDocument();
  });

  it("shows the piece, its reservations and its history", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const { user } = renderRoute("/kompass/material/parts/1");
    expect(await screen.findByText("überschritten")).toBeInTheDocument();
    expect(screen.getByText("überfällig")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Prüfungen" }));
    expect(screen.getAllByText("Hannah Beckers").length).toBeGreaterThan(0);
    await user.click(screen.getByRole("tab", { name: "Verlauf" }));
    expect(screen.getByText("Übergabe")).toBeInTheDocument();
  });

  it("puts the piece in the cart, and offers no hand-over for a piece I do not have", async () => {
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "In den Korb" }));
    const cart = within(await screen.findByRole("complementary", { name: "Korb" }));
    expect(cart.getByText("E1351")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zurückgeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Übergeben" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    expect(screen.getByRole("button", { name: "Defizit melden" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Bearbeiten" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Prüfung eintragen" })).not.toBeInTheDocument();
  });

  it("leaves edit mode when a link leads to another piece", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let patched = false;
    server.use(
      http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ parent: part(5) }))),
      http.get(api("/api/material/parts/5"), () =>
        HttpResponse.json(partOut({ id: 5, label: "S5", psa_id: null, note: "Rucksack" })),
      ),
      http.patch(api("/api/material/parts/5"), () => {
        patched = true;
        return HttpResponse.json(partOut());
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    expect(screen.getByDisplayValue("E1351")).toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Bandschlinge 120 cm S5" }));
    expect(await screen.findByText("Rucksack")).toBeInTheDocument();
    expect(currentUrl()).toBe("/kompass/material/parts/5");
    expect(screen.queryByRole("button", { name: "Speichern" })).not.toBeInTheDocument();
    expect(screen.queryByDisplayValue("E1351")).not.toBeInTheDocument();
    expect(patched).toBe(false);
  });

  it("builds a piece from the stock into this one, leaving out what cannot go in", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const calls: { query?: URLSearchParams; body?: unknown } = {};
    server.use(
      http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ components: [part(3)] }))),
      http.get(api("/api/material/parts"), ({ request }) => {
        calls.query = new URL(request.url).searchParams;
        return HttpResponse.json([
          part(1),
          part(2, { holder: ref(8, "Peter Lustig"), location: null, lent_until: TOMORROW }),
          part(5, { product_type: ref(12, "Karabiner") }),
        ]);
      }),
      http.patch(api("/api/material/parts/5"), async ({ request }) => {
        calls.body = await request.json();
        return HttpResponse.json(partOut({ id: 5, label: "S5", product_type: ref(12, "Karabiner") }));
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Teil einbauen" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Teil suchen"), "Kara");
    const add = await d.findByRole("button", { name: "Karabiner S5 einbauen" });
    // Only pieces in no other set, and neither the piece itself nor one on loan.
    expect(calls.query?.get("q")).toBe("Kara");
    expect(calls.query?.get("top_level")).toBe("true");
    for (const id of [1, 2]) {
      expect(d.queryByRole("button", { name: `Bandschlinge 120 cm S${id} einbauen` })).not.toBeInTheDocument();
    }
    await user.click(add);
    expect(await screen.findByText("Karabiner S5 eingebaut.")).toBeInTheDocument();
    expect(calls.body).toEqual({ parent: 1 });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("creates new pieces built into this one", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let body: unknown;
    server.use(
      http.post(api("/api/material/parts"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json([part(5), part(6)]);
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Neues Teil einbauen" }));
    const d = await dialog();
    await user.click(await d.findByRole("button", { name: "Materialtyp" }));
    await user.click(dropdown().getByRole("button", { name: "Bandschlinge 120 cm" }));
    const add = await screen.findByRole("dialog", {
      name: "Bandschlinge 120 cm in Bandschlinge 120 cm E1351 einbauen",
    });
    await user.type(within(add).getByLabelText("PSA-ID"), "E2");
    await user.click(within(add).getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(body).toMatchObject({ product_type: 10, psa_id: "E2", parent: 1 }));
  });

  it("takes a piece out, from the assembly or from the piece itself", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const patched: Record<number, unknown> = {};
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ parent: part(4), components: [part(3)] })),
      ),
      http.patch(api("/api/material/parts/:id"), async ({ request, params }) => {
        const id = Number(params.id);
        patched[id] = await request.json();
        return HttpResponse.json(partOut({ id, label: `S${id}`, psa_id: null }));
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("tab", { name: "Bestandteile" }));
    await user.click(screen.getByRole("button", { name: "Bandschlinge 120 cm S3 ausbauen" }));
    expect(await screen.findByText("Bandschlinge 120 cm S3 ausgebaut.")).toBeInTheDocument();
    expect(patched[3]).toEqual({ parent: null });
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Ausbauen" }));
    await waitFor(() => expect(patched[1]).toEqual({ parent: null }));
  });

  it("builds nothing into a piece out on loan, and offers no assembly without the inventory", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(
          partOut({ holder: ref(8, "Peter Lustig"), location: null, lent_until: TOMORROW, components: [part(3)] }),
        ),
      ),
    );
    const { user, unmount } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("tab", { name: "Bestandteile" }));
    // A lent set keeps its pieces.
    expect(screen.queryByRole("button", { name: /ausbauen/ })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    expect(screen.getByRole("button", { name: "Bearbeiten" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Teil einbauen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neues Teil einbauen" })).not.toBeInTheDocument();
    unmount();

    // A set is put together from the top, not from one of its pieces.
    server.use(http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ parent: part(4) }))));
    const nested = renderRoute("/kompass/material/parts/1");
    await nested.user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    expect(screen.getByRole("button", { name: "Ausbauen" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Teil einbauen" })).not.toBeInTheDocument();
    nested.unmount();

    useMe({ permissions: [] });
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ parent: part(4), components: [part(3)] })),
      ),
    );
    const second = renderRoute("/kompass/material/parts/1");
    await second.user.click(await screen.findByRole("tab", { name: "Bestandteile" }));
    expect(screen.queryByRole("button", { name: /ausbauen/ })).not.toBeInTheDocument();
    await second.user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    expect(screen.queryByRole("button", { name: "Teil einbauen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ausbauen" })).not.toBeInTheDocument();
  });

  it("lets a leader of the owning group pass a piece on, but not one lent to someone else", async () => {
    server.use(
      http.get(api("/api/members/groups"), () =>
        HttpResponse.json([{ ...GROUPS[0], leiters: [ref(7, "Hannah Beckers")] }]),
      ),
      http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ group: ref(5, "Jugend") }))),
      http.get(api("/api/material/parts/2"), () =>
        HttpResponse.json(
          partOut({
            id: 2,
            label: "S2",
            group: ref(5, "Jugend"),
            holder: ref(8, "Peter Lustig"),
            location: null,
            lent_until: TOMORROW,
          }),
        ),
      ),
    );
    const { user, unmount } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Übergeben" }));
    const d = await dialog();
    await user.click(d.getByRole("button", { name: "An" }));
    expect(dropdown().getByRole("button", { name: "Peter Lustig" })).toBeInTheDocument();
    unmount();

    renderRoute("/kompass/material/parts/2");
    expect(await screen.findByText(/an Peter Lustig verliehen/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Übergeben" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Zurücknehmen" })).not.toBeInTheDocument();
  });

  it("lets the lending team take back a piece lent to someone", async () => {
    useMe({ permissions: ["equipment.manage_lending"] });
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ holder: ref(8, "Peter Lustig"), location: null, lent_until: TOMORROW })),
      ),
      http.post(api("/api/material/returns"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ returned: [1] });
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    expect(await screen.findByRole("button", { name: "Übergeben" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zurücknehmen" }));
    await user.click((await dialog()).getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() => expect(body).toEqual({ parts: [1], sizes: [], location: null, flagged: [] }));
  });

  it("passes an overdue piece on until a day, from today on", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ holder: ref(7, "Hannah Beckers"), location: null, lent_until: "2020-01-01" })),
      ),
      http.post(api("/api/material/parts/transfer"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ warnings: [] });
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Übergeben" }));
    const d = await dialog();
    await user.click(d.getByRole("button", { name: "An" }));
    await user.click(dropdown().getByRole("button", { name: "Peter Lustig" }));
    expect(d.getByRole("radio", { name: "dauerhaft" })).not.toBeChecked();
    expect(d.getByLabelText("Rückgabe bis")).toHaveValue(TODAY);
    await user.click(d.getByRole("button", { name: "Übergeben" }));
    await waitFor(() =>
      expect(body).toEqual({ parts: [1], sizes: [], member: 8, location: null, due: TODAY }),
    );
  });

  it("records an inspection", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let fields: Record<string, string> = {};
    server.use(
      http.post(api("/api/material/parts/1/inspections"), async ({ request }) => {
        fields = await multipartFields(request);
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Prüfung eintragen" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Kommentar"), "Mantel ok");
    await user.click(d.getByRole("button", { name: "Eintragen" }));
    await waitFor(() => expect(fields).toEqual({ result: "ok", date: TODAY, comment: "Mantel ok" }));
  });

  it("returns a piece I hold, flagged as damaged", async () => {
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ holder: ref(7, "Hannah Beckers"), location: null })),
      ),
    );
    let body: unknown = null;
    server.use(
      http.post(api("/api/material/returns"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ returned: [1] });
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Zurückgeben" }));
    const d = await dialog();
    await user.click(d.getByLabelText("beschädigt"));
    await user.click(d.getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() => expect(body).toEqual({ parts: [1], sizes: [], location: null, flagged: [1] }));
  });

  it("deletes a piece without history after a plain confirmation, and drops it from the cart", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let deleted = false;
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ history: { loans: 0, reservations: 0, inspections: 0, handovers: 0 } })),
      ),
      http.delete(api("/api/material/parts/1"), () => {
        deleted = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "In den Korb" }));
    expect(JSON.parse(localStorage.getItem(CART_KEY)!).lines).toHaveLength(1);
    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    const d = await dialog();
    expect(d.getByText("Teil löschen?")).toBeInTheDocument();
    await user.click(d.getByRole("button", { name: "Löschen" }));
    expect(await screen.findByText("Teil gelöscht.")).toBeInTheDocument();
    expect(deleted).toBe(true);
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/types/10"));
    expect(JSON.parse(localStorage.getItem(CART_KEY)!).lines).toEqual([]);
  });

  it("warns before deleting a piece with history, and offers retiring it instead", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let deleted = false;
    server.use(
      http.get(api("/api/material/parts/1"), () =>
        HttpResponse.json(partOut({ history: { loans: 2, reservations: 1, inspections: 1, handovers: 1 } })),
      ),
      http.delete(api("/api/material/parts/1"), () => {
        deleted = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    let d = await dialog();
    expect(d.getByText("Teil mit Verlauf löschen?")).toBeInTheDocument();
    expect(
      d.getByText(/sein Verlauf gelöscht: 2 Ausleihen, 1 vergangene Reservierung, 1 Prüfung, 1 Übergabe\./),
    ).toBeInTheDocument();
    expect(d.getByText(/sondere es besser über eine Prüfung aus/)).toBeInTheDocument();
    await user.click(d.getByRole("button", { name: "Abbrechen" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(deleted).toBe(false);

    await user.click(screen.getByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    d = await dialog();
    await user.click(d.getByRole("button", { name: "Trotzdem löschen" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("asks for a lent piece to be taken back before it is deleted", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    server.use(http.get(api("/api/material/parts/1"), () => HttpResponse.json(partOut({ lent_until: TOMORROW }))));
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Löschen" }));
    expect(
      await screen.findByText("Ein verliehenes Teil muss vor dem Löschen zurückgenommen werden."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("offers deleting a piece to the inventory only", async () => {
    useMe({ permissions: ["equipment.manage_lending"] });
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    expect(screen.queryByRole("button", { name: "Löschen" })).not.toBeInTheDocument();
  });

  it("saves an edit and shows field errors", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let attempt = 0;
    server.use(
      http.patch(api("/api/material/parts/1"), () => {
        attempt += 1;
        return attempt === 1
          ? djangoValidation({ psa_id: ["PSA braucht eine PSA-ID."] })
          : HttpResponse.json(partOut());
      }),
    );
    const { user } = renderRoute("/kompass/material/parts/1");
    await user.click(await screen.findByRole("button", { name: "Aktionen ▾" }));
    await user.click(screen.getByRole("button", { name: "Bearbeiten" }));
    await user.clear(screen.getByDisplayValue("E1351"));
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect((await screen.findAllByText("PSA braucht eine PSA-ID.")).length).toBeGreaterThan(0);
    await user.click(screen.getByRole("button", { name: "Speichern" }));
    expect(await screen.findByText("Gespeichert.")).toBeInTheDocument();
  });
});

/* --- my material, requests, desk ------------------------------------------- */

describe("material — Mein Material", () => {
  it("marks only the current page in the menu", async () => {
    server.use(
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    const { user } = renderRoute("/kompass/material/mine");
    await user.click(await screen.findByRole("button", { name: /^Material/ }));
    const menu = within(document.querySelector(".nav-dropdown") as HTMLElement);
    expect(menu.getByRole("link", { name: "Mein Material" })).toHaveClass("active");
    expect(menu.getByRole("link", { name: "Materialbrowser" })).not.toHaveClass("active");
  });

  it("marks the Bestand in the menu on its tabs", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const { user } = renderRoute("/kompass/material/locations");
    await user.click(await screen.findByRole("button", { name: /^Material/ }));
    const menu = within(document.querySelector(".nav-dropdown") as HTMLElement);
    expect(menu.getByRole("link", { name: "Bestand" })).toHaveClass("active");
    expect(menu.getByRole("link", { name: "Materialbrowser" })).not.toHaveClass("active");
  });

  it("returns lent sizes", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({
          held: [],
          held_sizes: [
            { id: 40, size: { id: 1, name: "1", product_type: ref(11, "Friends") }, quantity: 3, due: "2020-01-01", overdue: true },
          ],
          reservations: [],
          to_decide: 0,
        }),
      ),
      http.post(api("/api/material/returns"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ returned: [] });
      }),
    );
    const { user } = renderRoute("/kompass/material/mine");
    expect(await screen.findByText("Keine Teile mit ID.")).toBeInTheDocument();
    expect(screen.getByText(/überfällig seit/)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zurückgeben" }));
    const d = await dialog();
    expect(d.getByLabelText("Anzahl Friends 1")).toHaveValue(3);
    await user.click(d.getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() =>
      expect(body).toEqual({ parts: [], sizes: [{ lent: 40, quantity: 3 }], location: null, flagged: [] }),
    );
  });

  it("returns what I select, picks up a reservation and cancels one", async () => {
    const calls: Record<string, unknown> = {};
    server.use(
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({
          held: [
            { ...part(1, { holder: ref(7, "Hannah Beckers") }), due: "2020-01-01", overdue: true },
            { ...part(2, { holder: ref(7, "Hannah Beckers") }), due: null, overdue: false },
          ],
          held_sizes: [
            { id: 40, size: { id: 1, name: "1", product_type: ref(11, "Friends") }, quantity: 2, due: TOMORROW, overdue: false },
          ],
          reservations: [reservation({ sizes: [{ size: { id: 2, name: "2", product_type: ref(11, "Friends") }, quantity: 2, group: null }] })],
          to_decide: 0,
        }),
      ),
      http.post(api("/api/material/returns"), async ({ request }) => {
        calls.returns = await request.json();
        return HttpResponse.json({ returned: [1] });
      }),
      http.post(api("/api/material/loans"), async ({ request }) => {
        calls.loans = await request.json();
        return HttpResponse.json({});
      }),
      http.get(api("/api/material/parts/lookup"), () => HttpResponse.json(partOut({ id: 9, label: "S9" }))),
      http.post(api("/api/material/reservations/20/cancel"), () => {
        calls.cancel = true;
        return HttpResponse.json(reservation({ status: "cancelled" }));
      }),
    );
    const { user } = renderRoute("/kompass/material/mine");
    expect(await screen.findByText(/überfällig seit/)).toBeInTheDocument();
    expect(screen.getByText("dauerhaft")).toBeInTheDocument();
    expect(screen.queryByText("Anfragen für deine Gruppen")).not.toBeInTheDocument();

    await user.click(screen.getAllByRole("checkbox")[1]);
    await user.click(screen.getByRole("button", { name: "1 zurückgeben" }));
    await user.click((await dialog()).getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() =>
      expect(calls.returns).toEqual({ parts: [1], sizes: [], location: null, flagged: [] }),
    );

    await user.click(screen.getAllByRole("button", { name: "Zurückgeben" })[0]);
    const back = await dialog();
    await user.tripleClick(back.getByLabelText("Anzahl Friends 1"));
    await user.keyboard("1");
    await user.click(back.getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() =>
      expect(calls.returns).toEqual({ parts: [], sizes: [{ lent: 40, quantity: 1 }], location: null, flagged: [] }),
    );

    await user.click(screen.getByRole("button", { name: "Abholen" }));
    const d = await dialog();
    await user.click(d.getByLabelText(/S2/));
    await user.type(d.getByLabelText("Anderes Teil per ID"), "S9");
    await user.click(d.getByRole("button", { name: "Hinzufügen" }));
    await user.click(await d.findByRole("button", { name: "4 Teile ausgeben" }));
    await waitFor(() =>
      expect(calls.loans).toEqual({
        parts: [1, 9],
        sizes: [{ size: 2, quantity: 2 }],
        reservation: 20,
        borrower: null,
        permanent: false,
      }),
    );

    await user.click(screen.getByRole("button", { name: "Stornieren" }));
    await user.click((await dialog()).getByRole("button", { name: "Stornieren" }));
    await waitFor(() => expect(calls.cancel).toBe(true));
  });

  it("hands selected pieces over for good", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({
          held: [{ ...part(1, { holder: ref(7, "Hannah Beckers") }), due: null, overdue: false }],
          held_sizes: [],
          reservations: [],
          to_decide: 0,
        }),
      ),
      http.post(api("/api/material/parts/transfer"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ warnings: ["S1 ist ab morgen für Peter reserviert."] });
      }),
    );
    const { user } = renderRoute("/kompass/material/mine");
    await user.click((await screen.findAllByRole("checkbox"))[1]);
    await user.click(screen.getByRole("button", { name: "1 übergeben" }));
    const d = await dialog();
    await user.click(d.getByRole("button", { name: "An" }));
    await user.click(dropdown().getByRole("button", { name: "Peter Lustig" }));
    expect(d.getByRole("radio", { name: "dauerhaft" })).toBeChecked();
    await user.click(d.getByRole("button", { name: "Übergeben" }));
    await waitFor(() =>
      expect(body).toEqual({ parts: [1], sizes: [], member: 8, location: null, due: null }),
    );
    expect(await screen.findByText("S1 ist ab morgen für Peter reserviert.")).toBeInTheDocument();
  });
});

describe("material — Anfragen in Mein Material", () => {
  it("approves a request for my group", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/reservations"), () =>
        HttpResponse.json([
          reservation({
            status: "requested",
            approvals: [{ group: ref(5, "Jugend"), approved: null, decided_by: null, comment: "" }],
            decidable_groups: [5],
          }),
        ]),
      ),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 1 }),
      ),
      http.post(api("/api/material/reservations/20/decide"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(reservation());
      }),
    );
    const { user } = renderRoute("/kompass/material/mine");
    expect(await screen.findByText("Anfragen für deine Gruppen")).toBeInTheDocument();
    await user.click(await screen.findByRole("button", { name: "Freigeben" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Kommentar an die anfragende Person"), "Viel Spaß");
    await user.click(d.getByRole("button", { name: "Freigeben" }));
    await waitFor(() => expect(body).toEqual({ group: 5, approved: true, comment: "Viel Spaß" }));
  });

  it("declines a request for my group", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/reservations"), () =>
        HttpResponse.json([
          reservation({
            status: "requested",
            approvals: [{ group: ref(5, "Jugend"), approved: null, decided_by: null, comment: "" }],
            decidable_groups: [5],
          }),
        ]),
      ),
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 1 }),
      ),
      http.post(api("/api/material/reservations/20/decide"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(reservation({ status: "declined" }));
      }),
    );
    const { user } = renderRoute("/kompass/material/mine");
    await user.click(await screen.findByRole("button", { name: "Ablehnen" }));
    const d = await dialog();
    await user.type(d.getByLabelText("Kommentar an die anfragende Person"), "Brauchen wir selbst");
    await user.click(d.getByRole("button", { name: "Ablehnen" }));
    await waitFor(() => expect(body).toEqual({ group: 5, approved: false, comment: "Brauchen wir selbst" }));
    expect(await screen.findByText("Abgelehnt.")).toBeInTheDocument();
  });

  it("sends the old requests page to my material", async () => {
    server.use(
      http.get(api("/api/material/mine"), () =>
        HttpResponse.json({ held: [], held_sizes: [], reservations: [], to_decide: 0 }),
      ),
    );
    renderRoute("/kompass/material/requests");
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/mine"));
  });
});

describe("material — Ausgabe", () => {
  it("hands out a reservation for its borrower and takes loans back", async () => {
    const calls: Record<string, unknown> = {};
    const loan = {
      id: 30,
      borrower: ref(8, "Peter Lustig"),
      out_at: "2026-01-01T10:00:00Z",
      due: "2020-01-01",
      reservation: null,
      overdue: true,
      lines: [{ part: part(3), returned_at: null }],
      sizes: [{ id: 41, size: { id: 1, name: "1", product_type: ref(11, "Friends") }, quantity: 2, returned: 1 }],
    };
    server.use(
      http.get(api("/api/material/desk"), () =>
        HttpResponse.json({
          pickups: [reservation({ borrower: ref(8, "Peter Lustig") })],
          due: [],
          overdue: [loan],
          requests: [],
          inspection_due: [part(4, { status: "inspection_due" })],
        }),
      ),
      http.post(api("/api/material/loans"), async ({ request }) => {
        calls.loans = await request.json();
        return HttpResponse.json({});
      }),
      http.post(api("/api/material/returns"), async ({ request }) => {
        calls.returns = await request.json();
        return HttpResponse.json({ returned: [3] });
      }),
    );
    const { user } = renderRoute("/kompass/material/desk");
    await user.click(await screen.findByRole("button", { name: "Ausgeben" }));
    await user.click((await dialog()).getByRole("button", { name: "2 Teile ausgeben" }));
    await waitFor(() =>
      expect(calls.loans).toEqual({ parts: [1, 2], sizes: [], reservation: 20, borrower: 8, permanent: false }),
    );

    expect(screen.getByText("Bandschlinge 120 cm S3, 1 × Friends 1")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zurücknehmen" }));
    await user.click((await dialog()).getByRole("button", { name: "Rückgabe bestätigen" }));
    await waitFor(() =>
      expect(calls.returns).toEqual({
        parts: [3],
        sizes: [{ lent: 41, quantity: 1 }],
        location: null,
        flagged: [],
      }),
    );
  });

  it("hands material to someone at the desk until a day", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/desk"), () =>
        HttpResponse.json({ pickups: [], due: [], overdue: [], requests: [], inspection_due: [] }),
      ),
      http.get(api("/api/material/parts/lookup"), () => HttpResponse.json(partOut())),
      http.get(api("/api/material/sizes"), () => HttpResponse.json([size(1, "1")])),
      http.post(api("/api/material/parts/transfer"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ warnings: [] });
      }),
    );
    const { user } = renderRoute("/kompass/material/desk");
    await user.click(await screen.findByRole("button", { name: "Übergeben" }));
    const d = await dialog();
    await user.click(d.getByRole("button", { name: "An" }));
    await user.click(dropdown().getByRole("button", { name: "Griffwerk (Ort)" }));
    await user.type(d.getByLabelText("Teil per ID"), "E1351");
    await user.click(d.getByRole("button", { name: "Hinzufügen" }));
    await d.findByText("E1351");
    await user.click(d.getByRole("button", { name: "Größen ohne ID" }));
    await user.click(dropdown().getByRole("button", { name: "Friends 1" }));
    expect(d.getByLabelText("Anzahl Friends 1")).toHaveValue(1);
    // Counted sizes go to a person: the place chosen before no longer counts.
    expect(d.getByText("Größen ohne ID gehen nur an eine Person, bis zu einem Tag.")).toBeInTheDocument();
    expect(d.getByRole("button", { name: "Übergeben" })).toBeDisabled();
    await user.click(d.getByRole("button", { name: "An" }));
    expect(dropdown().queryByRole("button", { name: "Griffwerk (Ort)" })).not.toBeInTheDocument();
    await user.click(dropdown().getByRole("button", { name: "Peter Lustig" }));
    expect(d.getByRole("radio", { name: "dauerhaft" })).toBeDisabled();
    await user.click(d.getByRole("button", { name: "Übergeben" }));
    await waitFor(() =>
      expect(body).toEqual({
        parts: [1],
        sizes: [{ size: 1, quantity: 1 }],
        member: 8,
        location: null,
        due: TOMORROW,
      }),
    );
  });
});

/* --- stock, PSA and the lists ----------------------------------------------- */

describe("material — Bestand", () => {
  it("filters the pieces and hands a selection on to a location (#449)", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/parts"), () =>
        HttpResponse.json([part(1), part(2, { holder: ref(8, "Peter Lustig"), location: null })]),
      ),
      http.post(api("/api/material/parts/transfer"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({ warnings: [] });
      }),
    );
    const { user } = renderRoute("/kompass/material/stock");
    expect(await screen.findByText("dauerhaft bei Peter Lustig")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "PSA-Prüfungen" })).toBeInTheDocument();
    await user.click(screen.getByRole("checkbox", { name: "Alle auswählen" }));
    await user.click(screen.getByRole("button", { name: "2 übergeben" }));
    const d = await dialog();
    await user.click(d.getByRole("button", { name: "An" }));
    await user.click(dropdown().getByRole("button", { name: "Griffwerk (Ort)" }));
    expect(d.queryByRole("radio", { name: "dauerhaft" })).not.toBeInTheDocument();
    await user.click(d.getByRole("button", { name: "Übergeben" }));
    await waitFor(() =>
      expect(body).toEqual({ parts: [1, 2], sizes: [], member: null, location: 3, due: null }),
    );
  });

  it("creates a new type and adds its pieces", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const calls: Record<string, unknown> = {};
    server.use(
      http.get(api("/api/material/parts"), () => HttpResponse.json([])),
      http.post(api("/api/material/types"), async ({ request }) => {
        calls.type = await request.json();
        return HttpResponse.json({ ...TYPE, id: 11, name: "Pickel", is_psa: false });
      }),
      http.get(api("/api/material/types"), () =>
        HttpResponse.json([CARD, { ...CARD, id: 11, name: "Pickel", is_psa: false }]),
      ),
      http.post(api("/api/material/parts"), async ({ request }) => {
        calls.parts = await request.json();
        return HttpResponse.json([part(5), part(6)]);
      }),
    );
    const { user } = renderRoute("/kompass/material/stock");
    await user.click(await screen.findByRole("button", { name: "Teile anlegen" }));
    const d = await dialog();
    await user.type(await d.findByLabelText("Name des Typs"), "Pickel");
    await user.click(d.getByRole("button", { name: "Typ anlegen" }));
    const add = await screen.findByRole("dialog", { name: "Pickel: Teile hinzufügen" });
    const count = within(add).getByLabelText("Anzahl (ohne IDs)");
    await user.clear(count);
    await user.type(count, "2");
    await user.click(within(add).getByRole("button", { name: "Anlegen" }));
    await waitFor(() => expect(calls.parts).toMatchObject({ product_type: 11, count: 2 }));
    expect(calls.type).toMatchObject({ name: "Pickel", is_psa: false });
    expect(await screen.findByText("2 Teile angelegt.")).toBeInTheDocument();
  });
});

describe("material — Bestand für wen", () => {
  it("shows no inventory actions to those without its rights", async () => {
    server.use(http.get(api("/api/material/parts"), () => HttpResponse.json([part(1)])));
    renderRoute("/kompass/material/stock");
    expect(await screen.findByText("Griffwerk")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Teile anlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "PSA-Prüfungen" })).not.toBeInTheDocument();
  });

  it("shows those who only lend the pieces and places, but not the inventory's pages", async () => {
    useMe({ permissions: ["equipment.manage_lending"] });
    server.use(http.get(api("/api/material/parts"), () => HttpResponse.json([part(1)])));
    const { user } = renderRoute("/kompass/material/stock");
    expect(await screen.findByText("Griffwerk")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Teile anlegen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "PSA-Prüfungen" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Wunschliste" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("link", { name: "Orte" }));
    await user.click(await screen.findByText("Di 18–20"));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Neuer Ort" })).not.toBeInTheDocument();
  });
});

describe("material — PSA-Prüfungen", () => {
  it("lists every unit with its next inspection", async () => {
    server.use(
      http.get(api("/api/material/psa"), ({ request }) =>
        HttpResponse.json(
          new URL(request.url).searchParams.get("retired") === "true"
            ? []
            : [
                {
                  ...part(1, { label: "E1351", psa_id: "E1351" }),
                  last_inspection: null,
                  next_inspection: "2020-01-01",
                  days_left: -5,
                  past_usage_period: true,
                  incomplete: true,
                },
                {
                  ...part(2, { label: "E2", psa_id: "E2" }),
                  last_inspection: { id: 1, date: "2025-01-01", result: "ok", inspector: null, comment: "", photo: null },
                  next_inspection: TOMORROW,
                  days_left: 1,
                  past_usage_period: false,
                  incomplete: false,
                },
              ],
        ),
      ),
    );
    const { user } = renderRoute("/kompass/material/psa");
    expect(await screen.findByText("5 Tage überfällig")).toBeInTheDocument();
    expect(screen.getByText("1 Tage")).toBeInTheDocument();
    expect(screen.getByText("Angaben fehlen")).toBeInTheDocument();
    await user.click(screen.getByRole("tab", { name: "Ausgesondert" }));
    expect(await screen.findByText("Keine PSA erfasst.")).toBeInTheDocument();
  });
});

describe("material — Wunschliste, Orte, Tags", () => {
  it("moves a wish to ordered", async () => {
    let body: unknown = null;
    server.use(
      http.get(api("/api/material/deficits"), () =>
        HttpResponse.json([
          {
            id: 1,
            product_type: null,
            text: "Seilsack",
            wanted_from: TODAY,
            wanted_to: null,
            comment: "",
            reported_by: ref(8, "Peter Lustig"),
            created_at: "2026-01-01T10:00:00Z",
            status: "open",
          },
        ]),
      ),
      http.patch(api("/api/material/deficits/1"), async ({ request }) => {
        body = await request.json();
        return HttpResponse.json({});
      }),
    );
    const { user } = renderRoute("/kompass/material/deficits");
    expect(await screen.findByText("Seilsack")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "offen ▾" }));
    await user.click(dropdown().getByRole("button", { name: "bestellt" }));
    await waitFor(() => expect(body).toEqual({ status: "ordered" }));
  });

  it("edits and deletes a location", async () => {
    useMe({ permissions: ["equipment.manage_inventory"] });
    const calls: Record<string, unknown> = {};
    server.use(
      http.put(api("/api/material/locations/3"), async ({ request }) => {
        calls.put = await request.json();
        return HttpResponse.json(LOCATIONS[0]);
      }),
      http.delete(api("/api/material/locations/3"), () => {
        calls.delete = true;
        return HttpResponse.json({ success: true });
      }),
    );
    const { user } = renderRoute("/kompass/material/locations");
    await user.click(await screen.findByText("Griffwerk"));
    let d = await dialog();
    await user.type(d.getByLabelText("Adresse"), "Ludwigsburg");
    await user.click(d.getByRole("button", { name: "Speichern" }));
    await waitFor(() =>
      expect(calls.put).toEqual({ name: "Griffwerk", address: "Ludwigsburg", opening_hours: "Di 18–20" }),
    );
    await user.click(await screen.findByText("Griffwerk"));
    d = await dialog();
    await user.click(d.getByRole("button", { name: "Löschen" }));
    await user.click(within(screen.getAllByRole("dialog")[screen.getAllByRole("dialog").length - 1]).getByRole("button", { name: "Löschen" }));
    await waitFor(() => expect(calls.delete).toBe(true));
  });

  it("shows the types carrying a tag", async () => {
    server.use(
      http.get(api("/api/material/categories/1"), () =>
        HttpResponse.json({ id: 1, name: "Hochtour", product_types: [ref(10, "Bandschlinge 120 cm")] }),
      ),
    );
    const { user } = renderRoute("/kompass/material/categories/1");
    await user.click(await screen.findByText("Bandschlinge 120 cm"));
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/types/10"));
  });

  it("redirects an old part link", async () => {
    renderRoute("/kompass/material/1");
    await waitFor(() => expect(currentUrl()).toBe("/kompass/material/parts/1"));
  });
});
