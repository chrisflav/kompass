import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type SectionBrief = components["schemas"]["SectionBrief"];
type SectionOut = components["schemas"]["SectionOut"];
type SectionIn = components["schemas"]["SectionIn"];

const emptySection: SectionIn = {
  title: "",
  urlname: "",
  website_text: "",
  show_in_navigation: true,
};

function SectionFormFields({
  form,
  onChange,
  errors = {},
}: {
  form: SectionIn;
  onChange: (patch: Partial<SectionIn>) => void;
  errors?: Record<string, string[]>;
}) {
  return (
    <>
      <Field label="Titel">
        <input value={form.title} onChange={(e) => onChange({ title: e.target.value })} required />
        {errors.title && <div className="field-error">{errors.title.join(" ")}</div>}
      </Field>
      <Field label="URL" hint="URL-Kürzel des Bereichs">
        <input
          value={form.urlname}
          onChange={(e) => onChange({ urlname: e.target.value })}
          required
        />
        {errors.urlname && <div className="field-error">{errors.urlname.join(" ")}</div>}
      </Field>
      <Field label="Webseitentext">
        <textarea
          value={form.website_text}
          onChange={(e) => onChange({ website_text: e.target.value })}
          rows={8}
        />
        {errors.website_text && (
          <div className="field-error">{errors.website_text.join(" ")}</div>
        )}
      </Field>
      <Field label="In Navigation anzeigen">
        <input
          type="checkbox"
          checked={form.show_in_navigation}
          onChange={(e) => onChange({ show_in_navigation: e.target.checked })}
        />
        {errors.show_in_navigation && (
          <div className="field-error">{errors.show_in_navigation.join(" ")}</div>
        )}
      </Field>
    </>
  );
}

export function SectionsList() {
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<SectionIn>(emptySection);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const query = useApiQuery(["sections"], () => unwrap(client.GET("/api/startpage/sections")));
  const rows = query.data ?? [];

  const create = useApiMutation(
    (body: SectionIn) => unwrap(client.POST("/api/startpage/sections", { body })),
    {
      invalidate: [["sections"]],
      onSuccess: (created: SectionOut) => {
        toast.success("Bereich angelegt.");
        setCreating(false);
        navigate(`/app/cms/sections/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  function openCreate() {
    setForm(emptySection);
    setFieldErrors({});
    setCreating(true);
  }

  const config: ListViewConfig<SectionBrief> = useMemo(
    () => ({
      sort: {
        title: (s) => s.title,
        urlname: (s) => s.urlname,
        absolute_urlname: (s) => s.absolute_urlname,
        navigation: (s) => s.show_in_navigation,
      },
      defaultSort: { key: "title", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Bereiche" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={openCreate}>Neuer Bereich</Button>}
      />
      {creating && (
        <Modal title="Neuer Bereich" onClose={() => setCreating(false)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setFieldErrors({});
              create.mutate(form);
            }}
          >
            <SectionFormFields
              form={form}
              onChange={(patch) => setForm({ ...form, ...patch })}
              errors={fieldErrors}
            />
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
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Bereiche vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(s) => s.id}
            onRowClick={(s) => navigate(`/app/cms/sections/${s.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (s) => s.title, sortKey: "title" },
              { header: "URL-Kürzel", cell: (s) => s.urlname, sortKey: "urlname" },
              { header: "Absoluter Pfad", cell: (s) => s.absolute_urlname, sortKey: "absolute_urlname" },
              {
                header: "Navigation",
                cell: (s) =>
                  s.show_in_navigation ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>,
                sortKey: "navigation",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function SectionDetailPage() {
  const { id } = useParams();
  const sectionId = Number(id);
  const query = useApiQuery(["sections", sectionId], () =>
    unwrap(
      client.GET("/api/startpage/sections/{section_id}", {
        params: { path: { section_id: sectionId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Bereiche", to: "/app/cms/sections" },
    { label: query.data?.title ?? "Bereich" },
  ];

  return (
    <QueryBoundary query={query}>
      {(section: SectionOut) => <SectionDetailBody section={section} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function draftFromSection(section: SectionOut): SectionIn {
  return {
    title: section.title,
    urlname: section.urlname,
    website_text: section.website_text ?? "",
    show_in_navigation: section.show_in_navigation,
  };
}

function SectionDetailBody({ section, crumbs }: { section: SectionOut; crumbs: Crumb[] }) {
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<SectionIn>(() => draftFromSection(section));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const set = (patch: Partial<SectionIn>) => setForm((prev) => ({ ...prev, ...patch }));

  const update = useApiMutation(
    (body: SectionIn) =>
      unwrap(
        client.PUT("/api/startpage/sections/{section_id}", {
          params: { path: { section_id: section.id } },
          body,
        }),
      ),
    {
      invalidate: [["sections"], ["sections", section.id]],
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
        client.DELETE("/api/startpage/sections/{section_id}", {
          params: { path: { section_id: section.id } },
        }),
      ),
    {
      invalidate: [["sections"]],
      onSuccess: () => {
        toast.success("Bereich gelöscht.");
        navigate("/app/cms/sections");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(draftFromSection(section));
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: section.title,
      edit: (
        <input value={form.title} onChange={(e) => set({ title: e.target.value })} required />
      ),
    },
    {
      label: "URL",
      field: "urlname",
      value: section.urlname,
      edit: (
        <input value={form.urlname} onChange={(e) => set({ urlname: e.target.value })} required />
      ),
    },
    { label: "Absoluter Pfad", value: section.absolute_urlname },
    {
      label: "Webseitentext",
      field: "website_text",
      value: section.website_text || "—",
      edit: (
        <textarea
          value={form.website_text}
          onChange={(e) => set({ website_text: e.target.value })}
          rows={8}
        />
      ),
    },
    {
      label: "In Navigation anzeigen",
      field: "show_in_navigation",
      value: section.show_in_navigation ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>,
      edit: (
        <input
          type="checkbox"
          checked={form.show_in_navigation}
          onChange={(e) => set({ show_in_navigation: e.target.checked })}
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
                      message: "Diesen Bereich wirklich löschen?",
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
