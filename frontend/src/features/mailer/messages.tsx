import { keepPreviousData, useQueryClient } from "@tanstack/react-query";
import { Fragment, type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { API_BASE } from "../../api/client";
import { usePermissions } from "../../api/me";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import {
  queryKeys,
  useEmailAddresses,
  useExcursions,
  useGroups,
  useMembers,
} from "../../api/queries";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft } from "../../components/inlineDraft";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  EmptyState,
  Field,
  formatDate,
  Menu,
  Modal,
  PageHeader,
  QueryBoundary,
  Tabs,
  type Crumb,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";
import { MultiSelect, SingleSelect, type Option, withSelected } from "./selects";

type MessageBrief = components["schemas"]["MessageBrief"];
type MessageOut = components["schemas"]["MessageOut"];
type MessageIn = components["schemas"]["MessageIn"];

/* --- list ---------------------------------------------------------------- */

/** Remembers for the session that the user asked for the older messages too. */
const ALL_MESSAGES_KEY = "mailer:messages:all";

function loadShowAll(): boolean {
  try {
    return sessionStorage.getItem(ALL_MESSAGES_KEY) === "1";
  } catch {
    return false;
  }
}

function saveShowAll() {
  try {
    sessionStorage.setItem(ALL_MESSAGES_KEY, "1");
  } catch {
    /* storage unavailable — the choice then only lasts for this page */
  }
}

/** The local date twelve months ago as `YYYY-MM-DD`, the start of the default window. */
function twelveMonthsAgo(): string {
  const d = new Date();
  d.setFullYear(d.getFullYear() - 1);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function MessagesList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  // The list loads the past 12 months (and every draft) unless the user asks
  // for the older messages, so search, filter and sort stay instant on the rows
  // loaded. While the older ones load, the recent rows stay on screen.
  const [showAll, setShowAll] = useState(loadShowAll);
  const since = useMemo(() => (showAll ? null : twelveMonthsAgo()), [showAll]);
  const query = useApiQuery(
    queryKeys.messageList(since),
    () =>
      unwrap(
        client.GET("/api/mailer/messages", {
          params: { query: since === null ? {} : { since } },
        }),
      ),
    { placeholderData: keepPreviousData },
  );
  const rows = query.data ?? [];
  const toast = useToast();
  const loadOlder = () => setShowAll(true);
  // Remember the choice only once the older messages are there; if loading
  // them fails, fall back to the 12-month view so the button comes back.
  const olderLoaded = showAll && query.isSuccess && !query.isPlaceholderData;
  const olderFailed = showAll && query.isError;
  useEffect(() => {
    if (olderLoaded) saveShowAll();
  }, [olderLoaded]);
  useEffect(() => {
    if (!olderFailed) return;
    setShowAll(false);
    toast.error("Ältere Nachrichten konnten nicht geladen werden.");
  }, [olderFailed, toast]);

  const config: ListViewConfig<MessageBrief> = useMemo(
    () => ({
      // Admin search_fields = subject.
      search: (m) => [m.subject],
      filters: [
        // Admin list_filter = sent.
        {
          key: "sent",
          label: "Status",
          options: [
            { value: "yes", label: "Gesendet" },
            { value: "no", label: "Entwurf" },
          ],
          match: (m, v) => (v === "yes") === Boolean(m.sent),
        },
      ],
      sort: {
        subject: (m) => m.subject,
        sent: (m) => m.sent,
        created: (m) => m.created_at,
        id: (m) => m.id,
      },
      // Admin ordering = -id (newest first).
      defaultSort: { key: "id", dir: "desc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Nachrichten" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("mailer.add_global_message") && (
            <Button onClick={() => navigate("/kompass/mailer/messages/new")}>
              Neue Nachricht
            </Button>
          )
        }
      />
      <ListToolbar view={view} />
      {(!showAll || query.isPlaceholderData) && (
        <div className="list-window">
          <p className="muted small">Zeigt Nachrichten der letzten 12 Monate und alle Entwürfe.</p>
          <Button variant="ghost" busy={showAll} onClick={loadOlder}>
            Ältere Nachrichten laden
          </Button>
        </div>
      )}
      <QueryBoundary query={query} empty="Keine Nachrichten vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/kompass/mailer/messages/${m.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              {
                header: "Betreff",
                cell: (m) => m.subject || "(ohne Betreff)",
                sortKey: "subject",
              },
              { header: "Empfänger", cell: (m) => m.recipients },
              { header: "Erstellt", cell: (m) => formatDate(m.created_at), sortKey: "created" },
              {
                header: "Status",
                cell: (m) =>
                  m.sent ? (
                    <Badge tone="success">Gesendet</Badge>
                  ) : (
                    <Badge tone="warning">Entwurf</Badge>
                  ),
                sortKey: "sent",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- compose ------------------------------------------------------------- */

/**
 * New message, composed on a page of its own in the layout of the detail page
 * (Details + Anhänge tabs, in edit mode from the start), so the text gets the
 * full width and attachments can be added before the message exists. Offers
 * "Senden" (create, upload the attachments, then send), "Als Entwurf speichern"
 * (create and upload only) and "Abbrechen" (confirms discarding any input).
 */
export function MessageComposePage() {
  const { can, loaded } = usePermissions();
  if (!loaded) return null;
  if (!can("mailer.add_global_message")) {
    return (
      <div>
        <PageHeader breadcrumbs={COMPOSE_CRUMBS} />
        <EmptyState>Du darfst keine Nachrichten verfassen.</EmptyState>
      </div>
    );
  }
  return <MessageComposer />;
}

const COMPOSE_CRUMBS: Crumb[] = [
  { label: "Nachrichten", to: "/kompass/mailer/messages" },
  { label: "Neue Nachricht" },
];

function MessageComposer() {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<MessageFormState>(() => emptyMessage());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [busy, setBusy] = useState(false);
  const [staged, setStaged] = useState(0);
  const { getRegistrar, runFlushes } = useFlushRegistry();
  // Save creates the message first and stores its id here; the staged
  // attachments are then uploaded to it.
  const createdId = useRef<number | null>(null);

  const create = useApiMutation(
    (body: MessageIn) => unwrap(client.POST("/api/mailer/messages", { body })),
    { invalidate: [queryKeys.messages()] },
  );
  const submit = useApiMutation(
    (id: number) =>
      unwrap(
        client.POST("/api/mailer/messages/{message_id}/submit", {
          params: { path: { message_id: id } },
        }),
      ),
    { invalidate: [queryKeys.messages()] },
  );

  // The read-only rows (status, author, …) only exist once the message does.
  const rows = useMessageRows(null, form, setForm, true).filter((r) => r.edit !== undefined);

  const dirty =
    form.subject.trim() !== "" ||
    form.content.trim() !== "" ||
    form.to_groups.length > 0 ||
    form.to_members.length > 0 ||
    form.to_freizeit !== null ||
    form.reply_to.length > 0 ||
    form.reply_to_email_address.length > 0 ||
    staged > 0;

  // Closing or reloading the tab asks first while there is unsaved input. (The
  // app runs on a <BrowserRouter>, where react-router's useBlocker is not
  // available, so in-app navigation away is not intercepted.)
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  async function requestCancel() {
    if (dirty && !(await confirm("Änderungen verwerfen?"))) return;
    navigate("/kompass/mailer/messages");
  }

  async function save(send: boolean) {
    if (!form.subject.trim() || !form.content.trim()) {
      toast.error("Betreff und Inhalt sind erforderlich.");
      return;
    }
    if (send && !(await confirm("Nachricht jetzt an alle Empfänger versenden?"))) return;
    setFieldErrors({});
    setBusy(true);
    try {
      const msg = await create.mutateAsync(form);
      createdId.current = msg.id;
      await runFlushes();
      if (send) await submit.mutateAsync(msg.id);
      toast.success(send ? "Nachricht versendet." : "Als Entwurf gespeichert.");
      navigate(`/kompass/mailer/messages/${msg.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Speichern fehlgeschlagen.");
      if (createdId.current === null) {
        if (err instanceof ApiError) setFieldErrors(err.fieldErrors);
        setBusy(false);
      } else {
        // The draft exists by now: carry on from its own page, so a retry edits
        // or sends it rather than creating a second one.
        navigate(`/kompass/mailer/messages/${createdId.current}`);
      }
    }
  }

  return (
    <div>
      <PageHeader
        breadcrumbs={COMPOSE_CRUMBS}
        actions={
          <>
            <Button type="button" variant="ghost" disabled={busy} onClick={requestCancel}>
              Abbrechen
            </Button>
            <Button type="button" variant="ghost" busy={busy} onClick={() => save(false)}>
              Als Entwurf speichern
            </Button>
            <Button type="button" busy={busy} onClick={() => save(true)}>
              Senden
            </Button>
          </>
        }
      />
      <Tabs
        tabs={[
          {
            id: "details",
            label: "Details",
            content: <EditableDetail rows={rows} editing errors={fieldErrors} />,
          },
          {
            id: "anhaenge",
            label: "Anhänge",
            content: (
              <Attachments
                message={createdId}
                editing
                registerFlush={getRegistrar("attachments")}
                onStagedChange={setStaged}
              />
            ),
          },
        ]}
      />
    </div>
  );
}

/* --- shared fields ------------------------------------------------------- */

/**
 * The message's fields as detail rows, for the detail page and the compose
 * page alike. The read-only values are the names `message` itself carries (none
 * while composing); the full lists only back the edit pickers, so they load
 * once editing starts.
 */
function useMessageRows(
  message: MessageOut | null,
  form: MessageFormState,
  setForm: (next: MessageFormState) => void,
  editing: boolean,
): DetailRow[] {
  const members = useMembers({ enabled: editing });
  const groups = useGroups({ enabled: editing });
  const excursions = useExcursions({ enabled: editing });
  const addresses = useEmailAddresses({ enabled: editing });

  // Seeded from the message's own recipients while the lists are still loading.
  const asOption = (r: { id: number; name: string }) => ({ value: r.id, label: r.name });
  const memberOptions: Option[] = withSelected(
    (members.data ?? []).map(asOption),
    message ? [...message.to_members, ...message.reply_to].map(asOption) : [],
  );
  const groupOptions: Option[] = withSelected(
    (groups.data ?? []).map(asOption),
    message ? message.to_groups.map(asOption) : [],
  );
  const excursionLabel = (e: { id: number; code: string; name: string }) => ({
    value: e.id,
    label: `${e.code} · ${e.name}`,
  });
  const excursionOptions: Option[] = withSelected(
    (excursions.data ?? []).map(excursionLabel),
    message?.to_freizeit ? [excursionLabel(message.to_freizeit)] : [],
  );
  const addressLabel = (a: { id: number; email: string }) => ({ value: a.id, label: a.email });
  const addressOptions: Option[] = withSelected(
    (addresses.data ?? []).map(addressLabel),
    message ? message.reply_to_email_address.map(addressLabel) : [],
  );

  return [
    {
      label: "Betreff",
      field: "subject",
      value: message?.subject,
      edit: (
        <input
          aria-label="Betreff"
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
          required
        />
      ),
    },
    {
      label: "Inhalt",
      field: "content",
      value: <span style={{ whiteSpace: "pre-wrap" }}>{message?.content}</span>,
      edit: (
        <textarea
          aria-label="Inhalt"
          rows={14}
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          required
        />
      ),
    },
    ...(message
      ? [
          {
            label: "Status",
            value: message.sent ? (
              <Badge tone="success">Gesendet</Badge>
            ) : (
              <Badge tone="warning">Entwurf</Badge>
            ),
          },
          { label: "Empfänger", value: message.recipients },
          { label: "Erstellt von", value: message.created_by?.name ?? "—" },
        ]
      : []),
    {
      label: "Gruppen",
      field: "to_groups",
      value: message && (message.to_groups.map((g) => g.name).join(", ") || "—"),
      edit: (
        <MultiSelect
          options={groupOptions}
          selected={form.to_groups}
          onChange={(v) => setForm({ ...form, to_groups: v })}
          placeholder="Gruppe hinzufügen"
        />
      ),
    },
    {
      label: "Teilnehmende",
      field: "to_members",
      value: message && (message.to_members.map((m) => m.name).join(", ") || "—"),
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.to_members}
          onChange={(v) => setForm({ ...form, to_members: v })}
          placeholder="Teilnehmende hinzufügen"
        />
      ),
    },
    {
      label: "Freizeit",
      field: "to_freizeit",
      value: message?.to_freizeit
        ? `${message.to_freizeit.code} · ${message.to_freizeit.name}`
        : "—",
      edit: (
        <SingleSelect
          options={excursionOptions}
          value={form.to_freizeit ?? null}
          onChange={(v) => setForm({ ...form, to_freizeit: v })}
        />
      ),
    },
    {
      label: "Antwort an (Teilnehmende)",
      field: "reply_to",
      value: message && (message.reply_to.map((m) => m.name).join(", ") || "—"),
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.reply_to}
          onChange={(v) => setForm({ ...form, reply_to: v })}
          placeholder="Teilnehmende hinzufügen"
        />
      ),
    },
    {
      label: "Antwort an (E-Mail)",
      field: "reply_to_email_address",
      value: message && (message.reply_to_email_address.map((a) => a.email).join(", ") || "—"),
      edit: (
        <MultiSelect
          options={addressOptions}
          selected={form.reply_to_email_address}
          onChange={(v) => setForm({ ...form, reply_to_email_address: v })}
          placeholder="Adresse hinzufügen"
        />
      ),
    },
  ];
}

/* --- detail -------------------------------------------------------------- */

export function MessageDetailPage() {
  const { id } = useParams();
  const messageId = Number(id);
  const query = useApiQuery(["mailer", "messages", messageId], () =>
    unwrap(
      client.GET("/api/mailer/messages/{message_id}", {
        params: { path: { message_id: messageId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "Nachrichten", to: "/kompass/mailer/messages" },
    { label: query.data?.subject || "Nachricht" },
  ];

  return (
    <QueryBoundary query={query}>
      {(message: MessageOut) => <MessageDetailBody message={message} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function MessageDetailBody({ message, crumbs }: { message: MessageOut; crumbs: Crumb[] }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<MessageFormState>(() => messageToForm(message));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: MessageIn) =>
      unwrap(
        client.PUT("/api/mailer/messages/{message_id}", {
          params: { path: { message_id: message.id } },
          body,
        }),
      ),
    {
      invalidate: [queryKeys.messages(), ["mailer", "messages", message.id]],
    },
  );

  const deletion = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/mailer/messages/{message_id}", {
          params: { path: { message_id: message.id } },
        }),
      ),
    {
      invalidate: [queryKeys.messages()],
      onSuccess: () => {
        toast.success("Nachricht gelöscht.");
        navigate("/kompass/mailer/messages");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(messageToForm(message));
    setFieldErrors({});
    setEditing(true);
  }

  const rows = useMessageRows(message, form, setForm, editing);

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setFieldErrors({});
        setSaving(true);
        try {
          await mutation.mutateAsync(form);
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
        breadcrumbs={crumbs}
        actions={
          editing ? (
            <Fragment key="edit">
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" busy={saving}>
                Speichern
              </Button>
            </Fragment>
          ) : (
            <Fragment key="view">
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              {!message.sent && (
                <>
                  <Menu label="Aktionen">
                    <SubmitAction message={message} />
                    <Button
                      type="button"
                      variant="danger"
                      busy={deletion.isPending}
                      onClick={async () => {
                        if (
                          await confirm({
                            message: "Nachricht wirklich löschen?",
                            danger: true,
                            confirmLabel: "Löschen",
                          })
                        )
                          deletion.mutate(undefined);
                      }}
                    >
                      Löschen
                    </Button>
                  </Menu>
                  <Button type="button" onClick={startEditing}>
                    Bearbeiten
                  </Button>
                </>
              )}
            </Fragment>
          )
        }
      />
      <Tabs
        tabs={[
          {
            id: "details",
            label: "Details",
            content: <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "anhaenge",
            label: "Anhänge",
            content: <Attachments message={message.id} editing={editing} registerFlush={getRegistrar("attachments")} />,
          },
        ]}
      />
    </form>
  );
}

/** Submit/send action — POST /submit, guarded to unsent messages only. */
function SubmitAction({ message }: { message: MessageOut }) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/mailer/messages/{message_id}/submit", {
          params: { path: { message_id: message.id } },
        }),
      ),
    {
      invalidate: [queryKeys.messages(), ["mailer", "messages", message.id]],
      onSuccess: () => toast.success("Nachricht versendet."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  if (message.sent) return null;
  return (
    <Button
      type="button"
      variant="ghost"
      busy={mutation.isPending}
      onClick={async () => {
        if (await confirm("Nachricht jetzt an alle Empfänger versenden?"))
          mutation.mutate(undefined);
      }}
    >
      Versenden
    </Button>
  );
}

/* --- attachments --------------------------------------------------------- */

type AttachmentData = { filename: string; file: File | null; url: string | null };

/** The backend's cap on an attachment (`file_size_validator(10)`, in MiB). */
const MAX_ATTACHMENT_MIB = 10;

/**
 * The message's attachments, staged while editing and applied on Save.
 *
 * `message` is the id of the message they belong to — or, while composing, a
 * ref that Save fills with the id of the message it has just created before it
 * runs the flushes; until then there is nothing to load and the staged files
 * only wait. `onStagedChange` reports how many files are waiting.
 */
function Attachments({
  message,
  editing,
  registerFlush,
  onStagedChange,
}: {
  message: number | RefObject<number | null>;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
  onStagedChange?: (count: number) => void;
}) {
  const qc = useQueryClient();
  const messageId = typeof message === "number" ? message : null;
  const query = useApiQuery(
    ["mailer", "messages", messageId, "attachments"],
    () =>
      unwrap(
        client.GET("/api/mailer/messages/{message_id}/attachments", {
          params: { path: { message_id: messageId as number } },
        }),
      ),
    { enabled: messageId !== null },
  );
  /** The message to upload to: known up front, or created by Save just now. */
  const target = (): number => {
    const id = typeof message === "number" ? message : message.current;
    if (id === null) throw new Error("Die Nachricht ist noch nicht gespeichert.");
    return id;
  };
  const refresh = (id: number) => {
    qc.invalidateQueries({ queryKey: ["mailer", "messages", id, "attachments"] });
    qc.invalidateQueries({ queryKey: ["mailer", "messages", id] });
  };
  const uploadM = useApiMutation(
    ({ id, file }: { id: number; file: File }) =>
      unwrap(
        client.POST("/api/mailer/messages/{message_id}/attachments", {
          params: { path: { message_id: id } },
          // Multipart upload: the field name is `f`; a custom serializer builds
          // the FormData because openapi-fetch would otherwise JSON-encode it.
          body: { f: file as unknown as string },
          bodySerializer(body: { f: unknown }) {
            const fd = new FormData();
            fd.append("f", body.f as File);
            return fd;
          },
        }),
      ),
    { onSuccess: (_data, { id }) => refresh(id) },
  );
  const deleteM = useApiMutation(
    (attachmentId: number) =>
      unwrap(
        client.DELETE("/api/mailer/attachments/{attachment_id}", {
          params: { path: { attachment_id: attachmentId } },
        }),
      ),
    { onSuccess: () => refresh(target()) },
  );

  // A failed upload names its file, so the user knows which one to add again.
  async function upload(d: AttachmentData) {
    if (!d.file) return;
    try {
      await uploadM.mutateAsync({ id: target(), file: d.file });
    } catch (e) {
      const detail =
        e instanceof ApiError && Object.keys(e.fieldErrors).length
          ? Object.values(e.fieldErrors).flat().join(" ")
          : e instanceof Error
            ? e.message
            : String(e);
      throw new Error(`„${d.filename}“: ${detail}`);
    }
  }

  const serverRows = (query.data ?? []).map((a) => ({
    id: a.id,
    data: { filename: a.filename, file: null, url: a.url ?? null } as AttachmentData,
  }));
  const { rows, removeRow, addRow } = useInlineDraft<AttachmentData>({
    serverRows,
    editing,
    create: upload,
    update: () => Promise.resolve(),
    remove: (id) => deleteM.mutateAsync(id),
    registerFlush,
  });
  const staged = rows.filter((r) => r.id === null).length;
  useEffect(() => onStagedChange?.(staged), [onStagedChange, staged]);
  const [adding, setAdding] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const tooLarge = file !== null && file.size > MAX_ATTACHMENT_MIB * 1024 * 1024;

  return (
    <>
      <InlineTable
        title="Anhänge"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        empty="Keine Anhänge."
        onDelete={(row) => removeRow(row)}
        onAdd={() => {
          setFile(null);
          setAdding(true);
        }}
        addLabel="Anhang"
        columns={[
          {
            header: "Datei",
            cell: (row) =>
              row.data.url ? (
                <a href={`${API_BASE}${row.data.url}`} target="_blank" rel="noreferrer">
                  {row.data.filename}
                </a>
              ) : (
                <span>
                  {row.data.filename} <span className="muted small">(neu)</span>
                </span>
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Anhang hinzufügen" onClose={() => setAdding(false)} size="sm">
          <div className="stack">
            <Field
              label="Datei"
              hint={`Wird der Nachricht als Anhang beigelegt (höchstens ${MAX_ATTACHMENT_MIB} MiB).`}
            >
              <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
              {tooLarge && file && (
                <div className="field-error">
                  {`Die Datei ist ${(file.size / 1024 / 1024).toFixed(1).replace(".", ",")} MiB groß; erlaubt sind höchstens ${MAX_ATTACHMENT_MIB} MiB.`}
                </div>
              )}
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={!file || tooLarge}
                onClick={() => {
                  if (file) addRow({ filename: file.name, file, url: null });
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

/* --- shared form --------------------------------------------------------- */

type MessageFormState = MessageIn;

function emptyMessage(): MessageFormState {
  return {
    subject: "",
    content: "",
    to_groups: [],
    to_members: [],
    to_freizeit: null,
    reply_to: [],
    reply_to_email_address: [],
  };
}

function messageToForm(m: MessageOut): MessageFormState {
  return {
    subject: m.subject,
    content: m.content,
    to_groups: m.to_groups.map((g) => g.id),
    to_members: m.to_members.map((x) => x.id),
    to_freizeit: m.to_freizeit ? m.to_freizeit.id : null,
    reply_to: m.reply_to.map((x) => x.id),
    reply_to_email_address: m.reply_to_email_address.map((a) => a.id),
  };
}
