import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { API_BASE } from "../../api/client";
import { usePermissions } from "../../api/me";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  formatDate,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type MaterialPartBrief = components["schemas"]["MaterialPartBrief"];
type MaterialPartOut = components["schemas"]["MaterialPartOut"];

/** Owner options for a part: every member, plus "no owner". */
function useOwnerOptions(enabled: boolean) {
  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")), {
    enabled,
  });
  return (members.data ?? []).map((m) => ({ value: m.id, label: m.name }));
}

function OwnerSelect({
  value,
  onChange,
  options,
}: {
  value: number | null;
  onChange: (owner: number | null) => void;
  options: { value: number; label: string }[];
}) {
  return (
    <Select
      value={value === null ? "" : String(value)}
      onChange={(v) => onChange(v === "" ? null : Number(v))}
      options={options}
      placeholder="Kein Besitzer"
      allowEmpty
      emptyLabel="Kein Besitzer"
    />
  );
}

/* --- list ---------------------------------------------------------------- */

export function PartsList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["material", "parts"], () =>
    unwrap(client.GET("/api/material/parts")),
  );
  const rows = query.data ?? [];

  // Owner filter options built from the owners already on the rows.
  const ownerOptions = useMemo(() => {
    const owners = new Map<number, string>();
    rows.forEach((p) => p.owner && owners.set(p.owner.id, p.owner.name));
    return [...owners]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([id, name]) => ({ value: String(id), label: name }));
  }, [rows]);

  const config: ListViewConfig<MaterialPartBrief> = useMemo(
    () => ({
      // Admin search_fields = name, description.
      search: (p) => [p.name, p.description],
      filters: [
        // Admin NotTooOldFilter over the computed not_too_old bool (labels shown
        // in the SPA's, un-inverted, sense: still-good vs too-old).
        {
          key: "age",
          label: "Zustand",
          options: [
            { value: "ok", label: "In Ordnung" },
            { value: "old", label: "Zu alt" },
          ],
          match: (p, v) => (v === "ok") === Boolean(p.not_too_old),
        },
        // Admin list_filter = owner.
        {
          key: "owner",
          label: "Besitzer",
          options: ownerOptions,
          match: (p, v) => String(p.owner?.id) === v,
        },
        // BACKEND-GAP: admin also has a material_cat (category) filter, but
        // MaterialPartBrief does not expose categories, so a category filter
        // cannot be built from the list rows client-side.
      ],
      sort: {
        name: (p) => p.name,
        description: (p) => p.description,
        owner: (p) => p.owner?.name ?? "",
        buy_date: (p) => p.buy_date,
        lifetime: (p) => Number(p.lifetime),
      },
      // Admin ordering = name.
      defaultSort: { key: "name", dir: "asc" },
    }),
    [ownerOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Material" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("material.add_materialpart") && (
            <Button onClick={() => setCreating(true)}>Neues Material</Button>
          )
        }
      />
      {creating && (
        <Modal title="Neues Material" onClose={() => setCreating(false)}>
          <PartCreateForm
            onSuccess={(p) => {
              setCreating(false);
              navigate(`/kompass/material/${p.id}`);
            }}
            onCancel={() => setCreating(false)}
          />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Kein Material vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`/kompass/material/${p.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (p) => p.name, sortKey: "name" },
              { header: "Beschreibung", cell: (p) => p.description || "—", sortKey: "description" },
              { header: "Besitzer", cell: (p) => p.owner?.name ?? "—", sortKey: "owner" },
              { header: "Kaufdatum", cell: (p) => formatDate(p.buy_date), sortKey: "buy_date" },
              { header: "Lebenszeit", cell: (p) => p.lifetime, sortKey: "lifetime" },
              {
                header: "Zustand",
                cell: (p) =>
                  p.not_too_old ? (
                    <Badge tone="success">In Ordnung</Badge>
                  ) : (
                    <Badge tone="danger">Zu alt</Badge>
                  ),
                // admin_order_field: not_too_old column orders by buy_date.
                sortKey: "buy_date",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail -------------------------------------------------------------- */

export function PartDetailPage() {
  const { id } = useParams();
  const partId = Number(id);
  const query = useApiQuery(["material", "parts", partId], () =>
    unwrap(
      client.GET("/api/material/parts/{part_id}", {
        params: { path: { part_id: partId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(part: MaterialPartOut) => <PartDetailBody part={part} />}
    </QueryBoundary>
  );
}

function PartDetailBody({ part }: { part: MaterialPartOut }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => partToForm(part));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const categories = useApiQuery(["material", "categories"], () =>
    unwrap(client.GET("/api/material/categories")),
  );

  const ownerOptions = useOwnerOptions(editing);
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: typeof form) =>
      unwrap(
        // PATCH is JSON-only (no photo); the photo is managed separately via the
        // dedicated multipart POST /parts/{part_id}/photo endpoint (see PartPhoto).
        client.PATCH("/api/material/parts/{part_id}", {
          params: { path: { part_id: part.id } },
          body: {
            name: body.name,
            description: body.description,
            buy_date: body.buy_date,
            lifetime: body.lifetime,
            material_cat: body.material_cat,
            owner: body.owner,
          },
        }),
      ),
    {
      invalidate: [
        ["material", "parts"],
        ["material", "parts", part.id],
      ],
    },
  );

  const deletion = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/material/parts/{part_id}", {
          params: { path: { part_id: part.id } },
        }),
      ),
    {
      invalidate: [["material", "parts"]],
      onSuccess: () => {
        toast.success("Material gelöscht.");
        navigate("/kompass/material");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(partToForm(part));
    setFieldErrors({});
    setEditing(true);
  }

  const categoryOptions = categories.data ?? [];

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: part.name,
      edit: (
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
      ),
    },
    {
      label: "Beschreibung",
      field: "description",
      value: part.description || "—",
      edit: (
        <textarea
          rows={3}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      ),
    },
    {
      label: "Kaufdatum",
      field: "buy_date",
      value: formatDate(part.buy_date),
      edit: (
        <input
          type="date"
          value={form.buy_date}
          onChange={(e) => setForm({ ...form, buy_date: e.target.value })}
        />
      ),
    },
    {
      label: "Lebenszeit (Jahre)",
      field: "lifetime",
      value: part.lifetime,
      edit: (
        <input
          type="number"
          step="0.1"
          value={form.lifetime}
          onChange={(e) => setForm({ ...form, lifetime: e.target.value })}
        />
      ),
    },
    {
      label: "Zustand",
      value: part.not_too_old ? (
        <Badge tone="success">In Ordnung</Badge>
      ) : (
        <Badge tone="danger">Zu alt</Badge>
      ),
    },
    {
      label: "Besitzer",
      field: "owner",
      value: part.owner?.name ?? "—",
      edit: (
        <OwnerSelect
          value={form.owner}
          onChange={(owner) => setForm({ ...form, owner })}
          options={ownerOptions}
        />
      ),
    },
    {
      label: "Kategorien",
      field: "material_cat",
      value: part.categories.map((c) => c.name).join(", ") || "—",
      edit: (
        <MultiSelect
          options={categoryOptions.map((c) => ({ value: c.id, label: c.name }))}
          selected={form.material_cat}
          onChange={(ids) => setForm({ ...form, material_cat: ids })}
          placeholder="Kategorie hinzufügen"
        />
      ),
    },
    {
      label: "Foto",
      value: part.photo ? (
        <a href={`${API_BASE}${part.photo}`} target="_blank" rel="noreferrer">
          Foto ansehen
        </a>
      ) : (
        "—"
      ),
    },
  ];

  return (
    <>
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setFieldErrors({});
          setSaving(true);
          try {
            await mutation.mutateAsync(form);
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
        <PageHeader
          breadcrumbs={[
            { label: "Material", to: "/kompass/material" },
            { label: part.name },
          ]}
          actions={
            editing ? (
              <>
                <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                  Abbrechen
                </Button>
                <Button type="submit" busy={saving}>
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
                  busy={deletion.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: "Material wirklich löschen?",
                        danger: true,
                        confirmLabel: "Löschen",
                      })
                    )
                      deletion.mutate(undefined);
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
      <PartPhoto part={part} />
    </>
  );
}

/* --- photo (dedicated multipart endpoint) -------------------------------- */

function PartPhoto({ part }: { part: MaterialPartOut }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const upload = useApiMutation(
    (file: File) =>
      unwrap(
        client.POST("/api/material/parts/{part_id}/photo", {
          params: { path: { part_id: part.id } },
          // Multipart upload: field name `photo`. A custom serializer builds the
          // FormData because openapi-fetch would otherwise JSON-encode it.
          body: { photo: file as unknown as string },
          bodySerializer(body: { photo: unknown }) {
            const fd = new FormData();
            fd.append("photo", body.photo as File);
            return fd;
          },
        }),
      ),
    {
      invalidate: [
        ["material", "parts"],
        ["material", "parts", part.id],
      ],
      onSuccess: () => {
        toast.success("Foto gespeichert.");
        if (fileRef.current) fileRef.current.value = "";
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div className="stack">
      <h3 style={{ fontSize: "1rem", fontWeight: 600 }}>Foto</h3>
      {part.photo ? (
        <a href={`${API_BASE}${part.photo}`} target="_blank" rel="noreferrer">
          Aktuelles Foto ansehen
        </a>
      ) : (
        <span>Kein Foto hinterlegt.</span>
      )}
      <div className="row-actions">
        <input
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/gif"
          disabled={upload.isPending}
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) upload.mutate(file);
          }}
        />
      </div>
    </div>
  );
}

function partToForm(part: MaterialPartOut) {
  return {
    name: part.name,
    description: part.description,
    buy_date: part.buy_date,
    lifetime: part.lifetime,
    material_cat: part.categories.map((c) => c.id),
    owner: part.owner?.id ?? null,
  };
}

/* --- create form (multipart, optional photo) ----------------------------- */

function PartCreateForm({
  onSuccess,
  onCancel,
}: {
  onSuccess: (p: MaterialPartOut) => void;
  onCancel?: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState({
    name: "",
    description: "",
    buy_date: "",
    lifetime: "",
    material_cat: [] as number[],
    owner: null as number | null,
  });
  const [photo, setPhoto] = useState<File | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const categories = useApiQuery(["material", "categories"], () =>
    unwrap(client.GET("/api/material/categories")),
  );
  const ownerOptions = useOwnerOptions(true);

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/material/parts", {
          // Multipart create: openapi-fetch would JSON-encode the object, so a
          // custom serializer packs the fields (and optional photo) into FormData.
          body: {
            name: form.name,
            description: form.description,
            buy_date: form.buy_date,
            lifetime: form.lifetime,
            material_cat: form.material_cat,
            owner: form.owner,
            ...(photo ? { photo: photo as unknown as string } : {}),
          },
          bodySerializer(body: Record<string, unknown>) {
            const fd = new FormData();
            fd.append("name", String(body.name));
            fd.append("description", String(body.description ?? ""));
            fd.append("buy_date", String(body.buy_date));
            fd.append("lifetime", String(body.lifetime));
            for (const c of (body.material_cat as number[]) ?? []) {
              fd.append("material_cat", String(c));
            }
            if (body.owner != null) fd.append("owner", String(body.owner));
            if (body.photo) fd.append("photo", body.photo as File);
            return fd;
          },
        }),
      ),
    {
      invalidate: [["material", "parts"]],
      onSuccess: (p) => {
        toast.success("Material angelegt.");
        onSuccess(p);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  const categoryOptions = categories.data ?? [];

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(undefined);
      }}
    >
      <Field label="Name">
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
      </Field>
      <Field label="Beschreibung">
        <textarea
          rows={3}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
        {fieldErrors.description && (
          <div className="field-error">{fieldErrors.description.join(" ")}</div>
        )}
      </Field>
      <Field label="Kaufdatum">
        <input
          type="date"
          value={form.buy_date}
          onChange={(e) => setForm({ ...form, buy_date: e.target.value })}
          required
        />
        {fieldErrors.buy_date && (
          <div className="field-error">{fieldErrors.buy_date.join(" ")}</div>
        )}
      </Field>
      <Field label="Lebenszeit (Jahre)">
        <input
          type="number"
          step="0.1"
          value={form.lifetime}
          onChange={(e) => setForm({ ...form, lifetime: e.target.value })}
          required
        />
        {fieldErrors.lifetime && (
          <div className="field-error">{fieldErrors.lifetime.join(" ")}</div>
        )}
      </Field>
      <Field label="Kategorien">
        <MultiSelect
          options={categoryOptions.map((c) => ({ value: c.id, label: c.name }))}
          selected={form.material_cat}
          onChange={(ids) => setForm({ ...form, material_cat: ids })}
          placeholder="Kategorie hinzufügen"
        />
        {fieldErrors.material_cat && (
          <div className="field-error">{fieldErrors.material_cat.join(" ")}</div>
        )}
      </Field>
      <Field label="Besitzer">
        <OwnerSelect
          value={form.owner}
          onChange={(owner) => setForm({ ...form, owner })}
          options={ownerOptions}
        />
        {fieldErrors.owner && <div className="field-error">{fieldErrors.owner.join(" ")}</div>}
      </Field>
      <Field label="Foto (optional)">
        <input
          type="file"
          accept="image/jpeg,image/png,image/gif"
          onChange={(e) => setPhoto(e.target.files?.[0] ?? null)}
        />
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Anlegen
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Abbrechen
          </Button>
        )}
      </div>
    </form>
  );
}
