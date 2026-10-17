import { useState } from "react";
import { useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { usePermissions } from "../../api/me";
import {
  Badge,
  Button,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type StatementApprovalOut = components["schemas"]["StatementApprovalOut"];
type ApprovalConstraintOut = components["schemas"]["ApprovalConstraintOut"];

const STATEMENTS = "/kompass/finance/statements";

/**
 * Who still has to sign a statement off, and who has.
 *
 * The approval engine has been complete since the rules engine landed: the
 * section's rules say who must sign (`Ruleset.approval`), the constraints are
 * frozen beside the payout at submission, eligibility is re-asked against
 * today, and `GET …/approval` reports all of it. None of it was rendered
 * anywhere, so a signer who had since lost the capability, an excluded signer
 * and the reason they were excluded, and an override and who made it, were all
 * facts that existed only in JSON.
 *
 * Reading is open to anybody who may see the statement — the person who handed
 * it in wants to know what it is waiting for. The two actions are not: signing
 * goes through `approve_obj` (the capability *and* the rules' own routing,
 * which is what `may_approve` in the payload answers), and an override needs
 * the treasurer's permission and a reason on the record.
 */
export function StatementApprovalPage() {
  const { id } = useParams();
  const statementId = Number(id);
  const query = useApiQuery(["finance", "statements", statementId, "approval"], () =>
    unwrap(
      client.GET("/api/finance/statements/{statement_id}/approval", {
        params: { path: { statement_id: statementId } },
      }),
    ),
  );
  return (
    <div className="flow">
      <PageHeader
        breadcrumbs={[
          { label: "Abrechnungen", to: STATEMENTS },
          { label: "Abrechnung", to: `${STATEMENTS}/${statementId}` },
          { label: "Freigabe" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(approval) => <Approval statementId={statementId} approval={approval} />}
      </QueryBoundary>
    </div>
  );
}

function tone(constraint: ApprovalConstraintOut) {
  if (!constraint.applicable) return "neutral" as const;
  if (constraint.overridden) return "warning" as const;
  if (constraint.satisfied) return "success" as const;
  return "info" as const;
}

function Approval({
  statementId,
  approval,
}: {
  statementId: number;
  approval: StatementApprovalOut;
}) {
  const toast = useToast();
  const { can } = usePermissions();
  const [overriding, setOverriding] = useState<ApprovalConstraintOut | null>(null);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<string[]>([]);

  const invalidate = [
    ["finance", "statements"],
    ["finance", "statements", statementId],
    ["finance", "statements", statementId, "approval"],
    ["finance", "statements", statementId, "transactions"],
  ];

  const approveM = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/approve", {
          params: { path: { statement_id: statementId } },
          body: { note: "" },
        }),
      ),
    {
      invalidate,
      onSuccess: () => toast.success("Freigabe erteilt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const overrideM = useApiMutation(
    (vars: { name: string; reason: string }) =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/override-approval", {
          params: { path: { statement_id: statementId } },
          body: vars,
        }),
      ),
    {
      invalidate,
      onSuccess: () => {
        toast.success("Schritt übergangen und vermerkt.");
        setOverriding(null);
        setReason("");
      },
      onError: (e: Error) => {
        // A refused override answers 422 with the reason it was refused — the
        // dialog says so rather than closing as though it had worked.
        if (e instanceof ApiError) setErrors(e.fieldErrors.__all__ ?? [e.message]);
        else setErrors([e.message]);
        toast.error(e.message);
      },
    },
  );

  const mayOverride = can("finance.process_statementsubmitted");

  return (
    <>
      <section className="flow-step">
        <h2 className="flow-title">Freigabe</h2>
        <p className="flow-lead">
          {approval.approved
            ? "Alle Freigaben liegen vor."
            : "Diese Unterschriften verlangen die Regeln der Sektion, bevor ausgezahlt wird."}
        </p>

        {approval.constraints.length === 0 ? (
          <p className="muted">
            Für diese Abrechnung verlangen die Regeln keine gesonderte Freigabe.
          </p>
        ) : (
          <ul className="preflight">
            {approval.constraints.map((constraint) => (
              <li
                key={constraint.name}
                className={`preflight-item ${constraint.open ? "bad" : "ok"}`}
              >
                <span className="preflight-mark" aria-hidden="true">
                  {constraint.open ? "✕" : "✓"}
                </span>
                <div>
                  <div className="summary-head">
                    <span>{constraint.description || constraint.name}</span>
                    <Badge tone={tone(constraint)}>{constraint.state_display}</Badge>
                  </div>
                  <ConstraintDetail constraint={constraint} />
                  {mayOverride && constraint.open && (
                    <div className="row-actions">
                      <Button
                        variant="ghost"
                        onClick={() => {
                          setErrors([]);
                          setReason("");
                          setOverriding(constraint);
                        }}
                      >
                        Ohne Unterschrift freigeben
                      </Button>
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {approval.may_approve && (
          <div className="stage-actions">
            <Button busy={approveM.isPending} onClick={() => approveM.mutate(undefined)}>
              Jetzt freigeben
            </Button>
          </div>
        )}
      </section>

      <section className="flow-step">
        <h3 className="fieldset-title">Unterschriften</h3>
        <p className="fieldset-help">
          Wer tatsächlich unterschrieben hat, in der Reihenfolge der Unterschriften.
        </p>
        {approval.signatures.length === 0 ? (
          <p className="muted">Noch niemand.</p>
        ) : (
          <ul className="plain-list">
            {approval.signatures.map((signature, index) => (
              <li key={index}>
                {signature.member?.name ?? "unbekannte Person"} ·{" "}
                {new Date(signature.at).toLocaleString("de-DE")}
                {signature.note ? ` · ${signature.note}` : ""}
              </li>
            ))}
          </ul>
        )}
      </section>

      {overriding && (
        <Modal title="Ohne Unterschrift freigeben" size="sm" onClose={() => setOverriding(null)}>
          <div className="stack">
            <p className="muted small">
              „{overriding.description || overriding.name}" wird ohne die verlangten
              Unterschriften freigegeben. Wer das tut und warum, bleibt dauerhaft vermerkt.
            </p>
            <Field label="Begründung">
              <textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} />
              {errors.length > 0 && <div className="field-error">{errors.join(" ")}</div>}
            </Field>
            <div className="row-actions">
              <Button
                busy={overrideM.isPending}
                onClick={() => overrideM.mutate({ name: overriding.name, reason })}
              >
                Übergehen
              </Button>
              <Button variant="ghost" onClick={() => setOverriding(null)}>
                Abbrechen
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
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
