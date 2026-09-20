import { useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { QRCodeSVG } from "qrcode.react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { mediaUrl } from "../../api/client";
import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  Badge,
  Button,
  DataTable,
  PageHeader,
  QueryBoundary,
  Select,
  useConfirmDialog,
  useToast,
  euro,
} from "../../components/ui";
import { EtappenRail, type Etappe } from "./stages";
import type { components } from "../../api/schema";

type StatementOut = components["schemas"]["StatementOut"];
type BillBrief = components["schemas"]["BillBrief"];
type TransactionOut = components["schemas"]["TransactionOut"];

type StageId = "expenses" | "bookings" | "payout";

const STATEMENTS = "/kompass/finance/statements";

/**
 * The treasurer-facing review pipeline.
 *
 * Processing used to be one modal that showed every control at once and left
 * the central decision — which bills the section actually covers — on a
 * different screen, with the receipt nowhere in sight. This walks the three
 * things that genuinely happen in order: judge the expenses against their
 * evidence, build the bank transfers, then pay.
 */
export function StatementReviewPage() {
  const { id } = useParams();
  const statementId = Number(id);
  const query = useApiQuery(["finance", "statements", statementId], () =>
    unwrap(
      client.GET("/api/finance/statements/{statement_id}", {
        params: { path: { statement_id: statementId } },
      }),
    ),
  );
  return (
    <QueryBoundary query={query}>
      {(statement) => <StatementReview statement={statement} />}
    </QueryBoundary>
  );
}

function StatementReview({ statement }: { statement: StatementOut }) {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [params, setParams] = useSearchParams();
  // Confirming means "I have paid these" — the admin gated it on the same
  // acknowledgement, so the treasurer cannot confirm a payout they never made.
  const [executed, setExecuted] = useState(false);

  const txQuery = useApiQuery(["finance", "statements", statement.id, "transactions"], () =>
    unwrap(
      client.GET("/api/finance/statements/{statement_id}/transactions", {
        params: { path: { statement_id: statement.id } },
      }),
    ),
  );
  const transactions = txQuery.data ?? [];

  const invalidate = [
    ["finance", "statements"],
    ["finance", "statements", statement.id],
    ["finance", "statements", statement.id, "transactions"],
    ["finance", "bills"],
  ];

  const covered = statement.bills.filter((b) => b.costs_covered);
  const rejected = statement.bills.filter((b) => !b.costs_covered);
  const coveredTotal = covered.reduce((s, b) => s + b.amount, 0);
  const txTotal = transactions.reduce((s, t) => s + t.amount, 0);

  // The pipeline is ordered by dependency: bookings need decided expenses, and
  // paying needs bookings that reconcile. Skipping ahead is what produced
  // half-processed statements in the old all-at-once modal.
  const stages: StageId[] = ["expenses", "bookings", "payout"];
  const reachable: Record<StageId, boolean> = {
    expenses: true,
    bookings: true,
    payout: statement.is_valid,
  };
  const requested = (params.get("stage") ?? "expenses") as StageId;
  const stage: StageId = stages.includes(requested) && reachable[requested] ? requested : "expenses";
  const goto = (next: StageId) => setParams({ stage: next });

  const etappen: Etappe[] = stages.map((s) => ({
    id: s,
    label: { expenses: "Prüfen", bookings: "Buchungen", payout: "Auszahlen" }[s],
    readout:
      s === "expenses"
        ? `${covered.length}/${statement.bills.length} · ${euro(coveredTotal)}`
        : s === "bookings"
          ? transactions.length === 0
            ? "keine"
            : `${transactions.length} · ${euro(txTotal)}`
          : statement.confirmed
            ? "ausgezahlt"
            : statement.is_valid
              ? euro(statement.total)
              : "gesperrt",
    state: s === stage ? "current" : stages.indexOf(s) < stages.indexOf(stage) ? "done" : "ahead",
    reachable: reachable[s],
  }));

  const actionM = useApiMutation((run: () => Promise<unknown>) => run(), {
    invalidate,
    onError: (e: Error) => toast.error(e.message),
  });
  const run = (fn: () => Promise<unknown>, success: string, after?: () => void) =>
    actionM.mutate(fn, {
      onSuccess: () => {
        toast.success(success);
        after?.();
      },
    });

  const path = { params: { path: { statement_id: statement.id } } } as const;

  return (
    <div className="flow">
      <PageHeader
        breadcrumbs={[
          { label: "Abrechnungen", to: STATEMENTS },
          { label: statement.title, to: `${STATEMENTS}/${statement.id}` },
          { label: "Prüfen" },
        ]}
        subtitle={
          statement.excursion
            ? `Eingereicht von ${statement.submitted_by?.name ?? "—"}`
            : undefined
        }
        actions={
          <>
            <Button variant="ghost" onClick={() => navigate(`${STATEMENTS}/${statement.id}`)}>
              Zurück
            </Button>
            <Button
              variant="danger"
              busy={actionM.isPending}
              onClick={async () => {
                const ok = await confirm({
                  title: "Abrechnung zurückgeben?",
                  message: "Die Abrechnung geht als Entwurf an die einreichende Person zurück und kann dort geändert werden.",
                  confirmLabel: "Zurückgeben",
                });
                if (ok)
                  run(
                    () =>
                      unwrap(client.POST("/api/finance/statements/{statement_id}/reject", path)),
                    "Abrechnung zurückgegeben.",
                    () => navigate(`${STATEMENTS}/${statement.id}`),
                  );
              }}
            >
              Zurückgeben
            </Button>
          </>
        }
      />

      <EtappenRail etappen={etappen} numbered onSelect={(id) => goto(id as StageId)} />

      <div className="flow-panel" key={stage}>
        {stage === "expenses" && (
          <PruefenStage
            statement={statement}
            covered={covered}
            rejected={rejected}
            coveredTotal={coveredTotal}
            invalidate={invalidate}
          />
        )}
        {stage === "bookings" && (
          <BuchungenStage
            statement={statement}
            transactions={transactions}
            coveredTotal={coveredTotal}
            busy={actionM.isPending}
            onGenerate={() =>
              run(
                () =>
                  unwrap(
                    client.POST(
                      "/api/finance/statements/{statement_id}/generate-transactions",
                      path,
                    ),
                  ),
                "Buchungen erzeugt.",
              )
            }
            onReduce={() =>
              run(
                () =>
                  unwrap(
                    client.POST("/api/finance/statements/{statement_id}/reduce-transactions", path),
                  ),
                "Buchungen zusammengefasst.",
              )
            }
            invalidate={invalidate}
          />
        )}
        {stage === "payout" && (
          <AuszahlenStage
            statement={statement}
            transactions={transactions}
            executed={executed}
            onExecutedChange={setExecuted}
          />
        )}
      </div>

      <div className="flow-nav">
        <div className="flow-nav-back">
          {stages.indexOf(stage) > 0 && (
            <Button variant="ghost" onClick={() => goto(stages[stages.indexOf(stage) - 1])}>
              Zurück
            </Button>
          )}
        </div>
        <div className="flow-nav-fwd">
          {stage === "payout" ? (
            <>
              <Button
                variant="ghost"
                busy={actionM.isPending}
                disabled={!statement.is_valid || !executed}
                onClick={() =>
                  run(
                    () =>
                      unwrap(client.POST("/api/finance/statements/{statement_id}/confirm", path)),
                    "Abrechnung bestätigt.",
                    () => navigate(`${STATEMENTS}/${statement.id}`),
                  )
                }
              >
                Nur bestätigen
              </Button>
              <Button
                busy={actionM.isPending}
                disabled={!statement.is_valid || !executed}
                onClick={async () => {
                  const ok = await confirm({
                    title: "Auszahlung bestätigen?",
                    message: `${euro(statement.total)} an ${payeeCount(transactions)} Empfänger*innen. Der Zuschussbeleg geht an die Geschäftsstelle.`,
                    confirmLabel: "Bestätigen & senden",
                  });
                  if (ok)
                    run(
                      () =>
                        unwrap(
                          client.POST("/api/finance/statements/{statement_id}/confirm", {
                            params: {
                              path: { statement_id: statement.id },
                              query: { send: true },
                            },
                          }),
                        ),
                      "Abrechnung bestätigt und Beleg versendet.",
                      () => navigate(`${STATEMENTS}/${statement.id}`),
                    );
                }}
              >
                Bestätigen & Beleg senden
              </Button>
            </>
          ) : (
            <Button
              disabled={!reachable[stages[stages.indexOf(stage) + 1]]}
              onClick={() => goto(stages[stages.indexOf(stage) + 1])}
            >
              Weiter
            </Button>
          )}
        </div>
      </div>

      {stage !== "payout" && !statement.is_valid && (
        <p className="flow-block">
          Auszahlen ist gesperrt: {statement.validity_display}
        </p>
      )}
    </div>
  );
}

function payeeCount(transactions: TransactionOut[]): number {
  return new Set(transactions.map((t) => t.member.id)).size;
}

/* --- stage 1: judge the expenses ----------------------------------------- */

/**
 * Expense decisions beside the evidence.
 *
 * Covering a bill is a judgement about a receipt, so the receipt is on screen
 * while the judgement is made — previously it lived behind a link on another
 * page, and the decision was a checkbox in an edit form.
 */
function PruefenStage({
  statement,
  covered,
  rejected,
  coveredTotal,
  invalidate,
}: {
  statement: StatementOut;
  covered: BillBrief[];
  rejected: BillBrief[];
  coveredTotal: number;
  invalidate: unknown[][];
}) {
  const toast = useToast();
  const bills = statement.bills;
  const [selectedId, setSelectedId] = useState<number | null>(bills[0]?.id ?? null);
  const selected = bills.find((b) => b.id === selectedId) ?? bills[0] ?? null;

  const qc = useQueryClient();
  const statementKey = ["finance", "statements", statement.id];

  // Covering a bill is a rapid, repeated judgement, so it must feel immediate:
  // write the decision into the cache on click and let the refetch confirm it.
  // Waiting for the round-trip made every click flash the whole list.
  const decideM = useApiMutation(
    (vars: { id: number; covered: boolean }) =>
      unwrap(
        client.PATCH("/api/finance/bills/{bill_id}", {
          params: { path: { bill_id: vars.id } },
          body: { costs_covered: vars.covered },
        }),
      ),
    {
      invalidate,
      onMutate: async (vars: { id: number; covered: boolean }) => {
        await qc.cancelQueries({ queryKey: statementKey });
        qc.setQueryData(statementKey, (old: StatementOut | undefined) =>
          old
            ? {
                ...old,
                bills: old.bills.map((b) =>
                  b.id === vars.id ? { ...b, costs_covered: vars.covered } : b,
                ),
              }
            : old,
        );
      },
      onError: (e: Error) => {
        toast.error(e.message);
        // The optimistic value was a guess; the server is the truth.
        qc.invalidateQueries({ queryKey: statementKey });
      },
    },
  );

  const rejectedTotal = rejected.reduce((s, b) => s + b.amount, 0);

  return (
    <section className="review">
      <div className="review-list">
        <h2 className="flow-title">Ausgaben prüfen</h2>
        <p className="flow-lead">
          Entscheide für jeden Beleg, ob die Sektion ihn übernimmt. Abgelehnte Belege zählen weiter
          in den LJP-Antrag, werden aber nicht erstattet.
        </p>

        <ul className="beleg-list">
          {bills.map((b) => (
            <li
              key={b.id}
              className={`beleg is-decidable${b.id === selected?.id ? " is-selected" : ""}${
                b.costs_covered ? " is-covered" : ""
              }`}
            >
              <button
                type="button"
                className="beleg-pick"
                aria-pressed={b.id === selected?.id}
                onClick={() => setSelectedId(b.id)}
              >
                <span className="beleg-main">
                  <span className="beleg-title">{b.short_description}</span>
                  <span className="beleg-sub">
                    {b.paid_by ? `ausgelegt von ${b.paid_by.name}` : "kein Zahler eingetragen"}
                    {!b.has_proof && " · ohne Bild"}
                  </span>
                </span>
                <span className="beleg-amount">{euro(b.amount)}</span>
              </button>
              <div className="beleg-decide">
                <Button
                  variant={b.costs_covered ? "primary" : "ghost"}
                  aria-pressed={b.costs_covered}
                  onClick={() => decideM.mutate({ id: b.id, covered: true })}
                >
                  Übernehmen
                </Button>
                <Button
                  variant={b.costs_covered ? "ghost" : "danger"}
                  aria-pressed={!b.costs_covered}
                  onClick={() => decideM.mutate({ id: b.id, covered: false })}
                >
                  Ablehnen
                </Button>
              </div>
            </li>
          ))}
          {bills.length === 0 && <li className="beleg-empty">Diese Abrechnung hat keine Belege.</li>}
        </ul>

        <div className="decide-tally">
          <div>
            <span className="tally-label">Übernommen</span>
            <strong>
              {covered.length} · {euro(coveredTotal)}
            </strong>
          </div>
          <div>
            <span className="tally-label">Abgelehnt</span>
            <strong>
              {rejected.length} · {euro(rejectedTotal)}
            </strong>
          </div>
        </div>
      </div>

      <aside className="review-proof">
        <span className="readout-caption">Nachweis</span>
        <ProofViewer bill={selected} />
      </aside>
    </section>
  );
}

function ProofViewer({ bill }: { bill: BillBrief | null }) {
  if (!bill) return <p className="muted">Kein Beleg ausgewählt.</p>;
  if (!bill.has_proof || !bill.proof_url) {
    return (
      <div className="proof-empty">
        <Badge tone="warning">Kein Bild hinterlegt</Badge>
        <p className="muted">
          Für „{bill.short_description}" wurde kein Kassenzettel hochgeladen.
        </p>
      </div>
    );
  }
  const url = mediaUrl(bill.proof_url);
  const isPdf = /\.pdf($|\?)/i.test(bill.proof_url);
  return (
    <figure className="proof">
      {isPdf ? (
        <object data={url} type="application/pdf" aria-label={bill.short_description}>
          <p className="muted">PDF kann nicht angezeigt werden.</p>
        </object>
      ) : (
        <img src={url} alt={`Beleg ${bill.short_description}`} />
      )}
      <figcaption>
        <span>{bill.short_description}</span>
        <a href={url} target="_blank" rel="noreferrer">
          Im Original öffnen
        </a>
      </figcaption>
    </figure>
  );
}

/* --- stage 2: build the transfers ---------------------------------------- */

function BuchungenStage({
  statement,
  transactions,
  coveredTotal,
  busy,
  onGenerate,
  onReduce,
  invalidate,
}: {
  statement: StatementOut;
  transactions: TransactionOut[];
  coveredTotal: number;
  busy: boolean;
  onGenerate: () => void;
  onReduce: () => void;
  invalidate: unknown[][];
}) {
  const toast = useToast();
  const ledgers = useApiQuery(["finance", "ledgers"], () =>
    unwrap(client.GET("/api/finance/ledgers/")),
  );
  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const ledgerOptions = ledgers.data ?? [];

  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState({ amount: "0", reference: "", member_id: "", ledger_id: "" });

  function beginEdit(t: TransactionOut) {
    setDraft({
      amount: String(t.amount ?? "0"),
      reference: t.reference ?? "",
      member_id: String(t.member.id),
      ledger_id: t.ledger ? String(t.ledger.id) : "",
    });
    setEditId(t.id);
  }

  const qc = useQueryClient();
  const txKey = ["finance", "statements", statement.id, "transactions"];

  // Assigning accounts is the bulk of this stage — one click per row — so the
  // select settles immediately rather than snapping back after the refetch.
  const patchM = useApiMutation(
    (vars: { id: number; ledger_id: number | null }) =>
      unwrap(
        client.PATCH("/api/finance/transactions/{transaction_id}", {
          params: { path: { transaction_id: vars.id } },
          body: { ledger_id: vars.ledger_id },
        }),
      ),
    {
      invalidate,
      onMutate: async (vars: { id: number; ledger_id: number | null }) => {
        await qc.cancelQueries({ queryKey: txKey });
        const ledger = ledgerOptions.find((l) => l.id === vars.ledger_id) ?? null;
        qc.setQueryData(txKey, (old: TransactionOut[] | undefined) =>
          old?.map((t) => (t.id === vars.id ? { ...t, ledger } : t)),
        );
      },
      onError: (e: Error) => {
        toast.error(e.message);
        qc.invalidateQueries({ queryKey: txKey });
      },
    },
  );

  const saveM = useApiMutation(
    (id: number) =>
      unwrap(
        client.PATCH("/api/finance/transactions/{transaction_id}", {
          params: { path: { transaction_id: id } },
          body: {
            amount: Number(draft.amount) || 0,
            reference: draft.reference,
            member_id: draft.member_id ? Number(draft.member_id) : null,
            ledger_id: draft.ledger_id ? Number(draft.ledger_id) : null,
          },
        }),
      ),
    {
      invalidate,
      onSuccess: () => {
        toast.success("Buchung gespeichert.");
        setEditId(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const issues = statement.transaction_issues;
  // Two rows to the same person from the same ledger become one bank transfer.
  const mergeable = useMemo(() => {
    const seen = new Map<string, number>();
    for (const t of transactions) {
      if (!t.ledger) continue;
      const key = `${t.member.id}:${t.ledger.id}`;
      seen.set(key, (seen.get(key) ?? 0) + 1);
    }
    return [...seen.values()].filter((n) => n > 1).length;
  }, [transactions]);
  const missingLedger = transactions.filter((t) => !t.ledger).length;

  const columns = [
    {
      header: "Empfänger*in",
      cell: (t: TransactionOut) =>
        editId === t.id ? (
          <Select
            value={draft.member_id}
            onChange={(v) => setDraft({ ...draft, member_id: v })}
            options={(members.data ?? []).map((m) => ({ value: m.id, label: m.name }))}
          />
        ) : (
          t.member.name
        ),
    },
    {
      header: "Verwendungszweck",
      cell: (t: TransactionOut) =>
        editId === t.id ? (
          <input
            value={draft.reference}
            onChange={(e) => setDraft({ ...draft, reference: e.target.value })}
          />
        ) : (
          t.reference
        ),
    },
    {
      header: "Betrag",
      cell: (t: TransactionOut) =>
        editId === t.id ? (
          <input
            type="number"
            step="0.01"
            value={draft.amount}
            onChange={(e) => setDraft({ ...draft, amount: e.target.value })}
          />
        ) : (
          euro(t.amount)
        ),
    },
    {
      // Assigning accounts is the bulk of this stage, so it stays a one-click
      // control in the normal row rather than something behind an edit mode.
      header: "Konto",
      cell: (t: TransactionOut) =>
        editId === t.id ? (
          <Select
            value={draft.ledger_id}
            onChange={(v) => setDraft({ ...draft, ledger_id: v })}
            options={ledgerOptions.map((l) => ({ value: l.id, label: l.name }))}
            placeholder="— keins —"
            allowEmpty
            emptyLabel="— keins —"
          />
        ) : (
          <Select
            value={t.ledger ? String(t.ledger.id) : ""}
            onChange={(v) => patchM.mutate({ id: t.id, ledger_id: v ? Number(v) : null })}
            options={ledgerOptions.map((l) => ({ value: l.id, label: l.name }))}
            placeholder="Konto wählen…"
          />
        ),
    },
    {
      header: "Bezahlt",
      cell: (t: TransactionOut) => (t.confirmed ? <Badge tone="success">Ja</Badge> : "Nein"),
    },
    {
      header: "",
      cell: (t: TransactionOut) =>
        editId === t.id ? (
          <span className="row-actions">
            <Button busy={saveM.isPending} onClick={() => saveM.mutate(t.id)}>
              Speichern
            </Button>
            <Button variant="ghost" onClick={() => setEditId(null)}>
              Abbrechen
            </Button>
          </span>
        ) : (
          <Button variant="ghost" onClick={() => beginEdit(t)}>
            Bearbeiten
          </Button>
        ),
    },
  ];

  return (
    <section className="flow-step flow-step-wide">
      <h2 className="flow-title">Buchungen</h2>
      <p className="flow-lead">
        Aus den übernommenen Ausgaben werden Überweisungen. Ordne jeder ein Konto zu und fasse
        zusammen, was an dieselbe Person geht.
      </p>

      {transactions.length === 0 ? (
        <div className="stage-empty">
          <p>
            Noch keine Buchungen. Erzeugt werden sie aus {euro(coveredTotal)} übernommenen Belegen
            {statement.excursion ? " sowie Entschädigung und Zuschüssen" : ""}.
          </p>
          <Button busy={busy} onClick={onGenerate}>
            Buchungen erzeugen
          </Button>
        </div>
      ) : (
        <>
          <DataTable rows={transactions} rowKey={(t) => t.id} columns={columns} />

          <div className="stage-actions">
            <Button variant="ghost" busy={busy} disabled={mergeable === 0} onClick={onReduce}>
              {mergeable === 0
                ? "Nichts zusammenzufassen"
                : `${mergeable} Empfänger*in zusammenfassen`}
            </Button>
            {missingLedger > 0 && (
              <span className="stage-hint">
                {missingLedger} Buchung(en) ohne Konto — Zusammenfassen und Auszahlen brauchen es.
              </span>
            )}
          </div>
        </>
      )}

      <div className={`abgleich ${issues.length === 0 ? "ok" : "bad"}`}>
        <span className="readout-caption">Abgleich</span>
        {issues.length === 0 ? (
          <p>Die Buchungen decken die Ausgaben genau.</p>
        ) : (
          <DataTable
            rows={issues}
            rowKey={(i) => i.member.id}
            columns={[
              { header: "Empfänger*in", cell: (i) => i.member.name },
              { header: "Gebucht", cell: (i) => euro(i.current) },
              { header: "Erwartet", cell: (i) => euro(i.target) },
              {
                header: "Differenz",
                cell: (i) => <Badge tone="danger">{euro(i.difference)}</Badge>,
              },
            ]}
          />
        )}
      </div>
    </section>
  );
}

/* --- stage 3: pay --------------------------------------------------------- */

/** Group an IBAN in fours, the way it is printed on a bank statement. */
function formatIban(iban: string): string {
  return iban.replace(/\s+/g, "").replace(/(.{4})/g, "$1 ").trim();
}

/**
 * The payout, and nothing else.
 *
 * This is the irreversible step, so the page carries only what is about to
 * happen — but it carries everything needed to *do* it: each recipient's IBAN
 * and an EPC-QR the treasurer scans with their banking app, exactly as the
 * admin's confirm view did. Every control that could still change the outcome
 * lives on the stages behind it.
 */
function AuszahlenStage({
  statement,
  transactions,
  executed,
  onExecutedChange,
}: {
  statement: StatementOut;
  transactions: TransactionOut[];
  executed: boolean;
  onExecutedChange: (v: boolean) => void;
}) {
  const total = transactions.reduce((s, t) => s + t.amount, 0);
  const unpayable = transactions.filter((t) => !t.code);

  return (
    <section className="payout-final">
      <h2 className="flow-title">Auszahlung</h2>
      <p className="flow-lead">
        {statement.confirmed
          ? "Diese Abrechnung ist bereits ausgezahlt."
          : `Überweise die folgenden ${transactions.length} Beträge an ${payeeCount(
              transactions,
            )} Empfänger*innen — scanne dazu den QR-Code mit deiner Banking-App — und bestätige die Abrechnung danach.`}
      </p>

      {unpayable.length > 0 && (
        <p className="flow-block">
          {unpayable.length} Buchung(en) ohne QR-Code:{" "}
          {unpayable.map((t) => t.member.name).join(", ")}. Ohne gültige IBAN muss die Überweisung
          von Hand erfasst werden.
        </p>
      )}

      <ul className="payout-rows">
        {transactions.map((t) => (
          <li key={t.id} className="payout-row">
            <div className="payout-row-main">
              <span className="payout-row-name">{t.member.name}</span>
              <span className="payout-row-iban">
                {t.iban ? (
                  formatIban(t.iban)
                ) : (
                  <span className="muted">keine IBAN hinterlegt</span>
                )}
                {t.iban && !t.iban_valid && <Badge tone="danger">ungültig</Badge>}
              </span>
              <span className="payout-row-ref">{t.reference}</span>
              <span className="payout-row-ledger">{t.ledger?.name ?? "—"}</span>
            </div>
            <div className="payout-row-amount">{euro(t.amount)}</div>
            <div className="payout-row-qr">
              {t.code ? (
                <>
                  <QRCodeSVG value={t.code} size={116} level="M" marginSize={1} />
                  <span className="payout-qr-caption">Scannen zum Überweisen</span>
                </>
              ) : (
                <span className="muted small">
                  {t.amount === 0 ? "Betrag ist 0 €" : "Keine gültige IBAN"}
                </span>
              )}
            </div>
          </li>
        ))}
      </ul>

      <div className="payout-total">
        <span>Gesamt</span>
        <strong>{euro(total)}</strong>
      </div>

      {!statement.confirmed && (
        <label className="payout-gate">
          <input
            type="checkbox"
            checked={executed}
            onChange={(e) => onExecutedChange(e.target.checked)}
          />
          <span>Ich habe die aufgeführten Überweisungen ausgeführt.</span>
        </label>
      )}
    </section>
  );
}
