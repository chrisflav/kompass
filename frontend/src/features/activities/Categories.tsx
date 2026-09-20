import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

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
  Tabs,
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

/**
 * Activity and training categories share one screen.
 *
 * Both are small reference tables that are edited rarely, and each list used to
 * carry a "jump to the other one" button — the split cost a nav entry and a
 * click without separating anything a user thinks of as separate. They are two
 * tabs of a single "Kategorien" page instead.
 *
 * The open tab lives in `?type=`, so a bookmark, the back button and the
 * breadcrumb out of a detail page all return to the tab you were on.
 */
type CategoryKind = "activity" | "training";

const DEFAULT_KIND: CategoryKind = "activity";

function kindFromParam(value: string | null): CategoryKind {
  return value === "training" ? "training" : DEFAULT_KIND;
}

/** The list URL for a kind — also where a detail page's breadcrumb returns to. */
export function categoriesPath(kind: CategoryKind): string {
  return kind === DEFAULT_KIND ? "/kompass/categories" : `/kompass/categories?type=${kind}`;
}

/* ====================================================================== */
/* The combined list page                                                 */
/* ====================================================================== */

export function CategoriesPage() {
  const { can } = usePermissions();
  const [params, setParams] = useSearchParams();
  const kind = kindFromParam(params.get("type"));

  const activityQuery = useApiQuery(["activity-categories"], () =>
    unwrap(client.GET("/api/members/activity-categories")),
  );
  const trainingQuery = useApiQuery(["training-categories"], () =>
    unwrap(client.GET("/api/members/training-categories")),
  );

  const [creating, setCreating] = useState(false);

  const count = kind === "activity" ? activityQuery.data?.length : trainingQuery.data?.length;
  const mayAdd = can(
    kind === "activity" ? "members.add_activitycategory" : "members.add_trainingcategory",
  );
  // Name the kind: a bare "3 Kategorien" above two tabs reads as a total.
  const noun = kind === "activity" ? "Aktivitätskategorien" : "Ausbildungskategorien";

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Kategorien" }]}
        subtitle={count !== undefined ? `${count} ${noun}` : undefined}
        actions={
          mayAdd ? <Button onClick={() => setCreating(true)}>Neue Kategorie</Button> : undefined
        }
      />

      {creating && kind === "activity" && (
        <NewActivityCategoryModal onClose={() => setCreating(false)} />
      )}
      {creating && kind === "training" && (
        <NewTrainingCategoryModal onClose={() => setCreating(false)} />
      )}

      <Tabs
        active={kind}
        onChange={(id) => {
          // Close a half-filled create dialog rather than carrying it across to
          // the other kind, where its fields do not apply.
          setCreating(false);
          setParams(id === DEFAULT_KIND ? {} : { type: id }, { replace: true });
        }}
        tabs={[
          {
            id: "activity",
            label: "Aktivitäten",
            content: <ActivityCategoryTable query={activityQuery} />,
          },
          {
            id: "training",
            label: "Ausbildungen",
            content: <TrainingCategoryTable query={trainingQuery} />,
          },
        ]}
      />
    </div>
  );
}

/* ====================================================================== */
/* ActivityCategory (Aktivitätskategorien)                                */
/* ====================================================================== */

function ActivityCategoryTable({
  query,
}: {
  query: ReturnType<typeof useApiQuery<ActivityCategoryOut[]>>;
}) {
  const navigate = useNavigate();
  return (
    <QueryBoundary query={query} empty="Keine Kategorien.">
      {(rows: ActivityCategoryOut[]) => (
        <DataTable
          rows={rows}
          rowKey={(c) => c.id}
          onRowClick={(c) => navigate(`/kompass/categories/activity/${c.id}`)}
          columns={[
            { header: "Name", cell: (c) => c.name },
            { header: "LJP-Kategorie", cell: (c) => c.ljp_category_display || c.ljp_category },
            { header: "Beschreibung", cell: (c) => c.description || "—" },
          ]}
        />
      )}
    </QueryBoundary>
  );
}

function NewActivityCategoryModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
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
        onClose();
        navigate(`/kompass/categories/activity/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <Modal title="Neue Aktivitätskategorie" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          create.mutate({ name, ljp_category: ljp, description });
        }}
      >
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={20} />
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
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
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
        navigate(categoriesPath("activity"));
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
          { label: "Kategorien", to: categoriesPath("activity") },
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

function TrainingCategoryTable({
  query,
}: {
  query: ReturnType<typeof useApiQuery<TrainingCategoryOut[]>>;
}) {
  const navigate = useNavigate();
  return (
    <QueryBoundary query={query} empty="Keine Kategorien.">
      {(rows: TrainingCategoryOut[]) => (
        <DataTable
          rows={rows}
          rowKey={(c) => c.id}
          onRowClick={(c) => navigate(`/kompass/categories/training/${c.id}`)}
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
  );
}

function NewTrainingCategoryModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
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
        onClose();
        navigate(`/kompass/categories/training/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <Modal title="Neue Ausbildungskategorie" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          create.mutate({ name, permission_needed: permissionNeeded });
        }}
      >
        <Field label="Name">
          <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={50} />
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
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
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
        navigate(categoriesPath("training"));
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
          { label: "Kategorien", to: categoriesPath("training") },
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
