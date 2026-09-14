import { useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  euro,
  PageHeader,
  QueryBoundary,
} from "../../components/ui";
import type { components } from "../../api/schema";

type TransactionBrief = components["schemas"]["TransactionBrief"];
type TransactionOut = components["schemas"]["TransactionOut"];
type StatementBrief = components["schemas"]["StatementBrief"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("de-DE");
}

/* --- list (read-only) ----------------------------------------------------
 * Full parity with the Django TransactionAdmin changelist: all list_display
 * columns (recipient/ledger/amount/reference/statement/paid/paid-on/authorized-by),
 * search over reference, filters (ledger/statement/confirmed), sortable headers. */

export function TransactionsList() {
  const navigate = useNavigate();
  const query = useApiQuery(["finance", "transactions"], () =>
    unwrap(client.GET("/api/finance/transactions")),
  );
  const statements = useApiQuery(["finance", "statements"], () =>
    unwrap(client.GET("/api/finance/statements")),
  );
  const rows = query.data ?? [];

  const statementTitle = useMemo(() => {
    const map = new Map<number, string>();
    (statements.data ?? []).forEach((s: StatementBrief) => map.set(s.id, s.title));
    return map;
  }, [statements.data]);

  const ledgerOptions = useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach((t) => t.ledger && map.set(String(t.ledger.id), t.ledger.name));
    return [...map].map(([value, label]) => ({ value, label }));
  }, [rows]);

  const statementOptions = useMemo(() => {
    const ids = new Set<number>();
    rows.forEach((t) => ids.add(t.statement_id));
    return [...ids]
      .sort((a, b) => a - b)
      .map((id) => ({ value: String(id), label: statementTitle.get(id) ?? `#${id}` }));
  }, [rows, statementTitle]);

  const config: ListViewConfig<TransactionBrief> = useMemo(
    () => ({
      search: (t) => [t.reference, t.member.name],
      filters: [
        {
          key: "ledger",
          label: "Konto",
          options: ledgerOptions,
          match: (t, v) => (t.ledger ? String(t.ledger.id) === v : false),
        },
        {
          key: "statement",
          label: "Abrechnung",
          options: statementOptions,
          match: (t, v) => String(t.statement_id) === v,
        },
        {
          key: "confirmed",
          label: "Bezahlt",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (t, v) => (v === "yes") === Boolean(t.confirmed),
        },
      ],
      sort: {
        member: (t) => t.member.name,
        ledger: (t) => t.ledger?.name,
        amount: (t) => t.amount,
        reference: (t) => t.reference,
        statement: (t) => t.statement_id,
        confirmed: (t) => t.confirmed,
        confirmed_date: (t) => t.confirmed_date,
        confirmed_by: (t) => t.confirmed_by?.name,
      },
    }),
    [ledgerOptions, statementOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader breadcrumbs={[{ label: "Buchungen" }]} subtitle={`${view.rows.length} / ${view.total}`} />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Buchungen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(t) => t.id}
            onRowClick={(t) => navigate(`/kompass/finance/transactions/${t.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Empfänger", cell: (t) => t.member.name, sortKey: "member" },
              { header: "Konto", cell: (t) => t.ledger?.name ?? "—", sortKey: "ledger" },
              { header: "Betrag", cell: (t) => euro(t.amount), sortKey: "amount" },
              { header: "Verwendungszweck", cell: (t) => t.reference, sortKey: "reference" },
              {
                header: "Abrechnung",
                cell: (t) => statementTitle.get(t.statement_id) ?? `#${t.statement_id}`,
                sortKey: "statement",
              },
              {
                header: "Bezahlt",
                cell: (t) => (t.confirmed ? <Badge tone="success">Ja</Badge> : "Nein"),
                sortKey: "confirmed",
              },
              {
                header: "Bezahlt am",
                cell: (t) => formatDate(t.confirmed_date),
                sortKey: "confirmed_date",
              },
              {
                header: "Autorisiert von",
                cell: (t) => t.confirmed_by?.name ?? "—",
                sortKey: "confirmed_by",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail (read-only) -------------------------------------------------- */

export function TransactionDetailPage() {
  const { id } = useParams();
  const transactionId = Number(id);
  const query = useApiQuery(["finance", "transactions", transactionId], () =>
    unwrap(
      client.GET("/api/finance/transactions/{transaction_id}", {
        params: { path: { transaction_id: transactionId } },
      }),
    ),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Buchungen", to: "/kompass/finance/transactions" },
          { label: query.data?.reference ?? "Buchung" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(tx: TransactionOut) => (
          <DetailList
            items={[
              ["Empfänger", tx.member.name],
              ["Betrag", euro(tx.amount)],
              ["Verwendungszweck", tx.reference],
              ["Konto", tx.ledger ? tx.ledger.name : "—"],
              [
                "Bezahlt",
                tx.confirmed ? <Badge tone="success">Ja</Badge> : <Badge tone="warning">Nein</Badge>,
              ],
              ["Bezahlt am", formatDate(tx.confirmed_date)],
              ["Autorisiert von", tx.confirmed_by ? tx.confirmed_by.name : "—"],
              [
                "Abrechnung",
                <Link to={`/kompass/finance/statements/${tx.statement_id}`}>#{tx.statement_id}</Link>,
              ],
              ["EPC-QR (Code)", <code style={{ wordBreak: "break-all" }}>{tx.code}</code>],
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
