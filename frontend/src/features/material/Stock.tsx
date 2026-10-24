import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  useRowSelection,
  useToast,
} from "../../components/ui";
import { AddPartsModal } from "./TypeDetail";
import {
  BASE,
  errorText,
  MATERIAL,
  ModalActions,
  PartStatus,
  HandOverModal,
  StockTabs,
  useMaterialRoles,
  whereabouts,
  Whereabouts,
  type PartBrief,
} from "./shared";

function options(rows: PartBrief[], pick: (p: PartBrief) => { id: number; name: string } | null) {
  const seen = new Map<number, string>();
  rows.forEach((p) => {
    const o = pick(p);
    if (o) seen.set(o.id, o.name);
  });
  return [...seen]
    .sort((a, b) => a[1].localeCompare(b[1]))
    .map(([id, name]) => ({ value: String(id), label: name }));
}

/** Every piece, filterable, with a batch hand-over (issue #449). */
export function Stock() {
  const navigate = useNavigate();
  const roles = useMaterialRoles();
  const query = useApiQuery(["material", "parts"], () => unwrap(client.GET("/api/material/parts")));
  const rows = query.data ?? [];
  const selection = useRowSelection<number>();
  const [transferring, setTransferring] = useState(false);
  const [creating, setCreating] = useState(false);

  const config: ListViewConfig<PartBrief> = useMemo(
    () => ({
      search: (p) => [p.label, p.product_type.name, p.serial_number, p.psa_id],
      filters: [
        {
          key: "type",
          label: "Typ",
          options: options(rows, (p) => p.product_type),
          match: (p, v) => String(p.product_type.id) === v,
        },
        {
          key: "group",
          label: "Gruppe",
          options: [{ value: "none", label: "Sektion" }, ...options(rows, (p) => p.group)],
          match: (p, v) => (v === "none" ? p.group === null : String(p.group?.id) === v),
        },
        {
          key: "holder",
          label: "Bei",
          options: options(rows, (p) => p.holder),
          match: (p, v) => String(p.holder?.id) === v,
        },
        {
          key: "location",
          label: "Ort",
          options: options(rows, (p) => p.location),
          match: (p, v) => String(p.location?.id) === v,
        },
        {
          key: "status",
          label: "Status",
          options: [
            { value: "active", label: "aktiv" },
            { value: "inspection_due", label: "Prüfung fällig" },
            { value: "lent", label: "verliehen" },
          ],
          match: (p, v) => (v === "lent" ? p.lent_until !== null : p.status === v),
        },
      ],
      sort: {
        type: (p) => p.product_type.name,
        label: (p) => p.label,
        where: (p) => whereabouts(p),
      },
      defaultSort: { key: "type", dir: "asc" },
    }),
    [rows],
  );
  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material", to: BASE }, { label: "Bestand" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          <>
            {selection.count > 0 && (
              <Button variant="ghost" onClick={() => setTransferring(true)}>
                {selection.count} übergeben
              </Button>
            )}
            {roles.inventory && <Button onClick={() => setCreating(true)}>Teile anlegen</Button>}
          </>
        }
      />
      <StockTabs />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Noch kein Material.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`${BASE}/parts/${p.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            selection={{
              selected: selection.selected,
              onToggle: (k) => selection.toggle(k as number),
              onToggleAll: (ks) => selection.toggleAll(ks as number[]),
            }}
            columns={[
              { header: "Typ", cell: (p) => p.product_type.name, sortKey: "type" },
              { header: "ID", cell: (p) => <span className="mono">{p.label}</span>, sortKey: "label" },
              { header: "Gehört", cell: (p) => p.group?.name ?? "Sektion" },
              { header: "Wo", cell: (p) => <Whereabouts part={p} />, sortKey: "where" },
              { header: "Status", cell: (p) => <PartStatus status={p.status} /> },
            ]}
          />
        )}
      </QueryBoundary>
      {transferring && (
        <HandOverModal
          parts={rows.filter((p) => selection.selected.has(p.id))}
          onClose={() => setTransferring(false)}
          onDone={() => {
            setTransferring(false);
            selection.clear();
          }}
        />
      )}
      {creating && <NewPartsModal onClose={() => setCreating(false)} />}
    </div>
  );
}

/** Pick a type (or create one), then add its pieces, built into ``parent`` if given. */
export function NewPartsModal({
  parent,
  onClose,
}: {
  parent?: Pick<PartBrief, "id" | "label" | "product_type">;
  onClose: () => void;
}) {
  const toast = useToast();
  const types = useApiQuery(["material", "types", "all"], () =>
    unwrap(client.GET("/api/material/types")),
  );
  const [typeId, setTypeId] = useState("");
  const [name, setName] = useState("");
  const [isPsa, setIsPsa] = useState(false);
  const create = useApiMutation(
    () => unwrap(client.POST("/api/material/types", {
          body: {
            name,
            is_psa: isPsa,
            manufacturer: "",
            product_group: "",
            description: "",
            article_number: "",
            inspection_interval_days: 365,
            tags: [],
          },
        })),
    {
      invalidate: [MATERIAL],
      onSuccess: (t) => setTypeId(String(t.id)),
      onError: (e) => toast.error(errorText(e)),
    },
  );
  const chosen = (types.data ?? []).find((t) => String(t.id) === typeId);
  if (chosen) return <AddPartsModal type={chosen} parent={parent} onClose={onClose} />;
  return (
    <Modal title="Teile anlegen" onClose={onClose}>
      <QueryBoundary query={types}>
        {(rows) => (
          <div className="stack">
            <Field label="Materialtyp">
              <Select
                value={typeId}
                onChange={setTypeId}
                placeholder="Typ wählen…"
                options={rows.map((t) => ({ value: t.id, label: t.name }))}
              />
            </Field>
            <p className="muted small">Oder einen neuen Typ anlegen:</p>
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault();
                if (name.trim()) create.mutate(undefined);
              }}
            >
              <Field label="Name des Typs">
                <input value={name} onChange={(e) => setName(e.target.value)} />
              </Field>
              <label className="inline-check">
                <input type="checkbox" checked={isPsa} onChange={(e) => setIsPsa(e.target.checked)} />
                persönliche Schutzausrüstung (PSA)
              </label>
              <ModalActions>
                <Button type="submit" variant="ghost" busy={create.isPending} disabled={!name.trim()}>
                  Typ anlegen
                </Button>
                <Button variant="ghost" onClick={onClose}>
                  Abbrechen
                </Button>
              </ModalActions>
            </form>
          </div>
        )}
      </QueryBoundary>
    </Modal>
  );
}
