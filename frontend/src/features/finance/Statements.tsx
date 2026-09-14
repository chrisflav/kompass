import { useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  DownloadButton,
  Menu,
  Modal,
  PageHeader,
  QueryBoundary,
  Tabs,
  useConfirmDialog,
  useToast,
  type Crumb,
  euro,
} from "../../components/ui";
import type { components } from "../../api/schema";

type StatementBrief = components["schemas"]["StatementBrief"];
type StatementOut = components["schemas"]["StatementOut"];
type MemberBrief = components["schemas"]["MemberBrief"];

/** Colour the status label the same way the admin does. */
function StatusBadge({ statement }: { statement: { confirmed: boolean; submitted: boolean; status_display: string } }) {
  const tone = statement.confirmed ? "success" : statement.submitted ? "info" : "warning";
  return <Badge tone={tone}>{statement.status_display}</Badge>;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("de-DE");
}

/* --- list ---------------------------------------------------------------- */

export function StatementsList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const query = useApiQuery(["finance", "statements"], () =>
    unwrap(client.GET("/api/finance/statements")),
  );
  const enums = useApiQuery(["finance", "enums"], () => unwrap(client.GET("/api/finance/enums")));
  const rows = query.data ?? [];

  const statusOptions = useMemo(
    () => (enums.data?.status ?? []).map((c) => ({ value: String(c.value), label: c.label })),
    [enums.data],
  );

  const config: ListViewConfig<StatementBrief> = useMemo(
    () => ({
      search: (s) => [s.title, s.short_description],
      filters: [
        {
          key: "status",
          label: "Status",
          options: statusOptions,
          match: (s, v) => String(s.status) === v,
        },
      ],
      sort: {
        title: (s) => s.title,
        total: (s) => s.total,
        created_by: (s) => s.created_by?.name,
        submitted_date: (s) => s.submitted_date,
        status: (s) => s.status,
      },
      defaultSort: { key: "submitted_date", dir: "desc" },
    }),
    [statusOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Abrechnungen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("finance.add_global_statement") && (
            <Button onClick={() => navigate("/kompass/finance/statements/new")}>
              Neue Abrechnung
            </Button>
          )
        }
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Abrechnungen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/kompass/finance/statements/${s.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (s) => s.title, sortKey: "title" },
              { header: "Gesamt", cell: (s) => s.total_pretty, sortKey: "total" },
              {
                header: "Angelegt von",
                cell: (s) => s.created_by?.name ?? "—",
                sortKey: "created_by",
              },
              {
                header: "Eingereicht am",
                cell: (s) => formatDate(s.submitted_date),
                sortKey: "submitted_date",
              },
              { header: "Status", cell: (s) => <StatusBadge statement={s} />, sortKey: "status" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail -------------------------------------------------------------- */

export function StatementDetailPage() {
  const { id } = useParams();
  const statementId = Number(id);
  const query = useApiQuery(["finance", "statements", statementId], () =>
    unwrap(
      client.GET("/api/finance/statements/{statement_id}", {
        params: { path: { statement_id: statementId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Abrechnungen", to: "/kompass/finance/statements" },
    { label: query.data?.title ?? "Abrechnung" },
  ];

  return (
    <QueryBoundary query={query}>
      {(statement: StatementOut) => <StatementDetailBody statement={statement} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

/**
 * The statement record view: everything the record holds, read-only.
 *
 * A statement is written in the submission flow and worked in the review
 * pipeline; this page only shows the result and points at whichever of the two
 * applies. It used to carry a second, field-shaped editor of its own, which
 * meant two different ways to change the same statement.
 */
function StatementDetailBody({ statement, crumbs }: { statement: StatementOut; crumbs: Crumb[] }) {
  const mainRows: [string, ReactNode][] = [
    ["Titel", statement.title],
    ["Status", <StatusBadge statement={statement} />],
    [
      "Gültig",
      statement.is_valid ? <Badge tone="success">Ja</Badge> : <Badge tone="danger">Nein</Badge>,
    ],
    ["Kurzbeschreibung", statement.short_description],
    [
      "Fahrt",
      statement.excursion ? (
        <Link to={`/kompass/excursions/${statement.excursion.id}`}>
          {statement.excursion.code} {statement.excursion.name}
        </Link>
      ) : (
        "—"
      ),
    ],
    ["Erklärung", statement.explanation || "—"],
    ["Preis pro Übernachtung", euro(Number(statement.night_cost) || 0)],
  ];

  const recipientRows: [string, ReactNode][] = [
    ["Aufwandsentschädigung an", joinMembers(statement.allowance_to)],
    ["Zuschuss an", memberName(statement.subsidy_to)],
    ["LJP-Beitrag an", memberName(statement.ljp_to)],
  ];

  const adminRows: [string, ReactNode][] = [
    ["Angelegt von", memberName(statement.created_by)],
    ["Eingereicht von", memberName(statement.submitted_by)],
    ["Eingereicht am", formatDate(statement.submitted_date)],
    ["Bezahlt von", memberName(statement.confirmed_by)],
    ["Bezahlt am", formatDate(statement.confirmed_date)],
  ];

  return (
    <div>
      <PageHeader
        breadcrumbs={crumbs}
        actions={
          <>
            <Button variant="ghost" onClick={() => history.back()}>
              Zurück
            </Button>
            <StatementActions statement={statement} />
          </>
        }
      />

      <Tabs
        tabs={[
          { id: "abrechnung", label: "Abrechnung", content: <DetailList items={mainRows} /> },
          {
            id: "empfaenger",
            label: "Empfänger",
            content: (
              <>
                <p className="fieldset-help">
                  {statement.excursion
                    ? "Aufwandsentschädigung, Zuschuss und LJP-Beitrag werden im Erstattungs-Schritt der Abrechnung gewählt — nur Jugendleiter*innen dieser Fahrt dürfen sie erhalten."
                    : "Aufwandsentschädigung, Zuschuss und LJP-Beitrag gibt es nur für Abrechnungen, die zu einer Ausfahrt gehören."}
                </p>
                <DetailList items={recipientRows} />
              </>
            ),
          },
          { id: "verwaltung", label: "Verwaltung", content: <DetailList items={adminRows} /> },
          {
            id: "belege",
            label: "Belege",
            content: <StatementBills statement={statement} />,
          },
        ]}
      />
    </div>
  );
}

/** The statement's receipts, read-only; they are added and edited in the flow. */
function StatementBills({ statement }: { statement: StatementOut }) {
  const navigate = useNavigate();
  return (
    <DataTable
      rows={statement.bills}
      rowKey={(b) => b.id}
      empty="Keine Belege."
      onRowClick={(b) => navigate(`/kompass/finance/bills/${b.id}`)}
      columns={[
        { header: "Beschreibung", cell: (b) => b.short_description },
        { header: "Ausgelegt von", cell: (b) => b.paid_by?.name ?? "—" },
        { header: "Betrag", cell: (b) => euro(b.amount) },
        {
          header: "Beleg",
          cell: (b) =>
            b.has_proof ? <Badge tone="success">Ja</Badge> : <Badge tone="warning">Fehlt</Badge>,
        },
        {
          header: "Übernommen",
          cell: (b) => (b.costs_covered ? <Badge tone="success">Ja</Badge> : "Nein"),
        },
      ]}
    />
  );
}

function memberName(member: MemberBrief | null | undefined): string {
  return member ? member.name : "—";
}

function joinMembers(members: MemberBrief[] | null | undefined): string {
  return members && members.length ? members.map((m) => m.name).join(", ") : "—";
}

/* --- state-machine actions ----------------------------------------------- */

/** How a state transition is gated before it runs: a plain "are you sure?"
 * prompt. */
type Gate = "simple";

interface StatementAction {
  label: string;
  run: () => Promise<unknown>;
  variant?: "ghost" | "danger";
  /** When set, clicking the button opens this confirmation Modal first. */
  gate?: Gate;
  /** Prompt text for the `simple` gate. */
  message?: string;
}

function StatementActions({ statement }: { statement: StatementOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const [pending, setPending] = useState<StatementAction | null>(null);

  const mutation = useApiMutation((run: () => Promise<unknown>) => run(), {
    invalidate: [["finance", "statements"], ["finance", "statements", statement.id]],
    onSuccess: () => {
      toast.success("Aktion ausgeführt.");
      setPending(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const deleteMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statement.id } },
        }),
      ),
    {
      invalidate: [["finance", "statements"]],
      onSuccess: () => {
        toast.success("Abrechnung gelöscht.");
        navigate("/kompass/finance/statements");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const path = { params: { path: { statement_id: statement.id } } } as const;
  const submitted = statement.submitted;
  const confirmed = statement.confirmed;
  const processable = submitted && !confirmed;

  const actions: StatementAction[] = [];

  // Submitting is the ending of the submission flow, not a loose button here —
  // a statement is handed in from the screen that shows what is being handed in.
  // unconfirm only while confirmed
  if (confirmed) {
    actions.push({
      label: "Bestätigung aufheben",
      variant: "ghost",
      gate: "simple",
      message: "Wirklich zurücksetzen?",
      run: () => unwrap(client.POST("/api/finance/statements/{statement_id}/unconfirm", path)),
    });
  }

  // Workflow / state-transition buttons plus the destructive delete, grouped into
  // a single "Aktionen ▾" menu (2+) or rendered as one ghost button (exactly 1).
  const workflowButtons: ReactNode[] = actions.map((a) => (
    <Button
      key={a.label}
      type="button"
      variant={a.variant ?? "ghost"}
      busy={mutation.isPending}
      onClick={() => (a.gate ? setPending(a) : mutation.mutate(a.run))}
    >
      {a.label}
    </Button>
  ));
  if (!submitted) {
    workflowButtons.push(
      <Button
        key="__delete"
        type="button"
        variant="danger"
        busy={deleteMutation.isPending}
        onClick={async () => {
          if (
            await confirm({
              message: "Abrechnung wirklich löschen?",
              danger: true,
              confirmLabel: "Löschen",
            })
          )
            deleteMutation.mutate(undefined);
        }}
      >
        Löschen
      </Button>,
    );
  }

  return (
    <>
      {confirmed && (
        <DownloadButton
          path={`/api/finance/documents/statements/${statement.id}/summary`}
          filename={`Abrechnung_${statement.id}_Zusammenfassung.pdf`}
        >
          Zusammenfassung (PDF)
        </DownloadButton>
      )}
      {/* Both working modes leave the record view for their own guided route:
          a draft is finished in the submission flow, a submitted statement is
          worked through the review pipeline. */}
      {!submitted && (
        <Button
          type="button"
          onClick={() => navigate(`/kompass/finance/statements/${statement.id}/edit`)}
        >
          Weiter bearbeiten
        </Button>
      )}
      {processable && can("finance.process_statementsubmitted") && (
        <Button
          type="button"
          onClick={() => navigate(`/kompass/finance/statements/${statement.id}/review`)}
        >
          Prüfen & auszahlen
        </Button>
      )}
      {workflowButtons.length >= 2 ? (
        <Menu label="Aktionen">{workflowButtons}</Menu>
      ) : (
        workflowButtons
      )}
      {/* Portal the modals to <body>: this component renders inside the
          statement's <form>, and a Modal's untyped close button would otherwise
          submit that form. */}
      {pending &&
        createPortal(
          <Modal title="Bestätigen" onClose={() => setPending(null)}>
            <div className="stack">
              <p>{pending.message}</p>
              <div className="row-actions">
                <Button
                  type="button"
                  busy={mutation.isPending}
                  onClick={() => mutation.mutate(pending.run)}
                >
                  Bestätigen
                </Button>
                <Button type="button" variant="ghost" onClick={() => setPending(null)}>
                  Abbrechen
                </Button>
              </div>
            </div>
          </Modal>,
          document.body,
        )}
    </>
  );
}
