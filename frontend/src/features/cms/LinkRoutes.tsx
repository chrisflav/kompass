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
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type LinkBrief = components["schemas"]["LinkBrief"];
type LinkOut = components["schemas"]["LinkOut"];
type LinkIn = components["schemas"]["LinkIn"];

const emptyLink: LinkIn = { title: "", description: "", url: "", visible: true };

function LinkFormFields({
  form,
  onChange,
  errors = {},
}: {
  form: LinkIn;
  onChange: (patch: Partial<LinkIn>) => void;
  errors?: Record<string, string[]>;
}) {
  return (
    <>
      <Field label="Titel">
        <input value={form.title} onChange={(e) => onChange({ title: e.target.value })} />
        {errors.title && <div className="field-error">{errors.title.join(" ")}</div>}
      </Field>
      <Field label="URL">
        <input value={form.url} onChange={(e) => onChange({ url: e.target.value })} required />
        {errors.url && <div className="field-error">{errors.url.join(" ")}</div>}
      </Field>
      <Field label="Beschreibung">
        <textarea
          value={form.description}
          onChange={(e) => onChange({ description: e.target.value })}
          rows={4}
        />
        {errors.description && <div className="field-error">{errors.description.join(" ")}</div>}
      </Field>
      <Field label="Sichtbar">
        <input
          type="checkbox"
          checked={form.visible}
          onChange={(e) => onChange({ visible: e.target.checked })}
        />
        {errors.visible && <div className="field-error">{errors.visible.join(" ")}</div>}
      </Field>
    </>
  );
}

export function LinksList() {
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState<LinkIn>(emptyLink);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const query = useApiQuery(["links"], () => unwrap(client.GET("/api/startpage/links")));
  const rows = query.data ?? [];

  const create = useApiMutation(
    (body: LinkIn) => unwrap(client.POST("/api/startpage/links", { body })),
    {
      invalidate: [["links"]],
      onSuccess: (created: LinkOut) => {
        toast.success("Link angelegt.");
        setCreating(false);
        navigate(`/app/cms/links/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  function openCreate() {
    setForm(emptyLink);
    setFieldErrors({});
    setCreating(true);
  }

  const config: ListViewConfig<LinkBrief> = useMemo(
    () => ({
      sort: {
        title: (l) => l.title,
        url: (l) => l.url,
        visible: (l) => l.visible,
      },
      defaultSort: { key: "title", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Links" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={openCreate}>Neuer Link</Button>}
      />
      {creating && (
        <Modal title="Neuer Link" onClose={() => setCreating(false)}>
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault();
              setFieldErrors({});
              create.mutate(form);
            }}
          >
            <LinkFormFields
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
      <QueryBoundary query={query} empty="Keine Links vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(l) => l.id}
            onRowClick={(l) => navigate(`/app/cms/links/${l.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (l) => l.title || "—", sortKey: "title" },
              { header: "URL", cell: (l) => l.url, sortKey: "url" },
              {
                header: "Sichtbar",
                cell: (l) =>
                  l.visible ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>,
                sortKey: "visible",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function LinkDetailPage() {
  const { id } = useParams();
  const linkId = Number(id);
  const query = useApiQuery(["links", linkId], () =>
    unwrap(
      client.GET("/api/startpage/links/{link_id}", { params: { path: { link_id: linkId } } }),
    ),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Links", to: "/app/cms/links" },
          { label: query.data?.title || "Link" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(link: LinkOut) => <LinkDetailBody link={link} />}
      </QueryBoundary>
    </div>
  );
}

function draftFromLink(link: LinkOut): LinkIn {
  return {
    title: link.title ?? "",
    description: link.description ?? "",
    url: link.url,
    visible: link.visible,
  };
}

function LinkDetailBody({ link }: { link: LinkOut }) {
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<LinkIn>(() => draftFromLink(link));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const set = (patch: Partial<LinkIn>) => setForm((prev) => ({ ...prev, ...patch }));

  const update = useApiMutation(
    (body: LinkIn) =>
      unwrap(
        client.PUT("/api/startpage/links/{link_id}", {
          params: { path: { link_id: link.id } },
          body,
        }),
      ),
    {
      invalidate: [["links"], ["links", link.id]],
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
        client.DELETE("/api/startpage/links/{link_id}", {
          params: { path: { link_id: link.id } },
        }),
      ),
    {
      invalidate: [["links"]],
      onSuccess: () => {
        toast.success("Link gelöscht.");
        navigate("/app/cms/links");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(draftFromLink(link));
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: link.title || "—",
      edit: <input value={form.title} onChange={(e) => set({ title: e.target.value })} />,
    },
    {
      label: "URL",
      field: "url",
      value: link.url,
      edit: <input value={form.url} onChange={(e) => set({ url: e.target.value })} required />,
    },
    {
      label: "Beschreibung",
      field: "description",
      value: link.description || "—",
      edit: (
        <textarea
          value={form.description}
          onChange={(e) => set({ description: e.target.value })}
          rows={4}
        />
      ),
    },
    {
      label: "Sichtbar",
      field: "visible",
      value: link.visible ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>,
      edit: (
        <input
          type="checkbox"
          checked={form.visible}
          onChange={(e) => set({ visible: e.target.checked })}
        />
      ),
    },
    {
      label: "Icon",
      value: link.icon ? (
        <img src={link.icon} alt="Icon" style={{ maxHeight: "3rem", maxWidth: "100%" }} />
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
        update.mutate(form);
      }}
    >
      <div className="detail-actions">
        {editing ? (
          <>
            <Button type="submit" busy={update.isPending}>
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
              busy={remove.isPending}
              onClick={async () => {
                if (
                  await confirm({
                    message: "Diesen Link wirklich löschen?",
                    danger: true,
                    confirmLabel: "Löschen",
                  })
                )
                  remove.mutate(undefined);
              }}
            >
              Löschen
            </Button>
            {/* Icon-Upload ist über POST /api/startpage/links/{id}/icon möglich, hier
                aber (Multipart) nicht umgesetzt — das Icon wird nur angezeigt. */}
          </>
        )}
      </div>
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
    </form>
  );
}
