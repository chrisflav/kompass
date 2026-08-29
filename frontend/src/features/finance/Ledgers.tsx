import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type LedgerListOut = components["schemas"]["LedgerListOut"];
type LedgerDetailOut = components["schemas"]["LedgerDetailOut"];

/* --- list ---------------------------------------------------------------- */

export function LedgersList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["ledgers"], () =>
    unwrap(client.GET("/api/finance/ledgers/")),
  );
  const rows = query.data ?? [];

  const config: ListViewConfig<LedgerListOut> = useMemo(
    () => ({
      search: (l) => [l.name],
      sort: { name: (l) => l.name },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Konten" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neues Konto</Button>}
      />
      {creating && (
        <Modal title="Neues Konto" onClose={() => setCreating(false)}>
          <LedgerCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Konten vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(l) => l.id}
            onRowClick={(l) => navigate(`/app/finance/ledgers/${l.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[{ header: "Name", cell: (l) => l.name, sortKey: "name" }]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function LedgerCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    (body: { name: string }) => unwrap(client.POST("/api/finance/ledgers/", { body })),
    {
      invalidate: [["ledgers"]],
      onSuccess: (created: LedgerDetailOut) => {
        toast.success("Konto angelegt.");
        onDone();
        navigate(`/app/finance/ledgers/${created.id}`);
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
        mutation.mutate({ name });
      }}
    >
      <Field label="Name">
        <input value={name} onChange={(e) => setName(e.target.value)} required />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
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

/* --- detail + edit + delete --------------------------------------------- */

export function LedgerDetailPage() {
  const { id } = useParams();
  const ledgerId = Number(id);
  const query = useApiQuery(["ledgers", ledgerId], () =>
    unwrap(
      client.GET("/api/finance/ledgers/{ledger_id}", {
        params: { path: { ledger_id: ledgerId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Konten", to: "/app/finance/ledgers" },
    { label: query.data?.name ?? "Konto" },
  ];

  return (
    <QueryBoundary query={query}>
      {(ledger: LedgerDetailOut) => <LedgerDetailBody ledger={ledger} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function LedgerDetailBody({ ledger, crumbs }: { ledger: LedgerDetailOut; crumbs: Crumb[] }) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(ledger.name);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/finance/ledgers/{ledger_id}", {
          params: { path: { ledger_id: ledger.id } },
        }),
      ),
    {
      invalidate: [["ledgers"]],
      onSuccess: () => {
        toast.success("Konto gelöscht.");
        navigate("/app/finance/ledgers");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const mutation = useApiMutation(
    (body: { name: string }) =>
      unwrap(
        client.PATCH("/api/finance/ledgers/{ledger_id}", {
          params: { path: { ledger_id: ledger.id } },
          body,
        }),
      ),
    {
      invalidate: [["ledgers"], ["ledgers", ledger.id]],
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
    setName(ledger.name);
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Name",
      value: ledger.name,
      field: "name",
      edit: <input value={name} onChange={(e) => setName(e.target.value)} required />,
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate({ name });
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
              <Button
                type="button"
                variant="danger"
                busy={remove.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      message: "Dieses Konto wirklich löschen?",
                      danger: true,
                      confirmLabel: "Löschen",
                    })
                  )
                    remove.mutate(undefined);
                }}
              >
                Löschen
              </Button>
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            </>
          )
        }
      />
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
    </form>
  );
}
