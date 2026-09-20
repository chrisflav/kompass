import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
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
  Select,
  Tabs,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft } from "../../components/inlineDraft";
import { MultiSelect, type Option } from "./_controls";
import type { components } from "../../api/schema";

type KlettertreffBrief = components["schemas"]["KlettertreffBrief"];
type KlettertreffOut = components["schemas"]["KlettertreffOut"];
type KlettertreffCreate = components["schemas"]["KlettertreffCreate"];
type KlettertreffUpdate = components["schemas"]["KlettertreffUpdate"];
type KlettertreffAttendeeCreate = components["schemas"]["KlettertreffAttendeeCreate"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

/**
 * Standard Django date drill-down buckets, evaluated client-side. Exported for
 * its own unit test: an unknown bucket cannot come from the list filter, whose
 * options are fixed, so that fallback is only reachable directly.
 */
export function dateBucket(value: string | null | undefined, bucket: string): boolean {
  if (bucket === "none") return !value;
  if (!value) return false;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  if (bucket === "today") return d.toDateString() === now.toDateString();
  if (bucket === "7days") {
    const diff = (now.getTime() - d.getTime()) / 86_400_000;
    return diff >= 0 && diff <= 7;
  }
  if (bucket === "month")
    return d.getFullYear() === now.getFullYear() && d.getMonth() === now.getMonth();
  if (bucket === "year") return d.getFullYear() === now.getFullYear();
  return true;
}

/* --- list ----------------------------------------------------------------
 * Admin KlettertreffAdmin: list_display (__str__, date, get_jugendleiter),
 * search_fields (date, location, topic), list_filter (date, group). Ordering
 * -date (API). */

export function KlettertreffList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["klettertreff"], () =>
    unwrap(client.GET("/api/members/klettertreff")),
  );
  const rows = query.data ?? [];

  const groupOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((k) => names.add(k.group.name));
    return [...names].sort().map((n) => ({ value: n, label: n }));
  }, [rows]);

  const config: ListViewConfig<KlettertreffBrief> = useMemo(
    () => ({
      search: (k) => [k.date, k.location, k.topic, k.group.name],
      filters: [
        {
          key: "group",
          label: "Gruppe",
          options: groupOptions,
          match: (k, v) => k.group.name === v,
        },
        {
          key: "date",
          label: "Datum",
          options: [
            { value: "today", label: "Heute" },
            { value: "7days", label: "Letzte 7 Tage" },
            { value: "month", label: "Dieser Monat" },
            { value: "year", label: "Dieses Jahr" },
            { value: "none", label: "Ohne Datum" },
          ],
          match: (k, v) => dateBucket(k.date, v),
        },
      ],
      sort: {
        group: (k) => k.group.name,
        date: (k) => k.date,
        location: (k) => k.location,
        topic: (k) => k.topic,
      },
      defaultSort: { key: "date", dir: "desc" },
    }),
    [groupOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Klettertreffs" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("members.add_klettertreff") && (
            <Button onClick={() => setCreating(true)}>Neuer Klettertreff</Button>
          )
        }
      />
      {creating && (
        <Modal title="Neuer Klettertreff" onClose={() => setCreating(false)}>
          <KlettertreffCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Klettertreff-Termine sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(k) => k.id}
            onRowClick={(k) => navigate(`/kompass/klettertreff/${k.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Gruppe", cell: (k) => k.group.name, sortKey: "group" },
              { header: "Datum", cell: (k) => formatDate(k.date), sortKey: "date" },
              { header: "Ort", cell: (k) => k.location || "—", sortKey: "location" },
              { header: "Thema", cell: (k) => k.topic || "—", sortKey: "topic" },
              {
                header: "Jugendleiter*innen",
                cell: (k) => (k.jugendleiter.length ? k.jugendleiter.join(", ") : "—"),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function KlettertreffCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [groupId, setGroupId] = useState("");
  const [date, setDate] = useState("");
  const [location, setLocation] = useState("");
  const [topic, setTopic] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const groupOptions = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );

  const mutation = useApiMutation(
    (body: KlettertreffCreate) => unwrap(client.POST("/api/members/klettertreff", { body })),
    {
      invalidate: [["klettertreff"]],
      onSuccess: (created: KlettertreffOut) => {
        toast.success("Klettertreff angelegt.");
        onDone();
        navigate(`/kompass/klettertreff/${created.id}`);
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
          group_id: Number(groupId),
          date: date || null,
          location,
          topic,
          jugendleiter_ids: [],
        });
      }}
    >
      <Field label="Gruppe">
        <Select
          value={groupId}
          onChange={(v) => setGroupId(v)}
          options={groupOptions}
          placeholder="Gruppe wählen …"
        />
        {fieldErrors.group_id && (
          <div className="field-error">{fieldErrors.group_id.join(" ")}</div>
        )}
      </Field>
      <Field label="Datum">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        {fieldErrors.date && <div className="field-error">{fieldErrors.date.join(" ")}</div>}
      </Field>
      <Field label="Ort">
        <input value={location} onChange={(e) => setLocation(e.target.value)} />
        {fieldErrors.location && (
          <div className="field-error">{fieldErrors.location.join(" ")}</div>
        )}
      </Field>
      <Field label="Thema">
        <input value={topic} onChange={(e) => setTopic(e.target.value)} />
        {fieldErrors.topic && <div className="field-error">{fieldErrors.topic.join(" ")}</div>}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending} disabled={groupId === ""}>
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

export function KlettertreffDetailPage() {
  const { id } = useParams();
  const klettertreffId = Number(id);
  const query = useApiQuery(["klettertreff", klettertreffId], () =>
    unwrap(
      client.GET("/api/members/klettertreff/{klettertreff_id}", {
        params: { path: { klettertreff_id: klettertreffId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(kt: KlettertreffOut) => <KlettertreffDetailBody kt={kt} />}
    </QueryBoundary>
  );
}

function makeForm(kt: KlettertreffOut) {
  return {
    date: kt.date ?? "",
    location: kt.location ?? "",
    topic: kt.topic ?? "",
    group_id: String(kt.group.id),
    jugendleiter_ids: kt.jugendleiter.map((j) => j.id),
  };
}

function KlettertreffDetailBody({ kt }: { kt: KlettertreffOut }) {
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const removeMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/klettertreff/{klettertreff_id}", {
          params: { path: { klettertreff_id: kt.id } },
        }),
      ),
    {
      invalidate: [["klettertreff"]],
      onSuccess: () => {
        toast.success("Klettertreff gelöscht.");
        navigate("/kompass/klettertreff");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeForm(kt));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")), {
    enabled: editing,
  });
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")), {
    enabled: editing,
  });
  const groupOptions = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: KlettertreffUpdate) =>
      unwrap(
        client.PATCH("/api/members/klettertreff/{klettertreff_id}", {
          params: { path: { klettertreff_id: kt.id } },
          body,
        }),
      ),
    { invalidate: [["klettertreff"], ["klettertreff", kt.id]] },
  );

  function startEditing() {
    setForm(makeForm(kt));
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Datum",
      field: "date",
      value: formatDate(kt.date),
      edit: (
        <input
          type="date"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
      ),
    },
    {
      label: "Ort",
      field: "location",
      value: kt.location || "—",
      edit: (
        <input
          value={form.location}
          onChange={(e) => setForm({ ...form, location: e.target.value })}
        />
      ),
    },
    {
      label: "Thema",
      field: "topic",
      value: kt.topic || "—",
      edit: (
        <input value={form.topic} onChange={(e) => setForm({ ...form, topic: e.target.value })} />
      ),
    },
    {
      label: "Gruppe",
      field: "group",
      value: kt.group.name,
      edit: (
        <Select
          value={form.group_id}
          onChange={(v) => setForm({ ...form, group_id: v })}
          options={groupOptions}
        />
      ),
    },
    {
      label: "Jugendleiter*innen",
      field: "jugendleiter",
      value: kt.jugendleiter.length ? kt.jugendleiter.map((j) => j.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.jugendleiter_ids}
          onChange={(ids) => setForm({ ...form, jugendleiter_ids: ids })}
          searchable
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setFieldErrors({});
        setSaving(true);
        try {
          await mutation.mutateAsync({
            date: form.date || null,
            location: form.location,
            topic: form.topic,
            group_id: Number(form.group_id),
            jugendleiter_ids: form.jugendleiter_ids,
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
      <PageHeader
        breadcrumbs={[
          { label: "Klettertreffs", to: "/kompass/klettertreff" },
          { label: kt.topic || kt.group.name },
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
              {can("members.delete_klettertreff") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={removeMutation.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${kt.topic || kt.group.name}“ wirklich löschen?`,
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
      <Tabs
        tabs={[
          {
            id: "allgemein",
            label: "Allgemein",
            content: <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "teilnehmer",
            label: "Teilnehmer*innen",
            content: (
              <KlettertreffAttendeesInline
                klettertreffId={kt.id}
                editing={editing}
                registerFlush={getRegistrar("attendees")}
              />
            ),
          },
        ]}
      />
    </form>
  );
}

/**
 * Klettertreff attendee inline (Django `KlettertreffAttendeeInline`). Links
 * members to the meeting; add + remove only (the model carries no per-row
 * fields beyond the member link).
 */
type AttendeeData = { member_id: number | null; member_name: string };

function KlettertreffAttendeesInline({
  klettertreffId,
  editing,
  registerFlush,
}: {
  klettertreffId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const listQuery = useApiQuery(["klettertreff", klettertreffId, "attendees"], () =>
    unwrap(
      client.GET("/api/members/klettertreff/{klettertreff_id}/attendees", {
        params: { path: { klettertreff_id: klettertreffId } },
      }),
    ),
  );
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")), {
    enabled: editing,
  });
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const invalidate = [
    ["klettertreff", klettertreffId, "attendees"],
    ["klettertreff", klettertreffId],
  ];
  const createM = useApiMutation(
    (body: KlettertreffAttendeeCreate) =>
      unwrap(
        client.POST("/api/members/klettertreff/{klettertreff_id}/attendees", {
          params: { path: { klettertreff_id: klettertreffId } },
          body,
        }),
      ),
    { invalidate },
  );
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/attendees/{attendee_id}", {
          params: { path: { attendee_id: id } },
        }),
      ),
    { invalidate },
  );

  const serverRows = (listQuery.data ?? []).map((a) => ({
    id: a.id,
    data: { member_id: a.member.id, member_name: a.member.name } as AttendeeData,
  }));
  const { rows, removeRow, addRow } = useInlineDraft<AttendeeData>({
    serverRows,
    editing,
    // Attendees carry no editable fields, so only create/delete run.
    create: (d) => createM.mutateAsync({ member_id: d.member_id ?? 0 }),
    update: () => Promise.resolve(),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });
  const [adding, setAdding] = useState<AttendeeData | null>(null);

  return (
    <>
      <InlineTable
        title="Teilnehmer*innen"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ member_id: null, member_name: "" })}
        addLabel="Teilnehmende"
        columns={[{ header: "Teilnehmende", cell: (row) => row.data.member_name || "—" }]}
      />
      {adding && (
        <Modal title="Teilnehmende hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Teilnehmende">
              <Select
                value={adding.member_id === null ? "" : String(adding.member_id)}
                onChange={(v) =>
                  setAdding({
                    member_id: v === "" ? null : Number(v),
                    member_name: memberOptions.find((o) => String(o.value) === v)?.label ?? "",
                  })
                }
                options={memberOptions}
                placeholder="Teilnehmende wählen …"
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={adding.member_id === null}
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
