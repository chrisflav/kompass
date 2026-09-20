import type { ReactNode } from "react";

/**
 * One leg of a statement's route.
 *
 * A statement genuinely travels a sequence — you cannot decide the payout before
 * the receipts are in, and you cannot pay before the bookings reconcile — so the
 * rail is wayfinding, not decoration. Each leg carries the *figure that leg
 * settled* (`7 · 412,80 €`) rather than a bare step number, which lets a reader
 * spot a mismatch between two legs without opening either of them.
 */
export interface Etappe {
  id: string;
  /** Short mono label, e.g. "Belege". */
  label: string;
  /** The figure this leg settled; shown under the label. */
  readout?: ReactNode;
  state: "done" | "current" | "ahead";
  /** When false the leg is not reachable yet and renders inert. */
  reachable?: boolean;
}

/**
 * Horizontal rail of route legs.
 *
 * `numbered` prints a mono index per leg. Use it only where the order is
 * enforced (the treasurer's review, where a leg can be blocked); the leader's
 * submission legs are self-describing and read as bureaucracy when numbered.
 */
export function EtappenRail({
  etappen,
  onSelect,
  numbered = false,
  label = "Etappen",
}: {
  etappen: Etappe[];
  onSelect?: (id: string) => void;
  numbered?: boolean;
  label?: string;
}) {
  return (
    <nav className="etappen" aria-label={label}>
      <ol>
        {etappen.map((e, i) => {
          const reachable = e.reachable !== false && !!onSelect;
          const Tag = reachable ? "button" : "div";
          return (
            <li key={e.id} className={`etappe is-${e.state}`}>
              <Tag
                {...(reachable
                  ? { type: "button" as const, onClick: () => onSelect?.(e.id) }
                  : {})}
                className="etappe-body"
                aria-current={e.state === "current" ? "step" : undefined}
                aria-disabled={e.reachable === false ? true : undefined}
              >
                <span className="etappe-label">
                  {numbered && <span className="etappe-index">{String(i + 1).padStart(2, "0")}</span>}
                  {e.label}
                </span>
                <span className="etappe-readout">{e.readout ?? "—"}</span>
              </Tag>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * A single pre-flight condition shown before an irreversible action.
 *
 * Blockers are surfaced *before* the button rather than as a 422 toast after it,
 * so a leader never presses "Einreichen" into a rejection.
 */
export function Check({ ok, children }: { ok: boolean; children: ReactNode }) {
  return (
    <li className={`preflight-item ${ok ? "ok" : "bad"}`}>
      <span className="preflight-mark" aria-hidden="true">
        {ok ? "✓" : "✕"}
      </span>
      <span>{children}</span>
    </li>
  );
}

export function Preflight({ children }: { children: ReactNode }) {
  return <ul className="preflight">{children}</ul>;
}
