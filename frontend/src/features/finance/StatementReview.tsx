import { lazy, Suspense, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { mediaUrl } from "../../api/client";
import { ChunkBoundary } from "../../components/ChunkBoundary";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { usePermissions } from "../../api/me";
import { useMembers } from "../../api/queries";
import {
  Badge,
  Button,
  DataTable,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  Spinner,
  useConfirmDialog,
  useToast,
  euro,
} from "../../components/ui";
import {
  ApprovalRecord,
  outstandingText,
  type ApprovalConstraintOut,
  type StatementApprovalOut,
} from "./approval";
import { EtappenRail, type Etappe } from "./stages";
import { payoutWords, type PayoutWords } from "./payout";
import type { components } from "../../api/schema";

type StatementOut = components["schemas"]["StatementOut"];
type BillBrief = components["schemas"]["BillBrief"];
type TransactionOut = components["schemas"]["TransactionOut"];

type StageId = "expenses" | "bookings" | "payout";

const STATEMENTS = "/kompass/finance/statements";

// Only the payout stage draws QR codes, so the encoder is fetched when it does.
const QRCodeSVG = lazy(() => import("qrcode.react").then((m) => ({ default: m.QRCodeSVG })));

/**
 * The treasurer-facing review pipeline.
 *
 * Processing used to be one modal that showed every control at once and left
 * the central decision — which bills the section actually covers — on a
 * different screen, with the receipt nowhere in sight. This walks the three
 * things that genuinely happen in order: judge the expenses against their
 * evidence, build the bank transfers, then release the payout.
 *
 * What *releasing* is, the section declares: in Heidelberg the person on this
 * screen makes the transfers and the statement ends up ausgezahlt; in
 * Ludwigsburg the Geschäftsstelle makes them and the statement ends up zur
 * Auszahlung übergeben. No sentence is true in both, so the last leg's wording,
 * its acknowledgement, its QR codes and its buttons all come out of
 * {@link payoutWords}.
 *
 * The last leg is also the approval record, which used to be a route of its
 * own. Two doors into one room, and this was the one that skipped the other:
 * "Prüfen & auszahlen" posted `/confirm`, which is a signature like any other
 * — so pressing it short of a quorum took the signature and answered "not
 * ready to be confirmed", while a separate "Freigabe" page offered the same
 * act under a different name. There is one surface now, and the act it offers
 * is whichever one is actually left to do: see {@link FreigabeStage}.
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
  // Only where the reviewer *is* the payer; a handoff has nothing to
  // acknowledge and `words.acknowledgement` is then null.
  const [executed, setExecuted] = useState(false);
  // Who makes the transfers, and therefore what every sentence below says: the
  // declaration of the rules this statement is bound to. See ./payout.
  const words = payoutWords(statement);
  const acknowledged = words.acknowledgement === null || executed;

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
    ["finance", "statements", statement.id, "approval"],
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

  // Only the last leg needs the record, and it needs it before the button is
  // offered: which act the button performs is the record's answer.
  const approvalQuery = useApiQuery(
    ["finance", "statements", statement.id, "approval"],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}/approval", {
          params: { path: { statement_id: statement.id } },
        }),
      ),
    { enabled: stage === "payout" },
  );
  const approval = approvalQuery.data;
  // A record that cannot be loaded must not take the payout with it: `confirm`
  // is the act this leg always offered, and it now names which of its two
  // refusals applies, so falling back to it is safe rather than silent.
  const completes = approval ? approval.completes_approval : approvalQuery.isError;

  const etappen: Etappe[] = stages.map((s) => ({
    id: s,
    label: { expenses: "Prüfen", bookings: "Buchungen", payout: "Freigabe" }[s],
    readout:
      s === "expenses"
        ? `${covered.length}/${statement.bills.length} · ${euro(coveredTotal)}`
        : s === "bookings"
          ? transactions.length === 0
            ? "keine"
            : `${transactions.length} · ${euro(txTotal)}`
          : statement.confirmed
            ? words.readout
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

  // A signature that is not the last one. It stays on this page — there is
  // nothing to go to, the statement is still waiting — and it says what it
  // did and what is left, read off the record the endpoint answers with
  // rather than guessed from a status code. The old route through `/confirm`
  // took the signature and reported "Statement is not ready to be confirmed."
  const signM = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/approve", {
          params: { path: { statement_id: statement.id } },
          body: { note: "" },
        }),
      ),
    {
      invalidate,
      onSuccess: (data: StatementApprovalOut) =>
        toast.success(
          data.approved
            ? "Freigabe vermerkt. Alle Freigaben liegen jetzt vor."
            : `Freigabe vermerkt. ${outstandingText(data)}`,
        ),
      onError: (e: Error) => toast.error(e.message),
    },
  );

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
            words={words}
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
          <FreigabeStage
            statement={statement}
            transactions={transactions}
            approval={approval}
            approvalError={approvalQuery.error?.message ?? null}
            completes={completes}
            executed={executed}
            onExecutedChange={setExecuted}
            words={words}
            invalidate={invalidate}
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
            /* Two acts, one button area, and the record decides which: a
               signature that completes the quorum releases the statement, so
               it is `confirm` with whatever the mode asks for in front of it;
               one short of the quorum only signs, so it is `approve`, which
               answers with the record and can say what is still missing.

               What "release" means is the section's declaration, so the labels,
               the dialog and the toast come out of `words`. Self-payment keeps
               its pair of buttons, the `send` flag and the acknowledgement; a
               handoff has one button and no flag, because its mail is not an
               extra — `/confirm` sends it, and refuses to move the status if it
               did not go. */
            completes ? (
              <>
                {words.releaseOnly !== null && (
                  <Button
                    variant="ghost"
                    busy={actionM.isPending}
                    disabled={!statement.is_valid || !acknowledged}
                    onClick={() =>
                      run(
                        () =>
                          unwrap(
                            client.POST("/api/finance/statements/{statement_id}/confirm", path),
                          ),
                        "Abrechnung bestätigt.",
                        () => navigate(`${STATEMENTS}/${statement.id}`),
                      )
                    }
                  >
                    {words.releaseOnly}
                  </Button>
                )}
                <Button
                  busy={actionM.isPending}
                  disabled={!statement.is_valid || !acknowledged}
                  onClick={async () => {
                    const ok = await confirm({
                      title: words.dialog.title,
                      message: words.dialog.message(
                        euro(statement.total),
                        payeeCount(transactions),
                      ),
                      confirmLabel: words.dialog.confirm,
                    });
                    if (ok)
                      run(
                        () =>
                          unwrap(
                            client.POST("/api/finance/statements/{statement_id}/confirm", {
                              params: {
                                path: { statement_id: statement.id },
                                // The office's copy is the handoff itself, so
                                // the server sends it; asking for it here as
                                // well would be a second mail for one act.
                                query: words.mailsItself ? {} : { send: true },
                              },
                            }),
                          ),
                        words.done,
                        () => navigate(`${STATEMENTS}/${statement.id}`),
                      );
                  }}
                >
                  {words.release}
                </Button>
              </>
            ) : (
              approval?.may_approve && (
                <Button
                  busy={signM.isPending}
                  disabled={!statement.is_valid}
                  onClick={() => signM.mutate(undefined)}
                >
                  Jetzt freigeben
                </Button>
              )
            )
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
        <p className="flow-block">{words.locked(statement.validity_display)}</p>
      )}
    </div>
  );
}

function payeeCount(transactions: TransactionOut[]): number {
  return new Set(transactions.map((t) => t.member.id)).size;
}

/**
 * Why one person has two rows.
 *
 * The section's rules can keep an amount out of every other bank transfer — a
 * Tourenleitervergütung is tax-relevant and has to arrive on its own — and the
 * two rows then read as a duplicate somebody forgot to combine, which sends a
 * finance officer hunting for the way to combine it that the rules have taken
 * away. This says they are deliberate.
 *
 * The token stays on hover rather than in the line. It is the ruleset's own
 * vocabulary: "steuerrelevant" happens to read as German, and another
 * section's token may be an identifier nobody outside its rules file knows, so
 * the screen states the consequence and offers the name.
 */
function SettlementMark({ group }: { group: string }) {
  return (
    <span className="settlement-mark" title={`Abrechnungsgruppe: ${group}`}>
      wird getrennt überwiesen
    </span>
  );
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
                    {b.paid_by ? `ausgelegt von ${b.paid_by.name}` : "kein*e Zahler*in eingetragen"}
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
  words,
  invalidate,
}: {
  statement: StatementOut;
  transactions: TransactionOut[];
  coveredTotal: number;
  busy: boolean;
  onGenerate: () => void;
  onReduce: () => void;
  words: PayoutWords;
  invalidate: unknown[][];
}) {
  const toast = useToast();
  const ledgers = useApiQuery(["ledgers"], () =>
    unwrap(client.GET("/api/finance/ledgers/")),
  );
  const members = useMembers();
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
  // What becomes one bank transfer is `(member, ledger, settlement_group)`, and
  // the count on the button has to use the same key as the merge itself
  // (`Statement.reduce_transactions`) or it offers work that cannot be done:
  // keyed on the first two, a section that keeps a taxable Vergütung out of the
  // travel costs read as one recipient to bundle, the POST ran, and nothing
  // merged — a button that did nothing and said nothing about why.
  const mergeable = useMemo(() => {
    const seen = new Map<string, number>();
    for (const t of transactions) {
      if (!t.ledger) continue;
      const key = `${t.member.id}:${t.ledger.id}:${t.settlement_group}`;
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
          <span className="recipient-cell">
            {t.member.name}
            {t.settlement_group && <SettlementMark group={t.settlement_group} />}
          </span>
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
      header: words.booked,
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
                : `${mergeable} ${mergeable === 1 ? "Empfänger*in" : "Empfänger*innen"} zusammenfassen`}
            </Button>
            {missingLedger > 0 && (
              <span className="stage-hint">{words.needsLedger(missingLedger)}</span>
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

/* --- stage 3: release ----------------------------------------------------- */

/** Group an IBAN in fours, the way it is printed on a bank statement. */
function formatIban(iban: string): string {
  return iban.replace(/\s+/g, "").replace(/(.{4})/g, "$1 ").trim();
}

/**
 * What the rules ask, who has signed — and the payout.
 *
 * One surface, because there is one act. The signatures the section's rules
 * ask for and the payout they release used to be two pages: this one, which
 * posted `/confirm`, and a "Freigabe" page, which posted `/approve`. Both are
 * `Statement.approve` underneath — a signature, which pays the statement out
 * when it completes the quorum and is simply recorded when it does not — so
 * the two pages were two names for one thing, and the one with "auszahlen" in
 * its label was the one that looked as though it skipped the other.
 *
 * The record comes first, because it is what decides whether the payout may
 * happen at all; the transfers follow, with each recipient's IBAN — and, where
 * the person on this screen is the one making them, the EPC-QR they scan with
 * their banking app, exactly as the admin's confirm view did. Every control
 * that could still change the outcome lives on the legs behind this one.
 *
 * Where the Geschäftsstelle makes the transfers the same rows are a last look
 * at what is about to be handed over, there is nothing to scan and nothing to
 * acknowledge, and the one button hands it over.
 *
 * Where a section asks for a single signature the whole thing is one step and
 * reads as one: one card, one acknowledgement, the buttons that were always
 * there.
 */
function FreigabeStage({
  statement,
  transactions,
  approval,
  approvalError,
  completes,
  executed,
  onExecutedChange,
  words,
  invalidate,
}: {
  statement: StatementOut;
  transactions: TransactionOut[];
  approval: StatementApprovalOut | undefined;
  approvalError: string | null;
  completes: boolean;
  executed: boolean;
  onExecutedChange: (v: boolean) => void;
  words: PayoutWords;
  invalidate: unknown[][];
}) {
  const total = transactions.reduce((s, t) => s + t.amount, 0);
  // Which bookings nobody can transfer, asked the way the mode cares about.
  // Where the reviewer pays, a missing QR code is the problem — they would have
  // to type the transfer out by hand. Where the office pays, the QR code is
  // nobody's business and the account is: a booking with no usable IBAN is one
  // the office cannot act on and cannot ask about, so it has to be fixed before
  // the handoff rather than after it. A booking of 0 € needs no transfer under
  // either reading.
  const unpayable = words.codes
    ? transactions.filter((t) => !t.code)
    : transactions.filter((t) => t.amount !== 0 && (!t.iban || !t.iban_valid));

  return (
    <section className="payout-final">
      <h2 className="flow-title">Freigabe</h2>
      {approval ? (
        <Freigaben statement={statement} approval={approval} invalidate={invalidate} />
      ) : (
        <p className="muted">{approvalError ?? "Freigaben werden geladen …"}</p>
      )}

      <h3 className="fieldset-title">{words.heading}</h3>
      <p className="flow-lead">
        {statement.confirmed
          ? words.released
          : words.lead(transactions.length, payeeCount(transactions))}
      </p>

      {unpayable.length > 0 && (
        <p className="flow-block">{words.unpayable(unpayable.map((t) => t.member.name))}</p>
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
              <span className="payout-row-ledger">
                {t.ledger?.name ?? "—"}
                {t.settlement_group && <SettlementMark group={t.settlement_group} />}
              </span>
            </div>
            <div className="payout-row-amount">{euro(t.amount)}</div>
            {/* A code is an instrument for making a transfer here and now, so
                only the mode that makes them draws one. In a handoff the rows
                are a last look at what is about to be handed over — the
                account, the reference, the amount — and a QR code nobody on
                this screen will scan is noise beside them. The office gets the
                same four facts on paper (`statement_summary.tex`). */}
            {words.codes && (
              <div className="payout-row-qr">
                {t.code ? (
                  <>
                    <ChunkBoundary>
                      <Suspense fallback={<Spinner />}>
                        <QRCodeSVG value={t.code} size={116} level="M" marginSize={1} />
                      </Suspense>
                    </ChunkBoundary>
                    <span className="payout-qr-caption">Scannen zum Überweisen</span>
                  </>
                ) : (
                  <span className="muted small">
                    {t.amount === 0 ? "Betrag ist 0 €" : "Keine gültige IBAN"}
                  </span>
                )}
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="payout-total">
        <span>Gesamt</span>
        <strong>{euro(total)}</strong>
      </div>

      {/* The acknowledgement belongs to the payout, so it is asked for when the
          next click *is* the payout. Asking it of a first signature would make
          somebody claim they had made transfers that nothing has released —
          and asking it at all in a section whose office makes the transfers
          would be the same false claim with nobody who could truthfully tick
          it, which is why `words.acknowledgement` is null there. */}
      {!statement.confirmed && completes && words.acknowledgement !== null && (
        <label className="payout-gate">
          <input
            type="checkbox"
            checked={executed}
            onChange={(e) => onExecutedChange(e.target.checked)}
          />
          <span>{words.acknowledgement}</span>
        </label>
      )}
    </section>
  );
}

/**
 * The signatures the rules ask for, where the signature is given.
 *
 * The sentence under the heading is the one the two-door interface never
 * managed to say: how much is still missing, and from which step. It comes out
 * of the record rather than out of a status code, so it is as true after a
 * signature as before one.
 */
function Freigaben({
  statement,
  approval,
  invalidate,
}: {
  statement: StatementOut;
  approval: StatementApprovalOut;
  invalidate: unknown[][];
}) {
  const toast = useToast();
  const { can } = usePermissions();
  const [overriding, setOverriding] = useState<ApprovalConstraintOut | null>(null);
  const [reason, setReason] = useState("");
  const [errors, setErrors] = useState<string[]>([]);

  const overrideM = useApiMutation(
    (vars: { name: string; reason: string }) =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/override-approval", {
          params: { path: { statement_id: statement.id } },
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
        const refusal = e instanceof ApiError ? e.fieldErrors.__all__ : undefined;
        setErrors(refusal ?? [e.message]);
        toast.error(e.message);
      },
    },
  );

  const idle = !statement.confirmed && !approval.completes_approval && !approval.may_approve;

  return (
    <>
      <p className="flow-lead">
        {statement.confirmed ? "Alle Freigaben liegen vor." : outstandingText(approval)}
      </p>
      <ApprovalRecord
        approval={approval}
        onOverride={
          can("finance.process_statementsubmitted")
            ? (constraint) => {
                setErrors([]);
                setReason("");
                setOverriding(constraint);
              }
            : undefined
        }
      />
      {idle && (
        <p className="stage-hint">
          Für dich ist hier nichts mehr zu tun — die Abrechnung wartet auf die fehlenden
          Unterschriften.
        </p>
      )}

      {overriding && (
        <Modal title="Ohne Unterschrift freigeben" size="sm" onClose={() => setOverriding(null)}>
          <div className="stack">
            <p className="muted small">
              „{overriding.description || overriding.name}" wird ohne die verlangten Unterschriften
              freigegeben. Wer das tut und warum, bleibt dauerhaft vermerkt.
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
