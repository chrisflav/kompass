import { useState, type ReactNode } from "react";
import { Link, NavLink } from "react-router-dom";

import { getToken } from "../../auth";
import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { usePermissions } from "../../api/me";
import { Badge, Button, Field, Modal, Select, useToast } from "../../components/ui";
import type { components } from "../../api/schema";

export type ProductTypeCard = components["schemas"]["ProductTypeCard"];
export type ProductTypeOut = components["schemas"]["ProductTypeOut"];
export type PartBrief = components["schemas"]["PartBrief"];
export type PartOut = components["schemas"]["PartOut"];
export type ReservationOut = components["schemas"]["ReservationOut"];
export type LoanOut = components["schemas"]["LoanOut"];
export type SizeOut = components["schemas"]["SizeOut"];
export type SizeRef = components["schemas"]["SizeRef"];
export type LocationOut = components["schemas"]["LocationOut"];

export const BASE = "/kompass/material";

/** Every material query key starts with this, so one invalidation refreshes them all. */
export const MATERIAL = ["material"];

/** Who may manage the inventory, and who may lend for others. */
export function useMaterialRoles() {
  const { can, canAny } = usePermissions();
  return {
    inventory: can("equipment.manage_inventory"),
    lending: can("equipment.manage_lending"),
    manager: canAny("equipment.manage_inventory", "equipment.manage_lending"),
  };
}

/** An absolute URL for a media path the API returns ("/media/…"). */
export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined;
  return path.startsWith("/") ? `${API_BASE}${path}` : path;
}

/** POST a multipart form (an upload) and parse the JSON answer. */
export async function postMultipart<T>(
  path: string,
  fields: Record<string, string | File | null | undefined>,
): Promise<T> {
  const data = new FormData();
  for (const [key, value] of Object.entries(fields)) {
    if (value !== null && value !== undefined && value !== "") data.append(key, value);
  }
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}` },
    body: data,
  });
  if (!res.ok) {
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

/** "2026-07-12" for a date, from its local year, month and day (not UTC). */
function localIso(date: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

export function isoToday(): string {
  return localIso(new Date());
}

export function addDays(iso: string, days: number): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return localIso(new Date(y, m - 1, d + days));
}

/** "12.07." for a date in the current year, "12.07.2027" otherwise. */
export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return y === String(new Date().getFullYear()) ? `${d}.${m}.` : `${d}.${m}.${y}`;
}

export function period(start: string, end: string): string {
  return start === end ? shortDate(start) : `${shortDate(start)} – ${shortDate(end)}`;
}

const PART_STATUS: Record<string, [string, "success" | "warning" | "danger" | "neutral"]> = {
  active: ["aktiv", "success"],
  inspection_due: ["Prüfung fällig", "warning"],
  retired: ["ausgesondert", "neutral"],
};

export function PartStatus({ status }: { status: string }) {
  const [label, tone] = PART_STATUS[status] ?? [status, "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}

const RESERVATION_STATUS: Record<
  string,
  [string, "success" | "warning" | "danger" | "neutral" | "info"]
> = {
  requested: ["angefragt", "warning"],
  confirmed: ["bestätigt", "success"],
  declined: ["abgelehnt", "danger"],
  cancelled: ["storniert", "neutral"],
  fulfilled: ["abgeholt", "info"],
};

export function ReservationStatus({ status }: { status: string }) {
  const [label, tone] = RESERVATION_STATUS[status] ?? [status, "neutral"];
  return <Badge tone={tone}>{label}</Badge>;
}

/**
 * Where a piece is, in one line: lent to someone until a day, with someone for
 * good, at a place, or nowhere recorded.
 */
export function whereabouts(
  part: Pick<PartBrief, "holder" | "location"> & { lent_until?: string | null },
): string {
  if (part.lent_until) {
    const until = `bis ${shortDate(part.lent_until)}`;
    return part.holder ? `an ${part.holder.name} verliehen ${until}` : `verliehen ${until}`;
  }
  if (part.holder) return `dauerhaft bei ${part.holder.name}`;
  if (part.location) return part.location.name;
  return "—";
}

/** {@link whereabouts}, in red once the return date has passed. */
export function Whereabouts({
  part,
}: {
  part: Pick<PartBrief, "holder" | "location"> & { lent_until?: string | null };
}) {
  const text = whereabouts(part);
  return part.lent_until && part.lent_until < isoToday() ? <Badge tone="danger">{text}</Badge> : <>{text}</>;
}

export function PartLink({ part }: { part: Pick<PartBrief, "id" | "label" | "product_type"> }) {
  return (
    <Link to={`${BASE}/parts/${part.id}`}>
      {part.product_type.name} <span className="mono">{part.label}</span>
    </Link>
  );
}

/** "Friends 2": a size with its type. */
export function sizeName(size: SizeRef): string {
  return `${size.product_type.name} ${size.name}`;
}

/** "3 × Steigeisen, 1 × Gurt, 2 × Friends 2" */
export function linesText(reservation: Pick<ReservationOut, "lines" | "sizes">): string {
  return [
    ...reservation.lines.map((l) => `${l.count} × ${l.product_type.name}`),
    ...reservation.sizes.map((s) => `${s.quantity} × ${sizeName(s.size)}`),
  ].join(", ");
}

/**
 * A number input for a count from ``min`` (0 by default) to ``max``. What is
 * typed stays as it is while editing, so the field can be cleared to type a
 * new number; it is clamped once the field is left.
 */
export function CountInput({
  value,
  min = 0,
  max,
  label,
  onChange,
}: {
  value: number;
  min?: number;
  max?: number;
  label: string;
  onChange: (value: number) => void;
}) {
  const [draft, setDraft] = useState<string | null>(null);
  const clamp = (n: number) => Math.max(min, max === undefined ? n : Math.min(max, n));
  return (
    <input
      type="number"
      className="cart-qty"
      min={min}
      max={max}
      aria-label={label}
      value={draft ?? value}
      onChange={(e) => {
        setDraft(e.target.value);
        if (e.target.value !== "" && !Number.isNaN(Number(e.target.value))) {
          onChange(clamp(Number(e.target.value)));
        }
      }}
      onBlur={() => setDraft(null)}
    />
  );
}

export function useLocations() {
  return useApiQuery(["material", "locations"], () =>
    unwrap(client.GET("/api/material/locations")),
  );
}

export function useTags() {
  return useApiQuery(["material", "categories"], () =>
    unwrap(client.GET("/api/material/categories")),
  );
}

/** Everyone material can be handed over to: every confirmed member, not only those one may see. */
export function useRecipients() {
  return useApiQuery(["material", "recipients"], () => unwrap(client.GET("/api/material/recipients")));
}

export function errorText(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  return error instanceof Error ? error.message : "Ein Fehler ist aufgetreten.";
}

/**
 * A type's or piece's photo, which opens large when clicked. Given an upload
 * ``path`` (in edit mode), a button over the photo, shown on hover or focus,
 * replaces it straight away instead.
 */
export function PhotoFrame({
  src,
  path,
  title,
}: {
  src: string | null | undefined;
  path?: string;
  /** What the photo shows, as the title of the enlarged view. */
  title: string;
}) {
  const toast = useToast();
  const [enlarged, setEnlarged] = useState(false);
  const upload = useApiMutation((file: File) => postMultipart(path!, { photo: file }), {
    invalidate: [MATERIAL],
    onSuccess: () => toast.success("Foto gespeichert."),
    onError: (e) => toast.error(errorText(e)),
  });
  return (
    <div className="material-detail-photo">
      {src && !path ? (
        <button
          type="button"
          className="photo-zoom"
          aria-label="Foto vergrößern"
          onClick={() => setEnlarged(true)}
        >
          <img src={mediaUrl(src)} alt="" />
        </button>
      ) : src ? (
        <img src={mediaUrl(src)} alt="" />
      ) : (
        <span aria-hidden>◇</span>
      )}
      {enlarged && src && (
        <Modal title={title} onClose={() => setEnlarged(false)} size="lg">
          <img className="photo-large" src={mediaUrl(src)} alt={title} />
        </Modal>
      )}
      {path && (
        <label className={`btn ghost photo-upload${upload.isPending ? " is-busy" : ""}`}>
          {src ? "Foto ändern" : "Foto hochladen"}
          <input
            type="file"
            accept="image/*"
            className="photo-upload-input"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
              e.target.value = "";
            }}
          />
        </label>
      )}
    </div>
  );
}

const STOCK_TABS = [
  { to: `${BASE}/stock`, label: "Teile" },
  { to: `${BASE}/psa`, label: "PSA-Prüfungen", inventory: true },
  { to: `${BASE}/deficits`, label: "Wunschliste", inventory: true },
  { to: `${BASE}/locations`, label: "Orte" },
  { to: `${BASE}/categories`, label: "Tags" },
];

/**
 * The material team's Bestand: its pages, one tab each. The PSA register and
 * the wishlist are the inventory's; those who only lend do not see them.
 */
export function StockTabs() {
  const roles = useMaterialRoles();
  return (
    <nav className="tab-bar" aria-label="Bestand">
      {STOCK_TABS.filter((t) => !t.inventory || roles.inventory).map((t) => (
        <NavLink key={t.to} to={t.to} end className={({ isActive }) => `tab${isActive ? " active" : ""}`}>
          {t.label}
        </NavLink>
      ))}
    </nav>
  );
}

/** A titled section of an overview page, headed like the dashboard's sections. */
export function Section({
  title,
  actions,
  children,
}: {
  title: ReactNode;
  /** Buttons on the right of the heading, such as those for a selection. */
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="dash-section">
      <div className="dash-head">
        <h3 className="eyebrow">{title}</h3>
        {actions && <div className="row-actions">{actions}</div>}
      </div>
      {children}
    </section>
  );
}

/** Actions in a modal's foot. */
export function ModalActions({ children }: { children: ReactNode }) {
  return <div className="row-actions">{children}</div>;
}

/* --- deficits -------------------------------------------------------------- */

type DeficitProps = {
  productType?: { id: number; name: string };
  start?: string;
  end?: string;
};

/** "Defizit melden" as a button, or inline in a sentence with ``link``. */
export function DeficitButton({ link = false, ...props }: DeficitProps & { link?: boolean }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      {link ? (
        <button type="button" className="link-button" onClick={() => setOpen(true)}>
          Defizit melden
        </button>
      ) : (
        <Button variant="ghost" onClick={() => setOpen(true)}>
          Defizit melden
        </Button>
      )}
      {open && <DeficitModal {...props} onClose={() => setOpen(false)} />}
    </>
  );
}

/** "Defizit melden": puts a wish on the Materialwarte's list. */
export function DeficitModal({ productType, start, end, onClose }: DeficitProps & { onClose: () => void }) {
  const toast = useToast();
  const [form, setForm] = useState({
    text: "",
    wanted_from: start ?? "",
    wanted_to: end ?? "",
    comment: "",
  });
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/deficits", {
          body: {
            product_type: productType?.id ?? null,
            text: form.text,
            wanted_from: form.wanted_from || null,
            wanted_to: form.wanted_to || null,
            comment: form.comment,
          },
        }),
      ),
    {
      invalidate: [["material", "deficits"]],
      onSuccess: () => {
        toast.success("Danke, das Materialteam kümmert sich darum.");
        onClose();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title="Defizit melden" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(undefined);
        }}
      >
        {productType ? (
          <p>
            Es gibt nicht genug <strong>{productType.name}</strong>.
          </p>
        ) : (
          <Field label="Was fehlt?">
            <input value={form.text} onChange={(e) => setForm({ ...form, text: e.target.value })} required />
          </Field>
        )}
        <div className="field-pair">
          <Field label="Gebraucht ab">
            <input
              type="date"
              value={form.wanted_from}
              onChange={(e) => setForm({ ...form, wanted_from: e.target.value })}
            />
          </Field>
          <Field label="bis">
            <input
              type="date"
              value={form.wanted_to}
              onChange={(e) => setForm({ ...form, wanted_to: e.target.value })}
            />
          </Field>
        </div>
        <Field label="Kommentar">
          <textarea rows={3} value={form.comment} onChange={(e) => setForm({ ...form, comment: e.target.value })} />
        </Field>
        <ModalActions>
          <Button type="submit" busy={mutation.isPending}>
            Melden
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}

/* --- handing over --------------------------------------------------------- */

/**
 * "Übergeben": hand pieces to a person, until a day or for good, or put them
 * at a place (issue #449). Until a day it is a loan with reminders; for good
 * the person just has them, and they stay bookable. At the desk (``desk``),
 * pieces are added by their ID and counted sizes can be lent too: only to a
 * person and until a day, as they carry no holder.
 */
export function HandOverModal({
  parts: initial,
  desk = false,
  onClose,
  onDone,
}: {
  parts: PartBrief[];
  desk?: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const recipients = useRecipients();
  const locations = useLocations();
  const sizeList = useApiQuery(["material", "sizes"], () => unwrap(client.GET("/api/material/sizes")), {
    enabled: desk,
  });
  const [parts, setParts] = useState<PartBrief[]>(initial);
  const [counts, setCounts] = useState<Record<number, number>>({});
  const [chosen, setTarget] = useState("");
  const lentUntil = initial.map((p) => p.lent_until).find(Boolean);
  const [forGood, setForGood] = useState(!desk && !lentUntil);
  // A lent piece is passed on until its return day, or today once that has passed.
  const [due, setDue] = useState(() =>
    lentUntil ? (lentUntil < isoToday() ? isoToday() : lentUntil) : addDays(isoToday(), 1),
  );
  const [code, setCode] = useState("");
  const [sizeChoice, setSizeChoice] = useState("");
  const sizeById = new Map((sizeList.data ?? []).map((s) => [s.id, s]));
  const sizes = Object.entries(counts)
    .map(([id, quantity]) => ({ size: Number(id), quantity }))
    .filter((s) => s.quantity > 0);
  // Counted sizes go to a person, never to a place.
  const target = sizes.length > 0 && chosen.startsWith("l:") ? "" : chosen;
  const toPerson = target.startsWith("m:");
  // Counted sizes carry no holder, so they can only be lent until a day.
  const permanent = forGood && sizes.length === 0;
  const count = parts.length + sizes.reduce((n, s) => n + s.quantity, 0);

  const lookup = useApiMutation(
    (value: string) =>
      unwrap(client.GET("/api/material/parts/lookup", { params: { query: { code: value } } })),
    {
      onSuccess: (part) => {
        if (!parts.some((p) => p.id === part.id)) setParts([...parts, part]);
        setCode("");
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const mutation = useApiMutation(
    () => {
      const [kind, id] = target.split(":");
      return unwrap(
        client.POST("/api/material/parts/transfer", {
          body: {
            parts: parts.map((p) => p.id),
            sizes,
            member: kind === "m" ? Number(id) : null,
            location: kind === "l" ? Number(id) : null,
            due: toPerson && !permanent ? due : null,
          },
        }),
      );
    },
    {
      invalidate: [MATERIAL],
      onSuccess: (data) => {
        toast.success("Übergeben.");
        data.warnings.forEach((w) => toast.error(w));
        onDone();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const options = [
    ...(recipients.data ?? []).map((m) => ({ value: `m:${m.id}`, label: m.name })),
    ...(sizes.length > 0
      ? []
      : (locations.data ?? []).map((l) => ({ value: `l:${l.id}`, label: `${l.name} (Ort)` }))),
  ];
  return (
    <Modal
      title={count === 0 ? "Übergeben" : count === 1 ? "1 Teil übergeben" : `${count} Teile übergeben`}
      onClose={onClose}
    >
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          if (target && count > 0) mutation.mutate(undefined);
        }}
      >
        <Field label="An">
          <Select
            value={target}
            onChange={setTarget}
            options={options}
            placeholder={sizes.length > 0 ? "Person wählen…" : "Person oder Ort wählen…"}
          />
        </Field>
        {sizes.length > 0 && (
          <p className="muted small">Größen ohne ID gehen nur an eine Person, bis zu einem Tag.</p>
        )}
        {desk && (
          <>
            <Field label="Teile mit ID">
              <div className="lookup-row">
                <input
                  aria-label="Teil per ID"
                  placeholder="z. B. E1351"
                  value={code}
                  onChange={(e) => setCode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      if (code.trim()) lookup.mutate(code.trim());
                    }
                  }}
                />
                <Button variant="ghost" busy={lookup.isPending} onClick={() => code.trim() && lookup.mutate(code.trim())}>
                  Hinzufügen
                </Button>
              </div>
            </Field>
            <Field label="Größen ohne ID">
              <Select
                value={sizeChoice}
                onChange={(v) => {
                  if (v) setCounts({ ...counts, [Number(v)]: (counts[Number(v)] ?? 0) + 1 });
                  setSizeChoice("");
                }}
                placeholder="Größe hinzufügen…"
                options={(sizeList.data ?? []).map((s) => ({ value: s.id, label: `${s.product_type.name} ${s.name}` }))}
              />
            </Field>
          </>
        )}
        <ul className="check-list">
          {parts.map((p) => (
            <li key={p.id}>
              {p.product_type.name} <span className="mono">{p.label}</span>
            </li>
          ))}
          {Object.keys(counts).map((id) => {
            const size = sizeById.get(Number(id));
            if (!size) return null;
            const name = `${size.product_type.name} ${size.name}`;
            return (
              <li key={`s${id}`} className="row-actions">
                <CountInput
                  label={`Anzahl ${name}`}
                  value={counts[Number(id)]}
                  onChange={(n) => setCounts({ ...counts, [Number(id)]: n })}
                />
                {name}
              </li>
            );
          })}
        </ul>
        {toPerson && (
          <fieldset className="choice">
            <legend>Wie lange?</legend>
            <label className="inline-check">
              <input type="radio" name="handover-until" checked={!permanent} onChange={() => setForGood(false)} />
              bis
              <input
                type="date"
                aria-label="Rückgabe bis"
                value={due}
                min={isoToday()}
                onChange={(e) => {
                  setDue(e.target.value);
                  setForGood(false);
                }}
              />
            </label>
            <label className="inline-check">
              <input
                type="radio"
                name="handover-until"
                checked={permanent}
                disabled={sizes.length > 0}
                onChange={() => setForGood(true)}
              />
              dauerhaft
            </label>
            <p className="muted small">
              {permanent
                ? "Bleibt reservierbar: wer es bucht, bittet um rechtzeitige Rückgabe."
                : "Eine Ausleihe mit Erinnerung vor der Rückgabe."}
            </p>
          </fieldset>
        )}
        <ModalActions>
          <Button type="submit" busy={mutation.isPending} disabled={!target || count === 0}>
            Übergeben
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}

/* --- returning ------------------------------------------------------------- */

/** Lent pieces of a size, still out: ``id`` is the lent size of the loan. */
export interface OutstandingSize {
  id: number;
  size: SizeRef;
  quantity: number;
}

/** Give pieces back, each to its home or to one chosen place, flagging any for inspection. */
export function ReturnModal({
  parts,
  sizes = [],
  onClose,
  onDone,
}: {
  parts: PartBrief[];
  sizes?: OutstandingSize[];
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const locations = useLocations();
  const [location, setLocation] = useState("");
  const [flagged, setFlagged] = useState<Set<number>>(() => new Set());
  const [counts, setCounts] = useState<Record<number, number>>(() =>
    Object.fromEntries(sizes.map((s) => [s.id, s.quantity])),
  );
  const pieces = parts.length + sizes.reduce((n, s) => n + s.quantity, 0);
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/returns", {
          body: {
            parts: parts.map((p) => p.id),
            sizes: sizes.map((s) => ({ lent: s.id, quantity: counts[s.id] ?? 0 })),
            location: location ? Number(location) : null,
            flagged: [...flagged],
          },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Zurückgegeben.");
        onDone();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title={pieces === 1 ? "1 Teil zurückgeben" : `${pieces} Teile zurückgeben`} onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(undefined);
        }}
      >
        <p className="muted">
          Leg jedes Teil zurück, bevor du bestätigst. Markiere, was beschädigt ist: es wird vor
          dem nächsten Verleih geprüft.
        </p>
        <ul className="check-list">
          {parts.map((p) => (
            <li key={p.id}>
              <span>
                {p.product_type.name} <span className="mono">{p.label}</span>
              </span>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={flagged.has(p.id)}
                  onChange={() => {
                    const next = new Set(flagged);
                    if (next.has(p.id)) next.delete(p.id);
                    else next.add(p.id);
                    setFlagged(next);
                  }}
                />
                beschädigt
              </label>
            </li>
          ))}
          {sizes.map((s) => (
            <li key={`s${s.id}`}>
              <span>{sizeName(s.size)}</span>
              <span className="row-actions">
                <CountInput
                  label={`Anzahl ${sizeName(s.size)}`}
                  value={counts[s.id] ?? 0}
                  max={s.quantity}
                  onChange={(n) => setCounts({ ...counts, [s.id]: n })}
                />
                <span className="muted small">von {s.quantity}</span>
              </span>
            </li>
          ))}
        </ul>
        <Field label="Zurück nach">
          <Select
            value={location}
            onChange={setLocation}
            allowEmpty
            emptyLabel="an den Stammort"
            placeholder="an den Stammort"
            options={(locations.data ?? []).map((l) => ({ value: l.id, label: l.name }))}
          />
        </Field>
        <ModalActions>
          <Button type="submit" busy={mutation.isPending}>
            Rückgabe bestätigen
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}

/* --- picking up ------------------------------------------------------------ */

/**
 * Hand out a reservation: its allocated pieces are pre-ticked, and any other
 * piece found in the cupboard can be added by its ID — it then stands in for an
 * allocated piece of the same type.
 */
export function PickupModal({
  reservation,
  forBorrower = false,
  onClose,
  onDone,
}: {
  reservation: ReservationOut;
  /** The desk hands out for the borrower rather than to itself. */
  forBorrower?: boolean;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const [pieces, setPieces] = useState<PartBrief[]>(reservation.parts);
  const [picked, setPicked] = useState<Set<number>>(
    () => new Set(reservation.parts.map((p) => p.id)),
  );
  const [counts, setCounts] = useState<Record<number, number>>(() =>
    Object.fromEntries(reservation.sizes.map((s) => [s.size.id, s.quantity])),
  );
  const total = picked.size + Object.values(counts).reduce((n, c) => n + c, 0);
  const sized = Object.values(counts).some((c) => c > 0);
  const [forGood, setForGood] = useState(false);
  const [code, setCode] = useState("");
  const lookup = useApiMutation(
    (value: string) =>
      unwrap(client.GET("/api/material/parts/lookup", { params: { query: { code: value } } })),
    {
      onSuccess: (part) => {
        if (!pieces.some((p) => p.id === part.id)) setPieces([...pieces, part]);
        setPicked(new Set([...picked, part.id]));
        setCode("");
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const lend = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/loans", {
          body: {
            parts: [...picked],
            sizes: reservation.sizes.map((s) => ({ size: s.size.id, quantity: counts[s.size.id] ?? 0 })),
            reservation: reservation.id,
            borrower: forBorrower ? reservation.borrower.id : null,
            permanent: forGood && !sized,
          },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Ausgegeben.");
        onDone();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title={`Abholen: ${period(reservation.start, reservation.end)}`} onClose={onClose}>
      <div className="stack">
        <p className="muted">{linesText(reservation)}</p>
        <ul className="check-list">
          {pieces.map((p) => (
            <li key={p.id}>
              <label className="inline-check">
                <input
                  type="checkbox"
                  checked={picked.has(p.id)}
                  onChange={() => {
                    const next = new Set(picked);
                    if (next.has(p.id)) next.delete(p.id);
                    else next.add(p.id);
                    setPicked(next);
                  }}
                />
                {p.product_type.name} <span className="mono">{p.label}</span>
              </label>
              <span className="muted small">{whereabouts(p)}</span>
            </li>
          ))}
          {reservation.sizes.map((s) => (
            <li key={`s${s.size.id}`}>
              <span>{sizeName(s.size)}</span>
              <span className="row-actions">
                <CountInput
                  label={`Anzahl ${sizeName(s.size)}`}
                  value={counts[s.size.id] ?? 0}
                  max={s.quantity}
                  onChange={(n) => setCounts({ ...counts, [s.size.id]: n })}
                />
                <span className="muted small">von {s.quantity}</span>
              </span>
            </li>
          ))}
        </ul>
        <form
          className="lookup-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (code.trim()) lookup.mutate(code.trim());
          }}
        >
          <input
            aria-label="Anderes Teil per ID"
            placeholder="Anderes Teil: ID eingeben"
            value={code}
            onChange={(e) => setCode(e.target.value)}
          />
          <Button type="submit" variant="ghost" busy={lookup.isPending}>
            Hinzufügen
          </Button>
        </form>
        <label className="inline-check">
          <input
            type="checkbox"
            checked={forGood && !sized}
            disabled={sized}
            onChange={(e) => setForGood(e.target.checked)}
          />
          dauerhaft behalten (sonst zurück bis {shortDate(reservation.end)})
        </label>
        <ModalActions>
          <Button busy={lend.isPending} disabled={total === 0} onClick={() => lend.mutate(undefined)}>
            {total === 1 ? "1 Teil ausgeben" : `${total} Teile ausgeben`}
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </div>
    </Modal>
  );
}
