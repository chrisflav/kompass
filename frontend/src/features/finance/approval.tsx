import { Badge, Button } from "../../components/ui";
import type { components } from "../../api/schema";

export type StatementApprovalOut = components["schemas"]["StatementApprovalOut"];
export type ApprovalConstraintOut = components["schemas"]["ApprovalConstraintOut"];

/**
 * The approval record, as a thing to read rather than a page to visit.
 *
 * It used to be its own route, beside the review pipeline — two doors into one
 * room, and the review pipeline's door was the one that paid the statement out.
 * The record now sits inside the review's last leg, where the signature is
 * given, and read-only on the statement's own page, where the person who handed
 * it in looks for what it is waiting for.
 *
 * What it shows comes from the section's rules: which signatures they ask for,
 * who may give them, who was excluded and by which forbid, who has signed, and
 * whether somebody went ahead without a signature. None of that is derived
 * here — the payload is assembled in one place on the server
 * (`finance.api.approval.approval_payload`) precisely so two renderings cannot
 * disagree about whether a statement is approved.
 */
export function ApprovalRecord({
  approval,
  onOverride,
}: {
  approval: StatementApprovalOut;
  /** When given, each open step offers an override; the caller owns the dialog. */
  onOverride?: (constraint: ApprovalConstraintOut) => void;
}) {
  if (approval.constraints.length === 0) {
    return (
      <p className="muted">Für diese Abrechnung verlangen die Regeln keine gesonderte Freigabe.</p>
    );
  }
  return (
    <>
      {/* One card per constraint: the state is said in words by the badge
          rather than in two colours, because there are more states than "done"
          and "not done" — it does not apply, nobody may sign, the rules could
          not say who. */}
      {approval.constraints.map((constraint) => (
        <div key={constraint.name} className="summary-card">
          <div className="summary-head">
            <span>{constraint.description || constraint.name}</span>
            <Badge tone={tone(constraint)}>{constraint.state_display}</Badge>
          </div>
          <ConstraintDetail constraint={constraint} />
          {onOverride && constraint.open && (
            <div className="row-actions">
              <Button variant="ghost" onClick={() => onOverride(constraint)}>
                Ohne Unterschrift freigeben
              </Button>
            </div>
          )}
        </div>
      ))}
      {approval.signatures.length > 0 && (
        <div className="freigabe-signatures">
          <span className="readout-caption">Unterschriften</span>
          <ul className="plain-list">
            {approval.signatures.map((signature, index) => (
              <li key={index}>
                {signature.member?.name ?? "unbekannte Person"} ·{" "}
                {new Date(signature.at).toLocaleString("de-DE")}
                {signature.note ? ` · ${signature.note}` : ""}
              </li>
            ))}
          </ul>
        </div>
      )}
    </>
  );
}

function tone(constraint: ApprovalConstraintOut) {
  if (!constraint.applicable) return "neutral" as const;
  if (constraint.overridden) return "warning" as const;
  if (constraint.satisfied) return "success" as const;
  return "info" as const;
}

/** Who may sign, who did, who was kept out — and, for an override, by whom. */
function ConstraintDetail({ constraint }: { constraint: ApprovalConstraintOut }) {
  const names = (people: { name: string }[]) => people.map((p) => p.name).join(", ");
  return (
    <dl className="summary-lines">
      <div>
        <dt>Verlangt</dt>
        <dd>
          {constraint.applicable
            ? `${constraint.required} Unterschrift${constraint.required === 1 ? "" : "en"}${
                constraint.missing ? `, noch ${constraint.missing} offen` : ""
              }`
            : "gilt für diese Abrechnung nicht"}
        </dd>
      </div>
      <div>
        <dt>Darf unterschreiben</dt>
        <dd>{constraint.eligible.length ? names(constraint.eligible) : "niemand"}</dd>
      </div>
      <div>
        <dt>Hat unterschrieben</dt>
        <dd>{constraint.signed_by.length ? names(constraint.signed_by) : "—"}</dd>
      </div>
      {constraint.excluded.length > 0 && (
        <div>
          <dt>Ausgeschlossen</dt>
          <dd>
            {constraint.excluded
              .map((e) => `${e.member?.name ?? "unbekannt"} (${e.forbid})`)
              .join(", ")}
          </dd>
        </div>
      )}
      {constraint.overridden && (
        <div>
          <dt>Übergangen von</dt>
          <dd>
            {constraint.overridden_by?.name ?? "unbekannt"}
            {constraint.override_reason ? ` · ${constraint.override_reason}` : ""}
          </dd>
        </div>
      )}
    </dl>
  );
}

/**
 * Where the statement stands, in one sentence.
 *
 * This is the sentence the two-door interface never said. Signing short of a
 * quorum used to answer "Statement is not ready to be confirmed." — a refusal,
 * over a signature that had just been taken — so the one thing a signer wanted
 * to know, how much is still missing and from which step, was never on screen.
 * It is read off the record after the signature, so it is what the server says
 * rather than what the client hoped.
 *
 * The open steps are *named* only where the rules ask for more than one step
 * at all: where they ask for exactly one there is nothing to disambiguate, the
 * card underneath says which it is, and naming it twice reads as ceremony —
 * which is the whole of Heidelberg's case.
 */
export function outstandingText(approval: StatementApprovalOut): string {
  const open = approval.constraints.filter((c) => c.open);
  if (open.length === 0) return "Alle Freigaben liegen vor.";
  const names = (steps: ApprovalConstraintOut[]) =>
    steps.map((c) => c.description || c.name).join(", ");
  // A step nobody may sign is not a step that is merely waiting: counting it
  // towards "noch eine Unterschrift" promises a signature that cannot be
  // given. The way out is an override, which the record offers on the step.
  const blocked = open.filter((c) => c.eligible.length === 0);
  if (blocked.length === open.length)
    return `Diese Abrechnung kommt nicht weiter: für ${names(blocked)} darf niemand unterschreiben.`;
  const missing = open.reduce((sum, c) => sum + c.missing, 0);
  const steps = approval.constraints.length > 1 ? `: ${names(open)}` : "";
  return missing === 1
    ? `Es fehlt noch eine Unterschrift${steps}.`
    : `Es fehlen noch ${missing} Unterschriften${steps}.`;
}
