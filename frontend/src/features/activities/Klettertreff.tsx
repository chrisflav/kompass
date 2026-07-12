import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  EditableDetail,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useToast,
  type DetailRow,
} from "../../components/ui";
import { InlineTable } from "../../components/inline";
import { MultiSelect, type Option } from "./_controls";
import type { components } from "../../api/schema";

type KlettertreffBrief = components["schemas"]["KlettertreffBrief"];
type KlettertreffOut = components["schemas"]["KlettertreffOut"];
type KlettertreffUpdate = components["schemas"]["KlettertreffUpdate"];
type KlettertreffAttendeeCreate = components["schemas"]["KlettertreffAttendeeCreate"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

/** Standard Django date drill-down buckets, evaluated client-side. */
function dateBucket(value: string | null | undefined, bucket: string): boolean {
  if (bucket === "none") return !value;
  if (!value) return false;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return false;
  const now = new Date();
  if (bucket === "today")
    return d.toDateString() === now.toDateString();
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
  const navigate = useNavigate();
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
        { key: "group", label: "Gruppe", options: groupOptions, match: (k, v) => k.group.name === v },
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
        breadcrumbs={[{ label: "Klettertreff" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Klettertreff-Termine sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(k) => k.id}
            onRowClick={(k) => navigate(`/app/klettertreff/${k.id}`)}
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
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Klettertreff", to: "/app/klettertreff" },
          { label: query.data ? query.data.topic || query.data.group.name : "Klettertreff" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(kt: KlettertreffOut) => <KlettertreffDetailBody kt={kt} />}
      </QueryBoundary>
    </div>
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
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeForm(kt));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const groupsQuery = useApiQuery(
    ["groups"],
    () => unwrap(client.GET("/api/members/groups")),
    { enabled: editing },
  );
  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const groupOptions = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const mutation = useApiMutation(
    (body: KlettertreffUpdate) =>
      unwrap(
        client.PATCH("/api/members/klettertreff/{klettertreff_id}", {
          params: { path: { klettertreff_id: kt.id } },
          body,
        }),
      ),
    {
      invalidate: [["klettertreff"], ["klettertreff", kt.id]],
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
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate({
          date: form.date || null,
          location: form.location,
          topic: form.topic,
          group_id: Number(form.group_id),
          jugendleiter_ids: form.jugendleiter_ids,
        });
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
          <Button type="button" onClick={startEditing}>
            Bearbeiten
          </Button>
        )}
      </div>
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
            content: <KlettertreffAttendeesInline klettertreffId={kt.id} editing={editing} />,
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
function KlettertreffAttendeesInline({
  klettertreffId,
  editing,
}: {
  klettertreffId: number;
  editing: boolean;
}) {
  const toast = useToast();
  const listQuery = useApiQuery(["klettertreff", klettertreffId, "attendees"], () =>
    unwrap(
      client.GET("/api/members/klettertreff/{klettertreff_id}/attendees", {
        params: { path: { klettertreff_id: klettertreffId } },
      }),
    ),
  );
  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const [memberId, setMemberId] = useState("");
  const invalidate = [
    ["klettertreff", klettertreffId, "attendees"],
    ["klettertreff", klettertreffId],
  ];

  const create = useApiMutation(
    (body: KlettertreffAttendeeCreate) =>
      unwrap(
        client.POST("/api/members/klettertreff/{klettertreff_id}/attendees", {
          params: { path: { klettertreff_id: klettertreffId } },
          body,
        }),
      ),
    {
      invalidate,
      onSuccess: () => {
        toast.success("Hinzugefügt.");
        setMemberId("");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );
  const remove = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/attendees/{attendee_id}", {
          params: { path: { attendee_id: id } },
        }),
      ),
    {
      invalidate,
      onSuccess: () => toast.success("Entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <InlineTable
      title="Teilnehmer*innen"
      rows={listQuery.data ?? []}
      rowKey={(a) => a.id}
      editing={editing}
      onDelete={(a) => remove.mutate(a.id)}
      columns={[{ header: "Mitglied", cell: (a) => a.member.name }]}
      renderAdd={() => (
        <div className="stack">
          <Select
            value={memberId}
            onChange={(v) => setMemberId(v)}
            options={memberOptions}
            placeholder="Mitglied wählen …"
          />
          <Button
            type="button"
            busy={create.isPending}
            onClick={() => {
              if (memberId === "") {
                toast.error("Bitte ein Mitglied wählen.");
                return;
              }
              create.mutate({ member_id: Number(memberId) });
            }}
          >
            Hinzufügen
          </Button>
        </div>
      )}
    />
  );
}
