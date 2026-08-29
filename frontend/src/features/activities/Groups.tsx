import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  DownloadButton,
  EditableDetail,
  Field,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useToast,
  type DetailRow,
} from "../../components/ui";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft, type DraftRow } from "../../components/inlineDraft";
import { ChoiceSelect, MultiSelect, WEEKDAY_OPTIONS, type Option } from "./_controls";
import type { components } from "../../api/schema";

type GroupOut = components["schemas"]["GroupOut"];
type GroupCreate = components["schemas"]["GroupCreate"];
type GroupUpdate = components["schemas"]["GroupUpdate"];
type RegistrationPasswordCreate = components["schemas"]["RegistrationPasswordCreate"];
type PermissionGroupUpdate = components["schemas"]["PermissionGroupUpdate"];

/* --- list ----------------------------------------------------------------
 * Admin GroupAdmin: list_display (name, year_from, year_to), search_fields
 * (name), ordering (name). The SPA list is richer (weekday/time/age/website);
 * we add the name search + sortable name and default to name ascending. */

export function GroupsList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const rows = query.data ?? [];

  const config: ListViewConfig<GroupOut> = useMemo(
    () => ({
      search: (g) => [g.name],
      filters: [
        {
          key: "website",
          label: "Webseite",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (g, v) => (v === "yes") === Boolean(g.show_website),
        },
      ],
      sort: {
        name: (g) => g.name,
        year_from: (g) => g.year_from,
        year_to: (g) => g.year_to,
      },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Gruppen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          <div className="row-actions">
            <Button onClick={() => setCreating(true)}>Neue Gruppe</Button>
            <DownloadButton
              path="/api/members/documents/groups/overview"
              method="POST"
              filename="Gruppenuebersicht.xlsx"
            >
              Übersicht (xlsx)
            </DownloadButton>
            <DownloadButton
              path="/api/members/documents/groups/checklist"
              method="POST"
              filename="Gruppen-Checkliste.pdf"
            >
              Checkliste (pdf)
            </DownloadButton>
          </div>
        }
      />
      {creating && (
        <Modal title="Neue Gruppe" onClose={() => setCreating(false)}>
          <GroupCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Gruppen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(g) => g.id}
            onRowClick={(g) => navigate(`/app/groups/${g.id}/members`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (g) => g.name, sortKey: "name" },
              { header: "Wochentag", cell: (g) => g.weekday_display || "—" },
              { header: "Zeit", cell: (g) => g.time_info || "—" },
              { header: "Jahrgänge", cell: (g) => g.age_info || "—" },
              { header: "Ab Jahrgang", cell: (g) => g.year_from, sortKey: "year_from" },
              { header: "Bis Jahrgang", cell: (g) => g.year_to, sortKey: "year_to" },
              {
                header: "Webseite",
                cell: (g) =>
                  g.show_website ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>,
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function GroupCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [yearFrom, setYearFrom] = useState("");
  const [yearTo, setYearTo] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    (body: GroupCreate) => unwrap(client.POST("/api/members/groups", { body })),
    {
      invalidate: [["groups"]],
      onSuccess: (created: GroupOut) => {
        toast.success("Gruppe angelegt.");
        onDone();
        navigate(`/app/groups/${created.id}`);
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
        mutation.mutate({
          name,
          description: description || null,
          year_from: yearFrom === "" ? null : Number(yearFrom),
          year_to: yearTo === "" ? null : Number(yearTo),
          leiter_ids: [],
        });
      }}
    >
      <Field label="Name">
        <input value={name} onChange={(e) => setName(e.target.value)} required />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
      </Field>
      <Field label="Beschreibung">
        <textarea value={description} onChange={(e) => setDescription(e.target.value)} />
        {fieldErrors.description && (
          <div className="field-error">{fieldErrors.description.join(" ")}</div>
        )}
      </Field>
      <Field label="Ab Jahrgang">
        <input
          type="number"
          value={yearFrom}
          onChange={(e) => setYearFrom(e.target.value)}
        />
        {fieldErrors.year_from && (
          <div className="field-error">{fieldErrors.year_from.join(" ")}</div>
        )}
      </Field>
      <Field label="Bis Jahrgang">
        <input type="number" value={yearTo} onChange={(e) => setYearTo(e.target.value)} />
        {fieldErrors.year_to && (
          <div className="field-error">{fieldErrors.year_to.join(" ")}</div>
        )}
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

export function GroupDetailPage() {
  const { id } = useParams();
  const groupId = Number(id);
  const query = useApiQuery(["groups", groupId], () =>
    unwrap(
      client.GET("/api/members/groups/{group_id}", {
        params: { path: { group_id: groupId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(group: GroupOut) => <GroupDetailBody group={group} />}
    </QueryBoundary>
  );
}

function makeForm(group: GroupOut) {
  return {
    name: group.name,
    description: group.description ?? "",
    show_website: group.show_website,
    year_from: String(group.year_from),
    year_to: String(group.year_to),
    weekday: group.weekday === null || group.weekday === undefined ? "" : String(group.weekday),
    start_time: group.start_time ?? "",
    end_time: group.end_time ?? "",
    show_website_year: group.show_website_year,
    show_website_weekday: group.show_website_weekday,
    show_website_time: group.show_website_time,
    show_website_contact_email: group.show_website_contact_email,
    contact_email_id:
      group.contact_email === null || group.contact_email === undefined
        ? ""
        : String(group.contact_email),
    leiter_ids: group.leiters.map((l) => l.id),
  };
}

function GroupDetailBody({ group }: { group: GroupOut }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeForm(group));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  // Options for the editable relations. `leiters` is Jugendleiter-restricted in
  // the admin form; the API has no filtered member endpoint, so we offer every
  // visible member here. BACKEND-GAP: no Jugendleiter-only member endpoint.
  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const emailsQuery = useApiQuery(
    ["mailer", "email-addresses"],
    () => unwrap(client.GET("/api/mailer/email-addresses")),
    { enabled: editing },
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );
  const emailOptions = useMemo(
    () => (emailsQuery.data ?? []).map((e) => ({ value: e.id, label: `${e.name} <${e.email}>` })),
    [emailsQuery.data],
  );

  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

  const mutation = useApiMutation(
    (body: GroupUpdate) =>
      unwrap(
        client.PATCH("/api/members/groups/{group_id}", {
          params: { path: { group_id: group.id } },
          body,
        }),
      ),
    { invalidate: [["groups"], ["groups", group.id]] },
  );

  function startEditing() {
    setForm(makeForm(group));
    setFieldErrors({});
    setEditing(true);
  }

  const bool = (v: boolean) => (v ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>);
  const checkbox = (key: keyof typeof form) => (
    <input
      type="checkbox"
      checked={Boolean(form[key])}
      onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
    />
  );

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: group.name,
      edit: (
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      ),
    },
    {
      label: "Beschreibung",
      field: "description",
      value: group.description || "—",
      edit: (
        <textarea
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      ),
    },
    {
      label: "Leiter*innen",
      field: "leiters",
      value: group.leiters.length ? group.leiters.map((l) => l.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.leiter_ids}
          onChange={(ids) => setForm({ ...form, leiter_ids: ids })}
          searchable
        />
      ),
    },
    {
      label: "Auf der Webseite",
      field: "show_website",
      value: bool(group.show_website),
      edit: checkbox("show_website"),
    },
    {
      label: "Ab Jahrgang",
      field: "year_from",
      value: group.year_from,
      edit: (
        <input
          type="number"
          value={form.year_from}
          onChange={(e) => setForm({ ...form, year_from: e.target.value })}
        />
      ),
    },
    {
      label: "Bis Jahrgang",
      field: "year_to",
      value: group.year_to,
      edit: (
        <input
          type="number"
          value={form.year_to}
          onChange={(e) => setForm({ ...form, year_to: e.target.value })}
        />
      ),
    },
    { label: "Jahrgänge (berechnet)", value: group.age_info || "—" },
    {
      label: "Jahrgänge auf Webseite",
      field: "show_website_year",
      value: bool(group.show_website_year),
      edit: checkbox("show_website_year"),
    },
    {
      label: "Kontakt-E-Mail",
      field: "contact_email",
      value: group.contact_email_display || "—",
      edit: (
        <Select
          value={form.contact_email_id}
          onChange={(v) => setForm({ ...form, contact_email_id: v })}
          options={emailOptions}
          placeholder="—"
          allowEmpty
          emptyLabel="—"
        />
      ),
    },
    {
      label: "Kontakt-E-Mail auf Webseite",
      field: "show_website_contact_email",
      value: bool(group.show_website_contact_email),
      edit: checkbox("show_website_contact_email"),
    },
    {
      label: "Wochentag",
      field: "weekday",
      value: group.weekday_display || "—",
      edit: (
        <ChoiceSelect
          value={form.weekday}
          onChange={(v) => setForm({ ...form, weekday: v })}
          options={WEEKDAY_OPTIONS}
          allowEmpty
        />
      ),
    },
    {
      label: "Wochentag auf Webseite",
      field: "show_website_weekday",
      value: bool(group.show_website_weekday),
      edit: checkbox("show_website_weekday"),
    },
    {
      label: "Zeit",
      field: "start_time",
      value: group.time_info || "—",
      edit: (
        <div className="stack">
          <input
            type="time"
            value={form.start_time}
            onChange={(e) => setForm({ ...form, start_time: e.target.value })}
          />
          <input
            type="time"
            value={form.end_time}
            onChange={(e) => setForm({ ...form, end_time: e.target.value })}
          />
        </div>
      ),
    },
    {
      label: "Zeit auf Webseite",
      field: "show_website_time",
      value: bool(group.show_website_time),
      edit: checkbox("show_website_time"),
    },
  ];

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setFieldErrors({});
        setSaving(true);
        try {
          await mutation.mutateAsync({
            name: form.name,
            description: form.description,
            show_website: form.show_website,
            year_from: Number(form.year_from),
            year_to: Number(form.year_to),
            weekday: form.weekday === "" ? null : Number(form.weekday),
            start_time: form.start_time || null,
            end_time: form.end_time || null,
            show_website_year: form.show_website_year,
            show_website_weekday: form.show_website_weekday,
            show_website_time: form.show_website_time,
            show_website_contact_email: form.show_website_contact_email,
            contact_email_id: form.contact_email_id === "" ? null : Number(form.contact_email_id),
            leiter_ids: form.leiter_ids,
          });
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
        breadcrumbs={[{ label: "Gruppen", to: "/app/groups" }, { label: group.name }]}
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
            id: "passwoerter",
            label: "Registrierungspasswörter",
            content: <RegistrationPasswordsInline groupId={group.id} editing={editing} registerFlush={getRegistrar("passwords")} />,
          },
          {
            id: "berechtigungen",
            label: "Gruppenberechtigungen",
            content: <PermissionGroupsInline groupId={group.id} editing={editing} registerFlush={getRegistrar("permissions")} />,
          },
        ]}
      />
    </form>
  );
}

/**
 * Registration-password inline (Django `RegistrationPasswordInline`). A group
 * may have several passwords; supports add, per-row password edit and delete.
 */
type PasswordData = { password: string };

function RegistrationPasswordsInline({
  groupId,
  editing,
  registerFlush,
}: {
  groupId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const invalidate = [["groups", groupId, "registration-passwords"]];
  const listQuery = useApiQuery(["groups", groupId, "registration-passwords"], () =>
    unwrap(
      client.GET("/api/members/groups/{group_id}/registration-passwords", {
        params: { path: { group_id: groupId } },
      }),
    ),
  );
  const createM = useApiMutation(
    (body: RegistrationPasswordCreate) =>
      unwrap(
        client.POST("/api/members/groups/{group_id}/registration-passwords", {
          params: { path: { group_id: groupId } },
          body,
        }),
      ),
    { invalidate },
  );
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/registration-passwords/{password_id}", {
          params: { path: { password_id: id } },
        }),
      ),
    { invalidate },
  );
  const patchM = useApiMutation(
    (vars: { id: number; password: string }) =>
      unwrap(
        client.PATCH("/api/members/registration-passwords/{password_id}", {
          params: { path: { password_id: vars.id } },
          body: { password: vars.password },
        }),
      ),
    { invalidate },
  );

  const serverRows = (listQuery.data ?? []).map((r) => ({
    id: r.id,
    data: { password: r.password ?? "" } as PasswordData,
  }));
  const { rows, setRow, removeRow, addRow } = useInlineDraft<PasswordData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync({ password: d.password }),
    update: (id, d) => patchM.mutateAsync({ id, password: d.password }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });
  const [adding, setAdding] = useState<PasswordData | null>(null);

  return (
    <>
      <InlineTable
        title="Registrierungspasswörter"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ password: "" })}
        addLabel="Passwort"
        columns={[
          {
            header: "Passwort",
            cell: (row) =>
              editing ? (
                <input
                  value={row.data.password}
                  onChange={(e) => setRow(row, { password: e.target.value })}
                />
              ) : (
                row.data.password || "—"
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Registrierungspasswort hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Passwort">
              <input
                value={adding.password}
                onChange={(e) => setAdding({ password: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={adding.password.trim() === ""}
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

type PermGroupData = {
  list_member_ids: number[];
  view_member_ids: number[];
  change_member_ids: number[];
  delete_member_ids: number[];
  list_group_ids: number[];
  view_group_ids: number[];
  change_group_ids: number[];
  delete_group_ids: number[];
};

const emptyPermGroup: PermGroupData = {
  list_member_ids: [],
  view_member_ids: [],
  change_member_ids: [],
  delete_member_ids: [],
  list_group_ids: [],
  view_group_ids: [],
  change_group_ids: [],
  delete_group_ids: [],
};

/** The 8 ACL relations of a `PermissionGroup`, keyed by the API field name. */
const PERM_MEMBER_FIELDS: { field: keyof PermGroupData; label: string }[] = [
  { field: "list_member_ids", label: "Darf folgende Teilnehmer*innen listen" },
  { field: "view_member_ids", label: "Darf folgende Teilnehmer*innen anzeigen" },
  { field: "change_member_ids", label: "Darf folgende Teilnehmer*innen ändern" },
  { field: "delete_member_ids", label: "Darf folgende Teilnehmer*innen löschen" },
];
const PERM_GROUP_FIELDS: { field: keyof PermGroupData; label: string }[] = [
  { field: "list_group_ids", label: "Darf Teilnehmer*innen folgender Gruppen listen" },
  { field: "view_group_ids", label: "Darf Teilnehmer*innen folgender Gruppen anzeigen" },
  { field: "change_group_ids", label: "Darf Teilnehmer*innen folgender Gruppen ändern" },
  { field: "delete_group_ids", label: "Darf Teilnehmer*innen folgender Gruppen löschen" },
];

/**
 * Group-permissions inline (Django `PermissionOnGroupInline`). SENSITIVE: each
 * `PermissionGroup` grants ACL access (list/view/change/delete) over this
 * group's members to selected members and to members of selected groups.
 * `group` is a one-to-one relation, so there is at most one row; the target
 * selects are edited in place and everything is applied on the main Save.
 */
function PermissionGroupsInline({
  groupId,
  editing,
  registerFlush,
}: {
  groupId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const invalidate = [["groups", groupId, "permission-groups"]];
  const listQuery = useApiQuery(["groups", groupId, "permission-groups"], () =>
    unwrap(
      client.GET("/api/members/groups/{group_id}/permission-groups", {
        params: { path: { group_id: groupId } },
      }),
    ),
  );
  // Members/groups are needed both for the editable selects and to resolve the
  // read-only summary names; fetched under the shared cache keys.
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );
  const groupOptions: Option[] = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );
  const memberNames = useMemo(
    () => new Map(memberOptions.map((o) => [o.value, o.label])),
    [memberOptions],
  );
  const groupNames = useMemo(
    () => new Map(groupOptions.map((o) => [o.value, o.label])),
    [groupOptions],
  );

  const createM = useApiMutation(
    (body: PermissionGroupUpdate) =>
      unwrap(
        client.POST("/api/members/groups/{group_id}/permission-groups", {
          params: { path: { group_id: groupId } },
          body,
        }),
      ),
    { invalidate },
  );
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/permission-groups/{permission_group_id}", {
          params: { path: { permission_group_id: id } },
        }),
      ),
    { invalidate },
  );
  const patchM = useApiMutation(
    (vars: { id: number; body: PermissionGroupUpdate }) =>
      unwrap(
        client.PATCH("/api/members/permission-groups/{permission_group_id}", {
          params: { path: { permission_group_id: vars.id } },
          body: vars.body,
        }),
      ),
    { invalidate },
  );

  const serverRows = (listQuery.data ?? []).map((r) => ({
    id: r.id,
    data: {
      list_member_ids: r.list_member_ids ?? [],
      view_member_ids: r.view_member_ids ?? [],
      change_member_ids: r.change_member_ids ?? [],
      delete_member_ids: r.delete_member_ids ?? [],
      list_group_ids: r.list_group_ids ?? [],
      view_group_ids: r.view_group_ids ?? [],
      change_group_ids: r.change_group_ids ?? [],
      delete_group_ids: r.delete_group_ids ?? [],
    } as PermGroupData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<PermGroupData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(d as PermissionGroupUpdate),
    update: (id, d) => patchM.mutateAsync({ id, body: d as PermissionGroupUpdate }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });

  const namesFor = (ids: number[], map: Map<number, string>) =>
    ids.length ? ids.map((id) => map.get(id) ?? `#${id}`).join(", ") : "—";

  const editSelect = (
    row: DraftRow<PermGroupData>,
    field: keyof PermGroupData,
    label: string,
    options: Option[],
  ) => (
    <div className="stack" key={field}>
      <span className="small">{label}</span>
      <MultiSelect
        options={options}
        selected={row.data[field]}
        onChange={(ids) => setRow(row, { ...row.data, [field]: ids } as PermGroupData)}
        searchable
      />
    </div>
  );

  const summary = (row: DraftRow<PermGroupData>) => (
    <dl className="detail-list">
      {[
        ...PERM_MEMBER_FIELDS.map((f) => ({ ...f, map: memberNames })),
        ...PERM_GROUP_FIELDS.map((f) => ({ ...f, map: groupNames })),
      ]
        .filter((f) => row.data[f.field].length > 0)
        .map((f) => (
          <div key={f.field}>
            <dt>{f.label}</dt>
            <dd>{namesFor(row.data[f.field], f.map)}</dd>
          </div>
        ))}
    </dl>
  );

  return (
    <InlineTable
      title="Gruppenberechtigungen"
      rows={rows}
      rowKey={(row) => row.key}
      editing={editing}
      onDelete={(row) => removeRow(row)}
      onAdd={rows.length === 0 ? () => addRow({ ...emptyPermGroup }) : undefined}
      addLabel="Berechtigungen"
      empty={editing ? "Keine Berechtigungen – oben anlegen." : "Keine Berechtigungen."}
      columns={[
        {
          header: "Berechtigungen",
          cell: (row) =>
            editing ? (
              <div className="stack">
                {PERM_MEMBER_FIELDS.map((f) => editSelect(row, f.field, f.label, memberOptions))}
                {PERM_GROUP_FIELDS.map((f) => editSelect(row, f.field, f.label, groupOptions))}
              </div>
            ) : (
              summary(row)
            ),
        },
      ]}
    />
  );
}
