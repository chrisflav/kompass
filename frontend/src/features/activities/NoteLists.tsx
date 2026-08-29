import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useFlushRegistry } from "../../components/inlineDraft";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  DownloadButton,
  EditableDetail,
  Field,
  Menu,
  Modal,
  PageHeader,
  QueryBoundary,
  Tabs,
  useToast,
  type DetailRow,
} from "../../components/ui";
import { ParticipantsInline } from "./_controls";
import type { components } from "../../api/schema";

type MemberNoteListBrief = components["schemas"]["MemberNoteListBrief"];
type MemberNoteListOut = components["schemas"]["MemberNoteListOut"];
type MemberNoteListCreate = components["schemas"]["MemberNoteListCreate"];
type MemberNoteListUpdate = components["schemas"]["MemberNoteListUpdate"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

/* --- list ----------------------------------------------------------------
 * Admin MemberNoteListAdmin: list_display (title, date), ordering (-date). The
 * declared search_fields=('name',) is a bug (the field is `title`); we search
 * the effective field, title. */

export function NoteListsList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["note-lists"], () =>
    unwrap(client.GET("/api/members/note-lists")),
  );
  const rows = query.data ?? [];

  const config: ListViewConfig<MemberNoteListBrief> = useMemo(
    () => ({
      search: (n) => [n.title],
      sort: {
        title: (n) => n.title,
        date: (n) => n.date,
      },
      defaultSort: { key: "date", dir: "desc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Notizlisten" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neue Notizliste</Button>}
      />
      {creating && (
        <Modal title="Neue Notizliste" onClose={() => setCreating(false)}>
          <NoteListCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Notizlisten sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(n) => n.id}
            onRowClick={(n) => navigate(`/app/notelists/${n.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (n) => n.title || "—", sortKey: "title" },
              { header: "Datum", cell: (n) => formatDate(n.date), sortKey: "date" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function NoteListCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [title, setTitle] = useState("");
  const [date, setDate] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    (body: MemberNoteListCreate) => unwrap(client.POST("/api/members/note-lists", { body })),
    {
      invalidate: [["note-lists"]],
      onSuccess: (created: MemberNoteListOut) => {
        toast.success("Notizliste angelegt.");
        onDone();
        navigate(`/app/notelists/${created.id}`);
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
        mutation.mutate({ title, date: date || null });
      }}
    >
      <Field label="Titel">
        <input value={title} onChange={(e) => setTitle(e.target.value)} required />
        {fieldErrors.title && <div className="field-error">{fieldErrors.title.join(" ")}</div>}
      </Field>
      <Field label="Datum">
        <input type="date" value={date} onChange={(e) => setDate(e.target.value)} />
        {fieldErrors.date && <div className="field-error">{fieldErrors.date.join(" ")}</div>}
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

/* --- detail + edit ------------------------------------------------------- */

export function NoteListDetailPage() {
  const { id } = useParams();
  const notelistId = Number(id);
  const query = useApiQuery(["note-lists", notelistId], () =>
    unwrap(
      client.GET("/api/members/note-lists/{notelist_id}", {
        params: { path: { notelist_id: notelistId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(list: MemberNoteListOut) => <NoteListDetailBody list={list} />}
    </QueryBoundary>
  );
}

function NoteListDetailBody({ list }: { list: MemberNoteListOut }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => ({
    title: list.title ?? "",
    date: list.date ?? "",
  }));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: MemberNoteListUpdate) =>
      unwrap(
        client.PATCH("/api/members/note-lists/{notelist_id}", {
          params: { path: { notelist_id: list.id } },
          body,
        }),
      ),
    { invalidate: [["note-lists"], ["note-lists", list.id]] },
  );

  function startEditing() {
    setForm({ title: list.title ?? "", date: list.date ?? "" });
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: list.title || "—",
      edit: (
        <input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} />
      ),
    },
    {
      label: "Datum",
      field: "date",
      value: formatDate(list.date),
      edit: (
        <input
          type="date"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
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
          await mutation.mutateAsync({ title: form.title, date: form.date || null });
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
          { label: "Notizlisten", to: "/app/notelists" },
          { label: list.title || "Notizliste" },
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
              <Menu label="Dokumente">
                <DownloadButton
                  path={`/api/members/documents/note-lists/${list.id}/summary`}
                  method="POST"
                  filename={`Notizliste_${list.id}.pdf`}
                >
                  Zusammenfassung (pdf)
                </DownloadButton>
              </Menu>
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
            id: "mitglieder",
            label: "Teilnehmende",
            content: (
              <ParticipantsInline
                title="Teilnehmende"
                editing={editing}
                queryKey={["note-lists", list.id, "participants"]}
                listFn={() =>
                  unwrap(
                    client.GET("/api/members/note-lists/{notelist_id}/participants", {
                      params: { path: { notelist_id: list.id } },
                    }),
                  )
                }
                createFn={(body) =>
                  unwrap(
                    client.POST("/api/members/note-lists/{notelist_id}/participants", {
                      params: { path: { notelist_id: list.id } },
                      body,
                    }),
                  )
                }
                invalidate={[
                  ["note-lists", list.id, "participants"],
                  ["note-lists", list.id],
                ]}
                registerFlush={getRegistrar("participants")}
              />
            ),
          },
        ]}
      />
    </form>
  );
}
