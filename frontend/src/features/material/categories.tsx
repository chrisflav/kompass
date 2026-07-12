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
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type MaterialCategoryBrief = components["schemas"]["MaterialCategoryBrief"];
type MaterialCategoryOut = components["schemas"]["MaterialCategoryOut"];

/* --- list ---------------------------------------------------------------- */

export function CategoriesList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["material", "categories"], () =>
    unwrap(client.GET("/api/material/categories")),
  );
  const rows = query.data ?? [];

  // Admin has no search_fields / list_filter; ordering = name.
  const config: ListViewConfig<MaterialCategoryBrief> = useMemo(
    () => ({
      sort: { name: (c) => c.name },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Materialkategorien" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neue Kategorie</Button>}
      />
      {creating && (
        <Modal title="Neue Kategorie" onClose={() => setCreating(false)}>
          <CategoryForm
            initial={{ name: "" }}
            submitLabel="Anlegen"
            onSubmit={(body) => unwrap(client.POST("/api/material/categories", { body }))}
            onSuccess={(c) => {
              setCreating(false);
              navigate(`/app/material/categories/${c.id}`);
            }}
            onCancel={() => setCreating(false)}
          />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Kategorien vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(c) => c.id}
            onRowClick={(c) => navigate(`/app/material/categories/${c.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[{ header: "Name", cell: (c) => c.name, sortKey: "name" }]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail -------------------------------------------------------------- */

export function CategoryDetailPage() {
  const { id } = useParams();
  const categoryId = Number(id);
  const query = useApiQuery(["material", "categories", categoryId], () =>
    unwrap(
      client.GET("/api/material/categories/{category_id}", {
        params: { path: { category_id: categoryId } },
      }),
    ),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Materialkategorien", to: "/app/material/categories" },
          { label: query.data?.name ?? "Kategorie" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(category: MaterialCategoryOut) => <CategoryDetailBody category={category} />}
      </QueryBoundary>
    </div>
  );
}

function CategoryDetailBody({ category }: { category: MaterialCategoryOut }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => ({ name: category.name }));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const mutation = useApiMutation(
    (body: typeof form) =>
      unwrap(
        client.PUT("/api/material/categories/{category_id}", {
          params: { path: { category_id: category.id } },
          body,
        }),
      ),
    {
      invalidate: [
        ["material", "categories"],
        ["material", "categories", category.id],
      ],
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

  const deletion = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/material/categories/{category_id}", {
          params: { path: { category_id: category.id } },
        }),
      ),
    {
      invalidate: [["material", "categories"]],
      onSuccess: () => {
        toast.success("Kategorie gelöscht.");
        navigate("/app/material/categories");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm({ name: category.name });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: category.name,
      edit: (
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
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
      <div className="detail-actions">
        {editing ? (
          <>
            <Button type="submit" busy={mutation.isPending}>
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Abbrechen
            </Button>
          </>
        ) : (
          <>
            <Button type="button" onClick={startEditing}>
              Bearbeiten
            </Button>
            <Button
              type="button"
              variant="danger"
              busy={deletion.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    message: "Kategorie wirklich löschen?",
                    danger: true,
                    confirmLabel: "Löschen",
                  })
                )
                  deletion.mutate(undefined);
              }}
            >
              Löschen
            </Button>
          </>
        )}
      </div>
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
      <h3>Material in dieser Kategorie</h3>
      <DataTable
        rows={category.material_parts}
        rowKey={(p) => p.id}
        onRowClick={(p) => navigate(`/app/material/${p.id}`)}
        columns={[{ header: "Name", cell: (p) => p.name }]}
        empty="Kein Material in dieser Kategorie."
      />
    </form>
  );
}

/* --- shared form --------------------------------------------------------- */

type CategoryFormState = components["schemas"]["MaterialCategoryIn"];

function CategoryForm({
  initial,
  submitLabel,
  onSubmit,
  onSuccess,
  onCancel,
  invalidate = [["material", "categories"]],
}: {
  initial: CategoryFormState;
  submitLabel: string;
  onSubmit: (body: CategoryFormState) => Promise<MaterialCategoryOut>;
  onSuccess: (c: MaterialCategoryOut) => void;
  onCancel?: () => void;
  invalidate?: unknown[][];
}) {
  const toast = useToast();
  const [form, setForm] = useState<CategoryFormState>(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation((body: CategoryFormState) => onSubmit(body), {
    invalidate,
    onSuccess: (c) => {
      toast.success("Gespeichert.");
      onSuccess(c);
    },
    onError: (e: Error) => {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      toast.error(e.message);
    },
  });

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(form);
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
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          {submitLabel}
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
