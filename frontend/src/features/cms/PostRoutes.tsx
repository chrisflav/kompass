import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";

import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft } from "../../components/inlineDraft";
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
  Spinner,
  Tabs,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type PostBrief = components["schemas"]["PostBrief"];
type PostOut = components["schemas"]["PostOut"];
type PostIn = components["schemas"]["PostIn"];
type SectionBrief = components["schemas"]["SectionBrief"];
type GroupOut = components["schemas"]["GroupOut"];
type ImageOut = components["schemas"]["ImageOut"];
type MemberBrief = components["schemas"]["MemberBrief"];
type MemberOnPostBrief = components["schemas"]["MemberOnPostBrief"];
type MemberOnPostOut = components["schemas"]["MemberOnPostOut"];
type MemberOnPostIn = components["schemas"]["MemberOnPostIn"];

const emptyPost: PostIn = {
  title: "",
  urlname: "",
  date: null,
  website_text: "",
  detailed: false,
  section_id: null,
  group_ids: [],
};

/** Form shared by create and edit; loads section + group choices itself. */
function PostForm({
  initial,
  submitLabel,
  busy,
  onSubmit,
  onCancel,
  errors = {},
}: {
  initial: PostIn;
  submitLabel: string;
  busy: boolean;
  onSubmit: (values: PostIn) => void;
  onCancel: () => void;
  errors?: Record<string, string[]>;
}) {
  const [form, setForm] = useState<PostIn>(initial);
  const set = (patch: Partial<PostIn>) => setForm((prev) => ({ ...prev, ...patch }));

  const sectionsQuery = useApiQuery(["sections"], () =>
    unwrap(client.GET("/api/startpage/sections")),
  );
  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));

  if (sectionsQuery.isLoading || groupsQuery.isLoading) return <Spinner />;
  const sections = (sectionsQuery.data ?? []) as SectionBrief[];
  const groups = (groupsQuery.data ?? []) as GroupOut[];

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit(form);
      }}
    >
      <Field label="Titel">
        <input value={form.title} onChange={(e) => set({ title: e.target.value })} required />
        {errors.title && <div className="field-error">{errors.title.join(" ")}</div>}
      </Field>
      <Field label="URL" hint="URL-Kürzel des Beitrags">
        <input value={form.urlname} onChange={(e) => set({ urlname: e.target.value })} />
        {errors.urlname && <div className="field-error">{errors.urlname.join(" ")}</div>}
      </Field>
      <Field label="Datum">
        <input
          type="date"
          value={form.date ?? ""}
          onChange={(e) => set({ date: e.target.value || null })}
        />
        {errors.date && <div className="field-error">{errors.date.join(" ")}</div>}
      </Field>
      <Field label="Bereich">
        <Select
          value={form.section_id != null ? String(form.section_id) : ""}
          onChange={(v) => set({ section_id: v ? Number(v) : null })}
          options={sections.map((s) => ({ value: s.id, label: s.title }))}
          placeholder="— kein Bereich —"
          allowEmpty
          emptyLabel="— kein Bereich —"
        />
        {errors.section && <div className="field-error">{errors.section.join(" ")}</div>}
      </Field>
      <Field label="Webseitentext">
        <textarea
          value={form.website_text}
          onChange={(e) => set({ website_text: e.target.value })}
          rows={8}
        />
        {errors.website_text && (
          <div className="field-error">{errors.website_text.join(" ")}</div>
        )}
      </Field>
      <Field label="Detailliert">
        <input
          type="checkbox"
          checked={form.detailed}
          onChange={(e) => set({ detailed: e.target.checked })}
        />
        {errors.detailed && <div className="field-error">{errors.detailed.join(" ")}</div>}
      </Field>
      <Field label="Gruppen">
        <MultiSelect
          options={groups.map((g) => ({ value: g.id, label: g.name }))}
          selected={form.group_ids}
          onChange={(ids) => set({ group_ids: ids })}
          placeholder="Gruppe hinzufügen"
        />
        {errors.groups && <div className="field-error">{errors.groups.join(" ")}</div>}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={busy}>
          {submitLabel}
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}

export function PostsList() {
  const navigate = useNavigate();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const query = useApiQuery(["posts"], () => unwrap(client.GET("/api/startpage/posts")));
  const rows = query.data ?? [];

  const create = useApiMutation(
    (body: PostIn) => unwrap(client.POST("/api/startpage/posts", { body })),
    {
      invalidate: [["posts"]],
      onSuccess: (created: PostOut) => {
        toast.success("Beitrag angelegt.");
        setCreating(false);
        navigate(`/app/cms/posts/${created.id}`);
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  // Options for the section list_filter — derived from the loaded rows.
  const sectionOptions = useMemo(() => {
    const seen = new Map<number, string>();
    rows.forEach((p) => {
      if (p.section_id != null) seen.set(p.section_id, p.section_title ?? String(p.section_id));
    });
    return [...seen]
      .sort((a, b) => a[1].localeCompare(b[1], "de"))
      .map(([value, label]) => ({ value: String(value), label }));
  }, [rows]);

  const config: ListViewConfig<PostBrief> = useMemo(
    () => ({
      search: (p) => [p.title],
      filters: [
        {
          key: "section",
          label: "Bereich",
          options: sectionOptions,
          match: (p, v) => String(p.section_id ?? "") === v,
        },
      ],
      sort: {
        title: (p) => p.title,
        date: (p) => p.date,
        section: (p) => p.section_title,
        absolute_urlname: (p) => p.absolute_urlname,
      },
      defaultSort: { key: "date", dir: "desc" },
    }),
    [sectionOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Beiträge" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neuer Beitrag</Button>}
      />
      {creating && (
        <Modal
          title="Neuer Beitrag"
          onClose={() => {
            setFieldErrors({});
            setCreating(false);
          }}
        >
          <PostForm
            initial={emptyPost}
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
      <QueryBoundary query={query} empty="Keine Beiträge vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(p) => p.id}
            onRowClick={(p) => navigate(`/app/cms/posts/${p.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Titel", cell: (p) => p.title || "—", sortKey: "title" },
              { header: "Datum", cell: (p) => p.date ?? "—", sortKey: "date" },
              { header: "Bereich", cell: (p) => p.section_title || "—", sortKey: "section" },
              { header: "URL", cell: (p) => p.absolute_urlname, sortKey: "absolute_urlname" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

export function PostDetailPage() {
  const { id } = useParams();
  const postId = Number(id);
  const query = useApiQuery(["posts", postId], () =>
    unwrap(
      client.GET("/api/startpage/posts/{post_id}", { params: { path: { post_id: postId } } }),
    ),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Beiträge", to: "/app/cms/posts" },
          { label: query.data?.title || "Beitrag" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(post: PostOut) => <PostDetailBody post={post} />}
      </QueryBoundary>
    </div>
  );
}

function draftFromPost(post: PostOut): PostIn {
  return {
    title: post.title,
    urlname: post.urlname,
    date: post.date ?? null,
    website_text: post.website_text ?? "",
    detailed: post.detailed,
    section_id: post.section?.id ?? null,
    group_ids: post.groups.map((g) => g.id),
  };
}

function PostDetailBody({ post }: { post: PostOut }) {
  const [editing, setEditing] = useState(false);
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<PostIn>(() => draftFromPost(post));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const set = (patch: Partial<PostIn>) => setForm((prev) => ({ ...prev, ...patch }));

  const sectionsQuery = useApiQuery(["sections"], () =>
    unwrap(client.GET("/api/startpage/sections")),
  );
  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const sections = (sectionsQuery.data ?? []) as SectionBrief[];
  const groups = (groupsQuery.data ?? []) as GroupOut[];

  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const update = useApiMutation(
    (body: PostIn) =>
      unwrap(
        client.PUT("/api/startpage/posts/{post_id}", {
          params: { path: { post_id: post.id } },
          body,
        }),
      ),
    { invalidate: [["posts"], ["posts", post.id]] },
  );

  const remove = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/startpage/posts/{post_id}", {
          params: { path: { post_id: post.id } },
        }),
      ),
    {
      invalidate: [["posts"]],
      onSuccess: () => {
        toast.success("Beitrag gelöscht.");
        navigate("/app/cms/posts");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(draftFromPost(post));
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: post.title || "—",
      edit: (
        <input value={form.title} onChange={(e) => set({ title: e.target.value })} required />
      ),
    },
    {
      label: "URL",
      field: "urlname",
      value: post.urlname || "—",
      edit: <input value={form.urlname} onChange={(e) => set({ urlname: e.target.value })} />,
    },
    { label: "Absoluter Pfad", value: post.absolute_urlname },
    {
      label: "Datum",
      field: "date",
      value: post.date ?? "—",
      edit: (
        <input
          type="date"
          value={form.date ?? ""}
          onChange={(e) => set({ date: e.target.value || null })}
        />
      ),
    },
    {
      label: "Bereich",
      field: "section",
      value: post.section ? post.section.title : "—",
      edit: (
        <Select
          value={form.section_id != null ? String(form.section_id) : ""}
          onChange={(v) => set({ section_id: v ? Number(v) : null })}
          options={sections.map((s) => ({ value: s.id, label: s.title }))}
          placeholder="— kein Bereich —"
          allowEmpty
          emptyLabel="— kein Bereich —"
        />
      ),
    },
    {
      label: "Webseitentext",
      field: "website_text",
      value: post.website_text || "—",
      edit: (
        <textarea
          value={form.website_text}
          onChange={(e) => set({ website_text: e.target.value })}
          rows={8}
        />
      ),
    },
    {
      label: "Detailliert",
      field: "detailed",
      value: post.detailed ? <Badge tone="info">Ja</Badge> : <Badge>Nein</Badge>,
      edit: (
        <input
          type="checkbox"
          checked={form.detailed}
          onChange={(e) => set({ detailed: e.target.checked })}
        />
      ),
    },
    {
      label: "Gruppen",
      field: "groups",
      value: post.groups.length ? post.groups.map((g) => g.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={groups.map((g) => ({ value: g.id, label: g.name }))}
          selected={form.group_ids}
          onChange={(ids) => set({ group_ids: ids })}
          placeholder="Gruppe hinzufügen"
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
          await update.mutateAsync(form);
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
      <div className="detail-actions">
        {editing ? (
          <>
            <Button type="submit" busy={saving}>
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
                    message: "Diesen Beitrag wirklich löschen?",
                    danger: true,
                    confirmLabel: "Löschen",
                  })
                )
                  remove.mutate(undefined);
              }}
            >
              Löschen
            </Button>
          </>
        )}
      </div>
      <Tabs
        tabs={[
          {
            id: "beitrag",
            label: "Beitrag",
            content: <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "bilder",
            label: "Bilder",
            content: <PostImagesInline postId={post.id} editing={editing} registerFlush={getRegistrar("images")} />,
          },
          {
            id: "personen",
            label: "Personen",
            content: <PostPersonsInline postId={post.id} editing={editing} registerFlush={getRegistrar("persons")} />,
          },
        ]}
      />
    </form>
  );
}

/* --- inline: Bilder (Image) ---------------------------------------------- */

type PostImageData = { name: string; f: string | null; file: File | null };

function PostImagesInline({
  postId,
  editing,
  registerFlush,
}: {
  postId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const query = useApiQuery(["startpage", "images"], () =>
    unwrap(client.GET("/api/startpage/images")),
  );
  const serverRows = ((query.data ?? []) as ImageOut[])
    .filter((i) => i.post_id === postId)
    .map((i) => ({ id: i.id, data: { name: i.name, f: i.f ?? null, file: null } as PostImageData }));

  const createM = useApiMutation(
    (f: File) =>
      unwrap(
        client.POST("/api/startpage/images", {
          // Multipart upload: fields `post_id` and `f`. A custom serializer
          // builds the FormData because openapi-fetch would JSON-encode it.
          body: { post_id: postId, f: f as unknown as string },
          bodySerializer(body: { post_id: number; f: unknown }) {
            const fd = new FormData();
            fd.append("post_id", String(body.post_id));
            fd.append("f", body.f as File);
            return fd;
          },
        }),
      ),
    { invalidate: [["startpage", "images"]] },
  );
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/startpage/images/{image_id}", {
          params: { path: { image_id: id } },
        }),
      ),
    { invalidate: [["startpage", "images"]] },
  );

  const { rows, removeRow, addRow } = useInlineDraft<PostImageData>({
    serverRows,
    editing,
    create: (d) => (d.file ? createM.mutateAsync(d.file) : Promise.resolve()),
    update: () => Promise.resolve(),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });
  const [adding, setAdding] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  return (
    <>
      <InlineTable
        title="Bilder"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => {
          setFile(null);
          setAdding(true);
        }}
        addLabel="Bild"
        columns={[
          { header: "Name", cell: (row) => row.data.name || "—" },
          {
            header: "Datei",
            cell: (row) =>
              row.data.f ? (
                <a href={`${API_BASE}${row.data.f}`} target="_blank" rel="noreferrer">
                  Öffnen
                </a>
              ) : (
                <span className="muted small">(neu)</span>
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Bild hinzufügen" onClose={() => setAdding(false)} size="sm">
          <div className="stack">
            <input
              type="file"
              accept="image/*"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            <div className="row-actions">
              <Button
                type="button"
                disabled={!file}
                onClick={() => {
                  if (file) addRow({ name: file.name, f: null, file });
                  setAdding(false);
                }}
              >
                Hinzufügen
              </Button>
              <Button type="button" variant="ghost" onClick={() => setAdding(false)}>
                Abbrechen
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}

/* --- inline: Personen (MemberOnPost) ------------------------------------- */

type MopData = {
  member_ids: number[];
  member_names: string[];
  description: string;
  tag: string;
};

const emptyMop: MopData = { member_ids: [], member_names: [], description: "", tag: "" };

function PostPersonsInline({
  postId,
  editing,
  registerFlush,
}: {
  postId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const briefsQuery = useApiQuery(["member-on-posts"], () =>
    unwrap(client.GET("/api/startpage/member-on-posts")),
  );
  const briefs = ((briefsQuery.data ?? []) as MemberOnPostBrief[]).filter(
    (b) => b.post_id === postId,
  );

  // The list endpoint returns only briefs (id/post_id/tag); fetch each row's
  // detail to display its members and description.
  const detailQueries = useQueries({
    queries: briefs.map((b) => ({
      queryKey: ["member-on-posts", b.id],
      queryFn: () =>
        unwrap(
          client.GET("/api/startpage/member-on-posts/{mop_id}", {
            params: { path: { mop_id: b.id } },
          }),
        ),
    })),
  });
  const persons = detailQueries
    .map((q) => q.data as MemberOnPostOut | undefined)
    .filter((d): d is MemberOnPostOut => Boolean(d));

  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const members = (membersQuery.data ?? []) as MemberBrief[];
  const namesFor = (ids: number[]) =>
    ids.map((id) => members.find((m) => m.id === id)?.name ?? "");

  const createM = useApiMutation(
    (body: MemberOnPostIn) => unwrap(client.POST("/api/startpage/member-on-posts", { body })),
    { invalidate: [["member-on-posts"]] },
  );
  const updateM = useApiMutation(
    (vars: { id: number; body: MemberOnPostIn }) =>
      unwrap(
        client.PUT("/api/startpage/member-on-posts/{mop_id}", {
          params: { path: { mop_id: vars.id } },
          body: vars.body,
        }),
      ),
    { invalidate: [["member-on-posts"]] },
  );
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/startpage/member-on-posts/{mop_id}", {
          params: { path: { mop_id: id } },
        }),
      ),
    { invalidate: [["member-on-posts"]] },
  );

  const serverRows = persons.map((p) => ({
    id: p.id,
    data: {
      member_ids: p.members.map((m) => m.id),
      member_names: p.members.map((m) => m.name),
      description: p.description ?? "",
      tag: p.tag ?? "",
    } as MopData,
  }));

  const body = (d: MopData): MemberOnPostIn => ({
    post_id: postId,
    member_ids: d.member_ids,
    description: d.description,
    tag: d.tag,
  });
  const { rows, setRow, removeRow, addRow } = useInlineDraft<MopData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(body(d)),
    update: (id, d) => updateM.mutateAsync({ id, body: body(d) }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });

  const [adding, setAdding] = useState<MopData | null>(null);

  const memberSelect = (value: MopData, onChange: (next: MopData) => void) => (
    <MultiSelect
      options={members.map((m) => ({ value: m.id, label: m.name }))}
      selected={value.member_ids}
      onChange={(ids) => onChange({ ...value, member_ids: ids, member_names: namesFor(ids) })}
      placeholder="Teilnehmende hinzufügen"
    />
  );

  return (
    <>
      <InlineTable
        title="Personen"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ ...emptyMop })}
        addLabel="Person"
        columns={[
          {
            header: "Teilnehmende",
            cell: (row) =>
              editing ? (
                memberSelect(row.data, (next) => setRow(row, next))
              ) : (
                row.data.member_names.join(", ") || "—"
              ),
          },
          {
            header: "Beschreibung",
            cell: (row) =>
              editing ? (
                <input
                  value={row.data.description}
                  onChange={(e) => setRow(row, { ...row.data, description: e.target.value })}
                />
              ) : (
                row.data.description || "—"
              ),
          },
          {
            header: "Tag",
            cell: (row) =>
              editing ? (
                <input
                  value={row.data.tag}
                  maxLength={20}
                  onChange={(e) => setRow(row, { ...row.data, tag: e.target.value })}
                />
              ) : (
                row.data.tag || "—"
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Person hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Teilnehmende">{memberSelect(adding, setAdding)}</Field>
            <Field label="Beschreibung">
              <input
                value={adding.description}
                onChange={(e) => setAdding({ ...adding, description: e.target.value })}
              />
            </Field>
            <Field label="Tag" hint="Kurzbezeichnung (max. 20 Zeichen)">
              <input
                value={adding.tag}
                maxLength={20}
                onChange={(e) => setAdding({ ...adding, tag: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={adding.member_ids.length === 0}
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
