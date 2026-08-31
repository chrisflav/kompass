import { useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  formatDate,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type LoginUserBrief = components["schemas"]["LoginUserBrief"];
type LoginUserOut = components["schemas"]["LoginUserOut"];
type AuthGroupBrief = components["schemas"]["AuthGroupBrief"];

const yesNo = (v: boolean) => (v ? <Badge tone="success">Ja</Badge> : <Badge>Nein</Badge>);

/* --- list ---------------------------------------------------------------- */

export function UsersList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["auth", "users"], () =>
    unwrap(client.GET("/api/logindata/users")),
  );
  const rows = query.data ?? [];

  const config: ListViewConfig<LoginUserBrief> = useMemo(
    () => ({
      search: (u) => [u.username, u.member_name ?? "", u.groups.join(" ")],
      filters: [
        {
          key: "active",
          label: "Aktiv",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (u, v) => (v === "yes") === Boolean(u.is_active),
        },
        {
          key: "staff",
          label: "Kompass-Zugang",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (u, v) => (v === "yes") === Boolean(u.is_staff),
        },
      ],
      sort: {
        username: (u) => u.username,
        member: (u) => u.member_name ?? "",
        last_login: (u) => u.last_login ?? "",
      },
      defaultSort: { key: "username", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Benutzer" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={can("auth.add_user") && <Button onClick={() => setCreating(true)}>Neuer Benutzer</Button>}
      />
      {creating && (
        <Modal title="Neuer Benutzer" onClose={() => setCreating(false)}>
          <UserCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Benutzer sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(u) => u.id}
            onRowClick={(u) => navigate(`/kompass/users/${u.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Benutzername", cell: (u) => u.username, sortKey: "username" },
              { header: "Teilnehmende:r", cell: (u) => u.member_name || "—", sortKey: "member" },
              { header: "Rechtegruppen", cell: (u) => u.groups.join(", ") || "—" },
              { header: "Aktiv", cell: (u) => yesNo(u.is_active) },
              { header: "Kompass-Zugang", cell: (u) => yesNo(u.is_staff) },
              { header: "Administrator", cell: (u) => yesNo(u.is_superuser) },
              {
                header: "Zuletzt angemeldet",
                cell: (u) => (u.last_login ? formatDate(u.last_login) : "—"),
                sortKey: "last_login",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

function UserCreateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password1, setPassword1] = useState("");
  const [password2, setPassword2] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const create = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/users", {
          body: { username, password1, password2 },
        }),
      ),
    {
      invalidate: [["auth", "users"]],
      onSuccess: (created: LoginUserOut) => {
        toast.success("Benutzer angelegt.");
        onDone();
        navigate(`/kompass/users/${created.id}`);
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
        create.mutate(undefined);
      }}
    >
      <Field label="Benutzername *">
        <input value={username} onChange={(e) => setUsername(e.target.value)} required />
        {fieldErrors.username && (
          <div className="field-error">{fieldErrors.username.join(" ")}</div>
        )}
      </Field>
      <Field label="Passwort *">
        <input
          type="password"
          value={password1}
          onChange={(e) => setPassword1(e.target.value)}
          required
        />
        {fieldErrors.password1 && (
          <div className="field-error">{fieldErrors.password1.join(" ")}</div>
        )}
      </Field>
      <Field label="Passwort wiederholen *">
        <input
          type="password"
          value={password2}
          onChange={(e) => setPassword2(e.target.value)}
          required
        />
        {fieldErrors.password2 && (
          <div className="field-error">{fieldErrors.password2.join(" ")}</div>
        )}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={create.isPending} disabled={!username.trim() || !password1}>
          Anlegen
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}

/* --- detail -------------------------------------------------------------- */

export function UserDetailPage() {
  const { id } = useParams();
  const userId = Number(id);
  const query = useApiQuery(["auth", "users", userId], () =>
    unwrap(
      client.GET("/api/logindata/users/{user_id}", { params: { path: { user_id: userId } } }),
    ),
  );
  return (
    <QueryBoundary query={query}>{(user: LoginUserOut) => <UserDetailBody user={user} />}</QueryBoundary>
  );
}

function UserDetailBody({ user }: { user: LoginUserOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const [editing, setEditing] = useState(false);
  const [settingPassword, setSettingPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState(() => ({
    username: user.username,
    is_active: user.is_active,
    is_staff: user.is_staff,
    is_superuser: user.is_superuser,
    group_ids: user.groups.map((g) => g.id),
  }));

  const groups = useApiQuery(["auth", "permission-groups"], () =>
    unwrap(client.GET("/api/logindata/permission-groups")),
  );

  const save = useApiMutation(
    () =>
      unwrap(
        client.PATCH("/api/logindata/users/{user_id}", {
          params: { path: { user_id: user.id } },
          body: form,
        }),
      ),
    {
      invalidate: [["auth", "users"], ["auth", "users", user.id]],
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
        client.DELETE("/api/logindata/users/{user_id}", {
          params: { path: { user_id: user.id } },
        }),
      ),
    {
      invalidate: [["auth", "users"]],
      onSuccess: () => {
        toast.success("Benutzer gelöscht.");
        navigate("/kompass/users");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const checkbox = (key: "is_active" | "is_staff" | "is_superuser") => (
    <input
      type="checkbox"
      checked={form[key]}
      onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
    />
  );

  const rows: DetailRow[] = [
    {
      label: "Benutzername",
      field: "username",
      value: user.username,
      edit: (
        <input
          value={form.username}
          onChange={(e) => setForm({ ...form, username: e.target.value })}
        />
      ),
    },
    {
      label: "Teilnehmende:r",
      value: user.member_id ? (
        <Link to={`/kompass/members/${user.member_id}`}>{user.member_name}</Link>
      ) : (
        "—"
      ),
    },
    { label: "Aktiv", field: "is_active", value: yesNo(user.is_active), edit: checkbox("is_active") },
    {
      label: "Kompass-Zugang",
      field: "is_staff",
      value: yesNo(user.is_staff),
      edit: checkbox("is_staff"),
      hint: "Ohne diesen Haken kann sich die Person nicht in Kompass anmelden.",
    },
    {
      label: "Administrator",
      field: "is_superuser",
      value: yesNo(user.is_superuser),
      edit: checkbox("is_superuser"),
      hint: "Administratoren haben alle Rechte, unabhängig von den Rechtegruppen.",
    },
    {
      label: "Rechtegruppen",
      field: "groups",
      value: user.groups.length ? user.groups.map((g) => g.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={(groups.data ?? []).map((g: AuthGroupBrief) => ({
            value: g.id,
            label: g.name,
          }))}
          selected={form.group_ids}
          onChange={(group_ids) => setForm({ ...form, group_ids })}
          placeholder="Rechtegruppe hinzufügen"
        />
      ),
    },
    { label: "Angelegt am", value: user.date_joined ? formatDate(user.date_joined) : "—" },
    { label: "Zuletzt angemeldet", value: user.last_login ? formatDate(user.last_login) : "—" },
  ];

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        save.mutate(undefined);
      }}
    >
      <PageHeader
        breadcrumbs={[{ label: "Benutzer", to: "/kompass/users" }, { label: user.username }]}
        actions={
          editing ? (
            <>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button type="submit" busy={save.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              {can("auth.change_user") && (
                <Button type="button" variant="ghost" onClick={() => setSettingPassword(true)}>
                  Passwort setzen
                </Button>
              )}
              {can("auth.delete_user") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={remove.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `Benutzerkonto „${user.username}“ wirklich löschen?`,
                        danger: true,
                        confirmLabel: "Löschen",
                      })
                    )
                      remove.mutate(undefined);
                  }}
                >
                  Löschen
                </Button>
              )}
              {can("auth.change_user") && (
                <Button
                  type="button"
                  onClick={() => {
                    setForm({
                      username: user.username,
                      is_active: user.is_active,
                      is_staff: user.is_staff,
                      is_superuser: user.is_superuser,
                      group_ids: user.groups.map((g) => g.id),
                    });
                    setFieldErrors({});
                    setEditing(true);
                  }}
                >
                  Bearbeiten
                </Button>
              )}
            </>
          )
        }
      />
      <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
      {settingPassword && (
        <SetPasswordModal user={user} onClose={() => setSettingPassword(false)} />
      )}
    </form>
  );
}

function SetPasswordModal({ user, onClose }: { user: LoginUserOut; onClose: () => void }) {
  const toast = useToast();
  const [p1, setP1] = useState("");
  const [p2, setP2] = useState("");
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const mutation = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/users/{user_id}/set-password", {
          params: { path: { user_id: user.id } },
          body: { new_password1: p1, new_password2: p2 },
        }),
      ),
    {
      onSuccess: () => {
        toast.success("Passwort gesetzt.");
        onClose();
      },
      onError: (e: Error) => {
        if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
        toast.error(e.message);
      },
    },
  );

  return (
    <Modal title={`Passwort für ${user.username} setzen`} onClose={onClose} size="sm">
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          setFieldErrors({});
          mutation.mutate(undefined);
        }}
      >
        <Field label="Neues Passwort *">
          <input type="password" value={p1} onChange={(e) => setP1(e.target.value)} required />
          {fieldErrors.new_password1 && (
            <div className="field-error">{fieldErrors.new_password1.join(" ")}</div>
          )}
        </Field>
        <Field label="Passwort wiederholen *">
          <input type="password" value={p2} onChange={(e) => setP2(e.target.value)} required />
          {fieldErrors.new_password2 && (
            <div className="field-error">{fieldErrors.new_password2.join(" ")}</div>
          )}
        </Field>
        <div className="row-actions">
          <Button type="submit" busy={mutation.isPending} disabled={!p1 || !p2}>
            Passwort setzen
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
  );
}
