import { useEffect, useMemo, useState } from "react";

import { Button, SearchableSelect, type SortState } from "./ui";

/** Persist list search/filter/sort per route so back-navigation restores it. */
interface PersistedState {
  search: string;
  filterValues: Record<string, string>;
  sort: SortState;
}

function loadState(key: string): PersistedState | null {
  try {
    const raw = sessionStorage.getItem(key);
    return raw ? (JSON.parse(raw) as PersistedState) : null;
  } catch {
    return null;
  }
}

function saveState(key: string, state: PersistedState) {
  try {
    sessionStorage.setItem(key, JSON.stringify(state));
  } catch {
    /* storage unavailable / quota — non-fatal */
  }
}

/**
 * Client-side list controls (search / filter / sort) mirroring the Django admin
 * list page. The SPA fetches the full list a user may see, so filtering and
 * sorting happen in-memory — instant, and no server query params needed.
 */

export interface FilterDef<T> {
  key: string;
  label: string;
  options: { value: string; label: string }[];
  /** Whether `row` matches the selected filter `value`. */
  match: (row: T, value: string) => boolean;
}

export interface ListViewConfig<T> {
  /** Values to full-text search across (case-insensitive substring). */
  search?: (row: T) => (string | number | null | undefined)[];
  filters?: FilterDef<T>[];
  /** sortKey → value accessor for that column. */
  sort?: Record<string, (row: T) => string | number | boolean | null | undefined>;
  defaultSort?: SortState;
}

export interface ListView<T> {
  rows: T[];
  total: number;
  search: string;
  setSearch: (v: string) => void;
  filterValues: Record<string, string>;
  setFilter: (key: string, value: string) => void;
  sort: SortState;
  toggleSort: (key: string) => void;
  /** True when a search term or any filter is active. */
  active: boolean;
  /** Clear search + all filters (and reset sort to the default). */
  reset: () => void;
  config: ListViewConfig<T>;
}

function compare(a: unknown, b: unknown): number {
  const an = a === null || a === undefined || a === "";
  const bn = b === null || b === undefined || b === "";
  if (an && bn) return 0;
  if (an) return 1; // empty sorts last
  if (bn) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  if (typeof a === "boolean" && typeof b === "boolean") return a === b ? 0 : a ? 1 : -1;
  return String(a).localeCompare(String(b), "de", { numeric: true, sensitivity: "base" });
}

export function useListView<T>(rows: T[], config: ListViewConfig<T>): ListView<T> {
  // Persist per list route so navigating into a row and back (browser back)
  // restores the search text, active filters and sort column.
  const storageKey =
    "listview:" + (typeof window !== "undefined" ? window.location.pathname : "");
  const [saved] = useState(() => loadState(storageKey));
  const [search, setSearch] = useState(() => saved?.search ?? "");
  const [filterValues, setFilterValues] = useState<Record<string, string>>(
    () => saved?.filterValues ?? {},
  );
  const [sort, setSort] = useState<SortState>(() => saved?.sort ?? config.defaultSort ?? null);

  useEffect(() => {
    saveState(storageKey, { search, filterValues, sort });
  }, [storageKey, search, filterValues, sort]);

  const setFilter = (key: string, value: string) =>
    setFilterValues((s) => ({ ...s, [key]: value }));

  const toggleSort = (key: string) =>
    setSort((cur) =>
      cur && cur.key === key
        ? { key, dir: cur.dir === "asc" ? "desc" : "asc" }
        : { key, dir: "asc" },
    );

  const result = useMemo(() => {
    let out = rows;
    const q = search.trim().toLowerCase();
    if (q && config.search) {
      out = out.filter((r) =>
        config.search!(r).some((f) => (f ?? "").toString().toLowerCase().includes(q)),
      );
    }
    for (const f of config.filters ?? []) {
      const val = filterValues[f.key];
      if (val) out = out.filter((r) => f.match(r, val));
    }
    if (sort && config.sort?.[sort.key]) {
      const acc = config.sort[sort.key];
      out = [...out].sort((a, b) => compare(acc(a), acc(b)) * (sort.dir === "asc" ? 1 : -1));
    }
    return out;
  }, [rows, search, filterValues, sort, config]);

  const active = search.trim() !== "" || Object.values(filterValues).some(Boolean);
  const reset = () => {
    setSearch("");
    setFilterValues({});
    setSort(config.defaultSort ?? null);
  };

  return {
    rows: result,
    total: rows.length,
    search,
    setSearch,
    filterValues,
    setFilter,
    sort,
    toggleSort,
    active,
    reset,
    config,
  };
}

/** Search box + filter dropdowns for a {@link useListView} result. */
export function ListToolbar<T>({ view }: { view: ListView<T> }) {
  const { config } = view;
  if (!config.search && !(config.filters && config.filters.length)) return null;
  return (
    <div className="list-toolbar">
      {config.search && (
        <input
          className="list-search"
          type="search"
          placeholder="Suchen…"
          value={view.search}
          onChange={(e) => view.setSearch(e.target.value)}
        />
      )}
      {(config.filters ?? []).map((f) => (
        <SearchableSelect
          key={f.key}
          label={f.label}
          value={view.filterValues[f.key] ?? ""}
          onChange={(v) => view.setFilter(f.key, v)}
          options={f.options}
        />
      ))}
      {view.active && (
        <Button type="button" variant="ghost" onClick={view.reset}>
          Filter zurücksetzen
        </Button>
      )}
    </div>
  );
}
