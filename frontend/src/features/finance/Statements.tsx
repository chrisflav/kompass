import { useMemo, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft, type DraftRow } from "../../components/inlineDraft";
import { postMultipart } from "./Bills";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  DownloadButton,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type StatementBrief = components["schemas"]["StatementBrief"];
type StatementOut = components["schemas"]["StatementOut"];
type ExcursionBrief = components["schemas"]["ExcursionBrief"];
type MemberBrief = components["schemas"]["MemberBrief"];
type TransactionOut = components["schemas"]["TransactionOut"];
type LedgerListOut = components["schemas"]["LedgerListOut"];

/** Colour the status label the same way the admin does. */
function StatusBadge({ statement }: { statement: { confirmed: boolean; submitted: boolean; status_display: string } }) {
  const tone = statement.confirmed ? "success" : statement.submitted ? "info" : "warning";
  return <Badge tone={tone}>{statement.status_display}</Badge>;
}

function euro(value: number): string {
  return `${value.toFixed(2)} €`;
}

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("de-DE");
}

/* --- list ---------------------------------------------------------------- */

export function StatementsList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
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
        actions={<Button onClick={() => setCreating(true)}>Neue Abrechnung</Button>}
      />
      {creating && (
        <Modal title="Neue Abrechnung" onClose={() => setCreating(false)}>
          <StatementCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Abrechnungen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/app/finance/statements/${s.id}`)}
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

/* --- create -------------------------------------------------------------- */

function StatementCreateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    short_description: "",
    explanation: "",
    excursion_id: "" as string,
    night_cost: "0",
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const excursions = useApiQuery(["members", "excursions"], () =>
    unwrap(client.GET("/api/members/excursions")),
  );

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements", {
          body: {
            short_description: form.short_description,
            explanation: form.explanation,
            excursion_id: form.excursion_id ? Number(form.excursion_id) : null,
            night_cost: Number(form.night_cost) || 0,
          },
        }),
      ),
    {
      invalidate: [["finance", "statements"]],
      onSuccess: (created: StatementOut) => {
        toast.success("Abrechnung angelegt.");
        onDone();
        navigate(`/app/finance/statements/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(undefined);
      }}
    >
      <Field label="Kurzbeschreibung">
        <input
          required
          value={form.short_description}
          onChange={(e) => setForm({ ...form, short_description: e.target.value })}
        />
        {fieldErrors.short_description && (
          <div className="field-error">{fieldErrors.short_description.join(" ")}</div>
        )}
      </Field>
      <Field label="Erklärung">
        <textarea
          value={form.explanation}
          onChange={(e) => setForm({ ...form, explanation: e.target.value })}
        />
        {fieldErrors.explanation && (
          <div className="field-error">{fieldErrors.explanation.join(" ")}</div>
        )}
      </Field>
      <Field label="Fahrt">
        <Select
          value={form.excursion_id}
          onChange={(v) => setForm({ ...form, excursion_id: v })}
          options={(excursions.data ?? []).map((ex: ExcursionBrief) => ({
            value: ex.id,
            label: `${ex.code} ${ex.name}`,
          }))}
          placeholder="— keine —"
          allowEmpty
          emptyLabel="— keine —"
        />
        {fieldErrors.excursion && (
          <div className="field-error">{fieldErrors.excursion.join(" ")}</div>
        )}
      </Field>
      <Field label="Preis pro Übernachtung">
        <input
          type="number"
          step="0.01"
          value={form.night_cost}
          onChange={(e) => setForm({ ...form, night_cost: e.target.value })}
        />
        {fieldErrors.night_cost && (
          <div className="field-error">{fieldErrors.night_cost.join(" ")}</div>
        )}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Anlegen
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
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

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Abrechnungen", to: "/app/finance/statements" },
          { label: query.data?.title ?? "Abrechnung" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(statement: StatementOut) => <StatementDetailBody statement={statement} />}
      </QueryBoundary>
    </div>
  );
}

function StatementDetailBody({ statement }: { statement: StatementOut }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState(() => ({
    short_description: statement.short_description ?? "",
    explanation: statement.explanation ?? "",
    night_cost: String(statement.night_cost ?? "0"),
  }));

  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: { short_description: string; explanation: string; night_cost: number }) =>
      unwrap(
        client.PATCH("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statement.id } },
          body,
        }),
      ),
    { invalidate: [["finance", "statements"], ["finance", "statements", statement.id]] },
  );

  function startEditing() {
    setForm({
      short_description: statement.short_description ?? "",
      explanation: statement.explanation ?? "",
      night_cost: String(statement.night_cost ?? "0"),
    });
    setFieldErrors({});
    setEditing(true);
  }

  // Fieldset "Abrechnung": mirrors the admin change form (short_description or
  // excursion / explanation / status). status is read-only (transitions only via
  // the action buttons); excursion is read-only (settable at create only).
  const mainRows: DetailRow[] = [
    { label: "Titel", value: statement.title },
    { label: "Status", value: <StatusBadge statement={statement} /> },
    {
      label: "Gültig",
      value: statement.is_valid ? (
        <Badge tone="success">Ja</Badge>
      ) : (
        <Badge tone="danger">Nein</Badge>
      ),
    },
    {
      label: "Kurzbeschreibung",
      value: statement.short_description,
      field: "short_description",
      edit: (
        <input
          value={form.short_description}
          onChange={(e) => setForm({ ...form, short_description: e.target.value })}
        />
      ),
    },
    {
      label: "Fahrt",
      value: statement.excursion
        ? `${statement.excursion.code} ${statement.excursion.name}`
        : "—",
    },
    {
      label: "Erklärung",
      value: statement.explanation || "—",
      field: "explanation",
      edit: (
        <textarea
          value={form.explanation}
          onChange={(e) => setForm({ ...form, explanation: e.target.value })}
        />
      ),
    },
    {
      label: "Preis pro Übernachtung",
      value: euro(Number(statement.night_cost) || 0),
      field: "night_cost",
      edit: (
        <input
          type="number"
          step="0.01"
          value={form.night_cost}
          onChange={(e) => setForm({ ...form, night_cost: e.target.value })}
        />
      ),
    },
  ];

  // Fieldset "Empfänger": M2M/FK recipients driving allowance/subsidy/LJP
  // transactions. Read-only in the API (edited in Django via the excursion inline).
  const recipientRows: DetailRow[] = [
    { label: "Aufwandsentschädigung an", value: joinMembers(statement.allowance_to) },
    { label: "Zuschuss an", value: memberName(statement.subsidy_to) },
    { label: "LJP-Beitrag an", value: memberName(statement.ljp_to) },
  ];

  // Fieldset "Verwaltung": read-only workflow metadata.
  const adminRows: DetailRow[] = [
    { label: "Angelegt von", value: memberName(statement.created_by) },
    { label: "Eingereicht von", value: memberName(statement.submitted_by) },
    { label: "Eingereicht am", value: formatDate(statement.submitted_date) },
    { label: "Bezahlt von", value: memberName(statement.confirmed_by) },
    { label: "Bezahlt am", value: formatDate(statement.confirmed_date) },
  ];

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setFieldErrors({});
        setSaving(true);
        try {
          await mutation.mutateAsync({
            short_description: form.short_description,
            explanation: form.explanation,
            night_cost: Number(form.night_cost) || 0,
          });
          await runFlushes();
          toast.success("Gespeichert.");
          setEditing(false);
        } catch (err) {
          if (err instanceof ApiError) setFieldErrors(err.fieldErrors);
          toast.error(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
        } finally {
          setSaving(false);
        }
      }}
    >
      <div className="detail-actions">
        {editing ? (
          <>
            <Button type="submit" busy={saving}>
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Abbrechen
            </Button>
          </>
        ) : (
          <>
            {!statement.submitted && (
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            )}
            <StatementActions statement={statement} />
          </>
        )}
      </div>

      <Tabs
        tabs={[
          { id: "abrechnung", label: "Abrechnung", content: <EditableDetail rows={mainRows} editing={editing} errors={fieldErrors} /> },
          { id: "empfaenger", label: "Empfänger", content: <EditableDetail rows={recipientRows} editing={editing} errors={fieldErrors} /> },
          { id: "verwaltung", label: "Verwaltung", content: <EditableDetail rows={adminRows} editing={editing} errors={fieldErrors} /> },
          {
            id: "betraege",
            label: "Beträge",
            content: (
              <DetailList
                items={[
                  ["Gesamt", euro(statement.total)],
                  ["Belege gesamt", euro(statement.total_bills)],
                  ["Belege (nicht übernommen)", euro(statement.total_bills_not_covered)],
                  ["Aufwandsentschädigung gesamt", euro(statement.total_allowance)],
                  ["Aufwandsentschädigung pro JL", euro(statement.allowance_per_yl)],
                  ["Ausgezahlte Aufwandsentschädigungen", statement.allowances_paid],
                  ["Zuschüsse gesamt", euro(statement.total_subsidies)],
                  ["Ausgezahlte Zuschüsse", euro(statement.subsidies_paid)],
                  ["Fahrtkosten gesamt", euro(statement.total_transportation)],
                  ["Fahrtkosten pro JL", euro(statement.transportation_per_yl)],
                  ["Übernachtungen gesamt", euro(statement.total_nights)],
                  ["Übernachtungen pro JL", euro(statement.nights_per_yl)],
                  ["Kosten pro Übernachtung", euro(statement.real_night_cost)],
                  ["Euro pro km", euro(statement.euro_per_km)],
                  ["Gesamt pro JL", euro(statement.total_per_yl)],
                  ["Personalkosten gesamt", euro(statement.total_staff)],
                  ["Personalkosten ausgezahlt", euro(statement.total_staff_paid)],
                  ["Reale Personenanzahl", statement.real_staff_count],
                  ["Organisationspauschale gesamt", euro(statement.total_org_fee)],
                  ["Gezahlte LJP-Beiträge", euro(statement.paid_ljp_contributions)],
                ]}
              />
            ),
          },
          { id: "belege", label: "Belege", content: <StatementBillsInline statement={statement} editing={editing} registerFlush={getRegistrar("bills")} /> },
          ...(statement.submitted && !statement.confirmed
            ? [
                {
                  id: "buchungen",
                  label: "Buchungen",
                  content: <StatementTransactionsInline statement={statement} />,
                },
              ]
            : []),
        ]}
      />
    </form>
  );
}

function memberName(member: MemberBrief | null | undefined): string {
  return member ? member.name : "—";
}

function joinMembers(members: MemberBrief[] | null | undefined): string {
  return members && members.length ? members.map((m) => m.name).join(", ") : "—";
}

/* --- Belege inline (add / edit / proof / remove) ------------------------- */

type BillData = {
  short_description: string;
  explanation: string;
  amount: string;
  paid_by_id: string;
  paid_by_name: string;
  costs_covered: boolean;
  refunded: boolean;
  /** A new/replacement proof scan to upload on Save (never carries the existing one). */
  proof: File | null;
};

const emptyBill: BillData = {
  short_description: "",
  explanation: "",
  amount: "0",
  paid_by_id: "",
  paid_by_name: "",
  costs_covered: false,
  refunded: false,
  proof: null,
};

/**
 * Bill inline mirroring the admin's `BillInline` on the statement change form.
 * The rows are always listed; when the statement is in edit mode (draft only)
 * each row can be edited in place (PATCH), its proof scan replaced (multipart
 * POST), removed (DELETE) or a new bill added (multipart POST). All buttons are
 * type="button" — this renders inside the statement's <form>.
 */
function StatementBillsInline({
  statement,
  editing,
  registerFlush,
}: {
  statement: StatementOut;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const members = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const memberOptions: MemberBrief[] = members.data ?? [];
  const memberName = (id: string) =>
    memberOptions.find((m) => String(m.id) === id)?.name ?? "";

  const invalidate = [
    ["finance", "statements"],
    ["finance", "statements", statement.id],
    ["finance", "bills"],
  ];
  const createM = useApiMutation((d: BillData) => {
    const fd = new FormData();
    fd.append("statement_id", String(statement.id));
    fd.append("short_description", d.short_description);
    fd.append("explanation", d.explanation);
    fd.append("amount", String(Number(d.amount) || 0));
    if (d.paid_by_id) fd.append("paid_by_id", d.paid_by_id);
    fd.append("costs_covered", String(d.costs_covered));
    if (d.proof) fd.append("proof", d.proof);
    return postMultipart("/api/finance/bills", fd);
  }, { invalidate });
  const updateM = useApiMutation(async (vars: { id: number; d: BillData }) => {
    await unwrap(
      client.PATCH("/api/finance/bills/{bill_id}", {
        params: { path: { bill_id: vars.id } },
        body: {
          short_description: vars.d.short_description,
          explanation: vars.d.explanation,
          amount: Number(vars.d.amount) || 0,
          paid_by_id: vars.d.paid_by_id ? Number(vars.d.paid_by_id) : null,
          costs_covered: vars.d.costs_covered,
          refunded: vars.d.refunded,
        },
      }),
    );
    if (vars.d.proof) {
      const fd = new FormData();
      fd.append("proof", vars.d.proof);
      await postMultipart(`/api/finance/bills/${vars.id}/proof`, fd);
    }
  }, { invalidate });
  const deleteM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/finance/bills/{bill_id}", {
          params: { path: { bill_id: id } },
        }),
      ),
    { invalidate },
  );

  const serverRows = statement.bills.map((b) => ({
    id: b.id,
    data: {
      short_description: b.short_description ?? "",
      explanation: b.explanation ?? "",
      amount: String(b.amount ?? "0"),
      paid_by_id: b.paid_by ? String(b.paid_by.id) : "",
      paid_by_name: b.paid_by?.name ?? "",
      costs_covered: b.costs_covered,
      refunded: b.refunded,
      proof: null,
    } as BillData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<BillData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(d),
    update: (id, d) => updateM.mutateAsync({ id, d }),
    remove: (id) => deleteM.mutateAsync(id),
    registerFlush,
  });
  const [adding, setAdding] = useState<BillData | null>(null);

  const memberSelect = (value: string, onChange: (v: string) => void) => (
    <Select
      value={value}
      onChange={onChange}
      options={memberOptions.map((m) => ({ value: m.id, label: m.name }))}
      placeholder="— niemand —"
      allowEmpty
      emptyLabel="— niemand —"
    />
  );

  const yesNo = (v: boolean) => (v ? <Badge tone="success">Ja</Badge> : "Nein");

  return (
    <>
      <InlineTable
        title="Belege"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ ...emptyBill })}
        addLabel="Beleg"
        empty="Keine Belege."
        columns={[
          {
            header: "Beschreibung",
            cell: (row: DraftRow<BillData>) =>
              editing ? (
                <input
                  value={row.data.short_description}
                  onChange={(e) => setRow(row, { ...row.data, short_description: e.target.value })}
                />
              ) : (
                row.data.short_description
              ),
          },
          {
            header: "Betrag",
            cell: (row: DraftRow<BillData>) =>
              editing ? (
                <input
                  type="number"
                  step="0.01"
                  value={row.data.amount}
                  onChange={(e) => setRow(row, { ...row.data, amount: e.target.value })}
                />
              ) : (
                euro(Number(row.data.amount))
              ),
          },
          {
            header: "Bezahlt von",
            cell: (row: DraftRow<BillData>) =>
              editing
                ? memberSelect(row.data.paid_by_id, (v) =>
                    setRow(row, { ...row.data, paid_by_id: v, paid_by_name: memberName(v) }),
                  )
                : row.data.paid_by_name || "—",
          },
          {
            header: "Übernommen",
            cell: (row: DraftRow<BillData>) =>
              editing ? (
                <input
                  type="checkbox"
                  checked={row.data.costs_covered}
                  onChange={(e) => setRow(row, { ...row.data, costs_covered: e.target.checked })}
                />
              ) : (
                yesNo(row.data.costs_covered)
              ),
          },
          {
            header: "Ausgezahlt",
            cell: (row: DraftRow<BillData>) =>
              editing ? (
                <input
                  type="checkbox"
                  checked={row.data.refunded}
                  onChange={(e) => setRow(row, { ...row.data, refunded: e.target.checked })}
                />
              ) : (
                yesNo(row.data.refunded)
              ),
          },
          {
            header: "Beleg-Scan",
            cell: (row: DraftRow<BillData>) =>
              editing ? (
                <input
                  type="file"
                  accept="application/pdf,image/jpeg,image/png,image/gif"
                  onChange={(e) => setRow(row, { ...row.data, proof: e.target.files?.[0] ?? null })}
                />
              ) : row.id !== null ? (
                <Link to={`/app/finance/bills/${row.id}`}>Öffnen</Link>
              ) : (
                <span className="muted small">(neu)</span>
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Beleg hinzufügen" onClose={() => setAdding(null)}>
          <div className="stack">
            <Field label="Kurzbeschreibung">
              <input
                value={adding.short_description}
                onChange={(e) => setAdding({ ...adding, short_description: e.target.value })}
              />
            </Field>
            <Field label="Erklärung">
              <textarea
                value={adding.explanation}
                onChange={(e) => setAdding({ ...adding, explanation: e.target.value })}
              />
            </Field>
            <Field label="Betrag">
              <input
                type="number"
                step="0.01"
                value={adding.amount}
                onChange={(e) => setAdding({ ...adding, amount: e.target.value })}
              />
            </Field>
            <Field label="Bezahlt von">
              {memberSelect(adding.paid_by_id, (v) =>
                setAdding({ ...adding, paid_by_id: v, paid_by_name: memberName(v) }),
              )}
            </Field>
            <Field label="Übernommen">
              <input
                type="checkbox"
                checked={adding.costs_covered}
                onChange={(e) => setAdding({ ...adding, costs_covered: e.target.checked })}
              />
            </Field>
            <Field label="Beleg-Scan (PDF/Bild, optional)">
              <input
                type="file"
                accept="application/pdf,image/jpeg,image/png,image/gif"
                onChange={(e) => setAdding({ ...adding, proof: e.target.files?.[0] ?? null })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={!adding.short_description}
                onClick={() => {
                  addRow(adding);
                  setAdding(null);
                }}
              >
                Hinzufügen
              </Button>
              <Button type="button" variant="ghost" onClick={() => setAdding(null)}>
                Abbrechen
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

/* --- Buchungen inline (per-row edit) ------------------------------------- */

/**
 * Transaction inline shown only for submitted-but-unconfirmed statements,
 * mirroring the admin's `TransactionInline`. Transactions are generated via the
 * state-machine actions (no add/remove here); each row can be edited in place —
 * amount, recipient (member), reference and ledger — via PATCH. All buttons are
 * type="button" so nothing submits the surrounding statement <form>.
 */
function StatementTransactionsInline({ statement }: { statement: StatementOut }) {
  const toast = useToast();

  const query = useApiQuery(
    ["finance", "statements", statement.id, "transactions"],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}/transactions", {
          params: { path: { statement_id: statement.id } },
        }),
      ),
  );
  const rows: TransactionOut[] = query.data ?? [];

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const memberOptions: MemberBrief[] = members.data ?? [];
  const ledgers = useApiQuery(["finance", "ledgers"], () =>
    unwrap(client.GET("/api/finance/ledgers/")),
  );
  const ledgerOptions: LedgerListOut[] = ledgers.data ?? [];

  const [editId, setEditId] = useState<number | null>(null);
  const [draft, setDraft] = useState({
    amount: "0",
    reference: "",
    member_id: "",
    ledger_id: "",
  });

  function beginEdit(t: TransactionOut) {
    setDraft({
      amount: String(t.amount ?? "0"),
      reference: t.reference ?? "",
      member_id: String(t.member.id),
      ledger_id: t.ledger ? String(t.ledger.id) : "",
    });
    setEditId(t.id);
  }

  const saveMutation = useApiMutation(
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
      invalidate: [
        ["finance", "statements", statement.id, "transactions"],
        ["finance", "statements", statement.id],
        ["finance", "transactions"],
      ],
      onSuccess: () => {
        toast.success("Buchung gespeichert.");
        setEditId(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const columns: { header: string; cell: (t: TransactionOut) => ReactNode }[] = [
    {
      header: "Empfänger",
      cell: (t) =>
        editId === t.id ? (
          <Select
            value={draft.member_id}
            onChange={(v) => setDraft({ ...draft, member_id: v })}
            options={memberOptions.map((m) => ({ value: m.id, label: m.name }))}
          />
        ) : (
          t.member.name
        ),
    },
    {
      header: "Konto",
      cell: (t) =>
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
          (t.ledger?.name ?? "—")
        ),
    },
    {
      header: "Betrag",
      cell: (t) =>
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
      header: "Verwendungszweck",
      cell: (t) =>
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
      header: "Bezahlt",
      cell: (t) => (t.confirmed ? <Badge tone="success">Ja</Badge> : "Nein"),
    },
    {
      header: "",
      cell: (t) =>
        editId === t.id ? (
          <span className="row-actions">
            <Button type="button" busy={saveMutation.isPending} onClick={() => saveMutation.mutate(t.id)}>
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditId(null)}>
              Abbrechen
            </Button>
          </span>
        ) : (
          <Button type="button" variant="ghost" onClick={() => beginEdit(t)}>
            Bearbeiten
          </Button>
        ),
    },
  ];

  return (
    <InlineTable
      title="Buchungen"
      rows={rows}
      columns={columns}
      rowKey={(t) => t.id}
      editing={false}
      empty="Keine Buchungen. Über „Buchungen erzeugen“ anlegen."
    />
  );
}

/* --- state-machine actions ----------------------------------------------- */

/**
 * How a destructive/irreversible action is gated before it runs: either a plain
 * "are you sure?" prompt (`simple`) or the finance overview popup that lets the
 * treasurer review the statement + its transactions before confirming
 * (`overview`).
 */
type Gate = "simple" | "overview";

interface StatementAction {
  label: string;
  run: () => Promise<unknown>;
  variant?: "ghost" | "danger";
  /** When set, clicking the button opens this confirmation Modal first. */
  gate?: Gate;
  /** Prompt text for the `simple` gate. */
  message?: string;
  /** Label of the proceed button inside the gate Modal. */
  proceedLabel?: string;
}

/**
 * Finance overview popup shown before confirming (paying) a statement — mirrors
 * the old admin "Abrechnung bestätigen" review screen. Summarises the statement
 * and lists its generated transactions so the treasurer can review before
 * paying, then offers "Bestätigen" (proceed → confirm), "Ablehnen" (→ reject)
 * and "Abbrechen" (just close).
 */
function ConfirmOverviewModal({
  statement,
  busy,
  proceedLabel,
  onProceed,
  onReject,
  onClose,
}: {
  statement: StatementOut;
  busy: boolean;
  proceedLabel: string;
  onProceed: () => void;
  onReject: () => void;
  onClose: () => void;
}) {
  const query = useApiQuery(
    ["finance", "statements", statement.id, "transactions"],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}/transactions", {
          params: { path: { statement_id: statement.id } },
        }),
      ),
  );

  return (
    <Modal title="Abrechnung bestätigen" onClose={onClose}>
      <div className="stack">
        <DetailList
          items={[
            ["Titel", statement.title],
            ["Gesamt", euro(statement.total)],
            ["Status", <StatusBadge statement={statement} />],
          ]}
        />
        <QueryBoundary query={query} empty="Keine Buchungen.">
          {(rows: TransactionOut[]) => (
            <DataTable
              rows={rows}
              rowKey={(t) => t.id}
              columns={[
                { header: "Empfänger", cell: (t) => t.member.name },
                { header: "Konto", cell: (t) => t.ledger?.name ?? "—" },
                { header: "Betrag", cell: (t) => euro(t.amount) },
                { header: "Verwendungszweck", cell: (t) => t.reference },
              ]}
            />
          )}
        </QueryBoundary>
        <div className="row-actions">
          <Button type="button" busy={busy} onClick={onProceed}>
            {proceedLabel}
          </Button>
          <Button type="button" variant="danger" busy={busy} onClick={onReject}>
            Ablehnen
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </div>
    </Modal>
  );
}

function StatementActions({ statement }: { statement: StatementOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
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
        navigate("/app/finance/statements");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const path = { params: { path: { statement_id: statement.id } } } as const;
  const submitted = statement.submitted;
  const confirmed = statement.confirmed;
  const processable = submitted && !confirmed;

  // reject is reachable both as its own button and as the "Ablehnen" action
  // inside the confirm overview popup, so keep its run in one place.
  const rejectRun = () =>
    unwrap(client.POST("/api/finance/statements/{statement_id}/reject", path));

  const actions: StatementAction[] = [];

  // submit only while still a draft
  if (!submitted) {
    actions.push({
      label: "Einreichen",
      gate: "simple",
      message: "Wirklich einreichen?",
      run: () => unwrap(client.POST("/api/finance/statements/{statement_id}/submit", path)),
    });
  }
  // process actions only while submitted & unconfirmed
  if (processable) {
    actions.push({
      label: "Buchungen erzeugen",
      run: () =>
        unwrap(client.POST("/api/finance/statements/{statement_id}/generate-transactions", path)),
    });
    actions.push({
      label: "Buchungen zusammenfassen",
      run: () =>
        unwrap(client.POST("/api/finance/statements/{statement_id}/reduce-transactions", path)),
    });
    actions.push({
      label: "Bestätigen (bezahlen)",
      gate: "overview",
      proceedLabel: "Bestätigen",
      run: () => unwrap(client.POST("/api/finance/statements/{statement_id}/confirm", path)),
    });
    actions.push({
      label: "Bestätigen & Zusammenfassung senden",
      gate: "overview",
      proceedLabel: "Bestätigen & senden",
      run: () =>
        unwrap(
          client.POST("/api/finance/statements/{statement_id}/confirm", {
            params: { path: { statement_id: statement.id }, query: { send: true } },
          }),
        ),
    });
    actions.push({
      label: "Ablehnen",
      variant: "danger",
      gate: "simple",
      message: "Abrechnung wirklich ablehnen?",
      run: rejectRun,
    });
  }
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

  return (
    <div className="row-actions">
      {actions.map((a) => (
        <Button
          key={a.label}
          type="button"
          variant={a.variant ?? "ghost"}
          busy={mutation.isPending}
          onClick={() => (a.gate ? setPending(a) : mutation.mutate(a.run))}
        >
          {a.label}
        </Button>
      ))}
      {/* Portal the confirmation Modals to <body>: this component renders inside
          the statement's <form>, and the Modal's untyped close button would
          otherwise submit that form. */}
      {pending &&
        pending.gate === "simple" &&
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
      {pending &&
        pending.gate === "overview" &&
        createPortal(
          <ConfirmOverviewModal
            statement={statement}
            busy={mutation.isPending}
            proceedLabel={pending.proceedLabel ?? "Bestätigen"}
            onProceed={() => mutation.mutate(pending.run)}
            onReject={() => mutation.mutate(rejectRun)}
            onClose={() => setPending(null)}
          />,
          document.body,
        )}
      {confirmed && (
        <DownloadButton
          path={`/api/finance/documents/statements/${statement.id}/summary`}
          filename={`Abrechnung_${statement.id}_Zusammenfassung.pdf`}
        >
          Zusammenfassung (PDF)
        </DownloadButton>
      )}
      {!submitted && (
        <Button
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
        </Button>
      )}
    </div>
  );
}
