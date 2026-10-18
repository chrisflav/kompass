import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { Outlet, useNavigate } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation } from "../../api/hooks";
import { Badge, Button, Field, Modal, useToast } from "../../components/ui";
import {
  addDays,
  BASE,
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
 * specific piece, or a size of a type kept by size and a quantity. Kept in localStorage so it survives a reload; the period is
 * shared with the catalogue, whose availability it drives.
 */
export interface CartLine {
  key: string;
  productType?: { id: number; name: string };
  quantity: number;
  part?: { id: number; label: string; typeName: string };
  size?: { id: number; name: string; typeName: string };
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
  setQuantity: (key: string, quantity: number) => void;
  remove: (key: string) => void;
  clear: () => void;
}

const STORAGE_KEY = "kompass_material_cart";

function load(): CartState {
  const fallback = { lines: [], start: isoToday(), end: addDays(isoToday(), 1) };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return fallback;
    const stored = JSON.parse(raw) as CartState;
    // A period that has passed is no use; start again from today.
    if (!stored.start || stored.start < isoToday()) {
      return { ...stored, start: fallback.start, end: fallback.end };
    }
    return stored;
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
  const [state, setState] = useState<CartState>(load);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      // Storage may be unavailable (private mode); the cart then lives for the visit.
    }
  }, [state]);

  const cart: Cart = {
    ...state,
    setPeriod: (start, end) => setState((s) => ({ ...s, start, end: end < start ? start : end })),
    addType: (productType, quantity = 1) =>
      setState((s) => {
        const key = `t${productType.id}`;
        const existing = s.lines.find((l) => l.key === key);
        const lines = existing
          ? s.lines.map((l) => (l.key === key ? { ...l, quantity: l.quantity + quantity } : l))
          : [...s.lines, { key, productType, quantity }];
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

/** Cart lines with the sizes of one type gathered under its name. */
function groupLines(lines: CartLine[]): { title?: string; lines: CartLine[] }[] {
  const groups: { title?: string; lines: CartLine[] }[] = [];
  for (const line of lines) {
    const title = line.size?.typeName;
    const last = groups[groups.length - 1];
    if (title && last?.title === title) last.lines.push(line);
    else groups.push({ title, lines: [line] });
  }
  return groups;
}

/** The cart panel: the period, what is in it, whether it is free, and the two ways to get it. */
export function CartPanel() {
  const cart = useCart();
  const toast = useToast();
  const navigate = useNavigate();
  const [note, setNote] = useState("");
  const [borrowing, setBorrowing] = useState(false);
  const [check, setCheck] = useState<{ problems: string[]; groups: string[] } | null>(null);

  // Whether everything is free is asked as soon as the cart or its period
  // changes, once the input settles; there is no separate "check" step.
  const checkMutation = useApiMutation(
    () => unwrap(client.POST("/api/material/reservations/check", { body: body(cart) })),
    {
      onSuccess: (data) =>
        setCheck({ problems: data.problems, groups: data.approval_groups.map((g) => g.name) }),
      onError: () => setCheck(null),
    },
  );
  const fingerprint = JSON.stringify([cart.lines.map((l) => [l.key, l.quantity]), cart.start, cart.end]);
  useEffect(() => {
    setCheck(null);
    if (cart.lines.length === 0) return;
    const timer = setTimeout(() => checkMutation.mutate(undefined), 400);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fingerprint]);

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

  const line = (l: CartLine, name: ReactNode) => (
    <li key={l.key}>
      {l.part ? (
        <span className="cart-line-name">
          {l.part.typeName} <span className="mono">{l.part.label}</span>
        </span>
      ) : (
        <>
          <input
            type="number"
            min={1}
            className="cart-qty"
            aria-label={`Anzahl ${lineName(l)}`}
            value={l.quantity}
            onChange={(e) => cart.setQuantity(l.key, Number(e.target.value))}
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
                <li key={g.title} className="cart-group">
                  <span className="cart-group-title">{g.title}</span>
                  <ul>{g.lines.map((l) => line(l, `Größe ${l.size!.name}`))}</ul>
                </li>
              ) : (
                g.lines.map((l) => line(l, lineName(l)))
              ),
            )}
          </ul>
          <div className="cart-check" role="status">
            {checkMutation.isPending || !check ? (
              <span className="muted small">Prüft, ob alles frei ist…</span>
            ) : check.problems.length === 0 ? (
              <span className="small">
                <Badge tone="success">Alles frei</Badge>
              </span>
            ) : (
              check.problems.map((p) => (
                <p key={p} className="error small">
                  {p}
                </p>
              ))
            )}
            {check && check.groups.length > 0 && (
              <p className="small muted">Braucht die Freigabe von {check.groups.join(", ")}.</p>
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
                onClick={() => (inHand ? setBorrowing(true) : reserveToTake.mutate(undefined))}
              >
                Jetzt mitnehmen
              </Button>
            )}
          </div>
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
          onClose={() => {
            setPickup(null);
            done();
          }}
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
