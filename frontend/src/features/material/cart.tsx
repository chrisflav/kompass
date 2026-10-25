import { createContext, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation } from "../../api/hooks";
import { useMe } from "../../api/me";
import { Badge, Button, Field, Modal, useConfirmDialog, useToast } from "../../components/ui";
import {
  addDays,
  BASE,
  CountInput,
  errorText,
  isoToday,
  MATERIAL,
  ModalActions,
  PickupModal,
  type PartBrief,
  type ReservationOut,
} from "./shared";

/**
 * The cart: what the user is about to reserve or borrow, and for when.
 *
 * A line is a type and a quantity (the server picks the pieces), one
 * specific piece, or a size of a type kept by size and a quantity. A set of
 * types goes in as its member types, each a line of its own. Kept in
 * localStorage, per user, so it survives a reload but not a change of user on
 * a shared device; the period is shared with the catalogue, whose
 * availability it drives.
 */
export interface CartLine {
  key: string;
  productType?: { id: number; name: string };
  quantity: number;
  part?: { id: number; label: string; typeName: string };
  size?: { id: number; name: string; typeName: string };
  /**
   * The set a type line came with, and how many of the type one set holds: the
   * line is shown under the set's name and taken out with it. A line merged
   * with one added otherwise has none.
   */
  set?: { name: string; perSet: number };
}

interface CartState {
  lines: CartLine[];
  start: string;
  end: string;
}

interface Cart extends CartState {
  setPeriod: (start: string, end: string) => void;
  addType: (productType: { id: number; name: string }, quantity?: number) => void;
  addPart: (part: Pick<PartBrief, "id" | "label" | "product_type">) => void;
  /** Add ``quantity`` of each size, such as one set: ``per_set`` of every size. */
  addSizes: (typeName: string, sizes: { id: number; name: string; quantity: number }[]) => void;
  /** Add one set of a set type: ``quantity`` of each member type. */
  addSet: (setName: string, types: { id: number; name: string; quantity: number }[]) => void;
  /** Take one set out again: ``perSet`` of each of its lines. */
  removeSet: (setName: string) => void;
  setQuantity: (key: string, quantity: number) => void;
  remove: (key: string) => void;
  clear: () => void;
}

/** Where the cart of a user is kept. */
export function cartStorageKey(userId: number): string {
  return `kompass_material_cart:${userId}`;
}

/** Where the cart was kept before it was per user; dropped, as whose it was is unknown. */
const LEGACY_KEY = "kompass_material_cart";

type Ref = { id: number; name: string };
const isRef = (value: unknown): value is Ref =>
  typeof value === "object" &&
  value !== null &&
  typeof (value as Ref).id === "number" &&
  typeof (value as Ref).name === "string";

/**
 * A stored line, reduced to what a line holds. Older carts kept the whole
 * type (its pieces, calendar and sizes); anything unreadable is dropped.
 */
function readLine(raw: unknown): CartLine | null {
  if (typeof raw !== "object" || raw === null) return null;
  const l = raw as Partial<CartLine>;
  const quantity = typeof l.quantity === "number" && l.quantity >= 1 ? Math.floor(l.quantity) : 1;
  if (l.part && typeof l.part.id === "number") {
    const { id, label, typeName } = l.part;
    return { key: `p${id}`, quantity: 1, part: { id, label: String(label), typeName: String(typeName) } };
  }
  if (l.size && typeof l.size.id === "number") {
    const { id, name, typeName } = l.size;
    return { key: `s${id}`, quantity, size: { id, name: String(name), typeName: String(typeName) } };
  }
  if (isRef(l.productType)) {
    const { id, name } = l.productType;
    const set =
      l.set && typeof l.set.name === "string" && typeof l.set.perSet === "number" && l.set.perSet >= 1
        ? { set: { name: l.set.name, perSet: Math.floor(l.set.perSet) } }
        : {};
    return { key: `t${id}`, quantity, productType: { id, name }, ...set };
  }
  return null;
}

function load(storageKey: string | null): CartState {
  const fallback = { lines: [], start: isoToday(), end: addDays(isoToday(), 1) };
  if (!storageKey) return fallback;
  try {
    localStorage.removeItem(LEGACY_KEY);
    const raw = localStorage.getItem(storageKey);
    if (!raw) return fallback;
    const stored = JSON.parse(raw) as Partial<CartState>;
    const lines = (Array.isArray(stored.lines) ? stored.lines : [])
      .map(readLine)
      .filter((l): l is CartLine => l !== null);
    // A period that has passed is no use; start again from today.
    if (typeof stored.start !== "string" || typeof stored.end !== "string" || stored.start < isoToday()) {
      return { ...fallback, lines };
    }
    return { lines, start: stored.start, end: stored.end < stored.start ? stored.start : stored.end };
  } catch {
    return fallback;
  }
}

const CartContext = createContext<Cart | null>(null);

export function useCart(): Cart {
  const cart = useContext(CartContext);
  if (!cart) throw new Error("useCart outside CartProvider");
  return cart;
}

export function CartProvider({ children }: { children: ReactNode }) {
  const me = useMe();
  const storageKey = me.data ? cartStorageKey(me.data.user_id) : null;
  const [state, setState] = useState<CartState>(() => load(storageKey));
  // Once the user is known (or another one signs in) their own cart is loaded.
  const [loadedKey, setLoadedKey] = useState(storageKey);
  if (loadedKey !== storageKey) {
    setLoadedKey(storageKey);
    setState(load(storageKey));
  }
  useEffect(() => {
    if (!storageKey) return;
    try {
      localStorage.setItem(storageKey, JSON.stringify(state));
    } catch {
      // Storage may be unavailable (private mode); the cart then lives for the visit.
    }
  }, [state, storageKey]);

  const cart: Cart = {
    ...state,
    setPeriod: (start, end) => setState((s) => ({ ...s, start, end: end < start ? start : end })),
    addType: (productType, quantity = 1) =>
      setState((s) => {
        const key = `t${productType.id}`;
        const existing = s.lines.find((l) => l.key === key);
        const lines = existing
          ? s.lines.map((l) => (l.key === key ? { ...l, quantity: l.quantity + quantity, set: undefined } : l))
          : [...s.lines, { key, productType: { id: productType.id, name: productType.name }, quantity }];
        return { ...s, lines };
      }),
    addPart: (part) =>
      setState((s) => {
        const key = `p${part.id}`;
        if (s.lines.some((l) => l.key === key)) return s;
        const line = {
          key,
          quantity: 1,
          part: { id: part.id, label: part.label, typeName: part.product_type.name },
        };
        return { ...s, lines: [...s.lines, line] };
      }),
    addSizes: (typeName, sizes) =>
      setState((s) => {
        let lines = s.lines;
        for (const size of sizes) {
          if (size.quantity < 1) continue;
          const key = `s${size.id}`;
          lines = lines.some((l) => l.key === key)
            ? lines.map((l) => (l.key === key ? { ...l, quantity: l.quantity + size.quantity } : l))
            : [...lines, { key, quantity: size.quantity, size: { id: size.id, name: size.name, typeName } }];
        }
        return { ...s, lines };
      }),
    addSet: (setName, types) =>
      setState((s) => {
        let lines = s.lines;
        for (const type of types) {
          if (type.quantity < 1) continue;
          const key = `t${type.id}`;
          const set = { name: setName, perSet: type.quantity };
          lines = lines.some((l) => l.key === key)
            ? lines.map((l) =>
                l.key === key
                  ? {
                      ...l,
                      quantity: l.quantity + type.quantity,
                      // Another set's line, or one added on its own, is no longer this set's alone.
                      set: l.set?.name === setName ? l.set : undefined,
                    }
                  : l,
              )
            : [...lines, { key, quantity: type.quantity, productType: { id: type.id, name: type.name }, set }];
        }
        return { ...s, lines };
      }),
    removeSet: (setName) =>
      setState((s) => ({
        ...s,
        lines: s.lines
          .map((l) => (l.set?.name === setName ? { ...l, quantity: l.quantity - l.set.perSet } : l))
          .filter((l) => l.quantity >= 1),
      })),
    setQuantity: (key, quantity) =>
      setState((s) => ({
        ...s,
        lines: s.lines.map((l) => (l.key === key ? { ...l, quantity: Math.max(1, quantity) } : l)),
      })),
    remove: (key) => setState((s) => ({ ...s, lines: s.lines.filter((l) => l.key !== key) })),
    clear: () => setState((s) => ({ ...s, lines: [] })),
  };
  return <CartContext.Provider value={cart}>{children}</CartContext.Provider>;
}

/** What the check said for one state of the cart, its ``fingerprint``. */
interface CheckResult {
  fingerprint: string;
  problems: string[];
  /** The groups whose material needs their approval. */
  groups: string[];
  error?: string;
}

/** The material routes share one cart. */
export function CartLayout() {
  return (
    <CartProvider>
      <Outlet />
    </CartProvider>
  );
}

function body(cart: Cart, note = "") {
  return {
    start: cart.start,
    end: cart.end,
    note,
    lines: cart.lines.map((l) =>
      l.part
        ? { part: l.part.id, quantity: 1 }
        : l.size
          ? { size: l.size.id, quantity: l.quantity }
          : { product_type: l.productType!.id, quantity: l.quantity },
    ),
  };
}

/** The period of the cart, which the availability shown everywhere refers to. */
export function PeriodPicker() {
  const cart = useCart();
  return (
    <div className="field-pair">
      <Field label="Von">
        <input
          type="date"
          value={cart.start}
          min={isoToday()}
          onChange={(e) => e.target.value && cart.setPeriod(e.target.value, cart.end)}
        />
      </Field>
      <Field label="Bis">
        <input
          type="date"
          value={cart.end}
          min={cart.start}
          onChange={(e) => e.target.value && cart.setPeriod(cart.start, e.target.value)}
        />
      </Field>
    </div>
  );
}

/**
 * A material page with the cart beside it. The catalogue always shows it, as
 * it holds the period; other pages only once something is in it.
 */
export function WithCart({ always = false, children }: { always?: boolean; children: ReactNode }) {
  const cart = useCart();
  const shown = always || cart.lines.length > 0;
  // The same elements either way, so the page (an open tab, say) stays as it
  // is when the first piece goes into the cart.
  return (
    <div className={shown ? "material-layout" : undefined}>
      <div className="material-main">{children}</div>
      {shown && <CartPanel />}
    </div>
  );
}

/** Cart lines with the sizes of one type, or the types of one set, gathered under its name. */
function groupLines(lines: CartLine[]): { title?: string; isSet?: boolean; lines: CartLine[] }[] {
  const groups: { title?: string; isSet?: boolean; lines: CartLine[] }[] = [];
  const byTitle = new Map<string, (typeof groups)[number]>();
  for (const line of lines) {
    const title = line.size?.typeName ?? line.set?.name;
    const id = line.size ? `s:${title}` : `t:${title}`;
    const group = title ? byTitle.get(id) : undefined;
    if (group) group.lines.push(line);
    else {
      const created = { title, isSet: Boolean(line.set), lines: [line] };
      groups.push(created);
      if (title) byTitle.set(id, created);
    }
  }
  return groups;
}

/** The cart panel: the period, what is in it, whether it is free, and the two ways to get it. */
export function CartPanel() {
  const cart = useCart();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const navigate = useNavigate();
  const [note, setNote] = useState("");
  const [borrowing, setBorrowing] = useState(false);
  const [check, setCheck] = useState<CheckResult | null>(null);

  // Whether everything is free is asked as soon as the cart or its period
  // changes, once the input settles; there is no separate "check" step. Each
  // answer carries the cart it was for, and only one for the cart as it is
  // now is kept: a slower answer for an earlier cart cannot overwrite it.
  const fingerprint = JSON.stringify([cart.lines.map((l) => [l.key, l.quantity]), cart.start, cart.end]);
  const latest = useRef(fingerprint);
  const checkMutation = useApiMutation(
    (request: { fingerprint: string; body: ReturnType<typeof body> }) =>
      unwrap(client.POST("/api/material/reservations/check", { body: request.body })),
    {
      onSuccess: (data, request) =>
        request.fingerprint === latest.current &&
        setCheck({
          fingerprint: request.fingerprint,
          problems: data.problems,
          groups: data.approval_groups.map((g) => g.name),
        }),
      onError: (e, request) =>
        request.fingerprint === latest.current &&
        setCheck({
          fingerprint: request.fingerprint,
          problems: [],
          groups: [],
          // Something in the cart is gone: a piece, type or size deleted since.
          error:
            e instanceof ApiError && e.status === 404
              ? "Etwas im Korb gibt es nicht mehr. Nimm es heraus oder leere den Korb."
              : `Ob alles frei ist, ließ sich nicht prüfen: ${errorText(e)}`,
        }),
    },
  );
  useEffect(() => {
    latest.current = fingerprint;
    if (cart.lines.length === 0) return;
    const request = { fingerprint, body: body(cart) };
    const timer = setTimeout(() => checkMutation.mutate(request), 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint]);
  const current = check?.fingerprint === fingerprint ? check : null;
  // Material of other groups is only lent once they agree: it is reserved, not taken.
  const needsApproval = (current?.groups.length ?? 0) > 0;

  const done = () => {
    cart.clear();
    setCheck(null);
    setNote("");
    navigate(`${BASE}/mine`);
  };
  const reserve = useApiMutation(
    () => unwrap(client.POST("/api/material/reservations", { body: body(cart, note) })),
    {
      invalidate: [MATERIAL],
      onSuccess: (r) => {
        toast.success(r.status === "requested" ? "Angefragt." : "Reserviert.");
        done();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );

  // "Jetzt mitnehmen", from today on. With only specific pieces and sizes in
  // the cart they are taken straight away; "any 3 of a type" is reserved
  // first, then picked up, so the pieces taken can be confirmed by their ID.
  const [pickup, setPickup] = useState<ReservationOut | null>(null);
  const parts = cart.lines.filter((l) => l.part);
  const sizes = cart.lines.filter((l) => l.size);
  const inHand = parts.length + sizes.length === cart.lines.length;
  const reserveToTake = useApiMutation(
    () => unwrap(client.POST("/api/material/reservations", { body: body(cart, note) })),
    {
      invalidate: [MATERIAL],
      onSuccess: (r) => {
        if (r.status === "confirmed") {
          setPickup(r);
        } else {
          toast.success("Angefragt. Nach der Freigabe holst du es unter Mein Material ab.");
          done();
        }
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  // Not picked up after all: the reservation was only made to take it along,
  // so ask whether it should stand, to be picked up later, or go again.
  const discard = useApiMutation(
    (id: number) =>
      unwrap(
        client.POST("/api/material/reservations/{reservation_id}/cancel", {
          params: { path: { reservation_id: id } },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => toast.success("Nichts reserviert."),
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const notPickedUp = async (r: ReservationOut) => {
    setPickup(null);
    const drop = await confirm({
      title: "Nicht mitgenommen",
      message: "Soll die Reservierung bestehen bleiben, damit du es später abholst?",
      confirmLabel: "Reservierung verwerfen",
      cancelLabel: "Reservierung behalten",
      danger: true,
    });
    if (drop) {
      discard.mutate(r.id);
    } else {
      toast.success("Reserviert – abholen kannst du es unter Mein Material.");
      done();
    }
  };

  const line = (l: CartLine, name: ReactNode) => (
    <li key={l.key}>
      {l.part ? (
        <span className="cart-line-name">
          {l.part.typeName} <span className="mono">{l.part.label}</span>
        </span>
      ) : (
        <>
          <CountInput
            label={`Anzahl ${lineName(l)}`}
            min={1}
            value={l.quantity}
            onChange={(n) => cart.setQuantity(l.key, n)}
          />
          <span className="cart-line-name">{name}</span>
        </>
      )}
      <button
        type="button"
        className="btn ghost icon"
        aria-label={`${lineName(l)} entfernen`}
        onClick={() => cart.remove(l.key)}
      >
        ×
      </button>
    </li>
  );

  return (
    <aside className="cart" aria-label="Korb">
      <div className="cart-head">
        <h3>Korb</h3>
        {cart.lines.length > 0 && (
          <button type="button" className="link-button small" onClick={cart.clear}>
            leeren
          </button>
        )}
      </div>
      <PeriodPicker />
      {cart.lines.length === 0 ? (
        <p className="muted small">
          Leg Material in den Korb, um es für diesen Zeitraum zu reservieren oder gleich
          mitzunehmen.
        </p>
      ) : (
        <>
          <ul className="cart-lines">
            {groupLines(cart.lines).map((g) =>
              g.title ? (
                <li key={`${g.isSet ? "t" : "s"}:${g.title}`} className="cart-group">
                  <span className="cart-group-title">
                    {g.title}
                    {g.isSet && (
                      <button
                        type="button"
                        className="link-button small"
                        aria-label={`Satz ${g.title} entfernen`}
                        onClick={() => cart.removeSet(g.title!)}
                      >
                        Satz entfernen
                      </button>
                    )}
                  </span>
                  <ul>{g.lines.map((l) => line(l, l.size ? `Größe ${l.size.name}` : lineName(l)))}</ul>
                </li>
              ) : (
                g.lines.map((l) => line(l, lineName(l)))
              ),
            )}
          </ul>
          <div className="cart-check" role="status">
            {!current ? (
              <span className="muted small">Prüft, ob alles frei ist…</span>
            ) : current.error ? (
              <p className="error small">{current.error}</p>
            ) : current.problems.length === 0 ? (
              <span className="small">
                <Badge tone="success">Alles frei</Badge>
              </span>
            ) : (
              current.problems.map((p) => (
                <p key={p} className="error small">
                  {p}
                </p>
              ))
            )}
            {needsApproval && (
              <p className="small muted">Braucht die Freigabe von {current!.groups.join(", ")}.</p>
            )}
          </div>
          <Field label="Notiz">
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="z. B. Ausfahrt" />
          </Field>
          <div className="cart-actions">
            <Button busy={reserve.isPending} onClick={() => reserve.mutate(undefined)}>
              Reservieren
            </Button>
            {cart.start === isoToday() && (
              <Button
                variant="ghost"
                busy={reserveToTake.isPending}
                disabled={needsApproval}
                onClick={() => (inHand ? setBorrowing(true) : reserveToTake.mutate(undefined))}
              >
                Jetzt mitnehmen
              </Button>
            )}
          </div>
          {cart.start === isoToday() && needsApproval && (
            <p className="small muted">
              Material anderer Gruppen nimmst du erst nach der Freigabe mit: reservier es, und hol es
              dann unter Mein Material ab.
            </p>
          )}
        </>
      )}
      {borrowing && (
        <TakeModal
          partIds={parts.map((l) => l.part!.id)}
          sizes={sizes.map((l) => ({ size: l.size!.id, quantity: l.quantity }))}
          onClose={() => setBorrowing(false)}
          onDone={() => {
            setBorrowing(false);
            done();
          }}
        />
      )}
      {pickup && (
        <PickupModal
          reservation={pickup}
          onClose={() => notPickedUp(pickup)}
          onDone={() => {
            setPickup(null);
            done();
          }}
        />
      )}
    </aside>
  );
}

function lineName(line: CartLine): string {
  if (line.part) return `${line.part.typeName} ${line.part.label}`;
  return line.size ? `${line.size.typeName} ${line.size.name}` : line.productType!.name;
}

/** Take pieces on the spot: until when, or for good. */
export function TakeModal({
  partIds,
  sizes = [],
  borrower,
  onClose,
  onDone,
}: {
  partIds: number[];
  sizes?: { size: number; quantity: number }[];
  borrower?: number;
  onClose: () => void;
  onDone: () => void;
}) {
  const toast = useToast();
  const cart = useContext(CartContext);
  const [due, setDue] = useState(() => cart?.end ?? addDays(isoToday(), 1));
  const count = partIds.length + sizes.reduce((n, s) => n + s.quantity, 0);
  const [forGood, setForGood] = useState(false);
  // Counted sizes carry no holder, so they can only be taken until a day.
  const permanent = forGood && sizes.length === 0;
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/loans", {
          body: permanent
            ? { parts: partIds, sizes: [], permanent: true, borrower: borrower ?? null }
            : { parts: partIds, sizes, due, borrower: borrower ?? null, permanent: false },
        }),
      ),
    {
      invalidate: [MATERIAL],
      onSuccess: () => {
        toast.success("Mitgenommen. Viel Spaß!");
        onDone();
      },
      onError: (e) => toast.error(errorText(e)),
    },
  );
  return (
    <Modal title="Mitnehmen" onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(undefined);
        }}
      >
        <p>
          {count === 1 ? "1 Teil" : `${count} Teile`} — wie lange brauchst du es?
        </p>
        <fieldset className="choice">
          <legend>Wie lange?</legend>
          <label className="inline-check">
            <input type="radio" name="take-until" checked={!permanent} onChange={() => setForGood(false)} />
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
              required
            />
          </label>
          <label className="inline-check">
            <input
              type="radio"
              name="take-until"
              checked={permanent}
              disabled={sizes.length > 0}
              onChange={() => setForGood(true)}
            />
            dauerhaft
          </label>
        </fieldset>
        <ModalActions>
          <Button type="submit" busy={mutation.isPending}>
            Mitnehmen
          </Button>
          <Button variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </ModalActions>
      </form>
    </Modal>
  );
}
