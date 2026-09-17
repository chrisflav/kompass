import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { mediaUrl } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  Field,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  useConfirmDialog,
  useToast,
  euro,
} from "../../components/ui";
import { postMultipart } from "./Bills";
import { Check, EtappenRail, Preflight, type Etappe } from "./stages";
import type { components } from "../../api/schema";

type StatementOut = components["schemas"]["StatementOut"];
type ExcursionBrief = components["schemas"]["ExcursionBrief"];
type ExcursionOut = components["schemas"]["ExcursionOut"];
type BillBrief = components["schemas"]["BillBrief"];
type MemberBrief = components["schemas"]["MemberBrief"];

type StepId = "purpose" | "receipts" | "reimbursement" | "submit";

const STATEMENTS = "/kompass/finance/statements";

/* --- draft ---------------------------------------------------------------- */

interface Draft {
  mode: "excursion" | "other";
  excursion_id: string;
  short_description: string;
  explanation: string;
  night_cost: string;
  allowance_to_ids: number[];
  subsidy_to_id: string;
  ljp_to_id: string;
}

function seed(s: StatementOut | null, presetExcursion?: string | null): Draft {
  return {
    // A brand-new statement starts on the excursion branch: nearly every
    // statement belongs to a trip, and the other branch is the exception.
    mode: s ? (s.excursion ? "excursion" : "other") : "excursion",
    // Arriving from an excursion's Abrechnung tab, the trip is already known.
    excursion_id: s?.excursion ? String(s.excursion.id) : (presetExcursion ?? ""),
    short_description: s?.short_description ?? "",
    explanation: s?.explanation ?? "",
    night_cost: s ? String(s.night_cost ?? 0) : "0",
    allowance_to_ids: (s?.allowance_to ?? []).map((m) => m.id),
    subsidy_to_id: s?.subsidy_to ? String(s.subsidy_to.id) : "",
    ljp_to_id: s?.ljp_to ? String(s.ljp_to.id) : "",
  };
}

/* --- page ----------------------------------------------------------------- */

/**
 * The leader-facing submission flow.
 *
 * Replaces "create a row in a modal, then hunt through four admin tabs, then
 * find Einreichen in a dropdown" with one linear route: say what it is, empty
 * the receipt shoebox, say who gets what, submit. Handing in is the default
 * ending; saving a draft is the way out, not the destination.
 */
export function StatementFlowPage() {
  const { id } = useParams();
  const statementId = id ? Number(id) : null;
  const query = useApiQuery(
    ["finance", "statements", statementId],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statementId as number } },
        }),
      ),
    { enabled: statementId !== null },
  );

  if (statementId === null) return <StatementFlow statement={null} />;
  return (
    <QueryBoundary query={query}>
      {(statement) => <StatementFlow key={statement.id} statement={statement} />}
    </QueryBoundary>
  );
}

function StatementFlow({ statement }: { statement: StatementOut | null }) {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [params, setParams] = useSearchParams();
  const presetExcursion = params.get("excursion");
  const [draft, setDraft] = useState<Draft>(() => seed(statement, presetExcursion));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const isExcursion = draft.mode === "excursion";
  const steps: StepId[] = isExcursion
    ? ["purpose", "receipts", "reimbursement", "submit"]
    : ["purpose", "receipts", "submit"];
  const requested = (params.get("stage") ?? "purpose") as StepId;
  // A statement that doesn't exist yet has nothing to hang the later legs on,
  // and dropping the excursion retires the Erstattung leg — in both cases fall
  // back rather than render a leg that can't work.
  const step: StepId = !statement ? "purpose" : steps.includes(requested) ? requested : "purpose";
  const goto = (next: StepId) => setParams({ stage: next }, { replace: false });

  const excursionId = draft.excursion_id ? Number(draft.excursion_id) : null;
  const excursions = useApiQuery(["members", "excursions"], () =>
    unwrap(client.GET("/api/members/excursions")),
  );
  const excursionQ = useApiQuery(
    ["members", "excursions", excursionId],
    () =>
      unwrap(
        client.GET("/api/members/excursions/{excursion_id}", {
          params: { path: { excursion_id: excursionId as number } },
        }),
      ),
    { enabled: excursionId !== null },
  );
  const excursion = excursionQ.data ?? null;

  // Arriving preselected from an excursion skips the picker, and with it the
  // naming the picker does — so name the draft after the trip once it loads.
  // Fires exactly once: the excursion query resolving later must never overwrite
  // a description the leader has since cleared or typed.
  const named = useRef(false);
  useEffect(() => {
    if (statement || !excursion || !presetExcursion || named.current) return;
    named.current = true;
    setDraft((d) =>
      d.short_description ? d : { ...d, short_description: excursion.name.slice(0, 30) },
    );
  }, [statement, excursion, presetExcursion]);

  const invalidate = [
    ["finance", "statements"],
    ["finance", "statements", statement?.id ?? 0],
    ["finance", "bills"],
  ];

  const saveM = useApiMutation(
    (d: Draft) => {
      const excursion_id = d.mode === "excursion" && d.excursion_id ? Number(d.excursion_id) : null;
      if (!statement) {
        return unwrap(
          client.POST("/api/finance/statements", {
            body: {
              short_description: d.short_description,
              explanation: d.explanation,
              excursion_id,
              night_cost: Number(d.night_cost) || 0,
            },
          }),
        );
      }
      return unwrap(
        client.PATCH("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statement.id } },
          body: {
            short_description: d.short_description,
            explanation: d.explanation,
            excursion_id,
            night_cost: Number(d.night_cost) || 0,
            allowance_to_ids: d.allowance_to_ids,
            subsidy_to_id: d.subsidy_to_id ? Number(d.subsidy_to_id) : null,
            ljp_to_id: d.ljp_to_id ? Number(d.ljp_to_id) : null,
          },
        }),
      );
    },
    {
      invalidate,
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  /** Persist the draft, then run `then` with the saved statement. */
  function save(then?: (s: StatementOut) => void) {
    setFieldErrors({});
    saveM.mutate(draft, { onSuccess: (saved) => then?.(saved) });
  }

  const submitM = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/submit", {
          params: { path: { statement_id: statement?.id as number } },
        }),
      ),
    {
      invalidate,
      onSuccess: () => {
        toast.success("Abrechnung eingereicht.");
        navigate(`${STATEMENTS}/${statement?.id}`);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const bills: BillBrief[] = statement?.bills ?? [];
  const billTotal = bills.reduce((sum, b) => sum + b.amount, 0);

  const etappen: Etappe[] = steps.map((s) => ({
    id: s,
    label: { purpose: "Anlass", receipts: "Belege", reimbursement: "Erstattung", submit: "Abschluss" }[s],
    readout: stepReadout(s, { draft, statement, excursion, bills, billTotal }),
    state: s === step ? "current" : steps.indexOf(s) < steps.indexOf(step) ? "done" : "ahead",
    reachable: statement !== null,
  }));

  const preflight = buildPreflight(statement, draft, bills);
  const ready = preflight.every((c) => c.ok);

  return (
    <div className="flow">
      <PageHeader
        breadcrumbs={[
          { label: "Abrechnungen", to: STATEMENTS },
          { label: statement ? statement.title : "Neue Abrechnung" },
        ]}
        actions={
          <Button
            variant="ghost"
            onClick={() =>
              statement ? navigate(`${STATEMENTS}/${statement.id}`) : navigate(STATEMENTS)
            }
          >
            Abbrechen
          </Button>
        }
      />

      <EtappenRail etappen={etappen} onSelect={(id) => goto(id as StepId)} />

      <div className="flow-panel" key={step}>
        {step === "purpose" && (
          <AnlassStep
            draft={draft}
            setDraft={setDraft}
            excursions={excursions.data ?? []}
            excursion={excursion}
            errors={fieldErrors}
            locked={statement !== null && statement.submitted}
          />
        )}
        {step === "receipts" && statement && (
          <BelegeStep statement={statement} excursion={excursion} />
        )}
        {step === "reimbursement" && statement && (
          <ErstattungStep
            statement={statement}
            excursion={excursion}
            draft={draft}
            setDraft={setDraft}
            onCommit={(d) => saveM.mutate(d)}
            errors={fieldErrors}
          />
        )}
        {step === "submit" && statement && (
          <AbschlussStep statement={statement} preflight={preflight} />
        )}
      </div>

      <div className="flow-nav">
        <div className="flow-nav-back">
          {steps.indexOf(step) > 0 && (
            <Button variant="ghost" onClick={() => goto(steps[steps.indexOf(step) - 1])}>
              Zurück
            </Button>
          )}
        </div>
        <div className="flow-nav-fwd">
          {step === "submit" ? (
            <>
              <Button
                variant="ghost"
                busy={saveM.isPending}
                onClick={() =>
                  save(() => {
                    toast.success("Entwurf gespeichert.");
                    navigate(`${STATEMENTS}/${statement?.id}`);
                  })
                }
              >
                Als Entwurf speichern
              </Button>
              <Button
                busy={submitM.isPending}
                disabled={!ready}
                onClick={async () => {
                  const ok = await confirm({
                    title: "Abrechnung einreichen?",
                    message: "Nach dem Einreichen kannst du die Abrechnung nicht mehr ändern. Die Kassenwartin prüft sie und zahlt aus.",
                    confirmLabel: "Einreichen",
                  });
                  if (ok) submitM.mutate(undefined);
                }}
              >
                Einreichen
              </Button>
            </>
          ) : (
            <Button
              busy={saveM.isPending}
              onClick={() =>
                save((saved) => {
                  const next = steps[steps.indexOf(step) + 1];
                  if (!statement) {
                    navigate(`${STATEMENTS}/${saved.id}/edit?stage=receipts`, {
                      replace: true,
                    });
                  } else {
                    goto(next);
                  }
                })
              }
            >
              Weiter
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}

/** The figure each leg settled, shown on the rail. */
function stepReadout(
  s: StepId,
  ctx: {
    draft: Draft;
    statement: StatementOut | null;
    excursion: ExcursionOut | null;
    bills: BillBrief[];
    billTotal: number;
  },
) {
  const { draft, statement, excursion, bills, billTotal } = ctx;
  if (s === "purpose") {
    if (draft.mode === "other") return draft.short_description || "Sonstige Ausgabe";
    return excursion?.name ?? draft.short_description ?? "—";
  }
  if (s === "receipts") {
    if (!statement) return "—";
    return `${bills.length} · ${euro(billTotal)}`;
  }
  if (s === "reimbursement") {
    if (!statement) return "—";
    return `${statement.allowances_paid} × Entschädigung`;
  }
  return statement ? euro(statement.total) : "—";
}

/* --- step 1: what is this for -------------------------------------------- */

function AnlassStep({
  draft,
  setDraft,
  excursions,
  excursion,
  errors,
  locked,
}: {
  draft: Draft;
  setDraft: (d: Draft) => void;
  excursions: ExcursionBrief[];
  excursion: ExcursionOut | null;
  errors: Record<string, string[]>;
  locked: boolean;
}) {
  return (
    <section className="flow-step">
      <h2 className="flow-title">Wofür ist diese Abrechnung?</h2>
      <p className="flow-lead">
        Fast jede Abrechnung gehört zu einer Fahrt. Dann rechnet Kompass Entschädigung und
        Zuschüsse selbst aus.
      </p>

      <div className="choice-cards" role="radiogroup" aria-label="Anlass">
        <ChoiceCard
          selected={draft.mode === "excursion"}
          disabled={locked}
          onSelect={() => setDraft({ ...draft, mode: "excursion" })}
          title="Für eine Fahrt"
          hint="Ausfahrt, Freizeit oder Ausbildung mit Zuschüssen"
        />
        <ChoiceCard
          selected={draft.mode === "other"}
          disabled={locked}
          onSelect={() =>
            // Recipients only exist for a trip, and the API rejects them once
            // the excursion is gone — drop them with it.
            setDraft({
              ...draft,
              mode: "other",
              excursion_id: "",
              allowance_to_ids: [],
              subsidy_to_id: "",
              ljp_to_id: "",
            })
          }
          title="Sonstige Ausgabe"
          hint="Material, Miete, Gebühren — nur Belege"
        />
      </div>

      {draft.mode === "excursion" && (
        <Field label="Fahrt">
          <Select
            value={draft.excursion_id}
            onChange={(v) => {
              const picked = excursions.find((e) => String(e.id) === v);
              setDraft({
                ...draft,
                excursion_id: v,
                // Recipients belong to the old trip; the API drops them too.
                allowance_to_ids: [],
                subsidy_to_id: "",
                ljp_to_id: "",
                short_description:
                  draft.short_description || (picked ? picked.name.slice(0, 30) : ""),
              });
            }}
            options={excursions.map((e) => ({ value: e.id, label: `${e.code} ${e.name}` }))}
            placeholder="Fahrt auswählen…"
          />
          {errors.excursion && <div className="field-error">{errors.excursion.join(" ")}</div>}
        </Field>
      )}

      {draft.mode === "excursion" && excursion && <ExcursionReadout excursion={excursion} />}

      <Field label="Kurzbeschreibung" hint="Erscheint auf der Überweisung. Höchstens 30 Zeichen.">
        <input
          maxLength={30}
          value={draft.short_description}
          onChange={(e) => setDraft({ ...draft, short_description: e.target.value })}
        />
        {errors.short_description && (
          <div className="field-error">{errors.short_description.join(" ")}</div>
        )}
      </Field>

      <Field label="Erklärung" hint="Optional. Was die Kassenwartin wissen sollte.">
        <textarea
          rows={3}
          value={draft.explanation}
          onChange={(e) => setDraft({ ...draft, explanation: e.target.value })}
        />
        {errors.explanation && <div className="field-error">{errors.explanation.join(" ")}</div>}
      </Field>
    </section>
  );
}

function ChoiceCard({
  selected,
  disabled,
  onSelect,
  title,
  hint,
}: {
  selected: boolean;
  disabled?: boolean;
  onSelect: () => void;
  title: string;
  hint: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      disabled={disabled}
      className={`choice-card${selected ? " selected" : ""}`}
      onClick={onSelect}
    >
      <span className="choice-title">{title}</span>
      <span className="choice-hint">{hint}</span>
    </button>
  );
}

/** The trip facts the payout is computed from — stated, not re-entered. */
function ExcursionReadout({ excursion }: { excursion: ExcursionOut }) {
  const items: [string, string][] = [
    ["Dauer", `${excursion.duration} T`],
    ["Übernachtungen", String(excursion.night_count)],
    ["Anreise", excursion.tour_approach_str],
    ["Kilometer", String(excursion.kilometers_traveled)],
    ["Leitung", String(excursion.staff_count)],
    ["Teilnehmende", String(excursion.participant_count)],
  ];
  return (
    <div className="readout">
      <span className="readout-caption">Aus der Fahrt übernommen</span>
      <dl>
        {items.map(([k, v]) => (
          <div key={k}>
            <dt>{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

/* --- step 2: receipts ----------------------------------------------------- */

interface BillDraft {
  short_description: string;
  explanation: string;
  amount: string;
  paid_by_id: string;
  proof: File | null;
}

const emptyBillDraft: BillDraft = {
  short_description: "",
  explanation: "",
  amount: "",
  paid_by_id: "",
  proof: null,
};

function BelegeStep({
  statement,
  excursion,
}: {
  statement: StatementOut;
  excursion: ExcursionOut | null;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [adding, setAdding] = useState<BillDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  // The people who actually went are the plausible payers; everyone else stays
  // reachable but sorted behind them.
  const memberOptions = useMemo(() => {
    const all: MemberBrief[] = members.data ?? [];
    const leaderIds = new Set((excursion?.jugendleiter ?? []).map((m) => m.id));
    const rank = (m: MemberBrief) => (leaderIds.has(m.id) ? 0 : 1);
    return [...all].sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name));
  }, [members.data, excursion]);

  const invalidate = [
    ["finance", "statements"],
    ["finance", "statements", statement.id],
    ["finance", "bills"],
  ];

  const createM = useApiMutation(
    (d: BillDraft) => {
      const fd = new FormData();
      fd.append("statement_id", String(statement.id));
      fd.append("short_description", d.short_description);
      fd.append("explanation", d.explanation);
      fd.append("amount", String(Number(d.amount) || 0));
      if (d.paid_by_id) fd.append("paid_by_id", d.paid_by_id);
      fd.append("costs_covered", "false");
      if (d.proof) fd.append("proof", d.proof);
      return postMultipart("/api/finance/bills", fd);
    },
    {
      invalidate,
      onSuccess: () => {
        toast.success("Beleg hinzugefügt.");
        setAdding(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const updateM = useApiMutation(
    async (vars: { id: number; d: BillDraft }) => {
      await unwrap(
        client.PATCH("/api/finance/bills/{bill_id}", {
          params: { path: { bill_id: vars.id } },
          body: {
            short_description: vars.d.short_description,
            explanation: vars.d.explanation,
            amount: Number(vars.d.amount) || 0,
            paid_by_id: vars.d.paid_by_id ? Number(vars.d.paid_by_id) : null,
          },
        }),
      );
      if (vars.d.proof) {
        const fd = new FormData();
        fd.append("proof", vars.d.proof);
        await postMultipart(`/api/finance/bills/${vars.id}/proof`, fd);
      }
    },
    {
      invalidate,
      onSuccess: () => {
        toast.success("Beleg gespeichert.");
        setEditingId(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const deleteM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/finance/bills/{bill_id}", { params: { path: { bill_id: id } } }),
      ),
    { invalidate, onError: (e: Error) => toast.error(e.message) },
  );

  const bills = statement.bills;
  const total = bills.reduce((s, b) => s + b.amount, 0);

  return (
    <section className="flow-step flow-step-wide">
      <h2 className="flow-title">Belege</h2>
      <p className="flow-lead">
        Alles, was jemand ausgelegt hat. Fotografiere den Kassenzettel — ohne Bild kann die
        Kassenwartin den Beleg nicht anerkennen.
      </p>

      <ul className="beleg-list">
        {bills.map((b) =>
          editingId === b.id ? (
            <li key={b.id} className="beleg is-editing">
              <BillForm
                initial={{
                  short_description: b.short_description ?? "",
                  explanation: b.explanation ?? "",
                  amount: String(b.amount),
                  paid_by_id: b.paid_by ? String(b.paid_by.id) : "",
                  proof: null,
                }}
                members={memberOptions}
                hasProof={b.has_proof}
                busy={updateM.isPending}
                submitLabel="Speichern"
                onSubmit={(d) => updateM.mutate({ id: b.id, d })}
                onCancel={() => setEditingId(null)}
              />
            </li>
          ) : (
            <li key={b.id} className="beleg">
              <div className="beleg-main">
                <span className="beleg-title">{b.short_description}</span>
                <span className="beleg-sub">
                  {b.paid_by ? `ausgelegt von ${b.paid_by.name}` : "kein Zahler eingetragen"}
                </span>
              </div>
              <div className="beleg-proof">
                {b.has_proof && b.proof_url ? (
                  // The badge only ever announced the scan; opening it is the
                  // point of having uploaded one.
                  <a
                    href={mediaUrl(b.proof_url)}
                    target="_blank"
                    rel="noreferrer"
                    className="beleg-proof-link"
                  >
                    Beleg ansehen
                  </a>
                ) : (
                  <Badge tone="warning">Bild fehlt</Badge>
                )}
              </div>
              <div className="beleg-amount">{euro(b.amount)}</div>
              <div className="beleg-actions">
                <Button variant="ghost" onClick={() => setEditingId(b.id)}>
                  Bearbeiten
                </Button>
                <Button
                  variant="ghost"
                  onClick={async () => {
                    const ok = await confirm({
                      title: "Beleg entfernen?",
                      message: `„${b.short_description}" wird gelöscht.`,
                      confirmLabel: "Entfernen",
                    });
                    if (ok) deleteM.mutate(b.id);
                  }}
                >
                  Entfernen
                </Button>
              </div>
            </li>
          ),
        )}
        {bills.length === 0 && !adding && (
          <li className="beleg-empty">Noch keine Belege. Füge den ersten hinzu.</li>
        )}
      </ul>

      {adding ? (
        <div className="beleg is-editing">
          <BillForm
            initial={adding}
            members={memberOptions}
            busy={createM.isPending}
            submitLabel="Beleg hinzufügen"
            onSubmit={(d) => createM.mutate(d)}
            onCancel={() => setAdding(null)}
          />
        </div>
      ) : (
        <Button variant="ghost" onClick={() => setAdding({ ...emptyBillDraft })}>
          + Beleg hinzufügen
        </Button>
      )}

      <div className="beleg-total">
        <span>Summe</span>
        <strong>{euro(total)}</strong>
      </div>
    </section>
  );
}

function BillForm({
  initial,
  members,
  hasProof,
  busy,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial: BillDraft;
  members: MemberBrief[];
  hasProof?: boolean;
  busy: boolean;
  submitLabel: string;
  onSubmit: (d: BillDraft) => void;
  onCancel: () => void;
}) {
  const [d, setD] = useState<BillDraft>(initial);
  return (
    <div className="beleg-form">
      <Field label="Wofür">
        <input
          autoFocus
          value={d.short_description}
          maxLength={30}
          onChange={(e) => setD({ ...d, short_description: e.target.value })}
        />
      </Field>
      <Field label="Betrag">
        <input
          type="number"
          step="0.01"
          inputMode="decimal"
          value={d.amount}
          onChange={(e) => setD({ ...d, amount: e.target.value })}
        />
      </Field>
      <Field label="Ausgelegt von">
        <Select
          value={d.paid_by_id}
          onChange={(v) => setD({ ...d, paid_by_id: v })}
          options={members.map((m) => ({ value: m.id, label: m.name }))}
          placeholder="Person auswählen…"
        />
      </Field>
      <Field label="Beleg-Bild" hint="Foto oder PDF, höchstens 5 MB.">
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/gif"
          onChange={(e) => setD({ ...d, proof: e.target.files?.[0] ?? null })}
        />
        {hasProof && !d.proof && <span className="field-hint">Ein Bild ist hinterlegt.</span>}
      </Field>
      <div className="beleg-form-actions">
        <Button busy={busy} onClick={() => onSubmit(d)}>
          {submitLabel}
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
}

/* --- step 3: who gets what ------------------------------------------------ */

function ErstattungStep({
  statement,
  excursion,
  draft,
  setDraft,
  onCommit,
  errors,
}: {
  statement: StatementOut;
  excursion: ExcursionOut | null;
  draft: Draft;
  setDraft: (d: Draft) => void;
  onCommit: (d: Draft) => void;
  errors: Record<string, string[]>;
}) {
  const leaders = excursion?.jugendleiter ?? [];
  const maxAllowances = statement.real_staff_count;
  // The payout figures come from the server, so every change is committed and
  // the preview below always shows what would actually be paid.
  const commit = (next: Draft) => {
    setDraft(next);
    onCommit(next);
  };
  const nightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (nightTimer.current) clearTimeout(nightTimer.current); }, []);

  return (
    <section className="flow-step">
      <h2 className="flow-title">Wer bekommt was?</h2>
      <p className="flow-lead">
        Entschädigung und Zuschüsse gehen nur an die Jugendleiter*innen dieser Fahrt. Die Beträge
        rechnet Kompass aus.
      </p>

      <Field
        label="Aufwandsentschädigung an"
        hint={`Höchstens ${maxAllowances} anerkannt — ${euro(statement.allowance_per_yl)} pro Person.`}
      >
        <MultiSelect
          options={leaders.map((m) => ({ value: m.id, label: m.name }))}
          selected={draft.allowance_to_ids}
          onChange={(ids) => commit({ ...draft, allowance_to_ids: ids })}
          placeholder="Jugendleiter*innen auswählen…"
          emptyText="Diese Fahrt hat keine Jugendleiter*innen."
        />
        {errors.allowance_to && <div className="field-error">{errors.allowance_to.join(" ")}</div>}
      </Field>

      <Field
        label="Fahrt- und Übernachtungszuschuss an"
        hint="Meist die Person, die Sprit und Hütte bezahlt hat."
      >
        <Select
          value={draft.subsidy_to_id}
          onChange={(v) => commit({ ...draft, subsidy_to_id: v })}
          options={leaders.map((m) => ({ value: m.id, label: m.name }))}
          placeholder="— niemand —"
          allowEmpty
          emptyLabel="— niemand —"
        />
      </Field>

      <Field
        label="LJP-Beitrag an"
        hint="Nur wenn für diese Fahrt ein LJP-Antrag gestellt wurde. Dann braucht jeder Beleg ein Bild."
      >
        <Select
          value={draft.ljp_to_id}
          onChange={(v) => commit({ ...draft, ljp_to_id: v })}
          options={leaders.map((m) => ({ value: m.id, label: m.name }))}
          placeholder="— niemand —"
          allowEmpty
          emptyLabel="— niemand —"
        />
      </Field>

      <Field label="Preis pro Übernachtung" hint="Was eine Person pro Nacht gekostet hat.">
        <input
          type="number"
          step="0.01"
          inputMode="decimal"
          value={draft.night_cost}
          onChange={(e) => {
            const next = { ...draft, night_cost: e.target.value };
            setDraft(next);
            if (nightTimer.current) clearTimeout(nightTimer.current);
            nightTimer.current = setTimeout(() => onCommit(next), 500);
          }}
        />
        {errors.night_cost && <div className="field-error">{errors.night_cost.join(" ")}</div>}
      </Field>

      <PayoutPreview statement={statement} />
    </section>
  );
}

/** The computed payout, itemised the way the reimbursement rules build it up. */
/** What this statement is claiming, assuming every receipt is covered.
 *
 * NOT `statement.total`: that counts only the bills the treasurer has already
 * marked covered, which at submission time is none of them. Showing it to
 * someone still filling the statement in prints receipts that the total then
 * silently excludes.
 */
function claimedTotal(s: StatementOut): number {
  return (
    s.total_bills_theoretic +
    s.total_allowance +
    s.total_subsidies -
    s.total_org_fee +
    s.paid_ljp_contributions
  );
}

interface PayoutLine {
  label: string;
  /** How the figure is arrived at, so two lines can never be mistaken for each other. */
  basis?: string;
  value: number;
}

function payoutLines(statement: StatementOut): PayoutLine[] {
  const lines: PayoutLine[] = [
    {
      label: "Belege",
      basis: `${statement.bills.length} ${statement.bills.length === 1 ? "Beleg" : "Belege"}`,
      value: statement.total_bills_theoretic,
    },
  ];
  if (statement.excursion) {
    // Both of these are shown even at zero. Filtering empty rows made the
    // Aufwandsentschädigung disappear whenever nobody was selected yet, leaving
    // the travel line looking like it.
    lines.push({
      label: "Aufwandsentschädigung",
      basis: `${statement.allowances_paid} × ${euro(statement.allowance_per_yl)} pro Person`,
      value: statement.total_allowance,
    });
    lines.push({
      label: "Fahrt- und Übernachtungszuschuss",
      basis: statement.subsidy_to ? `an ${statement.subsidy_to.name}` : "niemand ausgewählt",
      value: statement.total_subsidies,
    });
    if (statement.total_org_fee) {
      lines.push({ label: "Orga-Pauschale", value: -statement.total_org_fee });
    }
    // Shown as soon as a recipient is chosen, so the amount is visible here and
    // not only after the statement has been handed in.
    if (statement.ljp_to || statement.paid_ljp_contributions) {
      lines.push({
        label: "LJP-Beitrag",
        basis: statement.ljp_to ? `an ${statement.ljp_to.name}` : undefined,
        value: statement.paid_ljp_contributions,
      });
    }
  }
  return lines;
}

/** The computed payout, itemised the way the reimbursement rules build it up. */
function PayoutPreview({ statement }: { statement: StatementOut }) {
  const lines = payoutLines(statement);
  return (
    <div className="payout">
      <span className="payout-caption">Voraussichtliche Auszahlung</span>
      <dl>
        {lines.map((l) => (
          <div key={l.label}>
            <dt>
              {l.label}
              {l.basis && <span className="payout-basis">{l.basis}</span>}
            </dt>
            <dd>{euro(l.value)}</dd>
          </div>
        ))}
        <div className="payout-sum">
          <dt>Gesamt</dt>
          {/* The sum of the lines above, so the breakdown always adds up. */}
          <dd>{euro(claimedTotal(statement))}</dd>
        </div>
      </dl>
      <p className="payout-note">
        Die Kassenwartin entscheidet noch, welche Belege übernommen werden. Der ausgezahlte Betrag
        kann darum kleiner ausfallen.
      </p>
    </div>
  );
}

/* --- step 4: hand in ------------------------------------------------------ */

interface PreflightItem {
  ok: boolean;
  text: string;
}

function buildPreflight(
  statement: StatementOut | null,
  draft: Draft,
  bills: BillBrief[],
): PreflightItem[] {
  if (!statement) return [];
  const items: PreflightItem[] = [];

  items.push({
    ok: (statement.short_description ?? "").trim().length > 0,
    text: "Die Abrechnung hat eine Kurzbeschreibung.",
  });

  const claimsSomething =
    bills.length > 0 ||
    statement.allowance_to.length > 0 ||
    statement.subsidy_to !== null ||
    statement.ljp_to !== null;
  items.push({ ok: claimsSomething, text: "Die Abrechnung fordert mindestens einen Betrag." });

  const payerless = bills.filter((b) => !b.paid_by);
  items.push({
    ok: payerless.length === 0,
    text:
      payerless.length === 0
        ? "Bei jedem Beleg steht, wer ihn ausgelegt hat."
        : `${payerless.length} Beleg(e) ohne Zahler*in: ${payerless
            .map((b) => b.short_description)
            .join(", ")}. Ohne Zahler*in kann das Geld nicht überwiesen werden.`,
  });

  if (draft.mode === "excursion") {
    const tooMany = statement.allowance_to.length > statement.real_staff_count;
    items.push({
      ok: !tooMany,
      text: tooMany
        ? `Für diese Fahrt sind ${statement.real_staff_count} Aufwandsentschädigungen anerkannt, eingetragen sind ${statement.allowance_to.length}.`
        : "Die Empfänger*innen der Aufwandsentschädigung sind zulässig.",
    });

    if (statement.ljp_to) {
      const missing = bills.filter((b) => !b.has_proof);
      items.push({
        ok: missing.length === 0,
        text:
          missing.length === 0
            ? "Jeder Beleg hat ein Bild — Voraussetzung für den LJP-Beitrag."
            : `Für den LJP-Beitrag braucht jeder Beleg ein Bild. Es fehlen: ${missing
                .map((b) => b.short_description)
                .join(", ")}.`,
      });
    }
  }

  return items;
}

function AbschlussStep({
  statement,
  preflight,
}: {
  statement: StatementOut;
  preflight: PreflightItem[];
}) {
  const blockers = preflight.filter((c) => !c.ok);
  return (
    <section className="flow-step">
      <h2 className="flow-title">Prüfen und einreichen</h2>
      <p className="flow-lead">
        {blockers.length === 0
          ? "Alles vollständig. Nach dem Einreichen übernimmt die Kassenwartin."
          : "Das fehlt noch, bevor du einreichen kannst."}
      </p>

      <Preflight>
        {preflight.map((c, i) => (
          <Check key={i} ok={c.ok}>
            {c.text}
          </Check>
        ))}
      </Preflight>

      {/* The same breakdown as the reimbursement step, from the same figures —
          two summaries of one statement must never disagree. */}
      <div className="summary-card">
        <div className="summary-head">
          <span>{statement.title}</span>
          <strong>{euro(claimedTotal(statement))}</strong>
        </div>
        <dl className="summary-lines">
          {payoutLines(statement).map((l) => (
            <div key={l.label}>
              <dt>
                {l.label}
                {l.basis && <span className="payout-basis">{l.basis}</span>}
              </dt>
              <dd>{euro(l.value)}</dd>
            </div>
          ))}
        </dl>
      </div>
    </section>
  );
}
