import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";

import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { InlineTable } from "../../components/inline";
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

  const update = useApiMutation(
    (body: PostIn) =>
      unwrap(
        client.PUT("/api/startpage/posts/{post_id}", {
          params: { path: { post_id: post.id } },
          body,
        }),
      ),
    {
      invalidate: [["posts"], ["posts", post.id]],
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
            content: <PostImagesInline postId={post.id} editing={editing} />,
          },
          {
            id: "personen",
            label: "Personen",
            content: <PostPersonsInline postId={post.id} editing={editing} />,
          },
        ]}
      />
    </form>
  );
}

/* --- inline: Bilder (Image) ---------------------------------------------- */

function PostImagesInline({ postId, editing }: { postId: number; editing: boolean }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);

  const query = useApiQuery(["startpage", "images"], () =>
    unwrap(client.GET("/api/startpage/images")),
  );
  const images = ((query.data ?? []) as ImageOut[]).filter((i) => i.post_id === postId);

  const create = useApiMutation(
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
    {
      invalidate: [["startpage", "images"]],
      onSuccess: () => {
        toast.success("Bild hinzugefügt.");
        setFile(null);
        if (fileRef.current) fileRef.current.value = "";
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const remove = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/startpage/images/{image_id}", {
          params: { path: { image_id: id } },
        }),
      ),
    {
      invalidate: [["startpage", "images"]],
      onSuccess: () => toast.success("Bild entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <InlineTable<ImageOut>
      title="Bilder"
      rows={images}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => remove.mutate(r.id)}
      columns={[
        { header: "Name", cell: (r) => r.name },
        {
          header: "Datei",
          cell: (r) =>
            r.f ? (
              <a href={`${API_BASE}${r.f}`} target="_blank" rel="noreferrer">
                Öffnen
              </a>
            ) : (
              "—"
            ),
        },
      ]}
      renderAdd={() => (
        <div className="row-actions">
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <Button
            type="button"
            busy={create.isPending}
            disabled={!file}
            onClick={() => file && create.mutate(file)}
          >
            Hinzufügen
          </Button>
        </div>
      )}
    />
  );
}

/* --- inline: Personen (MemberOnPost) ------------------------------------- */

type MopDraft = { member_ids: number[]; description: string; tag: string };

const emptyMopDraft: MopDraft = { member_ids: [], description: "", tag: "" };

function PostPersonsInline({ postId, editing }: { postId: number; editing: boolean }) {
  const toast = useToast();

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

  const [draft, setDraft] = useState<MopDraft>(emptyMopDraft);
  const [editState, setEditState] = useState<(MopDraft & { id: number }) | null>(null);

  const create = useApiMutation(
    (body: MemberOnPostIn) => unwrap(client.POST("/api/startpage/member-on-posts", { body })),
    {
      invalidate: [["member-on-posts"]],
      onSuccess: () => {
        toast.success("Personen hinzugefügt.");
        setDraft(emptyMopDraft);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const update = useApiMutation(
    (vars: { id: number; body: MemberOnPostIn }) =>
      unwrap(
        client.PUT("/api/startpage/member-on-posts/{mop_id}", {
          params: { path: { mop_id: vars.id } },
          body: vars.body,
        }),
      ),
    {
      invalidate: [["member-on-posts"]],
      onSuccess: () => {
        toast.success("Gespeichert.");
        setEditState(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const remove = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/startpage/member-on-posts/{mop_id}", {
          params: { path: { mop_id: id } },
        }),
      ),
    {
      invalidate: [["member-on-posts"]],
      onSuccess: () => toast.success("Personen entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const memberSelect = (values: MopDraft, onChange: (next: MopDraft) => void) => (
    <MultiSelect
      options={members.map((m) => ({ value: m.id, label: m.name }))}
      selected={values.member_ids}
      onChange={(ids) => onChange({ ...values, member_ids: ids })}
      placeholder="Teilnehmende hinzufügen"
    />
  );

  const columns = [
    {
      header: "Teilnehmende",
      cell: (r: MemberOnPostOut) => r.members.map((m) => m.name).join(", ") || "—",
    },
    { header: "Beschreibung", cell: (r: MemberOnPostOut) => r.description || "—" },
    { header: "Tag", cell: (r: MemberOnPostOut) => r.tag || "—" },
    ...(editing
      ? [
          {
            header: "",
            cell: (r: MemberOnPostOut) => (
              <Button
                type="button"
                variant="ghost"
                onClick={() =>
                  setEditState({
                    id: r.id,
                    member_ids: r.members.map((m) => m.id),
                    description: r.description ?? "",
                    tag: r.tag ?? "",
                  })
                }
              >
                Bearbeiten
              </Button>
            ),
          },
        ]
      : []),
  ];

  return (
    <InlineTable<MemberOnPostOut>
      title="Personen"
      rows={persons}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => remove.mutate(r.id)}
      columns={columns}
      renderAdd={() =>
        editState ? (
          <div className="stack">
            <Field label="Teilnehmende">
              {memberSelect(editState, (next) => setEditState({ ...editState, ...next }))}
            </Field>
            <Field label="Beschreibung">
              <input
                value={editState.description}
                onChange={(e) => setEditState({ ...editState, description: e.target.value })}
              />
            </Field>
            <Field label="Tag" hint="Kurzbezeichnung (max. 20 Zeichen)">
              <input
                value={editState.tag}
                maxLength={20}
                onChange={(e) => setEditState({ ...editState, tag: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                busy={update.isPending}
                onClick={() =>
                  update.mutate({
                    id: editState.id,
                    body: {
                      post_id: postId,
                      member_ids: editState.member_ids,
                      description: editState.description,
                      tag: editState.tag,
                    },
                  })
                }
              >
                Speichern
              </Button>
              <Button type="button" variant="ghost" onClick={() => setEditState(null)}>
                Abbrechen
              </Button>
            </div>
          </div>
        ) : (
          <div className="stack">
            <Field label="Teilnehmende">
              {memberSelect(draft, setDraft)}
            </Field>
            <Field label="Beschreibung">
              <input
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </Field>
            <Field label="Tag" hint="Kurzbezeichnung (max. 20 Zeichen)">
              <input
                value={draft.tag}
                maxLength={20}
                onChange={(e) => setDraft({ ...draft, tag: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                busy={create.isPending}
                disabled={draft.member_ids.length === 0}
                onClick={() =>
                  create.mutate({
                    post_id: postId,
                    member_ids: draft.member_ids,
                    description: draft.description,
                    tag: draft.tag,
                  })
                }
              >
                Hinzufügen
              </Button>
            </div>
          </div>
        )
      }
    />
  );
}
