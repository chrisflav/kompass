import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { mediaUrl } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useExcursions, useMembers } from "../../api/queries";
import {
  Badge,
  Button,
  Field,
  PageHeader,
  QueryBoundary,
  Select,
  useConfirmDialog,
  useToast,
  euro,
} from "../../components/ui";
import { AnswerField, DerivedFacts, TYPED_INTO, type Answers } from "./answers";
import { postMultipart } from "./Bills";
import { Check, EtappenRail, Preflight, type Etappe } from "./stages";
import type { components } from "../../api/schema";

type StatementOut = components["schemas"]["StatementOut"];
type StatementFormOut = components["schemas"]["StatementFormOut"];
type InputDeclarationOut = components["schemas"]["InputDeclarationOut"];
type FormStepOut = components["schemas"]["FormStepOut"];
type TransferPartyOut = components["schemas"]["TransferPartyOut"];
type ExcursionBrief = components["schemas"]["ExcursionBrief"];
type ExcursionOut = components["schemas"]["ExcursionOut"];
type BillBrief = components["schemas"]["BillBrief"];
type MemberBrief = components["schemas"]["MemberBrief"];

type StepId = "purpose" | "receipts" | "reimbursement" | "submit";

const STATEMENTS = "/kompass/finance/statements";

/* --- draft ---------------------------------------------------------------- */

/**
 * What the first leg of the flow collects.
 *
 * It used to carry four more fields — `night_cost`, `allowance_to_ids`,
 * `subsidy_to_id`, `ljp_to_id` — because `Statement` had four columns by those
 * names. The answers the section's rules ask for are not here any more: they
 * are declared by the rules, served by `GET …/form`, and edited by
 * `ErstattungStep` against `PATCH … {inputs}`.
 */
interface Draft {
  mode: "excursion" | "other";
  excursion_id: string;
  short_description: string;
  explanation: string;
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
  // A receipt is only saved by the button that adds it. Its form is state on a
  // panel this flow throws away whenever the leg changes (`key={step}`), so
  // leaving the Belege leg with one open used to drop what had been typed
  // without a word — and the leader who then saved the draft found no receipt
  // in it. The flow stays put instead, and says what is in the way.
  const [enteringBill, setEnteringBill] = useState(false);

  const requested = (params.get("stage") ?? "purpose") as StepId;
  // Whether this statement has an Erstattung leg, asked of the rules rather
  // than of the excursion.
  //
  // The leg used to appear only for a statement that named a trip, from when it
  // was four fields about a trip's allowances. It asks the *ruleset's*
  // questions now, and a ruleset does not care whether there was a trip:
  // Ludwigsburg's asks the same `regime` of a Fortbildung as of a Freizeit. So
  // gating the leg on the excursion hid all eight questions the rules ask of a
  // statement without one — among them the only place to say which part of the
  // regulation applies.
  //
  // Unknown counts as "asks something", in both directions: the rail is drawn
  // before the form lands, and neither a leg that appears late nor a
  // `?stage=reimbursement` that bounces to Anlass while the form is in flight
  // is something a person should see. The leg is retired only once the rules
  // are known to ask nothing — and never out from under somebody standing on
  // it, which is why `requested` counts as well.
  const formQ = useStatementForm(statement);
  const asksNothing = formQ.data !== undefined && formQ.data.inputs.length === 0;
  const steps: StepId[] =
    asksNothing && requested !== "reimbursement"
      ? ["purpose", "receipts", "submit"]
      : ["purpose", "receipts", "reimbursement", "submit"];
  // A statement that doesn't exist yet has nothing to hang the later legs on,
  // and a hand-written `?stage=` may name no leg at all — in both cases fall
  // back rather than render a leg that can't work.
  const step: StepId = !statement ? "purpose" : steps.includes(requested) ? requested : "purpose";
  const goto = (next: StepId) => setParams({ stage: next }, { replace: false });

  /**
   * Run `go`, unless something on this leg would be lost by moving.
   *
   * Every way out of a leg goes through here — Weiter, Zurück, a leg picked off
   * the rail and the draft that ends the flow — because an unsaved receipt is
   * lost by all four of them equally.
   */
  function leaving(go: () => void) {
    if (enteringBill) {
      toast.error("Der Beleg ist noch nicht hinzugefügt. Füge ihn hinzu oder verwirf ihn.");
      return;
    }
    go();
  }

  const excursionId = draft.excursion_id ? Number(draft.excursion_id) : null;
  const excursions = useExcursions();
  const excursionQ = useApiQuery(
    ["excursions", excursionId],
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

  // What stands between this statement and being handed in, asked of the
  // section's rules rather than re-derived here. Fetched at this level, not in
  // the last leg, because the Einreichen button is here.
  const preflightQ = usePreflight(statement);
  const ready = preflightQ.data?.ok ?? false;

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

      <EtappenRail etappen={etappen} onSelect={(id) => leaving(() => goto(id as StepId))} />

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
          <BelegeStep
            statement={statement}
            excursion={excursion}
            onEntering={setEnteringBill}
          />
        )}
        {step === "reimbursement" && statement && <ErstattungStep statement={statement} />}
        {step === "submit" && statement && <AbschlussStep statement={statement} />}
      </div>

      <div className="flow-nav">
        <div className="flow-nav-back">
          {steps.indexOf(step) > 0 && (
            <Button
              variant="ghost"
              onClick={() => leaving(() => goto(steps[steps.indexOf(step) - 1]))}
            >
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
                  leaving(() =>
                    save((saved) => {
                      toast.success("Entwurf gespeichert.");
                      navigate(`${STATEMENTS}/${saved.id}`);
                    }),
                  )
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
                leaving(() =>
                  save((saved) => {
                    const next = steps[steps.indexOf(step) + 1];
                    if (!statement) {
                      navigate(`${STATEMENTS}/${saved.id}/edit?stage=receipts`, {
                        replace: true,
                      });
                    } else {
                      goto(next);
                    }
                  }),
                )
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
    // What the leg settles, from the resolved transfers rather than from a
    // count of allowance recipients — which only one section's rules have.
    const people = statement.transfers.filter((t) => t.destination.kind === "member");
    return `${people.length} × Erstattung`;
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
          // Dropping the trip drops the answers that named its youth leaders,
          // and the API does that itself: whom the rules offer is derived from
          // the excursion, so an answer naming somebody goes with it.
          onSelect={() => setDraft({ ...draft, mode: "other", excursion_id: "" })}
          title="Sonstige Ausgabe"
          hint="Material, Miete, Gebühren, Fortbildung"
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
  onEntering,
}: {
  statement: StatementOut;
  excursion: ExcursionOut | null;
  /** Whether a receipt form is open, so the flow can refuse to throw it away. */
  onEntering: (entering: boolean) => void;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [adding, setAdding] = useState<BillDraft | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);

  // Reported upwards rather than asked for from above, because the flow's nav
  // is the only thing that needs to know and this step is the only thing that
  // does. The unmount case matters as much as the open one: once the receipt is
  // added the form closes, and the flow has to be let go of again.
  const entering = adding !== null || editingId !== null;
  useEffect(() => {
    onEntering(entering);
    return () => onEntering(false);
  }, [entering, onEntering]);

  const members = useMembers();
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

/**
 * The questions the section's rules ask about this statement.
 *
 * Nothing here knows what they are. `GET …/form` returns the declarations —
 * with the people a party-valued answer may name already resolved to `{id,
 * name}` — and `answers.tsx` renders the widget vocabulary. The form is asked
 * for again after every save, because a ruleset may retire a question once an
 * earlier answer makes it moot (`relevant_inputs`).
 */
function ErstattungStep({ statement }: { statement: StatementOut }) {
  const formQ = useStatementForm(statement);
  return (
    <section className="flow-step">
      <h2 className="flow-title">Wer bekommt was?</h2>
      <p className="flow-lead">
        Diese Fragen stellt die Finanzordnung der Sektion. Die Beträge rechnet Kompass daraus
        selbst aus.
      </p>
      <QueryBoundary query={formQ}>
        {(form) => <AnswerForm statement={statement} form={form} />}
      </QueryBoundary>
      <PayoutPreview statement={statement} />
    </section>
  );
}

/** How long a typed-into field waits before it becomes a request. */
const TYPING_PAUSE = 500;

function AnswerForm({ statement, form }: { statement: StatementOut; form: StatementFormOut }) {
  const toast = useToast();
  const [answers, setAnswers] = useState<Answers>(() => ({ ...form.answers }));
  const [errors, setErrors] = useState<Record<string, string[]>>({});
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  /**
   * The edits the server has not been told about yet, by key.
   *
   * A `PATCH` carries these and nothing else. It used to carry the whole
   * answerable subset on every edit, which is how an answer nobody had touched
   * travelled with somebody else's — and a key the rules have since retired is
   * refused (#579), so re-asserting one turned an unrelated edit into "Diese
   * Regeln fragen Teilnehmerliste nicht ab.". `PATCH … {inputs}` merges by key,
   * so one key is a whole request.
   *
   * An edit still waiting out a typing pause is in here too: a pick that
   * arrives during the pause cancels the timer, and what had been typed goes
   * out with the pick rather than being dropped.
   */
  const unsent = useRef<Answers>({});
  // The keys a `PATCH` may carry, which is neither "everything answered" nor
  // "everything declared".
  //
  // A ruleset may retire a question once an earlier answer makes it moot, and
  // the API refuses a key the rules do not ask for — so an edit to a question
  // that has since gone off the form is held back rather than sent.
  //
  // And a derived answer is refused too, keyed by that question: the figure is
  // a reading of the excursion, resolved again on every evaluation, so a value
  // sent for it would land where nothing reads it. Nothing renders a control
  // for one, so nothing should ever put one in `unsent`; this is the second
  // lock on the mistake the API refuses — echoing the form back as served.
  const answerable = useMemo(
    () =>
      new Set(
        form.inputs.filter((declared) => !declared.derived).map((declared) => declared.key),
      ),
    [form.inputs],
  );
  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const saveM = useApiMutation(
    (next: Answers) =>
      unwrap(
        client.PATCH("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statement.id } },
          body: { inputs: next },
        }),
      ),
    {
      // Both the statement (the payout below) and the form (a question the
      // rules may have just retired) are stale once an answer lands.
      invalidate: [
        ["finance", "statements"],
        ["finance", "statements", statement.id],
        ["finance", "statements", statement.id, "form"],
      ],
      onError: (e: Error) => {
        // A 422 is keyed by the answer it is about, so the message lands under
        // the question rather than only in a toast.
        if (e instanceof ApiError) setErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  /**
   * Hand the unsent edits over, minus anything the form does not ask for.
   *
   * A key is dropped from `unsent` as it goes rather than once it lands: a
   * refusal is reported where it belongs (`onError`) and the answer stays on
   * the form, but a body the API has already refused must not be sent again on
   * the next edit — or every later request would carry the same 422 with it.
   */
  function send() {
    const body = Object.fromEntries(
      Object.entries(unsent.current).filter(([key]) => answerable.has(key)),
    );
    if (Object.keys(body).length === 0) return;
    for (const key of Object.keys(body)) delete unsent.current[key];
    saveM.mutate(body);
  }

  function change(declaration: InputDeclarationOut, value: unknown) {
    setAnswers((previous) => ({ ...previous, [declaration.key]: value }));
    setErrors({});
    unsent.current[declaration.key] = value;
    if (timer.current) clearTimeout(timer.current);
    if (TYPED_INTO.has(declaration.type)) {
      timer.current = setTimeout(send, TYPING_PAUSE);
    } else {
      send();
    }
  }

  if (form.inputs.length === 0) {
    return <p className="muted">Für diese Abrechnung fragen die Regeln nichts ab.</p>;
  }
  return (
    <>
      {form.steps.map((step) => (
        <AnswerGroup
          key={step.label}
          step={step}
          form={form}
          answers={answers}
          errors={errors}
          onChange={change}
        />
      ))}
    </>
  );
}

/**
 * One group of questions, as the ruleset grouped them.
 *
 * `steps` always partitions the whole form, so this is the only way the form is
 * laid out — including the degenerate case, a ruleset that named no steps,
 * which comes back as a single group with an empty label and reads as the flat
 * list it was before there were steps.
 *
 * Sections and not pages, deliberately. This form is already one leg of a
 * wizard (`EtappenRail`), and a second wizard inside it would make "Weiter"
 * mean two different things on one screen — and hide questions behind a step
 * the person cannot see they still have to answer. The backend is of the same
 * mind: `steps` carries a label and its keys and nothing else, no page state
 * and no notion of a step being finished.
 *
 * The readings come first within a group: what the trip says, then what it
 * leaves to be answered.
 */
function AnswerGroup({
  step,
  form,
  answers,
  errors,
  onChange,
}: {
  step: FormStepOut;
  form: StatementFormOut;
  answers: Answers;
  errors: Record<string, string[]>;
  onChange: (declaration: InputDeclarationOut, value: unknown) => void;
}) {
  const declared = step.keys
    .map((key) => form.inputs.find((declaration) => declaration.key === key))
    .filter((declaration): declaration is InputDeclarationOut => declaration !== undefined);
  const derived = declared.filter((declaration) => declaration.derived);
  const asked = declared.filter((declaration) => !declaration.derived);
  return (
    <section className="answer-group">
      {step.label && <h3 className="answer-group-title">{step.label}</h3>}
      {derived.length > 0 && (
        // Read from `form.answers` rather than from the draft: a derived figure
        // is resolved again on every request and nothing stores it, so the form
        // as served is the only place it is current.
        <DerivedFacts declarations={derived} answers={form.answers} />
      )}
      {asked.map((declaration) => (
        <AnswerField
          key={declaration.key}
          declaration={declaration}
          value={answers[declaration.key]}
          // The whole map, not this key's messages: a table's refusals are
          // keyed by a path into it (`"reisen[1].kilometers"`), so where a
          // message lands is the renderer's business and not the form's.
          errors={errors}
          onChange={(value) => onChange(declaration, value)}
        />
      ))}
    </section>
  );
}

/** Who the section is paying, as the engine resolved it. */
function partyName(party: TransferPartyOut): string {
  if (party.kind === "member") return party.member?.name ?? "unbekannt";
  return party.kind === "section" ? "die Sektion" : "die Teilnehmenden";
}

/**
 * The payout, as the rules resolved it.
 *
 * This used to be `payoutLines` plus `claimedTotal`: four hardcoded line kinds
 * and a sum the client computed from five named totals, both of which had to
 * be edited whenever the regulation paid something else. `StatementOut.
 * transfers` is the engine's own answer — who owes whom how much, under which
 * rule — and the last one is the balancing transfer, so the list adds up to
 * zero by construction.
 */
function PayoutPreview({ statement }: { statement: StatementOut }) {
  const transfers = statement.transfers;
  const toPeople = transfers
    .filter((t) => t.destination.kind === "member")
    .reduce((sum, t) => sum + t.amount, 0);
  const fromPeople = transfers
    .filter((t) => t.source.kind === "member")
    .reduce((sum, t) => sum + t.amount, 0);
  return (
    <div className="payout">
      <span className="payout-caption">Voraussichtliche Auszahlung</span>
      {transfers.length === 0 ? (
        <p className="muted">Noch nichts zu erstatten.</p>
      ) : (
        <dl>
          {transfers.map((t, i) => (
            <div key={`${t.rule_id}-${i}`}>
              <dt>
                {t.label || t.category}
                <span className="payout-basis">
                  {partyName(t.source)} → {partyName(t.destination)}
                  {t.explanation ? ` · ${t.explanation}` : ""}
                </span>
              </dt>
              <dd>{euro(t.amount)}</dd>
            </div>
          ))}
          <div className="payout-sum">
            <dt>An Personen</dt>
            {/* What the section transfers out, less what it charges back. */}
            <dd>{euro(toPeople - fromPeople)}</dd>
          </div>
        </dl>
      )}
      <p className="payout-note">
        Die Kassenwartin entscheidet noch, welche Belege übernommen werden. Der ausgezahlte Betrag
        kann darum kleiner ausfallen.
      </p>
    </div>
  );
}

/* --- step 4: hand in ------------------------------------------------------ */

/**
 * What stands between this statement and being handed in.
 *
 * `buildPreflight` used to re-derive this in the client: a description, "claims
 * something", a payer per receipt, the allowance count against the approved
 * staff count, a picture per receipt when LJP is claimed. Three of those five
 * were the Heidelberg rules restated in TypeScript, where they could and did
 * drift from the Python. `GET …/preflight` asks the section's own rules, which
 * is also exactly what `submit` refuses on.
 */
function AbschlussStep({ statement }: { statement: StatementOut }) {
  const preflightQ = usePreflight(statement);
  return (
    <section className="flow-step">
      <h2 className="flow-title">Prüfen und einreichen</h2>
      <QueryBoundary query={preflightQ}>
        {(preflight) => (
          <>
            <p className="flow-lead">
              {preflight.ok
                ? "Alles vollständig. Nach dem Einreichen übernimmt die Kassenwartin."
                : "Das fehlt noch, bevor du einreichen kannst."}
            </p>
            <Preflight>
              {preflight.checks.map((c, i) => (
                <Check key={i} ok={c.ok}>
                  {c.message}
                </Check>
              ))}
              {preflight.errors.map((message, i) => (
                <Check key={`e${i}`} ok={false}>
                  {message}
                </Check>
              ))}
              {preflight.checks.length === 0 && preflight.errors.length === 0 && (
                <Check ok>Die Regeln der Sektion haben nichts zu beanstanden.</Check>
              )}
            </Preflight>
          </>
        )}
      </QueryBoundary>

      {/* The same breakdown as the reimbursement step, from the same transfers —
          two summaries of one statement must never disagree. */}
      <PayoutPreview statement={statement} />
    </section>
  );
}

/**
 * The questions the section's rules ask about this statement, and its answers.
 *
 * Asked for at two levels off one cache entry: the leg renders the form, and
 * the flow above it needs to know whether there is anything to render at all —
 * a statement whose rules ask nothing has no Erstattung leg. One key, so the
 * two are never out of step and only one request goes out.
 */
function useStatementForm(statement: StatementOut | null) {
  return useApiQuery(
    ["finance", "statements", statement?.id ?? 0, "form"],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}/form", {
          params: { path: { statement_id: statement?.id as number } },
        }),
      ),
    { enabled: statement !== null },
  );
}

/** The section's own preconditions for handing this statement in. */
function usePreflight(statement: StatementOut | null) {
  return useApiQuery(
    ["finance", "statements", statement?.id ?? 0, "preflight"],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}/preflight", {
          params: { path: { statement_id: statement?.id as number } },
        }),
      ),
    { enabled: statement !== null },
  );
}
