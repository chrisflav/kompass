import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  type Crumb,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type TrainingBrief = components["schemas"]["TrainingBrief"];
type TrainingOut = components["schemas"]["TrainingOut"];
type TrainingCreate = components["schemas"]["MemberTrainingCreate"];
type TrainingUpdate = components["schemas"]["MemberTrainingUpdate"];
type TrainingCategoryOut = components["schemas"]["TrainingCategoryOut"];
type ActivityCategoryOut = components["schemas"]["ActivityCategoryOut"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

function boolBadge(value: boolean | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value ? <Badge tone="success">Ja</Badge> : <Badge tone="warning">Nein</Badge>;
}

const fieldsetTitle = { marginTop: "1.5rem" } as const;

/* --- list ----------------------------------------------------------------
 * Full parity with MemberTrainingAdmin: all list_display columns (title,
 * member, date, category, activities, participated, passed, certificate),
 * search over title, filters (category, passed, activity, member), sortable
 * headers, default ordering by -date. */

export function TrainingsList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["trainings"], () => unwrap(client.GET("/api/members/trainings")));
  const rows = query.data ?? [];

  const categoryOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((t) => names.add(t.category_name));
    return [...names].sort().map((n) => ({ value: n, label: n }));
  }, [rows]);

  const memberOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((t) => names.add(t.member_name));
    return [...names].sort().map((n) => ({ value: n, label: n }));
  }, [rows]);

  const activityOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((t) => t.activities.forEach((a) => names.add(a)));
    return [...names].sort().map((n) => ({ value: n, label: n }));
  }, [rows]);

  const config: ListViewConfig<TrainingBrief> = useMemo(
    () => ({
      search: (t) => [t.title],
      filters: [
        { key: "category", label: "Kategorie", options: categoryOptions, match: (t, v) => t.category_name === v },
        { key: "member", label: "Teilnehmende", options: memberOptions, match: (t, v) => t.member_name === v },
        {
          key: "activity",
          label: "Tätigkeit",
          options: activityOptions,
          match: (t, v) => t.activities.includes(v),
        },
        {
          key: "passed",
          label: "Bestanden",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
            { value: "unknown", label: "Unbekannt" },
          ],
          match: (t, v) =>
            v === "unknown"
              ? t.passed === null || t.passed === undefined
              : (v === "yes") === Boolean(t.passed),
        },
      ],
      sort: {
        title: (t) => t.title,
        member: (t) => t.member_name,
        date: (t) => t.date,
        category: (t) => t.category_name,
        participated: (t) => t.participated,
        passed: (t) => t.passed,
      },
      defaultSort: { key: "date", dir: "desc" },
    }),
    [categoryOptions, memberOptions, activityOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Ausbildungen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("members.add_global_membertraining") && (
            <Button onClick={() => setCreating(true)}>Neue Ausbildung</Button>
          )
        }
      />
      {creating && (
        <Modal title="Neue Ausbildung" onClose={() => setCreating(false)}>
          <TrainingCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Ausbildungen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(t) => t.id}
            onRowClick={(t) => navigate(`/app/trainings/${t.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (t) => t.title, sortKey: "title" },
              { header: "Teilnehmende", cell: (t) => t.member_name, sortKey: "member" },
              { header: "Datum", cell: (t) => formatDate(t.date), sortKey: "date" },
              { header: "Kategorie", cell: (t) => t.category_name, sortKey: "category" },
              { header: "Tätigkeiten", cell: (t) => t.activities.join(", ") || "—" },
              { header: "Teilgenommen", cell: (t) => boolBadge(t.participated), sortKey: "participated" },
              { header: "Bestanden", cell: (t) => boolBadge(t.passed), sortKey: "passed" },
              {
                header: "Nachweis",
                cell: (t) =>
                  t.certificate ? (
                    <a
                      href={t.certificate}
                      target="_blank"
                      rel="noreferrer"
                      onClick={(e) => e.stopPropagation()}
                    >
                      Öffnen
                    </a>
                  ) : (
                    "—"
                  ),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function TrainingCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [memberId, setMemberId] = useState("");
  const [title, setTitle] = useState("");
  const [categoryId, setCategoryId] = useState("");
  const [date, setDate] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const categoriesQuery = useApiQuery(["training-categories"], () =>
    unwrap(client.GET("/api/members/training-categories")),
  );
  const memberOptions = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );
  const categoryOptions = useMemo(
    () => (categoriesQuery.data ?? []).map((c) => ({ value: c.id, label: c.name })),
    [categoriesQuery.data],
  );

  const mutation = useApiMutation(
    (body: TrainingCreate) => unwrap(client.POST("/api/members/trainings", { body })),
    {
      invalidate: [["trainings"]],
      onSuccess: (created: TrainingOut) => {
        toast.success("Ausbildung angelegt.");
        onDone();
        navigate(`/app/trainings/${created.id}`);
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
        mutation.mutate({
          member_id: Number(memberId),
          title,
          category_id: Number(categoryId),
          date: date || null,
          activity_ids: [],
        });
      }}
    >
      <Field label="Teilnehmende">
        <Select
          value={memberId}
          onChange={(v) => setMemberId(v)}
          options={memberOptions}
          placeholder="Teilnehmende wählen …"
        />
        {fieldErrors.member_id && (
          <div className="field-error">{fieldErrors.member_id.join(" ")}</div>
        )}
      </Field>
      <Field label="Titel">
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        {fieldErrors.title && <div className="field-error">{fieldErrors.title.join(" ")}</div>}
      </Field>
      <Field label="Kategorie">
        <Select
          value={categoryId}
          onChange={(v) => setCategoryId(v)}
          options={categoryOptions}
          placeholder="Kategorie wählen …"
        />
        {fieldErrors.category_id && (
          <div className="field-error">{fieldErrors.category_id.join(" ")}</div>
        )}
      </Field>
      <Field label="Datum">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        {fieldErrors.date && <div className="field-error">{fieldErrors.date.join(" ")}</div>}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending} disabled={memberId === "" || categoryId === ""}>
          Anlegen
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}

/* --- detail + edit ------------------------------------------------------- */

export function TrainingDetailPage() {
  const { id } = useParams();
  const trainingId = Number(id);
  const query = useApiQuery(["trainings", trainingId], () =>
    unwrap(
      client.GET("/api/members/trainings/{training_id}", {
        params: { path: { training_id: trainingId } },
      }),
    ),
  );
  const crumbs: Crumb[] = [
    { label: "Ausbildungen", to: "/app/trainings" },
    { label: query.data?.title ?? "Ausbildung" },
  ];

  return (
    <QueryBoundary query={query}>
      {(training: TrainingOut) => <TrainingDetailBody training={training} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function makeDraft(t: TrainingOut) {
  return {
    title: t.title ?? "",
    comments: t.comments ?? "",
    participated: t.participated ?? false,
    passed: t.passed ?? false,
    date: t.date ?? "",
    category_id: String(t.category_id ?? ""),
    activity_ids: t.activity_ids ?? [],
  };
}

function TrainingDetailBody({ training, crumbs }: { training: TrainingOut; crumbs: Crumb[] }) {
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const removeMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/trainings/{training_id}", {
          params: { path: { training_id: training.id } },
        }),
      ),
    {
      invalidate: [["members", "trainings"]],
      onSuccess: () => {
        toast.success("Ausbildung gelöscht.");
        navigate("/app/trainings");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeDraft(training));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const categoriesQuery = useApiQuery(
    ["training-categories"],
    () => unwrap(client.GET("/api/members/training-categories")),
    { enabled: editing },
  );
  const activitiesQuery = useApiQuery(
    ["activity-categories"],
    () => unwrap(client.GET("/api/members/activity-categories")),
    { enabled: editing },
  );

  const mutation = useApiMutation<TrainingOut, TrainingUpdate>(
    (body: TrainingUpdate) =>
      unwrap(
        client.PATCH("/api/members/trainings/{training_id}", {
          params: { path: { training_id: training.id } },
          body,
        }),
      ),
    {
      invalidate: [["trainings"], ["trainings", training.id]],
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
    setForm(makeDraft(training));
    setFieldErrors({});
    setEditing(true);
  }

  const categories: TrainingCategoryOut[] = categoriesQuery.data ?? [];
  const activities: ActivityCategoryOut[] = activitiesQuery.data ?? [];

  const rows: DetailRow[] = [
    {
      label: "Titel",
      value: training.title,
      field: "title",
      edit: (
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      ),
    },
    { label: "Teilnehmende", value: training.member.name },
    {
      label: "Kategorie",
      value: training.category,
      field: "category",
      edit: (
        <Select
          value={form.category_id}
          onChange={(v) => setForm({ ...form, category_id: v })}
          options={categories.map((c) => ({ value: c.id, label: c.name }))}
          placeholder="Kategorie wählen …"
        />
      ),
    },
    {
      label: "Tätigkeiten",
      value: training.activities.length ? training.activities.join(", ") : "—",
      field: "activities",
      edit: (
        <MultiSelect
          options={activities.map((a) => ({ value: a.id, label: a.name }))}
          selected={form.activity_ids}
          onChange={(ids) => setForm({ ...form, activity_ids: ids })}
          placeholder="Tätigkeit hinzufügen"
        />
      ),
    },
    {
      label: "Datum",
      value: formatDate(training.date),
      field: "date",
      edit: (
        <input
          type="date"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
      ),
    },
    {
      label: "Teilgenommen",
      value: boolBadge(training.participated),
      field: "participated",
      edit: (
        <input
          type="checkbox"
          checked={form.participated}
          onChange={(e) => setForm({ ...form, participated: e.target.checked })}
        />
      ),
    },
    {
      label: "Bestanden",
      value: boolBadge(training.passed),
      field: "passed",
      edit: (
        <input
          type="checkbox"
          checked={form.passed}
          onChange={(e) => setForm({ ...form, passed: e.target.checked })}
        />
      ),
    },
    {
      label: "Kommentar",
      value: training.comments || "—",
      field: "comments",
      edit: (
        <textarea
          value={form.comments}
          onChange={(e) => setForm({ ...form, comments: e.target.value })}
        />
      ),
    },
    {
      label: "Teilnahmebescheinigung",
      value: training.certificate ? (
        <a href={training.certificate} target="_blank" rel="noreferrer">
          Öffnen
        </a>
      ) : (
        "—"
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate({
          title: form.title,
          comments: form.comments,
          participated: form.participated,
          passed: form.passed,
          date: form.date || null,
          category_id: form.category_id ? Number(form.category_id) : null,
          activity_ids: form.activity_ids,
        });
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
              {can("members.delete_global_membertraining") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={removeMutation.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${training.title || "Ausbildung"}“ wirklich löschen?`,
                        danger: true,
                        confirmLabel: "Löschen",
                      })
                    )
                      removeMutation.mutate(undefined);
                  }}
                >
                  Löschen
                </Button>
              )}
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            </>
          )
        }
      />
      <h3 className="fieldset-title" style={fieldsetTitle}>
        Ausbildung
      </h3>
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
    </form>
  );
}
