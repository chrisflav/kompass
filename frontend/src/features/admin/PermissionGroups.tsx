import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Button,
  DataTable,
  EditableDetail,
  Field,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  useConfirmDialog,
  useToast,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type AuthGroupBrief = components["schemas"]["AuthGroupBrief"];
type AuthGroupOut = components["schemas"]["AuthGroupOut"];
type PermissionBrief = components["schemas"]["PermissionBrief"];

/* --- list ---------------------------------------------------------------- */

export function PermissionGroupsList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["auth", "permission-groups"], () =>
    unwrap(client.GET("/api/logindata/permission-groups")),
  );
  const rows = query.data ?? [];

  const config: ListViewConfig<AuthGroupBrief> = useMemo(
    () => ({
      search: (g) => [g.name],
      sort: {
        name: (g) => g.name,
        permission_count: (g) => g.permission_count,
        user_count: (g) => g.user_count,
      },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [],
  );
  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Rechtegruppen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("auth.add_group") && <Button onClick={() => setCreating(true)}>Neue Rechtegruppe</Button>
        }
      />
      {creating && (
        <Modal title="Neue Rechtegruppe" onClose={() => setCreating(false)} size="lg">
          <PermissionGroupForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Rechtegruppen sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(g) => g.id}
            onRowClick={(g) => navigate(`/app/permission-groups/${g.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (g) => g.name, sortKey: "name" },
              { header: "Rechte", cell: (g) => g.permission_count, sortKey: "permission_count" },
              { header: "Benutzer", cell: (g) => g.user_count, sortKey: "user_count" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/** Permission picker shared by the create modal and the detail edit form. */
function PermissionPicker({
  selected,
  onChange,
}: {
  selected: number[];
  onChange: (ids: number[]) => void;
}) {
  const permissions = useApiQuery(["auth", "permissions"], () =>
    unwrap(client.GET("/api/logindata/permissions")),
  );
  const options = (permissions.data ?? []).map((p: PermissionBrief) => ({
    value: p.id,
    // The codename is what an administrator recognises from the rules files;
    // the human label alone is ambiguous across apps ("Can add group").
    label: `${p.label} (${p.codename})`,
  }));
  return (
    <MultiSelect
      options={options}
      selected={selected}
      onChange={onChange}
      placeholder="Recht hinzufügen"
      emptyText="Keine passenden Rechte."
    />
  );
}

function PermissionGroupForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [permissionIds, setPermissionIds] = useState<number[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const create = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/logindata/permission-groups", {
          body: { name, permission_ids: permissionIds },
        }),
      ),
    {
      invalidate: [["auth", "permission-groups"]],
      onSuccess: (created: AuthGroupOut) => {
        toast.success("Rechtegruppe angelegt.");
        onDone();
        navigate(`/app/permission-groups/${created.id}`);
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
      <Field label="Name *">
        <input value={name} onChange={(e) => setName(e.target.value)} required />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
      </Field>
      <Field label="Rechte">
        <PermissionPicker selected={permissionIds} onChange={setPermissionIds} />
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={create.isPending} disabled={!name.trim()}>
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

export function PermissionGroupDetailPage() {
  const { id } = useParams();
  const groupId = Number(id);
  const query = useApiQuery(["auth", "permission-groups", groupId], () =>
    unwrap(
      client.GET("/api/logindata/permission-groups/{group_id}", {
        params: { path: { group_id: groupId } },
      }),
    ),
  );
  return (
    <QueryBoundary query={query}>
      {(group: AuthGroupOut) => <PermissionGroupDetailBody group={group} />}
    </QueryBoundary>
  );
}

function PermissionGroupDetailBody({ group }: { group: AuthGroupOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState(() => ({
    name: group.name,
    permission_ids: group.permissions.map((p) => p.id),
  }));

  const save = useApiMutation(
    () =>
      unwrap(
        client.PATCH("/api/logindata/permission-groups/{group_id}", {
          params: { path: { group_id: group.id } },
          body: form,
        }),
      ),
    {
      invalidate: [["auth", "permission-groups"], ["auth", "permission-groups", group.id]],
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
        client.DELETE("/api/logindata/permission-groups/{group_id}", {
          params: { path: { group_id: group.id } },
        }),
      ),
    {
      invalidate: [["auth", "permission-groups"]],
      onSuccess: () => {
        toast.success("Rechtegruppe gelöscht.");
        navigate("/app/permission-groups");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: group.name,
      edit: <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />,
    },
    { label: "Benutzer in dieser Gruppe", value: group.user_count },
    {
      label: "Rechte",
      field: "permissions",
      value: group.permissions.length ? (
        <ul className="plain-list">
          {group.permissions.map((p) => (
            <li key={p.id}>
              {p.label} <code>{p.codename}</code>
            </li>
          ))}
        </ul>
      ) : (
        "—"
      ),
      edit: (
        <PermissionPicker
          selected={form.permission_ids}
          onChange={(permission_ids) => setForm({ ...form, permission_ids })}
        />
      ),
    },
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
        breadcrumbs={[
          { label: "Rechtegruppen", to: "/app/permission-groups" },
          { label: group.name },
        ]}
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
              {can("auth.delete_group") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={remove.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `Rechtegruppe „${group.name}“ wirklich löschen? ${group.user_count} Benutzer verlieren die darin enthaltenen Rechte.`,
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
              {can("auth.change_group") && (
                <Button
                  type="button"
                  onClick={() => {
                    setForm({
                      name: group.name,
                      permission_ids: group.permissions.map((p) => p.id),
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
    </form>
  );
}
