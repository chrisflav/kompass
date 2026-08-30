import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useRowHints } from "../../api/helpTexts";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import { LJP_CATEGORY_OPTIONS } from "./_controls";
import type { components } from "../../api/schema";

type ActivityCategoryOut = components["schemas"]["ActivityCategoryOut"];
type ActivityCategoryUpdate = components["schemas"]["ActivityCategoryUpdate"];
type TrainingCategoryOut = components["schemas"]["TrainingCategoryOut"];
type TrainingCategoryUpdate = components["schemas"]["TrainingCategoryUpdate"];

/* ====================================================================== */
/* ActivityCategory (Aktivitätskategorien)                                */
/* ====================================================================== */

export function ActivityCategoriesList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const toast = useToast();
  const query = useApiQuery(["activity-categories"], () =>
    unwrap(client.GET("/api/members/activity-categories")),
  );

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [ljp, setLjp] = useState(LJP_CATEGORY_OPTIONS[0].value);
  const [description, setDescription] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const create = useApiMutation(
    (body: ActivityCategoryUpdate) =>
      unwrap(client.POST("/api/members/activity-categories", { body })),
    {
      invalidate: [["activity-categories"]],
      onSuccess: (created: ActivityCategoryOut) => {
        toast.success("Kategorie angelegt.");
        setName("");
        setDescription("");
        setLjp(LJP_CATEGORY_OPTIONS[0].value);
        setCreating(false);
        navigate(`/app/activity-categories/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Aktivitätskategorien" }]}
        subtitle={query.data ? `${query.data.length} Kategorien` : undefined}
        actions={
          <div className="row-actions">
            {can("members.add_activitycategory") && (
              <Button onClick={() => setCreating(true)}>Neue Kategorie</Button>
            )}
            <Button variant="ghost" onClick={() => navigate("/app/training-categories")}>
              Ausbildungskategorien
            </Button>
          </div>
        }
      />

      {creating && (
        <Modal title="Neue Aktivitätskategorie" onClose={() => setCreating(false)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setFieldErrors({});
              create.mutate({ name, ljp_category: ljp, description });
            }}
          >
            <Field label="Name">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={20}
              />
            </Field>
            {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
            <Field label="LJP-Kategorie">
              <Select value={ljp} onChange={(v) => setLjp(v)} options={LJP_CATEGORY_OPTIONS} />
            </Field>
            {fieldErrors.ljp_category && (
              <div className="field-error">{fieldErrors.ljp_category.join(" ")}</div>
            )}
            <Field label="Beschreibung">
              <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
            </Field>
            {fieldErrors.description && (
              <div className="field-error">{fieldErrors.description.join(" ")}</div>
            )}
            <div className="row-actions">
              <Button type="submit" busy={create.isPending}>
                Anlegen
              </Button>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                Abbrechen
              </Button>
            </div>
          </form>
        </Modal>
      )}

      <QueryBoundary query={query} empty="Keine Kategorien.">
        {(rows: ActivityCategoryOut[]) => (
          <DataTable
            rows={rows}
            rowKey={(c) => c.id}
            onRowClick={(c) => navigate(`/app/activity-categories/${c.id}`)}
            columns={[
              { header: "Name", cell: (c) => c.name },
              { header: "LJP-Kategorie", cell: (c) => c.ljp_category_display || c.ljp_category },
              { header: "Beschreibung", cell: (c) => c.description || "—" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function ActivityCategoryDetailPage() {
  const { id } = useParams();
  const categoryId = Number(id);
  const query = useApiQuery(["activity-categories", categoryId], () =>
    unwrap(
      client.GET("/api/members/activity-categories/{category_id}", {
        params: { path: { category_id: categoryId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(cat: ActivityCategoryOut) => <ActivityCategoryDetailBody cat={cat} />}
    </QueryBoundary>
  );
}

function ActivityCategoryDetailBody({ cat }: { cat: ActivityCategoryOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  // Attach recovered model help_text to each row by its backend field name.
  const withHints = useRowHints();
  const confirm = useConfirmDialog();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => ({
    name: cat.name,
    ljp_category: cat.ljp_category,
    description: cat.description,
  }));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    (body: ActivityCategoryUpdate) =>
      unwrap(
        client.PATCH("/api/members/activity-categories/{category_id}", {
          params: { path: { category_id: cat.id } },
          body,
        }),
      ),
    {
      invalidate: [["activity-categories"], ["activity-categories", cat.id]],
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

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/activity-categories/{category_id}", {
          params: { path: { category_id: cat.id } },
        }),
      ),
    {
      invalidate: [["activity-categories"]],
      onSuccess: () => {
        toast.success("Gelöscht.");
        navigate("/app/activity-categories");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm({ name: cat.name, ljp_category: cat.ljp_category, description: cat.description });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: cat.name,
      edit: (
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      ),
    },
    {
      label: "LJP-Kategorie",
      field: "ljp_category",
      value: cat.ljp_category_display || cat.ljp_category,
      edit: (
        <Select
          value={form.ljp_category}
          onChange={(v) => setForm({ ...form, ljp_category: v })}
          options={LJP_CATEGORY_OPTIONS}
        />
      ),
    },
    {
      label: "Beschreibung",
      field: "description",
      value: cat.description || "—",
      edit: (
        <textarea
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(form);
      }}
    >
      <PageHeader
        breadcrumbs={[
          { label: "Aktivitätskategorien", to: "/app/activity-categories" },
          { label: cat.name },
        ]}
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
                      message: "Diese Aktivitätskategorie wirklich löschen?",
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
      <EditableDetail
        rows={withHints(rows, "activitycategory")}
        editing={editing}
        errors={fieldErrors}
      />
    </form>
  );
}

/* ====================================================================== */
/* TrainingCategory (Ausbildungskategorien)                               */
/* ====================================================================== */

export function TrainingCategoriesList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const toast = useToast();
  const query = useApiQuery(["training-categories"], () =>
    unwrap(client.GET("/api/members/training-categories")),
  );

  const [creating, setCreating] = useState(false);
  const [name, setName] = useState("");
  const [permissionNeeded, setPermissionNeeded] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const create = useApiMutation(
    (body: TrainingCategoryUpdate) =>
      unwrap(client.POST("/api/members/training-categories", { body })),
    {
      invalidate: [["training-categories"]],
      onSuccess: (created: TrainingCategoryOut) => {
        toast.success("Kategorie angelegt.");
        setName("");
        setPermissionNeeded(false);
        setCreating(false);
        navigate(`/app/training-categories/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Ausbildungskategorien" }]}
        subtitle={query.data ? `${query.data.length} Kategorien` : undefined}
        actions={
          <div className="row-actions">
            {can("members.add_trainingcategory") && (
              <Button onClick={() => setCreating(true)}>Neue Kategorie</Button>
            )}
            <Button variant="ghost" onClick={() => navigate("/app/activity-categories")}>
              Aktivitätskategorien
            </Button>
          </div>
        }
      />

      {creating && (
        <Modal title="Neue Ausbildungskategorie" onClose={() => setCreating(false)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setFieldErrors({});
              create.mutate({ name, permission_needed: permissionNeeded });
            }}
          >
            <Field label="Name">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                maxLength={50}
              />
            </Field>
            {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
            <label
              className="field"
              style={{ flexDirection: "row", alignItems: "center", gap: "0.5rem" }}
            >
              <input
                type="checkbox"
                checked={permissionNeeded}
                onChange={(e) => setPermissionNeeded(e.target.checked)}
              />
              <span className="field-label">Berechtigung erforderlich</span>
            </label>
            {fieldErrors.permission_needed && (
              <div className="field-error">{fieldErrors.permission_needed.join(" ")}</div>
            )}
            <div className="row-actions">
              <Button type="submit" busy={create.isPending}>
                Anlegen
              </Button>
              <Button type="button" variant="ghost" onClick={() => setCreating(false)}>
                Abbrechen
              </Button>
            </div>
          </form>
        </Modal>
      )}

      <QueryBoundary query={query} empty="Keine Kategorien.">
        {(rows: TrainingCategoryOut[]) => (
          <DataTable
            rows={rows}
            rowKey={(c) => c.id}
            onRowClick={(c) => navigate(`/app/training-categories/${c.id}`)}
            columns={[
              { header: "Name", cell: (c) => c.name },
              {
                header: "Berechtigung erforderlich",
                cell: (c) =>
                  c.permission_needed ? <Badge tone="warning">Ja</Badge> : <Badge>Nein</Badge>,
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function TrainingCategoryDetailPage() {
  const { id } = useParams();
  const categoryId = Number(id);
  const query = useApiQuery(["training-categories", categoryId], () =>
    unwrap(
      client.GET("/api/members/training-categories/{category_id}", {
        params: { path: { category_id: categoryId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(cat: TrainingCategoryOut) => <TrainingCategoryDetailBody cat={cat} />}
    </QueryBoundary>
  );
}

function TrainingCategoryDetailBody({ cat }: { cat: TrainingCategoryOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => ({
    name: cat.name,
    permission_needed: cat.permission_needed,
  }));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    (body: TrainingCategoryUpdate) =>
      unwrap(
        client.PATCH("/api/members/training-categories/{category_id}", {
          params: { path: { category_id: cat.id } },
          body,
        }),
      ),
    {
      invalidate: [["training-categories"], ["training-categories", cat.id]],
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

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/training-categories/{category_id}", {
          params: { path: { category_id: cat.id } },
        }),
      ),
    {
      invalidate: [["training-categories"]],
      onSuccess: () => {
        toast.success("Gelöscht.");
        navigate("/app/training-categories");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm({ name: cat.name, permission_needed: cat.permission_needed });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: cat.name,
      edit: (
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      ),
    },
    {
      label: "Berechtigung erforderlich",
      field: "permission_needed",
      value: cat.permission_needed ? <Badge tone="warning">Ja</Badge> : <Badge>Nein</Badge>,
      edit: (
        <input
          type="checkbox"
          checked={form.permission_needed}
          onChange={(e) => setForm({ ...form, permission_needed: e.target.checked })}
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(form);
      }}
    >
      <PageHeader
        breadcrumbs={[
          { label: "Ausbildungskategorien", to: "/app/training-categories" },
          { label: cat.name },
        ]}
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
                      message: "Diese Ausbildungskategorie wirklich löschen?",
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
