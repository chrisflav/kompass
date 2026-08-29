import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { getToken } from "../../auth";
import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type BillBrief = components["schemas"]["BillBrief"];
type BillOut = components["schemas"]["BillOut"];
type StatementBrief = components["schemas"]["StatementBrief"];

function euro(value: number): string {
  return `${value.toFixed(2)} €`;
}

/**
 * Multipart POST with the bearer token attached, mirroring `downloadArtifact`'s
 * fetch pattern. openapi-fetch types the `proof` field as a plain string (binary
 * placeholder) so a real File must be sent through FormData rather than the typed
 * client. Returns the parsed BillOut, throwing {@link ApiError} on failure.
 */
export async function postMultipart(path: string, form: FormData): Promise<BillOut> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as BillOut;
}

/* --- list ---------------------------------------------------------------- */

export function BillsList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["finance", "bills"], () =>
    unwrap(client.GET("/api/finance/bills")),
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

  const statementOptions = useMemo(() => {
    const ids = new Set<number>();
    rows.forEach((b) => ids.add(b.statement_id));
    return [...ids]
      .sort((a, b) => a - b)
      .map((id) => ({ value: String(id), label: statementTitle.get(id) ?? `#${id}` }));
  }, [rows, statementTitle]);

  const paidByOptions = useMemo(() => {
    const map = new Map<string, string>();
    rows.forEach((b) => b.paid_by && map.set(String(b.paid_by.id), b.paid_by.name));
    return [...map].map(([value, label]) => ({ value, label }));
  }, [rows]);

  const config: ListViewConfig<BillBrief> = useMemo(
    () => ({
      search: (b) => [b.short_description, b.explanation],
      filters: [
        {
          key: "statement",
          label: "Abrechnung",
          options: statementOptions,
          match: (b, v) => String(b.statement_id) === v,
        },
        {
          key: "paid_by",
          label: "Bezahlt von",
          options: paidByOptions,
          match: (b, v) => (b.paid_by ? String(b.paid_by.id) === v : false),
        },
        {
          key: "refunded",
          label: "Ausgezahlt",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (b, v) => (v === "yes") === Boolean(b.refunded),
        },
      ],
      sort: {
        short_description: (b) => b.short_description,
        amount: (b) => b.amount,
        paid_by: (b) => b.paid_by?.name,
        statement: (b) => b.statement_id,
      },
    }),
    [statementOptions, paidByOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Belege" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neuer Beleg</Button>}
      />
      {creating && <BillCreateForm onDone={() => setCreating(false)} />}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Belege sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(b) => b.id}
            onRowClick={(b) => navigate(`/app/finance/bills/${b.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Beschreibung", cell: (b) => b.short_description, sortKey: "short_description" },
              {
                header: "Abrechnung",
                cell: (b) => statementTitle.get(b.statement_id) ?? `#${b.statement_id}`,
                sortKey: "statement",
              },
              { header: "Erklärung", cell: (b) => b.explanation || "—" },
              { header: "Betrag", cell: (b) => euro(b.amount), sortKey: "amount" },
              { header: "Bezahlt von", cell: (b) => (b.paid_by ? b.paid_by.name : "—"), sortKey: "paid_by" },
              {
                header: "Übernommen",
                cell: (b) => (b.costs_covered ? <Badge tone="success">Ja</Badge> : "Nein"),
              },
              {
                header: "Ausgezahlt",
                cell: (b) => (b.refunded ? <Badge tone="success">Ja</Badge> : "Nein"),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function BillCreateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    statement_id: "",
    short_description: "",
    explanation: "",
    amount: "0",
    paid_by_id: "",
    costs_covered: false,
  });
  const [proof, setProof] = useState<File | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const statements = useApiQuery(["finance", "statements"], () =>
    unwrap(client.GET("/api/finance/statements")),
  );

  const mutation = useApiMutation(
    () => {
      const fd = new FormData();
      fd.append("statement_id", form.statement_id);
      fd.append("short_description", form.short_description);
      fd.append("explanation", form.explanation);
      fd.append("amount", String(Number(form.amount) || 0));
      if (form.paid_by_id) fd.append("paid_by_id", form.paid_by_id);
      fd.append("costs_covered", String(form.costs_covered));
      if (proof) fd.append("proof", proof);
      return postMultipart("/api/finance/bills", fd);
    },
    {
      invalidate: [["finance", "bills"]],
      onSuccess: (created: BillOut) => {
        toast.success("Beleg angelegt.");
        onDone();
        navigate(`/app/finance/bills/${created.id}`);
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
      <Field label="Abrechnung">
        <Select
          value={form.statement_id}
          onChange={(v) => setForm({ ...form, statement_id: v })}
          options={(statements.data ?? []).map((s: StatementBrief) => ({
            value: s.id,
            label: s.title,
          }))}
          placeholder="— wählen —"
        />
        {fieldErrors.statement && (
          <div className="field-error">{fieldErrors.statement.join(" ")}</div>
        )}
      </Field>
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
      <Field label="Betrag">
        <input
          type="number"
          step="0.01"
          value={form.amount}
          onChange={(e) => setForm({ ...form, amount: e.target.value })}
        />
        {fieldErrors.amount && (
          <div className="field-error">{fieldErrors.amount.join(" ")}</div>
        )}
      </Field>
      <Field label="Übernommen">
        <input
          type="checkbox"
          checked={form.costs_covered}
          onChange={(e) => setForm({ ...form, costs_covered: e.target.checked })}
        />
      </Field>
      <Field label="Beleg-Scan (PDF/Bild, optional)">
        <input
          type="file"
          accept="application/pdf,image/jpeg,image/png,image/gif"
          onChange={(e) => setProof(e.target.files?.[0] ?? null)}
        />
      </Field>
      {/* BACKEND-GAP: no endpoint to list members, so "Bezahlt von" is entered as a numeric member id. */}
      <Field label="Bezahlt von (Teilnehmenden-ID)">
        <input
          type="number"
          value={form.paid_by_id}
          onChange={(e) => setForm({ ...form, paid_by_id: e.target.value })}
        />
        {fieldErrors.paid_by && (
          <div className="field-error">{fieldErrors.paid_by.join(" ")}</div>
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

export function BillDetailPage() {
  const { id } = useParams();
  const billId = Number(id);
  const query = useApiQuery(["finance", "bills", billId], () =>
    unwrap(
      client.GET("/api/finance/bills/{bill_id}", {
        params: { path: { bill_id: billId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Belege", to: "/app/finance/bills" },
    { label: query.data?.short_description ?? "Beleg" },
  ];

  return (
    <QueryBoundary query={query}>
      {(bill: BillOut) => <BillDetailBody bill={bill} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function BillDetailBody({ bill, crumbs }: { bill: BillOut; crumbs: Crumb[] }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState(() => ({
    short_description: bill.short_description ?? "",
    explanation: bill.explanation ?? "",
    amount: String(bill.amount ?? "0"),
    costs_covered: bill.costs_covered,
    refunded: bill.refunded,
    paid_by_id: bill.paid_by ? String(bill.paid_by.id) : "",
  }));

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.PATCH("/api/finance/bills/{bill_id}", {
          params: { path: { bill_id: bill.id } },
          body: {
            short_description: form.short_description,
            explanation: form.explanation,
            amount: Number(form.amount) || 0,
            costs_covered: form.costs_covered,
            refunded: form.refunded,
            paid_by_id: form.paid_by_id ? Number(form.paid_by_id) : null,
          },
        }),
      ),
    {
      invalidate: [["finance", "bills"], ["finance", "bills", bill.id]],
      onSuccess: () => {
        toast.success("Gespeichert.");
        setEditing(false);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  function startEditing() {
    setForm({
      short_description: bill.short_description ?? "",
      explanation: bill.explanation ?? "",
      amount: String(bill.amount ?? "0"),
      costs_covered: bill.costs_covered,
      refunded: bill.refunded,
      paid_by_id: bill.paid_by ? String(bill.paid_by.id) : "",
    });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Kurzbeschreibung",
      value: bill.short_description,
      field: "short_description",
      edit: (
        <input
          value={form.short_description}
          onChange={(e) => setForm({ ...form, short_description: e.target.value })}
        />
      ),
    },
    {
      label: "Erklärung",
      value: bill.explanation || "—",
      field: "explanation",
      edit: (
        <textarea
          value={form.explanation}
          onChange={(e) => setForm({ ...form, explanation: e.target.value })}
        />
      ),
    },
    {
      label: "Betrag",
      value: euro(bill.amount),
      field: "amount",
      edit: (
        <input
          type="number"
          step="0.01"
          value={form.amount}
          onChange={(e) => setForm({ ...form, amount: e.target.value })}
        />
      ),
    },
    {
      label: "Bezahlt von",
      value: bill.paid_by ? bill.paid_by.name : "—",
      field: "paid_by",
      /* BACKEND-GAP: no endpoint to list members, so "Bezahlt von" is entered as a numeric member id. */
      edit: (
        <input
          type="number"
          placeholder="Teilnehmenden-ID"
          value={form.paid_by_id}
          onChange={(e) => setForm({ ...form, paid_by_id: e.target.value })}
        />
      ),
    },
    {
      label: "Übernommen",
      value: bill.costs_covered ? <Badge tone="success">Ja</Badge> : "Nein",
      field: "costs_covered",
      edit: (
        <input
          type="checkbox"
          checked={form.costs_covered}
          onChange={(e) => setForm({ ...form, costs_covered: e.target.checked })}
        />
      ),
    },
    {
      label: "Ausgezahlt",
      value: bill.refunded ? <Badge tone="success">Ja</Badge> : "Nein",
      field: "refunded",
      edit: (
        <input
          type="checkbox"
          checked={form.refunded}
          onChange={(e) => setForm({ ...form, refunded: e.target.checked })}
        />
      ),
    },
    {
      label: "Abrechnung",
      value: <Link to={`/app/finance/statements/${bill.statement_id}`}>#{bill.statement_id}</Link>,
    },
    {
      label: "Beleg-Scan",
      value:
        bill.has_proof && bill.proof_url ? (
          <a href={bill.proof_url} target="_blank" rel="noreferrer">
            Öffnen
          </a>
        ) : (
          <Badge tone="warning">Fehlt</Badge>
        ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(undefined);
      }}
    >
      <PageHeader
        breadcrumbs={crumbs}
        actions={
          editing ? (
            <>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" busy={mutation.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <BillActions bill={bill} />
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            </>
          )
        }
      />
      <Tabs
        tabs={[
          { id: "beleg", label: "Beleg", content: <EditableDetail rows={rows} editing={editing} errors={fieldErrors} /> },
          {
            id: "proof",
            label: "Beleg-Scan hochladen",
            content: <BillProofUpload bill={bill} />,
          },
        ]}
      />
    </form>
  );
}

/* --- proof upload -------------------------------------------------------- */

function BillProofUpload({ bill }: { bill: BillOut }) {
  const toast = useToast();
  const [proof, setProof] = useState<File | null>(null);

  const mutation = useApiMutation(
    (file: File) => {
      const fd = new FormData();
      fd.append("proof", file);
      return postMultipart(`/api/finance/bills/${bill.id}/proof`, fd);
    },
    {
      invalidate: [["finance", "bills"], ["finance", "bills", bill.id]],
      onSuccess: () => {
        toast.success("Beleg-Scan hochgeladen.");
        setProof(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div className="row-actions">
      <input
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/gif"
        onChange={(e) => setProof(e.target.files?.[0] ?? null)}
      />
      <Button
        type="button"
        busy={mutation.isPending}
        disabled={!proof}
        onClick={() => {
          if (proof) mutation.mutate(proof);
        }}
      >
        Hochladen
      </Button>
    </div>
  );
}

/* --- delete action ------------------------------------------------------- */

function BillActions({ bill }: { bill: BillOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();

  const deleteMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/finance/bills/{bill_id}", {
          params: { path: { bill_id: bill.id } },
        }),
      ),
    {
      invalidate: [["finance", "bills"]],
      onSuccess: () => {
        toast.success("Beleg gelöscht.");
        navigate("/app/finance/bills");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <Button
      type="button"
      variant="danger"
      busy={deleteMutation.isPending}
      onClick={async () => {
        if (
          await confirm({
            message: "Beleg wirklich löschen?",
            danger: true,
            confirmLabel: "Löschen",
          })
        )
          deleteMutation.mutate(undefined);
      }}
    >
      Löschen
    </Button>
  );
}
