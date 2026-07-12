import { useMemo, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { InlineTable } from "../../components/inline";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Tabs,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";
import { MultiSelect, SingleSelect, type Option } from "./selects";

type MessageBrief = components["schemas"]["MessageBrief"];
type MessageOut = components["schemas"]["MessageOut"];
type MessageIn = components["schemas"]["MessageIn"];
type AttachmentOut = components["schemas"]["AttachmentOut"];

/* --- list ---------------------------------------------------------------- */

export function MessagesList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["mailer", "messages"], () =>
    unwrap(client.GET("/api/mailer/messages")),
  );
  const rows = query.data ?? [];

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
        actions={<Button onClick={() => setCreating(true)}>Neue Nachricht</Button>}
      />
      {creating && (
        <Modal title="Neue Nachricht" onClose={() => setCreating(false)}>
          <MessageCreateDialog onClose={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Nachrichten vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/app/mailer/messages/${m.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              {
                header: "Betreff",
                cell: (m) => m.subject || "(ohne Betreff)",
                sortKey: "subject",
              },
              { header: "Empfänger", cell: (m) => m.recipients },
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

/* --- create dialog ------------------------------------------------------- */

/**
 * Create form rendered inside the messages-list modal. Offers three actions:
 * "Senden" (create then trigger the send action), "Als Entwurf speichern"
 * (create without sending) and "Abbrechen" (confirms discarding when the form
 * carries any input).
 */
function MessageCreateDialog({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();
  const [form, setForm] = useState<MessageFormState>(() => emptyMessage());
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groups = useApiQuery(["members", "groups"], () =>
    unwrap(client.GET("/api/members/groups")),
  );
  const excursions = useApiQuery(["members", "excursions"], () =>
    unwrap(client.GET("/api/members/excursions")),
  );
  const addresses = useApiQuery(["mailer", "email-addresses"], () =>
    unwrap(client.GET("/api/mailer/email-addresses")),
  );

  const create = useApiMutation(
    (body: MessageIn) => unwrap(client.POST("/api/mailer/messages", { body })),
    {
      invalidate: [["mailer", "messages"]],
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  const submit = useApiMutation(
    (id: number) =>
      unwrap(
        client.POST("/api/mailer/messages/{message_id}/submit", {
          params: { path: { message_id: id } },
        }),
      ),
    {
      invalidate: [["mailer", "messages"]],
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const memberOptions: Option[] = (members.data ?? []).map((m) => ({
    value: m.id,
    label: m.name,
  }));
  const groupOptions: Option[] = (groups.data ?? []).map((g) => ({
    value: g.id,
    label: g.name,
  }));
  const excursionOptions: Option[] = (excursions.data ?? []).map((e) => ({
    value: e.id,
    label: `${e.code} · ${e.name}`,
  }));
  const addressOptions: Option[] = (addresses.data ?? []).map((a) => ({
    value: a.id,
    label: a.email,
  }));

  const dirty =
    form.subject.trim() !== "" ||
    form.content.trim() !== "" ||
    form.to_groups.length > 0 ||
    form.to_members.length > 0 ||
    form.to_freizeit !== null ||
    form.reply_to.length > 0 ||
    form.reply_to_email_address.length > 0;

  const busy = create.isPending || submit.isPending;

  async function requestCancel() {
    if (dirty && !(await confirm("Änderungen verwerfen?"))) return;
    onClose();
  }

  function valid(): boolean {
    if (!form.subject.trim() || !form.content.trim()) {
      toast.error("Betreff und Inhalt sind erforderlich.");
      return false;
    }
    return true;
  }

  async function saveDraft() {
    if (!valid()) return;
    setFieldErrors({});
    const msg = await create.mutateAsync(form);
    toast.success("Als Entwurf gespeichert.");
    onClose();
    navigate(`/app/mailer/messages/${msg.id}`);
  }

  async function sendNow() {
    if (!valid()) return;
    if (!(await confirm("Nachricht jetzt an alle Empfänger versenden?"))) return;
    setFieldErrors({});
    const msg = await create.mutateAsync(form);
    await submit.mutateAsync(msg.id);
    toast.success("Nachricht versendet.");
    onClose();
    navigate(`/app/mailer/messages/${msg.id}`);
  }

  return (
    <div className="stack">
      <Field label="Betreff">
        <input
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
          required
        />
        {fieldErrors.subject && (
          <div className="field-error">{fieldErrors.subject.join(" ")}</div>
        )}
      </Field>
      <Field label="Inhalt">
        <textarea
          rows={8}
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          required
        />
        {fieldErrors.content && (
          <div className="field-error">{fieldErrors.content.join(" ")}</div>
        )}
      </Field>
      <Field label="Empfänger-Gruppen">
        <MultiSelect
          options={groupOptions}
          selected={form.to_groups}
          onChange={(v) => setForm({ ...form, to_groups: v })}
          placeholder="Gruppe hinzufügen"
        />
      </Field>
      <Field label="Empfänger-Mitglieder">
        <MultiSelect
          options={memberOptions}
          selected={form.to_members}
          onChange={(v) => setForm({ ...form, to_members: v })}
          placeholder="Mitglied hinzufügen"
        />
      </Field>
      <Field label="Freizeit-Teilnehmer">
        <SingleSelect
          options={excursionOptions}
          value={form.to_freizeit ?? null}
          onChange={(v) => setForm({ ...form, to_freizeit: v })}
        />
      </Field>
      <Field label="Antwort an (Mitglieder)">
        <MultiSelect
          options={memberOptions}
          selected={form.reply_to}
          onChange={(v) => setForm({ ...form, reply_to: v })}
          placeholder="Mitglied hinzufügen"
        />
      </Field>
      <Field label="Antwort an (E-Mail-Adressen)">
        <MultiSelect
          options={addressOptions}
          selected={form.reply_to_email_address}
          onChange={(v) => setForm({ ...form, reply_to_email_address: v })}
          placeholder="Adresse hinzufügen"
        />
      </Field>
      <div className="row-actions">
        <Button type="button" busy={busy} onClick={sendNow}>
          Senden
        </Button>
        <Button type="button" variant="ghost" busy={busy} onClick={saveDraft}>
          Als Entwurf speichern
        </Button>
        <Button type="button" variant="ghost" disabled={busy} onClick={requestCancel}>
          Abbrechen
        </Button>
      </div>
    </div>
  );
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

  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Nachrichten", to: "/app/mailer/messages" },
          { label: query.data?.subject || "Nachricht" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(message: MessageOut) => <MessageDetailBody message={message} />}
      </QueryBoundary>
    </div>
  );
}

function MessageDetailBody({ message }: { message: MessageOut }) {
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<MessageFormState>(() => messageToForm(message));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groups = useApiQuery(["members", "groups"], () =>
    unwrap(client.GET("/api/members/groups")),
  );
  const excursions = useApiQuery(["members", "excursions"], () =>
    unwrap(client.GET("/api/members/excursions")),
  );
  const addresses = useApiQuery(["mailer", "email-addresses"], () =>
    unwrap(client.GET("/api/mailer/email-addresses")),
  );

  const mutation = useApiMutation(
    (body: MessageIn) =>
      unwrap(
        client.PUT("/api/mailer/messages/{message_id}", {
          params: { path: { message_id: message.id } },
          body,
        }),
      ),
    {
      invalidate: [
        ["mailer", "messages"],
        ["mailer", "messages", message.id],
      ],
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

  const deletion = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/mailer/messages/{message_id}", {
          params: { path: { message_id: message.id } },
        }),
      ),
    {
      invalidate: [["mailer", "messages"]],
      onSuccess: () => {
        toast.success("Nachricht gelöscht.");
        navigate("/app/mailer/messages");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(messageToForm(message));
    setFieldErrors({});
    setEditing(true);
  }

  const memberOptions: Option[] = (members.data ?? []).map((m) => ({ value: m.id, label: m.name }));
  const groupOptions: Option[] = (groups.data ?? []).map((g) => ({ value: g.id, label: g.name }));
  const excursionOptions: Option[] = (excursions.data ?? []).map((e) => ({
    value: e.id,
    label: `${e.code} · ${e.name}`,
  }));
  const addressOptions: Option[] = (addresses.data ?? []).map((a) => ({
    value: a.id,
    label: a.email,
  }));

  const rows: DetailRow[] = [
    {
      label: "Betreff",
      field: "subject",
      value: message.subject,
      edit: (
        <input
          value={form.subject}
          onChange={(e) => setForm({ ...form, subject: e.target.value })}
          required
        />
      ),
    },
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
    {
      label: "Gruppen",
      field: "to_groups",
      value: message.to_groups.map((g) => g.name).join(", ") || "—",
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
      label: "Mitglieder",
      field: "to_members",
      value: message.to_members.map((m) => m.name).join(", ") || "—",
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.to_members}
          onChange={(v) => setForm({ ...form, to_members: v })}
          placeholder="Mitglied hinzufügen"
        />
      ),
    },
    {
      label: "Freizeit",
      field: "to_freizeit",
      value: message.to_freizeit
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
      label: "Antwort an (Mitglieder)",
      field: "reply_to",
      value: message.reply_to.map((m) => m.name).join(", ") || "—",
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.reply_to}
          onChange={(v) => setForm({ ...form, reply_to: v })}
          placeholder="Mitglied hinzufügen"
        />
      ),
    },
    {
      label: "Antwort an (E-Mail)",
      field: "reply_to_email_address",
      value: message.reply_to_email_address.map((a) => a.email).join(", ") || "—",
      edit: (
        <MultiSelect
          options={addressOptions}
          selected={form.reply_to_email_address}
          onChange={(v) => setForm({ ...form, reply_to_email_address: v })}
          placeholder="Adresse hinzufügen"
        />
      ),
    },
    {
      label: "Inhalt",
      field: "content",
      value: <span style={{ whiteSpace: "pre-wrap" }}>{message.content}</span>,
      edit: (
        <textarea
          rows={8}
          value={form.content}
          onChange={(e) => setForm({ ...form, content: e.target.value })}
          required
        />
      ),
    },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(form);
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
          <>
            {!message.sent && (
              <Button type="button" onClick={startEditing}>
                Bearbeiten
              </Button>
            )}
            <SubmitAction message={message} />
            {!message.sent && (
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
            )}
          </>
        )}
      </div>
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
            content: <Attachments message={message} editing={editing} />,
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
      invalidate: [
        ["mailer", "messages"],
        ["mailer", "messages", message.id],
      ],
      onSuccess: () => toast.success("Nachricht versendet."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  if (message.sent) return null;
  return (
    <Button
      type="button"
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

function Attachments({ message, editing }: { message: MessageOut; editing: boolean }) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);
  const query = useApiQuery(["mailer", "messages", message.id, "attachments"], () =>
    unwrap(
      client.GET("/api/mailer/messages/{message_id}/attachments", {
        params: { path: { message_id: message.id } },
      }),
    ),
  );
  const attachments: AttachmentOut[] = query.data ?? [];

  const upload = useApiMutation(
    (file: File) =>
      unwrap(
        client.POST("/api/mailer/messages/{message_id}/attachments", {
          params: { path: { message_id: message.id } },
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
    {
      invalidate: [
        ["mailer", "messages", message.id, "attachments"],
        ["mailer", "messages", message.id],
      ],
      onSuccess: () => {
        toast.success("Anhang hochgeladen.");
        if (fileRef.current) fileRef.current.value = "";
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const deletion = useApiMutation(
    (attachmentId: number) =>
      unwrap(
        client.DELETE("/api/mailer/attachments/{attachment_id}", {
          params: { path: { attachment_id: attachmentId } },
        }),
      ),
    {
      invalidate: [
        ["mailer", "messages", message.id, "attachments"],
        ["mailer", "messages", message.id],
      ],
      onSuccess: () => toast.success("Anhang gelöscht."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <InlineTable
      title="Anhänge"
      rows={attachments}
      rowKey={(a) => a.id}
      editing={editing}
      empty="Keine Anhänge."
      onDelete={(a) => deletion.mutate(a.id)}
      columns={[
        {
          header: "Datei",
          cell: (a) =>
            a.url ? (
              <a href={`${API_BASE}${a.url}`} target="_blank" rel="noreferrer">
                {a.filename}
              </a>
            ) : (
              a.filename
            ),
        },
      ]}
      renderAdd={() => (
        <div className="row-actions">
          <input
            ref={fileRef}
            type="file"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) upload.mutate(file);
            }}
            disabled={upload.isPending}
          />
        </div>
      )}
    />
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
