import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type ReactNode,
} from "react";
import { createPortal } from "react-dom";
import { Link } from "react-router-dom";

import { downloadArtifact } from "../api/http";

/** Close the popover when a click/focus lands outside `ref`. */
function useOutsideClose(
  ref: React.RefObject<HTMLElement | null>,
  close: () => void,
  // A portalled dropdown is not a DOM descendant of its trigger, so without
  // this the mousedown on an option would close the menu and unmount the
  // button before its click could fire — the option would never be selectable.
  alsoInside?: React.RefObject<HTMLElement | null>,
) {
  useEffect(() => {
    function onDown(e: MouseEvent) {
      const target = e.target as Node;
      if (ref.current?.contains(target)) return;
      if (alsoInside?.current?.contains(target)) return;
      close();
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [ref, close, alsoInside]);
}

/**
 * A dropdown panel rendered into <body>, positioned against its trigger.
 *
 * Selects are used inside `.table-wrap`, which scrolls horizontally and
 * therefore clips vertically too — an in-flow dropdown was cut off, and on the
 * last row it stretched the scroll container instead of overlaying it. Fixed
 * positioning in a portal escapes every ancestor's overflow. It flips above the
 * trigger when there is not enough room below, and never runs off either edge.
 */
function AnchoredDropdown({
  anchorRef,
  panelRef,
  children,
}: {
  anchorRef: React.RefObject<HTMLElement | null>;
  panelRef: React.RefObject<HTMLDivElement>;
  children: ReactNode;
}) {
  const [style, setStyle] = useState<CSSProperties>({ visibility: "hidden" });

  useLayoutEffect(() => {
    const anchor = anchorRef.current;
    if (!anchor) return;
    const place = () => {
      const r = anchor.getBoundingClientRect();
      const width = Math.max(r.width, 200);
      const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
      const panelHeight = panelRef.current?.offsetHeight ?? 260;
      const openUp = window.innerHeight - r.bottom < panelHeight && r.top > panelHeight;
      setStyle({
        position: "fixed",
        width,
        left,
        ...(openUp
          ? { bottom: window.innerHeight - r.top + 4 }
          : { top: r.bottom + 4, maxHeight: window.innerHeight - r.bottom - 16 }),
      });
    };
    place();
    // `true` catches scrolls of any ancestor, including the table wrapper.
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [anchorRef, panelRef]);

  return createPortal(
    <div className="ms-dropdown is-anchored" ref={panelRef} style={style}>
      {children}
    </div>,
    document.body,
  );
}

/* --- state views --------------------------------------------------------- */

export function Spinner({ label = "Lädt…" }: { label?: string }) {
  return (
    <p className="muted state" role="status">
      {label}
    </p>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const msg = error instanceof Error ? error.message : "Ein Fehler ist aufgetreten.";
  return (
    <p className="error state" role="alert">
      {msg}
    </p>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return <p className="muted state">{children}</p>;
}

/**
 * Render the loading / error / empty / ready states of a TanStack Query result
 * uniformly. `children` only runs once `data` is present.
 */
export function QueryBoundary<T>({
  query,
  children,
  empty,
}: {
  query: { data?: T; isLoading: boolean; error: Error | null };
  children: (data: T) => ReactNode;
  empty?: ReactNode;
}) {
  if (query.isLoading) return <Spinner />;
  if (query.error) return <ErrorState error={query.error} />;
  if (query.data === undefined) return <ErrorState error={new Error("Keine Daten.")} />;
  if (empty !== undefined && Array.isArray(query.data) && query.data.length === 0) {
    return <EmptyState>{empty}</EmptyState>;
  }
  return <>{children(query.data)}</>;
}

/* --- buttons ------------------------------------------------------------- */

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "ghost" | "danger";
  busy?: boolean;
};

export function Button({
  variant = "primary",
  busy,
  children,
  type,
  onClick,
  ...rest
}: ButtonProps) {
  // Default to type="button" so a button never submits a form by accident.
  const resolvedType = type ?? "button";
  return (
    <button
      // Keep the label while busy: swapping it for "…" collapses the button's
      // width, which reflowed every row it sat in on each quick mutation.
      className={`btn ${variant}${busy ? " is-busy" : ""}`}
      type={resolvedType}
      disabled={busy || rest.disabled}
      onClick={(e) => {
        // Guards the React reconciliation race: when a non-submit button's
        // onClick re-renders it into a submit button (e.g. "Bearbeiten" →
        // "Speichern") within the same click, the click's default action would
        // otherwise submit the now-submit button. preventDefault neutralises it
        // (a real type="button" has no default action, so this is a no-op there).
        if (resolvedType !== "submit") e.preventDefault();
        onClick?.(e);
      }}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Button that downloads a document artifact, surfacing errors as a toast. */
export function DownloadButton({
  path,
  method = "GET",
  body,
  filename,
  children,
}: {
  path: string;
  method?: "GET" | "POST";
  body?: unknown;
  filename?: string;
  children: ReactNode;
}) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  return (
    <Button
      type="button"
      variant="ghost"
      busy={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await downloadArtifact(path, { method, body, filename });
        } catch (e) {
          toast.error(e instanceof Error ? e.message : "Download fehlgeschlagen.");
        } finally {
          setBusy(false);
        }
      }}
    >
      {children}
    </Button>
  );
}

/* --- badges -------------------------------------------------------------- */

export function Badge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

/* --- tables -------------------------------------------------------------- */

export interface Column<T> {
  header: string;
  cell: (row: T) => ReactNode;
  width?: string;
  /** Column key for sorting (mirrors the admin's sortable list columns). */
  sortKey?: string;
}

export type SortState = { key: string; dir: "asc" | "desc" } | null;

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  onRowClick,
  empty = "Keine Einträge.",
  sort,
  onSort,
  selection,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string | number;
  onRowClick?: (row: T) => void;
  empty?: ReactNode;
  sort?: SortState;
  onSort?: (key: string) => void;
  /** Enables the leading checkbox column (the admin's bulk-action selector). */
  selection?: {
    selected: Set<string | number>;
    onToggle: (key: string | number) => void;
    onToggleAll: (keys: (string | number)[]) => void;
  };
}) {
  if (rows.length === 0) return <EmptyState>{empty}</EmptyState>;
  const keys = rows.map(rowKey);
  const allSelected = keys.length > 0 && keys.every((k) => selection?.selected.has(k));
  return (
    <div className="table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {selection && (
              <th className="select-col">
                <input
                  type="checkbox"
                  checked={allSelected}
                  aria-label="Alle auswählen"
                  onChange={() => selection.onToggleAll(keys)}
                />
              </th>
            )}
            {columns.map((c) => {
              const sortable = onSort && c.sortKey;
              const active = sort && c.sortKey === sort.key;
              return (
                <th key={c.header} style={c.width ? { width: c.width } : undefined}>
                  {sortable ? (
                    <button
                      type="button"
                      className={`th-sort${active ? " active" : ""}`}
                      onClick={() => onSort!(c.sortKey!)}
                    >
                      {c.header}
                      <span className="sort-arrow">
                        {active ? (sort!.dir === "asc" ? "▲" : "▼") : "↕"}
                      </span>
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const key = rowKey(row);
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                className={onRowClick ? "clickable" : undefined}
              >
                {selection && (
                  // Stop the click here: selecting a row must not also open it.
                  <td className="select-col" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selection.selected.has(key)}
                      aria-label="Zeile auswählen"
                      onChange={() => selection.onToggle(key)}
                    />
                  </td>
                )}
                {columns.map((c) => (
                  <td key={c.header}>{c.cell(row)}</td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/**
 * Bulk-selection state for a list, mirroring the admin changelist's action bar.
 * Selection is kept as row keys so it survives re-sorting and re-filtering.
 */
export function useRowSelection<K extends string | number>() {
  const [selected, setSelected] = useState<Set<K>>(() => new Set());
  const toggle = useCallback((key: K) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }, []);
  const toggleAll = useCallback((keys: K[]) => {
    setSelected((prev) => {
      const allOn = keys.length > 0 && keys.every((k) => prev.has(k));
      return allOn ? new Set() : new Set(keys);
    });
  }, []);
  const clear = useCallback(() => setSelected(new Set()), []);
  return { selected, toggle, toggleAll, clear, count: selected.size };
}

/* --- tabs ---------------------------------------------------------------- */

export interface Tab {
  id: string;
  label: ReactNode;
  content: ReactNode;
}

/**
 * Tabbed sections for a detail/edit view (mirrors the JET admin's tabbed
 * fieldsets + inlines). ALL panels stay mounted (inactive ones hidden) so that
 * shared edit-form draft state and inline row state survive tab switches, and
 * so a single Save persists every tab. Tab buttons are type="button" — they
 * live inside the parent <form> and must never submit it.
 */
export function Tabs({
  tabs,
  active: controlledActive,
  onChange,
}: {
  tabs: Tab[];
  /** Controlled active tab. Omit to let Tabs keep the state itself. */
  active?: string;
  /** Called instead of the internal setter when the tab is controlled. */
  onChange?: (id: string) => void;
}) {
  const [uncontrolledActive, setActive] = useState(() => tabs[0]?.id);
  const active = controlledActive ?? uncontrolledActive;
  // An unknown id (a hand-edited URL, a tab that has gone away) falls back to
  // the first tab rather than rendering an empty panel.
  const activeId = tabs.some((t) => t.id === active) ? active : tabs[0]?.id;

  // Surface validation errors on the tab that contains them: every panel stays
  // mounted, so after each render we scan each panel's DOM for a `.field-error`
  // and flag its tab red — the user sees which tab to open without hunting.
  const panelRefs = useRef<Record<string, HTMLDivElement | null>>({});
  const [errorTabs, setErrorTabs] = useState<Set<string>>(() => new Set());
  useLayoutEffect(() => {
    const next = new Set<string>();
    for (const t of tabs) {
      if (panelRefs.current[t.id]?.querySelector(".field-error")) next.add(t.id);
    }
    const changed =
      next.size !== errorTabs.size || [...next].some((id) => !errorTabs.has(id));
    if (changed) setErrorTabs(next);
  });

  return (
    <div className="tabs">
      <div className="tab-bar" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={t.id === activeId}
            className={`tab${t.id === activeId ? " active" : ""}${errorTabs.has(t.id) ? " has-error" : ""}`}
            onClick={() => (onChange ? onChange(t.id) : setActive(t.id))}
          >
            {t.label}
          </button>
        ))}
      </div>
      {tabs.map((t) => (
        <div
          key={t.id}
          ref={(el) => {
            panelRefs.current[t.id] = el;
          }}
          role="tabpanel"
          hidden={t.id !== activeId}
          className="tab-panel"
        >
          {t.content}
        </div>
      ))}
    </div>
  );
}

/* --- detail list --------------------------------------------------------- */

export function DetailList({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl className="detail">
      {items.map(([label, value]) => (
        <div className="detail-row" key={label}>
          <dt>{label}</dt>
          <dd>{value ?? "—"}</dd>
        </div>
      ))}
    </dl>
  );
}

export interface DetailRow {
  label: string;
  /** Read-only display for view mode. */
  value: ReactNode;
  /** Input(s) shown in this row's cell when editing. Omit for read-only rows. */
  edit?: ReactNode;
  /** Backend field name; a matching validation error is shown under this row. */
  field?: string;
  /** Help text shown under the input while editing (recovered model help_text). */
  hint?: string;
}

/**
 * A detail list whose structure is identical in view and edit mode: editing
 * only replaces the cell contents of rows that declare an ``edit`` control with
 * that control; every other row stays exactly as displayed. Per-field
 * validation errors (keyed by ``row.field``) render under the offending input.
 */
export function EditableDetail({
  rows,
  editing,
  errors,
}: {
  rows: DetailRow[];
  editing: boolean;
  errors?: Record<string, string[]>;
}) {
  return (
    <dl className="detail">
      {rows.map((row) => {
        const rowErrors = editing && row.field && errors ? errors[row.field] : undefined;
        return (
          <div
            className={rowErrors && rowErrors.length ? "detail-row has-error" : "detail-row"}
            key={row.label}
          >
            <dt>{row.label}</dt>
            <dd>
              {editing && row.edit !== undefined ? row.edit : (row.value ?? "—")}
              {editing && row.edit !== undefined && row.hint && (
                <div className="field-hint">{row.hint}</div>
              )}
              {rowErrors && rowErrors.length > 0 && (
                <div className="field-error">{rowErrors.join(" ")}</div>
              )}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}

/* --- form fields --------------------------------------------------------- */

export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  return (
    <label className="field">
      <span className="field-label">{label}</span>
      {children}
      {hint && <span className="field-hint">{hint}</span>}
    </label>
  );
}

/* --- formatting ----------------------------------------------------------- */

/** Render an amount as German currency (comma decimal), e.g. ``1.234,50 €``.
 *
 * The finance surface used to carry four copies of a dot-decimal formatter, so
 * the same amount read ``40.00 €`` on one page and ``40,00 €`` on the next. */
export function euro(value: number | null | undefined): string {
  return `${(Number(value) || 0).toLocaleString("de-DE", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })} €`;
}

/** Render an ISO date (``YYYY-MM-DD``) as a German date, tolerating null.
 *
 * Dates used to be shown raw in material, Termine and the CMS while members and
 * excursions formatted theirs, so the same value looked different depending on
 * which page you were on. */
export function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

/* --- document title ------------------------------------------------------ */

/** Sets the browser tab title to `<title> · Kompass` (or just `Kompass`) for as
 *  long as the calling component is mounted. Used by `PageHeader` for every
 *  list/detail page, and directly on the pages that don't render a header. */
export function useDocumentTitle(title?: string) {
  useEffect(() => {
    document.title = title ? `${title} · Kompass` : "Kompass";
  }, [title]);
}

/* --- breadcrumbs & page header ------------------------------------------- */

export interface Crumb {
  label: ReactNode;
  /** Link target; the last crumb usually omits it (it's the current page). */
  to?: string;
}

/** Navigation trail; the final crumb renders as the page's heading. */
export function Breadcrumbs({ items }: { items: Crumb[] }) {
  return (
    <nav className="breadcrumbs" aria-label="Navigationspfad">
      {items.map((c, i) => {
        const last = i === items.length - 1;
        return (
          <span className="crumb" key={i}>
            {c.to && !last ? (
              <Link to={c.to}>{c.label}</Link>
            ) : (
              <span className={last ? "crumb-current" : undefined}>{c.label}</span>
            )}
            {!last && <span className="crumb-sep">/</span>}
          </span>
        );
      })}
    </nav>
  );
}

export function PageHeader({
  title,
  subtitle,
  actions,
  breadcrumbs,
}: {
  title?: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  breadcrumbs?: Crumb[];
}) {
  // Keep the browser tab title in step with navigation: use the last breadcrumb
  // (the current page) if it's a plain string, otherwise the `title` prop.
  const lastCrumb = breadcrumbs?.[breadcrumbs.length - 1]?.label;
  useDocumentTitle(typeof lastCrumb === "string" ? lastCrumb : title);

  return (
    <div className="page-header">
      <div>
        {breadcrumbs && breadcrumbs.length > 0 ? (
          <Breadcrumbs items={breadcrumbs} />
        ) : (
          title && <h2>{title}</h2>
        )}
        {subtitle && <p className="muted">{subtitle}</p>}
      </div>
      {actions && <div className="page-actions">{actions}</div>}
    </div>
  );
}

/* --- dropdown menu ------------------------------------------------------- */

/** A button that toggles a dropdown of items (e.g. grouped document actions). */
export function Menu({ label, children }: { label: ReactNode; children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null!);
  useOutsideClose(ref, () => setOpen(false), panelRef);
  return (
    <div className="menu" ref={ref}>
      <Button type="button" variant="ghost" onClick={() => setOpen((o) => !o)}>
        {label} ▾
      </Button>
      {open && (
        <div className="menu-dropdown" onClick={() => setOpen(false)}>
          {children}
        </div>
      )}
    </div>
  );
}

/* --- searchable multi-select (badges) ------------------------------------ */

export interface MultiOption {
  value: number;
  label: string;
}

/**
 * Multi-select rendered as a row of removable badges plus a searchable dropdown.
 * Operates on numeric ids. Drop-in for the old checkbox-list MultiSelect
 * (``searchable``/``emptyText`` accepted for compatibility, always searchable).
 */
export function MultiSelect({
  options,
  selected,
  onChange,
  placeholder = "Auswählen…",
  emptyText = "Keine Einträge.",
}: {
  options: MultiOption[];
  selected: number[];
  onChange: (next: number[]) => void;
  searchable?: boolean;
  placeholder?: string;
  emptyText?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null!);
  useOutsideClose(ref, () => setOpen(false), panelRef);

  const selectedSet = new Set(selected);
  const byValue = new Map(options.map((o) => [o.value, o.label]));
  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? options.filter((o) => o.label.toLowerCase().includes(needle))
    : options;

  const toggle = (v: number) =>
    onChange(selectedSet.has(v) ? selected.filter((x) => x !== v) : [...selected, v]);

  return (
    <div className="multiselect" ref={ref}>
      <div className="ms-badges">
        {selected.map((v) => (
          <span className="badge ms-badge" key={v}>
            {byValue.get(v) ?? v}
            <button
              type="button"
              className="ms-remove"
              aria-label="Entfernen"
              onClick={() => toggle(v)}
            >
              ×
            </button>
          </span>
        ))}
        <button type="button" className="ms-toggle" onClick={() => setOpen((o) => !o)}>
          + {placeholder}
        </button>
      </div>
      {open && (
        <AnchoredDropdown anchorRef={ref} panelRef={panelRef}>
          <input
            className="ms-search"
            type="search"
            autoFocus
            placeholder="Suchen…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="ms-options">
            {filtered.length === 0 ? (
              <div className="muted small ms-empty">{emptyText}</div>
            ) : (
              filtered.map((o) => (
                <button
                  type="button"
                  key={o.value}
                  className={selectedSet.has(o.value) ? "ms-opt selected" : "ms-opt"}
                  onClick={() => toggle(o.value)}
                >
                  <span>{o.label}</span>
                  {selectedSet.has(o.value) && <span className="ms-check">✓</span>}
                </button>
              ))
            )}
          </div>
        </AnchoredDropdown>
      )}
    </div>
  );
}

/* --- searchable single-select (filters) ---------------------------------- */

/**
 * A searchable single-select rendered as a trigger button that always shows the
 * current selection (so it's clear what is being filtered), plus a dropdown with
 * a search box and a clear ("alle") option. Values are strings; "" means unset.
 */
export function SearchableSelect({
  value,
  onChange,
  options,
  label,
  allLabel = "alle",
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
  /** Prefix shown on the trigger, e.g. "Gruppe". */
  label: string;
  allLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null!);
  useOutsideClose(ref, () => setOpen(false), panelRef);

  const current = options.find((o) => o.value === value);
  const needle = q.trim().toLowerCase();
  const filtered = needle
    ? options.filter((o) => o.label.toLowerCase().includes(needle))
    : options;

  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
    setQ("");
  };

  return (
    <div className="searchselect" ref={ref}>
      <button
        type="button"
        className={value ? "ss-trigger active" : "ss-trigger"}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="ss-label">{label}:</span>{" "}
        <span className="ss-value">{current ? current.label : allLabel}</span>
        <span className="ss-caret">▾</span>
      </button>
      {open && (
        <AnchoredDropdown anchorRef={ref} panelRef={panelRef}>
          <input
            className="ms-search"
            type="search"
            autoFocus
            placeholder="Suchen…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="ms-options">
            <button
              type="button"
              className={value === "" ? "ms-opt selected" : "ms-opt"}
              onClick={() => pick("")}
            >
              <span>{allLabel}</span>
              {value === "" && <span className="ms-check">✓</span>}
            </button>
            {filtered.map((o) => (
              <button
                type="button"
                key={o.value}
                className={o.value === value ? "ms-opt selected" : "ms-opt"}
                onClick={() => pick(o.value)}
              >
                <span>{o.label}</span>
                {o.value === value && <span className="ms-check">✓</span>}
              </button>
            ))}
          </div>
        </AnchoredDropdown>
      )}
    </div>
  );
}

/* --- searchable single-select (form fields) ------------------------------ */

/**
 * A form single-select styled like {@link MultiSelect} / {@link SearchableSelect}
 * (a trigger showing the current value + a searchable dropdown). Drop-in for a
 * native <select>: string value, "" = unset. Set ``allowEmpty`` to offer a
 * clear option.
 */
export function Select({
  value,
  onChange,
  options,
  placeholder = "Auswählen…",
  allowEmpty = false,
  emptyLabel = "—",
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string | number; label: string }[];
  placeholder?: string;
  allowEmpty?: boolean;
  emptyLabel?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const panelRef = useRef<HTMLDivElement>(null!);
  useOutsideClose(ref, () => setOpen(false), panelRef);

  const opts = options.map((o) => ({ value: String(o.value), label: o.label }));
  const current = opts.find((o) => o.value === value);
  const needle = q.trim().toLowerCase();
  const filtered = needle ? opts.filter((o) => o.label.toLowerCase().includes(needle)) : opts;
  const pick = (v: string) => {
    onChange(v);
    setOpen(false);
    setQ("");
  };

  return (
    <div className="searchselect ss-field" ref={ref}>
      <button type="button" className="ss-trigger" onClick={() => setOpen((o) => !o)}>
        <span className={current ? "ss-value" : "muted"}>
          {current ? current.label : placeholder}
        </span>
        <span className="ss-caret">▾</span>
      </button>
      {open && (
        <AnchoredDropdown anchorRef={ref} panelRef={panelRef}>
          <input
            className="ms-search"
            type="search"
            autoFocus
            placeholder="Suchen…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
          <div className="ms-options">
            {allowEmpty && (
              <button
                type="button"
                className={value === "" ? "ms-opt selected" : "ms-opt"}
                onClick={() => pick("")}
              >
                <span>{emptyLabel}</span>
                {value === "" && <span className="ms-check">✓</span>}
              </button>
            )}
            {filtered.map((o) => (
              <button
                type="button"
                key={o.value}
                className={o.value === value ? "ms-opt selected" : "ms-opt"}
                onClick={() => pick(o.value)}
              >
                <span>{o.label}</span>
                {o.value === value && <span className="ms-check">✓</span>}
              </button>
            ))}
          </div>
        </AnchoredDropdown>
      )}
    </div>
  );
}

/* --- modal / confirm ----------------------------------------------------- */

export function Modal({
  title,
  onClose,
  children,
  size = "md",
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  /** Dialog width: sm for confirmations, md (default) for forms, lg for wide forms. */
  size?: "sm" | "md" | "lg";
}) {
  // Rendered via a portal to <body> so the dialog is never nested inside a page
  // <form> — a modal button (incl. the × / type=submit save) can't accidentally
  // submit an outer form, and it always overlays regardless of layout context.
  // The portal only breaks the *DOM* nesting though: React replays events along
  // the component tree, so a submit inside the dialog would still reach the
  // onSubmit of the page form this modal is rendered from. Stop it here — a
  // dialog is its own surface and never submits what is behind it.
  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        className={`modal ${size}`}
        onClick={(e) => e.stopPropagation()}
        onSubmit={(e) => e.stopPropagation()}
        role="dialog"
        aria-label={title}
      >
        <div className="modal-header">
          <h3>{title}</h3>
          <button
            type="button"
            className="btn ghost icon"
            onClick={onClose}
            aria-label="Schließen"
          >
            ×
          </button>
        </div>
        <div className="modal-body">{children}</div>
      </div>
    </div>,
    document.body,
  );
}

/* --- confirm dialog (global) --------------------------------------------- */

interface ConfirmOptions {
  message: ReactNode;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
}

type ConfirmFn = (opts: ConfirmOptions | string) => Promise<boolean>;

const ConfirmContext = createContext<ConfirmFn | null>(null);

/**
 * App-wide styled confirmation dialog — replaces window.confirm/alert. Usage:
 *   const confirm = useConfirmDialog();
 *   if (await confirm("Wirklich löschen?")) remove();
 */
export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<
    (ConfirmOptions & { resolve: (v: boolean) => void }) | null
  >(null);

  const confirm = useCallback<ConfirmFn>((opts) => {
    const normalized = typeof opts === "string" ? { message: opts } : opts;
    return new Promise<boolean>((resolve) => setState({ ...normalized, resolve }));
  }, []);

  const settle = (value: boolean) => {
    state?.resolve(value);
    setState(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <Modal title={state.title ?? "Bestätigen"} onClose={() => settle(false)} size="sm">
          <div className="stack">
            <p>{state.message}</p>
            <div className="row-actions">
              <Button
                type="button"
                variant={state.danger ? "danger" : "primary"}
                onClick={() => settle(true)}
              >
                {state.confirmLabel ?? "Bestätigen"}
              </Button>
              <Button type="button" variant="ghost" onClick={() => settle(false)}>
                {state.cancelLabel ?? "Abbrechen"}
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirmDialog(): ConfirmFn {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error("useConfirmDialog must be used within ConfirmProvider");
  return ctx;
}

/* --- toasts -------------------------------------------------------------- */

interface Toast {
  id: number;
  message: string;
  tone: "success" | "error";
}

interface ToastApi {
  success: (message: string) => void;
  error: (message: string) => void;
}

const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  // Auto-dismiss timers, so a pending one cannot fire after this provider is
  // gone (it would set state on an unmounted tree).
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  useEffect(() => () => timers.current.forEach(clearTimeout), []);

  const push = useCallback((message: string, tone: "success" | "error") => {
    // Derive a stable-enough id from the current queue length + timestamp is not
    // available deterministically here; use an incrementing ref via functional
    // update instead.
    setToasts((prev) => {
      const id = (prev[prev.length - 1]?.id ?? 0) + 1;
      const next = [...prev, { id, message, tone }];
      // Errors linger longer than confirmations — they carry more to read and
      // are more costly to miss. Either can be dismissed early with a click.
      const ttl = tone === "error" ? 7000 : 4000;
      timers.current.push(
        setTimeout(() => setToasts((cur) => cur.filter((t) => t.id !== id)), ttl),
      );
      return next;
    });
  }, []);

  const dismiss = useCallback(
    (id: number) => setToasts((cur) => cur.filter((t) => t.id !== id)),
    [],
  );

  const api: ToastApi = {
    success: (m) => push(m, "success"),
    error: (m) => push(m, "error"),
  };

  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="toast-stack">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`toast ${t.tone}`}
            role={t.tone === "error" ? "alert" : "status"}
            onClick={() => dismiss(t.id)}
            title="Zum Ausblenden klicken"
          >
            <span className="toast-tag">{t.tone === "success" ? "Erledigt" : "Fehler"}</span>
            <span className="toast-msg">{t.message}</span>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}
