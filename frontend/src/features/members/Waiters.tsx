import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { usePermissions } from "../../api/me";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Menu,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  type Crumb,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type WaiterBrief = components["schemas"]["WaiterBrief"];
type WaiterOut = components["schemas"]["WaiterOut"];
type WaiterUpdate = components["schemas"]["WaiterUpdate"];
type GroupOut = components["schemas"]["GroupOut"];
type EnumChoice = components["schemas"]["MemberEnumChoice"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

/** Tri-state waiting-status badge: null = pending, true = confirmed, false = expired. */
function waitingBadge(value: boolean | null | undefined) {
  if (value === null || value === undefined) return <Badge tone="warning">Ausstehend</Badge>;
  return value ? <Badge tone="success">Ja</Badge> : <Badge tone="danger">Nein</Badge>;
}

/* --- list ----------------------------------------------------------------
 * Full parity with MemberWaitingListAdmin: all list_display columns (name,
 * birth date, age, gender, application date, latest group invitation, email
 * confirmed, waiting status confirmed, missed reminders), search over
 * prename/lastname/email, filters (email confirmed, age, gender, waiting
 * status), sortable headers, default ordering by application date. */

export function WaitersList() {
  const navigate = useNavigate();
  const query = useApiQuery(["waiters"], () => unwrap(client.GET("/api/members/waiters")));
  const enumsQuery = useApiQuery(["members", "enums"], () =>
    unwrap(client.GET("/api/members/enums")),
  );
  const rows = query.data ?? [];

  const genderChoices = enumsQuery.data?.gender ?? [];
  const genderLabel = (value: number) => {
    const hit = genderChoices.find((c: EnumChoice) => Number(c.value) === value);
    return hit ? hit.label : String(value);
  };

  const genderOptions = useMemo(
    () => genderChoices.map((c: EnumChoice) => ({ value: String(c.value), label: c.label })),
    [genderChoices],
  );

  const ageOptions = useMemo(() => {
    const ages = new Set<number>();
    rows.forEach((w) => {
      if (w.age !== null && w.age !== undefined) ages.add(w.age);
    });
    return [...ages].sort((a, b) => a - b).map((a) => ({ value: String(a), label: String(a) }));
  }, [rows]);

  const config: ListViewConfig<WaiterBrief> = useMemo(
    () => ({
      search: (w) => [w.name, w.prename, w.lastname, w.email],
      filters: [
        {
          key: "confirmed_mail",
          label: "E-Mail bestätigt",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (w, v) => (v === "yes") === Boolean(w.confirmed_mail),
        },
        {
          key: "gender",
          label: "Geschlecht",
          options: genderOptions,
          match: (w, v) => String(w.gender) === v,
        },
        { key: "age", label: "Alter", options: ageOptions, match: (w, v) => String(w.age) === v },
        {
          key: "waiting",
          label: "Wartestatus",
          options: [
            { value: "yes", label: "Bestätigt" },
            { value: "no", label: "Abgelaufen" },
            { value: "pending", label: "Ausstehend" },
          ],
          match: (w, v) =>
            v === "pending"
              ? w.waiting_confirmed === null || w.waiting_confirmed === undefined
              : (v === "yes") === Boolean(w.waiting_confirmed),
        },
      ],
      sort: {
        name: (w) => w.lastname,
        birth_date: (w) => w.birth_date,
        age: (w) => w.age,
        gender: (w) => w.gender,
        application_date: (w) => w.application_date,
        confirmed_mail: (w) => w.confirmed_mail,
        sent_reminders: (w) => w.sent_reminders,
      },
      defaultSort: { key: "application_date", dir: "asc" },
    }),
    [genderOptions, ageOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Warteliste" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Wartelisten-Bewerbungen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(w) => w.id}
            onRowClick={(w) => navigate(`/app/waiters/${w.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (w) => w.name, sortKey: "name" },
              {
                header: "Geburtsdatum",
                cell: (w) => formatDate(w.birth_date),
                sortKey: "birth_date",
              },
              { header: "Alter", cell: (w) => w.age ?? "—", sortKey: "age" },
              { header: "Geschlecht", cell: (w) => genderLabel(w.gender), sortKey: "gender" },
              {
                header: "Bewerbungsdatum",
                cell: (w) => formatDate(w.application_date),
                sortKey: "application_date",
              },
              { header: "Letzte Gruppeneinladung", cell: (w) => w.latest_group_invitation || "—" },
              {
                header: "E-Mail bestätigt",
                cell: (w) => (w.confirmed_mail ? <Badge tone="success">Ja</Badge> : "—"),
                sortKey: "confirmed_mail",
              },
              { header: "Wartestatus", cell: (w) => waitingBadge(w.waiting_confirmed) },
              {
                header: "Verpasste Erinnerungen",
                cell: (w) => w.sent_reminders,
                sortKey: "sent_reminders",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail + edit + invite ---------------------------------------------- */

export function WaiterDetailPage() {
  const { id } = useParams();
  const waiterId = Number(id);
  const query = useApiQuery(["waiters", waiterId], () =>
    unwrap(
      client.GET("/api/members/waiters/{waiter_id}", { params: { path: { waiter_id: waiterId } } }),
    ),
  );
  const crumbs: Crumb[] = [
    { label: "Warteliste", to: "/app/waiters" },
    { label: query.data?.name ?? "Wartelisten-Bewerbung" },
  ];

  return (
    <QueryBoundary query={query}>
      {(waiter: WaiterOut) => <WaiterDetailBody waiter={waiter} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

function makeDraft(w: WaiterOut) {
  return {
    prename: w.prename ?? "",
    lastname: w.lastname ?? "",
    email: w.email ?? "",
    birth_date: w.birth_date ?? "",
    gender: String(w.gender ?? ""),
    application_text: w.application_text ?? "",
    comments: w.comments ?? "",
  };
}

function WaiterDetailBody({ waiter, crumbs }: { waiter: WaiterOut; crumbs: Crumb[] }) {
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const removeMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/waiters/{waiter_id}", {
          params: { path: { waiter_id: waiter.id } },
        }),
      ),
    {
      invalidate: [["waiters"]],
      onSuccess: () => {
        toast.success("Bewerbung gelöscht.");
        navigate("/app/waiters");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeDraft(waiter));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const enumsQuery = useApiQuery(
    ["members", "enums"],
    () => unwrap(client.GET("/api/members/enums")),
    { enabled: editing },
  );
  const genderChoices = enumsQuery.data?.gender ?? [];

  const mutation = useApiMutation<WaiterOut, WaiterUpdate>(
    (body: WaiterUpdate) =>
      unwrap(
        client.PATCH("/api/members/waiters/{waiter_id}", {
          params: { path: { waiter_id: waiter.id } },
          body,
        }),
      ),
    {
      invalidate: [["waiters"], ["waiters", waiter.id]],
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
    setForm(makeDraft(waiter));
    setFieldErrors({});
    setEditing(true);
  }

  const rows: DetailRow[] = [
    { label: "Name", value: waiter.name },
    {
      label: "Vorname",
      value: waiter.prename,
      field: "prename",
      edit: (
        <input
          value={form.prename}
          onChange={(e) => setForm({ ...form, prename: e.target.value })}
        />
      ),
    },
    {
      label: "Nachname",
      value: waiter.lastname,
      field: "lastname",
      edit: (
        <input
          value={form.lastname}
          onChange={(e) => setForm({ ...form, lastname: e.target.value })}
        />
      ),
    },
    {
      label: "E-Mail",
      value: waiter.email || "—",
      field: "email",
      edit: (
        <input value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} />
      ),
    },
    {
      label: "Geburtsdatum",
      value: formatDate(waiter.birth_date),
      field: "birth_date",
      edit: (
        <input
          type="date"
          value={form.birth_date}
          onChange={(e) => setForm({ ...form, birth_date: e.target.value })}
        />
      ),
    },
    { label: "Alter", value: waiter.age ?? "—" },
    {
      label: "Geschlecht",
      value: waiter.gender_str,
      field: "gender",
      edit: (
        <Select
          value={form.gender}
          onChange={(v) => setForm({ ...form, gender: v })}
          options={genderChoices.map((c: EnumChoice) => ({
            value: String(c.value),
            label: c.label,
          }))}
          placeholder="Geschlecht wählen …"
        />
      ),
    },
    {
      label: "Möchtest du uns noch etwas mitteilen?",
      value: waiter.application_text || "—",
      field: "application_text",
      edit: (
        <textarea
          value={form.application_text}
          onChange={(e) => setForm({ ...form, application_text: e.target.value })}
        />
      ),
    },
    { label: "Bewerbungsdatum", value: formatDate(waiter.application_date) },
    {
      label: "Kommentare",
      value: waiter.comments || "—",
      field: "comments",
      edit: (
        <textarea
          value={form.comments}
          onChange={(e) => setForm({ ...form, comments: e.target.value })}
        />
      ),
    },
    { label: "Verpasste Erinnerungen", value: waiter.sent_reminders },
    {
      label: "E-Mail bestätigt",
      value: waiter.confirmed_mail ? (
        <Badge tone="success">Ja</Badge>
      ) : (
        <Badge tone="warning">Nein</Badge>
      ),
    },
    { label: "Wartestatus bestätigt", value: waitingBadge(waiter.waiting_confirmed) },
    { label: "Letzte Gruppeneinladung", value: waiter.latest_group_invitation || "—" },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate({
          prename: form.prename,
          lastname: form.lastname,
          email: form.email,
          birth_date: form.birth_date || null,
          gender: form.gender === "" ? null : Number(form.gender),
          application_text: form.application_text,
          comments: form.comments,
        });
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
              <Button type="submit" busy={mutation.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <WaiterInvite waiter={waiter} />
              <WaiterReminders waiter={waiter} />
              {can("members.delete_global_memberwaitinglist") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={removeMutation.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${waiter.name}“ wirklich löschen?`,
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
            id: "bewerbung",
            label: "Bewerbung",
            content: <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "einladungen",
            label: "Einladungen",
            content: <WaiterInvitations waiter={waiter} />,
          },
        ]}
      />
    </form>
  );
}

/** Read-only history of the waiter's group invitations. */
function WaiterInvitations({ waiter }: { waiter: WaiterOut }) {
  return (
    <div>
      <h3 className="fieldset-title" style={{ marginTop: "1.5rem" }}>
        Gruppeneinladungen
      </h3>
      <DataTable
        rows={waiter.invitations}
        rowKey={(i) => i.id}
        empty="Keine Einladungen."
        columns={[
          { header: "Gruppe", cell: (i) => i.group.name },
          { header: "Status", cell: (i) => i.status },
          { header: "Datum", cell: (i) => formatDate(i.date) },
        ]}
      />
    </div>
  );
}

/** The waiting-list reminder actions (``MemberWaitingListAdmin.actions``). */
function WaiterReminders({ waiter }: { waiter: WaiterOut }) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();

  const run = useApiMutation((a: { success: string; call: () => Promise<unknown> }) => a.call(), {
    invalidate: [["waiters"], ["waiters", waiter.id]],
    onSuccess: (_data, a) => toast.success(a.success),
    onError: (e: Error) => toast.error(e.message),
  });

  if (!can("members.change_global_memberwaitinglist")) return null;

  const recipient = waiter.email || waiter.name;
  const actions = [
    {
      label: "Wartebestätigung anfordern",
      question: `${waiter.name} per E-Mail an ${recipient} fragen, ob die Bewerbung weiter gelten soll?`,
      success: `Anfrage an ${recipient} verschickt.`,
      call: () =>
        unwrap(
          client.POST("/api/members/waiters/{waiter_id}/request-wait-confirmation", {
            params: { path: { waiter_id: waiter.id } },
          }),
        ),
    },
    {
      label: "Bestätigungsmail an alle Adressen",
      question: `Bestätigungsmail an ${recipient} senden?`,
      success: `Bestätigungsmail an ${recipient} verschickt.`,
      call: () =>
        unwrap(
          client.POST("/api/members/waiters/{waiter_id}/request-mail-confirmation", {
            params: { path: { waiter_id: waiter.id }, query: { rerequest: true } },
          }),
        ),
    },
    {
      label: "Bestätigungsmail nur an offene Adressen",
      question: `Bestätigungsmail nur an noch unbestätigte Adressen von ${waiter.name} senden?`,
      success: "Offene Bestätigungen erneut angefordert.",
      call: () =>
        unwrap(
          client.POST("/api/members/waiters/{waiter_id}/request-mail-confirmation", {
            params: { path: { waiter_id: waiter.id }, query: { rerequest: false } },
          }),
        ),
    },
  ];

  return (
    <Menu label="Erinnerungen">
      {actions.map((a) => (
        <Button
          key={a.label}
          type="button"
          variant="ghost"
          busy={run.isPending}
          onClick={async () => {
            if (await confirm({ title: a.label, message: a.question, confirmLabel: "Senden" }))
              run.mutate(a);
          }}
        >
          {a.label}
        </Button>
      ))}
    </Menu>
  );
}

/** "In Gruppe einladen": pick a group, edit the invitation text, then send. */
function WaiterInvite({ waiter }: { waiter: WaiterOut }) {
  const toast = useToast();
  const [open, setOpen] = useState(false);
  const [groupId, setGroupId] = useState<string>("");
  const [text, setText] = useState("");

  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")), {
    enabled: open,
  });
  const groups = groupsQuery.data ?? [];

  const mutation = useApiMutation<WaiterOut, void>(
    () =>
      unwrap(
        client.POST("/api/members/waiters/{waiter_id}/invite", {
          params: { path: { waiter_id: waiter.id } },
          body: { group_id: Number(groupId), text: text || null },
        }),
      ),
    {
      invalidate: [["waiters"], ["waiters", waiter.id]],
      onSuccess: () => {
        toast.success("Einladung versendet.");
        close();
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  // Prefill the editable invitation text with the selected group's template.
  function selectGroup(v: string) {
    setGroupId(v);
    const g = groups.find((x) => String(x.id) === v);
    setText(g?.invitation_text_template ?? "");
  }

  function close() {
    setOpen(false);
    setGroupId("");
    setText("");
  }

  return (
    <>
      <Button type="button" variant="ghost" onClick={() => setOpen(true)}>
        In Gruppe einladen
      </Button>
      {open && (
        <Modal title="In Gruppe einladen" onClose={close}>
          <div className="stack">
            <QueryBoundary query={groupsQuery} empty="Keine Gruppen verfügbar.">
              {(gs: GroupOut[]) => (
                <>
                  <Field label="Gruppe">
                    <Select
                      value={groupId}
                      onChange={selectGroup}
                      options={gs.map((g) => ({ value: g.id, label: g.name }))}
                      placeholder="Gruppe wählen …"
                    />
                  </Field>
                  {groupId !== "" && (
                    <Field label="Einladungstext" hint="Wird an die Bewerber*in gesendet.">
                      <textarea rows={12} value={text} onChange={(e) => setText(e.target.value)} />
                    </Field>
                  )}
                </>
              )}
            </QueryBoundary>
            <div className="row-actions">
              <Button
                type="button"
                busy={mutation.isPending}
                disabled={!groupId}
                onClick={() => {
                  if (groupId) mutation.mutate();
                }}
              >
                Einladen
              </Button>
              <Button type="button" variant="ghost" onClick={close}>
                Abbrechen
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </>
  );
}
