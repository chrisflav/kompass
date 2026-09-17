import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useListView, type ListViewConfig } from "./list";

interface Row {
  id: number;
  name: string;
  age: number | null;
  group: string;
  active: boolean;
}

const ROWS: Row[] = [
  { id: 1, name: "Zoe Ziegler", age: 12, group: "Klettergruppe", active: true },
  { id: 2, name: "Anna Ärmel", age: 30, group: "Alpingruppe", active: false },
  { id: 3, name: "Bernd Bauer", age: null, group: "Klettergruppe", active: true },
  { id: 4, name: "ölaf Öhler", age: 8, group: "Alpingruppe", active: true },
];

const config: ListViewConfig<Row> = {
  search: (r) => [r.name, r.group],
  filters: [
    {
      key: "group",
      label: "Gruppe",
      options: [
        { value: "Klettergruppe", label: "Klettergruppe" },
        { value: "Alpingruppe", label: "Alpingruppe" },
      ],
      match: (r, v) => r.group === v,
    },
    {
      key: "active",
      label: "Aktiv",
      options: [
        { value: "yes", label: "Ja" },
        { value: "no", label: "Nein" },
      ],
      match: (r, v) => (v === "yes") === r.active,
    },
  ],
  sort: { name: (r) => r.name, age: (r) => r.age },
  defaultSort: { key: "name", dir: "asc" },
};

const names = (rows: Row[]) => rows.map((r) => r.name);

describe("useListView", () => {
  it("applies the default sort", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    expect(names(result.current.rows)).toEqual([
      "Anna Ärmel",
      "Bernd Bauer",
      "ölaf Öhler",
      "Zoe Ziegler",
    ]);
    expect(result.current.total).toBe(4);
  });

  it("searches case-insensitively across every configured field", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    act(() => result.current.setSearch("kletter"));
    expect(names(result.current.rows)).toEqual(["Bernd Bauer", "Zoe Ziegler"]);
    // `total` stays the unfiltered count so the header can read "2 / 4".
    expect(result.current.total).toBe(4);
  });

  it("combines a search with a filter", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    act(() => result.current.setSearch("kletter"));
    act(() => result.current.setFilter("active", "yes"));
    expect(names(result.current.rows)).toEqual(["Bernd Bauer", "Zoe Ziegler"]);
    act(() => result.current.setFilter("active", "no"));
    expect(result.current.rows).toHaveLength(0);
  });

  it("treats an empty filter value as 'no filter'", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    act(() => result.current.setFilter("group", "Alpingruppe"));
    expect(result.current.rows).toHaveLength(2);
    act(() => result.current.setFilter("group", ""));
    expect(result.current.rows).toHaveLength(4);
    expect(result.current.active).toBe(false);
  });

  it("toggles a column between ascending and descending", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    act(() => result.current.toggleSort("age"));
    expect(result.current.sort).toEqual({ key: "age", dir: "asc" });
    // A null age sorts last regardless of direction.
    expect(names(result.current.rows)).toEqual([
      "ölaf Öhler",
      "Zoe Ziegler",
      "Anna Ärmel",
      "Bernd Bauer",
    ]);
    act(() => result.current.toggleSort("age"));
    expect(result.current.sort).toEqual({ key: "age", dir: "desc" });
    // The "empty sorts last" rule is inverted along with everything else, so a
    // null age leads when sorting descending. Asserted so the behaviour is a
    // decision rather than an accident.
    expect(names(result.current.rows)).toEqual([
      "Bernd Bauer",
      "Anna Ärmel",
      "Zoe Ziegler",
      "ölaf Öhler",
    ]);
  });

  it("sorts German text by locale, not by code point", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    // "ölaf" collates with "o", so it precedes "Zoe" — a code-point sort would
    // push the lowercase umlaut to the end.
    expect(names(result.current.rows).indexOf("ölaf Öhler")).toBeLessThan(
      names(result.current.rows).indexOf("Zoe Ziegler"),
    );
  });

  it("reports `active` once anything is applied, and clears it on reset", () => {
    const { result } = renderHook(() => useListView(ROWS, config));
    expect(result.current.active).toBe(false);
    act(() => result.current.setSearch("anna"));
    expect(result.current.active).toBe(true);
    act(() => result.current.reset());
    expect(result.current.active).toBe(false);
    expect(result.current.search).toBe("");
    expect(result.current.sort).toEqual(config.defaultSort);
    expect(result.current.rows).toHaveLength(4);
  });

  it("restores search, filters and sort for the same route", () => {
    const first = renderHook(() => useListView(ROWS, config));
    act(() => first.result.current.setSearch("kletter"));
    act(() => first.result.current.setFilter("active", "yes"));
    act(() => first.result.current.toggleSort("age"));
    first.unmount();

    // Same location => the state a user left behind comes back.
    const second = renderHook(() => useListView(ROWS, config));
    expect(second.result.current.search).toBe("kletter");
    expect(second.result.current.filterValues.active).toBe("yes");
    expect(second.result.current.sort).toEqual({ key: "age", dir: "asc" });
  });

  it("survives sessionStorage being unavailable", () => {
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error("denied");
    };
    try {
      const { result } = renderHook(() => useListView(ROWS, config));
      expect(result.current.rows).toHaveLength(4);
    } finally {
      Storage.prototype.getItem = getItem;
    }
  });

  it("survives sessionStorage refusing to be written to", () => {
    // Private-mode quota errors surface on setItem, not on read.
    const setItem = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error("quota");
    };
    try {
      const { result } = renderHook(() => useListView(ROWS, config));
      act(() => result.current.setSearch("Anna"));
      expect(result.current.rows).toHaveLength(1);
    } finally {
      Storage.prototype.setItem = setItem;
    }
  });

  it("re-derives when the underlying rows change", () => {
    const { result, rerender } = renderHook(({ rows }) => useListView(rows, config), {
      initialProps: { rows: ROWS },
    });
    expect(result.current.total).toBe(4);
    rerender({ rows: ROWS.slice(0, 2) });
    expect(result.current.total).toBe(2);
  });
});
