import { useMemo, useState } from "react";
import { Route, useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  DownloadButton,
  EditableDetail,
  Modal,
  PageHeader,
  QueryBoundary,
  Tabs,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";
import {
  EVENTART,
  GRUPPE,
  KATEGORIE,
  KLASSIFIZIERUNG,
  KONDITION,
  SAISON,
  Select,
  TECHNIK,
  TerminForm,
  emptyTermin,
  type TerminFormValues,
} from "./TerminForm";

type TerminBrief = components["schemas"]["TerminBrief"];
type TerminOut = components["schemas"]["TerminOut"];

/* --- list ---------------------------------------------------------------- */

function TermineList() {
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const query = useApiQuery(["termine"], () =>
    unwrap(client.GET("/api/ludwigsburgalpin/termine")),
  );
  const rows = query.data ?? [];

  const create = useApiMutation(
    (body: TerminFormValues) =>
      unwrap(client.POST("/api/ludwigsburgalpin/termine", { body })),
    {
      invalidate: [["termine"]],
      onSuccess: (created: TerminOut) => {
        toast.success("Termin angelegt.");
        setCreating(false);
        navigate(`/app/events/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  // Options for the group list_filter — derived from the loaded rows (each row
  // carries both the raw code `group` and the labelled `group_display`).
  const groupOptions = useMemo(() => {
    const seen = new Map<string, string>();
    rows.forEach((t) => seen.set(t.group, t.group_display));
    return [...seen].sort((a, b) => a[1].localeCompare(b[1], "de")).map(([value, label]) => ({
      value,
      label,
    }));
  }, [rows]);

  const config: ListViewConfig<TerminBrief> = useMemo(
    () => ({
      filters: [
        {
          key: "group",
          label: "Gruppe",
          options: groupOptions,
          match: (t, v) => t.group === v,
        },
      ],
      sort: {
        title: (t) => t.title,
        start_date: (t) => t.start_date,
        end_date: (t) => t.end_date,
        group: (t) => t.group_display,
        category: (t) => t.category_display,
        responsible: (t) => t.responsible,
      },
      defaultSort: { key: "start_date", dir: "asc" },
    }),
    [groupOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Termine" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          <>
            <DownloadButton
              path="/api/ludwigsburgalpin/documents/termine/overview"
              method="POST"
              body={{ termin_ids: null }}
              filename="Termine_Uebersicht.xlsx"
            >
              Übersicht (Excel)
            </DownloadButton>
            <Button onClick={() => setCreating(true)}>Neuer Termin</Button>
          </>
        }
      />
      {creating && (
        <Modal
          title="Neuer Termin"
          onClose={() => {
            setFieldErrors({});
            setCreating(false);
          }}
        >
          <TerminForm
            initial={emptyTermin}
            submitLabel="Anlegen"
            busy={create.isPending}
            errors={fieldErrors}
            onSubmit={(values) => {
              setFieldErrors({});
              create.mutate(values);
            }}
            onCancel={() => {
              setFieldErrors({});
              setCreating(false);
            }}
          />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Termine vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(t) => t.id}
            onRowClick={(t) => navigate(`/app/events/${t.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (t) => t.title, sortKey: "title" },
              { header: "Von", cell: (t) => t.start_date, sortKey: "start_date" },
              { header: "Bis", cell: (t) => t.end_date, sortKey: "end_date" },
              { header: "Gruppe", cell: (t) => t.group_display, sortKey: "group" },
              { header: "Kategorie", cell: (t) => t.category_display, sortKey: "category" },
              { header: "Organisator", cell: (t) => t.responsible || "—", sortKey: "responsible" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail + edit + delete --------------------------------------------- */

function TerminDetailPage() {
  const { id } = useParams();
  const terminId = Number(id);
  const query = useApiQuery(["termine", terminId], () =>
    unwrap(
      client.GET("/api/ludwigsburgalpin/termine/{termin_id}", {
        params: { path: { termin_id: terminId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Termine", to: "/app/events" },
    { label: query.data?.title ?? "Termin" },
  ];

  return (
    <QueryBoundary query={query}>
      {(termin: TerminOut) => <TerminDetailBody termin={termin} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

/** Build an edit-friendly draft (numbers kept as numbers) from a Termin. */
function draftFromTermin(termin: TerminOut): TerminFormValues {
  return {
    title: termin.title,
    subtitle: termin.subtitle ?? "",
    start_date: termin.start_date,
    end_date: termin.end_date,
    group: termin.group,
    responsible: termin.responsible,
    phone: termin.phone ?? "",
    email: termin.email,
    category: termin.category,
    condition: termin.condition,
    technik: termin.technik,
    saison: termin.saison,
    eventart: termin.eventart,
    klassifizierung: termin.klassifizierung,
    equipment: termin.equipment ?? "",
    voraussetzungen: termin.voraussetzungen ?? "",
    description: termin.description ?? "",
    max_participants: termin.max_participants,
    anforderung_hoehe: termin.anforderung_hoehe ?? 0,
    anforderung_strecke: termin.anforderung_strecke ?? 0,
    anforderung_dauer: termin.anforderung_dauer ?? 0,
  };
}

function TerminDetailBody({ termin, crumbs }: { termin: TerminOut; crumbs: Crumb[] }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<TerminFormValues>(() => draftFromTermin(termin));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const set = <K extends keyof TerminFormValues>(key: K, value: TerminFormValues[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const update = useApiMutation(
    (body: TerminFormValues) =>
      unwrap(
        client.PATCH("/api/ludwigsburgalpin/termine/{termin_id}", {
          params: { path: { termin_id: termin.id } },
          body,
        }),
      ),
    {
      invalidate: [["termine"], ["termine", termin.id]],
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
        client.DELETE("/api/ludwigsburgalpin/termine/{termin_id}", {
          params: { path: { termin_id: termin.id } },
        }),
      ),
    {
      invalidate: [["termine"]],
      onSuccess: () => {
        toast.success("Termin gelöscht.");
        navigate("/app/events");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    // Re-sync the draft from the (possibly refetched) termin before editing.
    setForm(draftFromTermin(termin));
    setFieldErrors({});
    setEditing(true);
  }

  const allgemeinRows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: termin.title,
      edit: <input value={form.title} onChange={(e) => set("title", e.target.value)} required />,
    },
    {
      label: "Untertitel",
      field: "subtitle",
      value: termin.subtitle || "—",
      edit: <input value={form.subtitle} onChange={(e) => set("subtitle", e.target.value)} />,
    },
    {
      label: "Von",
      field: "start_date",
      value: termin.start_date,
      edit: (
        <input
          type="date"
          value={form.start_date}
          onChange={(e) => set("start_date", e.target.value)}
          required
        />
      ),
    },
    {
      label: "Bis",
      field: "end_date",
      value: termin.end_date,
      edit: (
        <input
          type="date"
          value={form.end_date}
          onChange={(e) => set("end_date", e.target.value)}
          required
        />
      ),
    },
    {
      label: "Gruppe",
      field: "group",
      value: termin.group_display,
      edit: <Select value={form.group} options={GRUPPE} onChange={(v) => set("group", v)} />,
    },
    {
      label: "Organisator",
      field: "responsible",
      value: termin.responsible,
      edit: (
        <input
          value={form.responsible}
          onChange={(e) => set("responsible", e.target.value)}
          required
        />
      ),
    },
    {
      label: "Telefonnummer",
      field: "phone",
      value: termin.phone || "—",
      edit: <input value={form.phone} onChange={(e) => set("phone", e.target.value)} />,
    },
    {
      label: "E-Mail",
      field: "email",
      value: termin.email,
      edit: (
        <input
          type="email"
          value={form.email}
          onChange={(e) => set("email", e.target.value)}
          required
        />
      ),
    },
    {
      label: "Kategorie",
      field: "category",
      value: termin.category_display,
      edit: (
        <Select value={form.category} options={KATEGORIE} onChange={(v) => set("category", v)} />
      ),
    },
  ];

  const anforderungenRows: DetailRow[] = [
    {
      label: "Kondition",
      field: "condition",
      value: termin.condition_display,
      edit: (
        <Select value={form.condition} options={KONDITION} onChange={(v) => set("condition", v)} />
      ),
    },
    {
      label: "Technik",
      field: "technik",
      value: termin.technik_display,
      edit: <Select value={form.technik} options={TECHNIK} onChange={(v) => set("technik", v)} />,
    },
    {
      label: "Saison",
      field: "saison",
      value: termin.saison_display,
      edit: <Select value={form.saison} options={SAISON} onChange={(v) => set("saison", v)} />,
    },
    {
      label: "Eventart",
      field: "eventart",
      value: termin.eventart_display,
      edit: (
        <Select value={form.eventart} options={EVENTART} onChange={(v) => set("eventart", v)} />
      ),
    },
    {
      label: "Klassifizierung",
      field: "klassifizierung",
      value: termin.klassifizierung_display,
      edit: (
        <Select
          value={form.klassifizierung}
          options={KLASSIFIZIERUNG}
          onChange={(v) => set("klassifizierung", v)}
        />
      ),
    },
    {
      label: "Max. Teilnehmerzahl",
      field: "max_participants",
      value: termin.max_participants,
      edit: (
        <input
          type="number"
          value={form.max_participants}
          onChange={(e) => set("max_participants", Number(e.target.value))}
        />
      ),
    },
    {
      label: "Höhenmeter in Meter",
      field: "anforderung_hoehe",
      value: termin.anforderung_hoehe ?? "—",
      edit: (
        <input
          type="number"
          value={form.anforderung_hoehe}
          onChange={(e) => set("anforderung_hoehe", Number(e.target.value))}
        />
      ),
    },
    {
      label: "Strecke in Kilometer",
      field: "anforderung_strecke",
      value: termin.anforderung_strecke ?? "—",
      edit: (
        <input
          type="number"
          value={form.anforderung_strecke}
          onChange={(e) => set("anforderung_strecke", Number(e.target.value))}
        />
      ),
    },
    {
      label: "Etappendauer in Stunden",
      field: "anforderung_dauer",
      value: termin.anforderung_dauer ?? "—",
      edit: (
        <input
          type="number"
          value={form.anforderung_dauer}
          onChange={(e) => set("anforderung_dauer", Number(e.target.value))}
        />
      ),
    },
  ];

  const beschreibungRows: DetailRow[] = [
    {
      label: "Ausrüstung",
      field: "equipment",
      value: termin.equipment || "—",
      edit: (
        <textarea
          value={form.equipment}
          onChange={(e) => set("equipment", e.target.value)}
          rows={2}
        />
      ),
    },
    {
      label: "Voraussetzungen",
      field: "voraussetzungen",
      value: termin.voraussetzungen || "—",
      edit: (
        <textarea
          value={form.voraussetzungen}
          onChange={(e) => set("voraussetzungen", e.target.value)}
          rows={2}
        />
      ),
    },
    {
      label: "Beschreibung",
      field: "description",
      value: termin.description || "—",
      edit: (
        <textarea
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          rows={4}
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        update.mutate(form);
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
              <Button type="submit" busy={update.isPending}>
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
                      message: "Diesen Termin wirklich löschen?",
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
      <Tabs
        tabs={[
          {
            id: "allgemein",
            label: "Allgemein",
            content: (
              <EditableDetail rows={allgemeinRows} editing={editing} errors={fieldErrors} />
            ),
          },
          {
            id: "anforderungen",
            label: "Anforderungen",
            content: (
              <EditableDetail rows={anforderungenRows} editing={editing} errors={fieldErrors} />
            ),
          },
          {
            id: "beschreibung",
            label: "Beschreibung",
            content: (
              <EditableDetail rows={beschreibungRows} editing={editing} errors={fieldErrors} />
            ),
          },
        ]}
      />
    </form>
  );
}

/* --- route fragment ------------------------------------------------------ */

export const eventsRoutes = (
  <>
    <Route path="events" element={<TermineList />} />
    <Route path="events/:id" element={<TerminDetailPage />} />
  </>
);
