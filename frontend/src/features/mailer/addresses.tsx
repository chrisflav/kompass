import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useRowHints } from "../../api/helpTexts";
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
import { MultiSelect, type Option } from "./selects";

type EmailAddressBrief = components["schemas"]["EmailAddressBrief"];
type EmailAddressOut = components["schemas"]["EmailAddressOut"];
type EmailAddressIn = components["schemas"]["EmailAddressIn"];

/* --- list ---------------------------------------------------------------- */

export function EmailAddressesList() {
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["mailer", "email-addresses"], () =>
    unwrap(client.GET("/api/mailer/email-addresses")),
  );
  const rows = query.data ?? [];

  // Admin has no search_fields / list_filter; ordering = name.
  const config: ListViewConfig<EmailAddressBrief> = useMemo(
    () => ({
      sort: {
        name: (a) => a.name,
        email: (a) => a.email,
        internal_only: (a) => a.internal_only,
      },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "E-Mail-Adressen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={<Button onClick={() => setCreating(true)}>Neue Adresse</Button>}
      />
      {creating && (
        <Modal title="Neue E-Mail-Adresse" onClose={() => setCreating(false)}>
          <EmailAddressForm
            initial={emptyAddress()}
            submitLabel="Anlegen"
            onSubmit={(body) => unwrap(client.POST("/api/mailer/email-addresses", { body }))}
            onSuccess={(a) => {
              setCreating(false);
              navigate(`/app/mailer/addresses/${a.id}`);
            }}
            onCancel={() => setCreating(false)}
          />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine E-Mail-Adressen vorhanden.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(a) => a.id}
            onRowClick={(a) => navigate(`/app/mailer/addresses/${a.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (a) => a.name, sortKey: "name" },
              { header: "E-Mail", cell: (a) => a.email, sortKey: "email" },
              {
                header: "Intern",
                cell: (a) =>
                  a.internal_only ? <Badge tone="info">Nur intern</Badge> : "—",
                sortKey: "internal_only",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail -------------------------------------------------------------- */

export function EmailAddressDetailPage() {
  const { id } = useParams();
  const addressId = Number(id);
  const query = useApiQuery(["mailer", "email-addresses", addressId], () =>
    unwrap(
      client.GET("/api/mailer/email-addresses/{address_id}", {
        params: { path: { address_id: addressId } },
      }),
    ),
  );

  const crumbs: Crumb[] = [
    { label: "E-Mail-Adressen", to: "/app/mailer/addresses" },
    { label: query.data?.name ?? "E-Mail-Adresse" },
  ];

  return (
    <QueryBoundary query={query}>
      {(address: EmailAddressOut) => (
        <EmailAddressDetailBody address={address} crumbs={crumbs} />
      )}
    </QueryBoundary>
  );
}

function EmailAddressDetailBody({
  address,
  crumbs,
}: {
  address: EmailAddressOut;
  crumbs: Crumb[];
}) {
  // Attach recovered model help_text to each row by its backend field name.
  const withHints = useRowHints();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<AddressFormState>(() => addressToForm(address));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const navigate = useNavigate();
  const toast = useToast();
  const confirm = useConfirmDialog();

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groups = useApiQuery(["members", "groups"], () =>
    unwrap(client.GET("/api/members/groups")),
  );

  const mutation = useApiMutation(
    (body: EmailAddressIn) =>
      unwrap(
        client.PUT("/api/mailer/email-addresses/{address_id}", {
          params: { path: { address_id: address.id } },
          body,
        }),
      ),
    {
      invalidate: [
        ["mailer", "email-addresses"],
        ["mailer", "email-addresses", address.id],
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
        client.DELETE("/api/mailer/email-addresses/{address_id}", {
          params: { path: { address_id: address.id } },
        }),
      ),
    {
      invalidate: [["mailer", "email-addresses"]],
      onSuccess: () => {
        toast.success("Adresse gelöscht.");
        navigate("/app/mailer/addresses");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  function startEditing() {
    setForm(addressToForm(address));
    setFieldErrors({});
    setEditing(true);
  }

  const memberOptions: Option[] = (members.data ?? []).map((m) => ({ value: m.id, label: m.name }));
  const groupOptions: Option[] = (groups.data ?? []).map((g) => ({ value: g.id, label: g.name }));

  const rows: DetailRow[] = [
    {
      label: "Name",
      field: "name",
      value: address.name,
      edit: (
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
      ),
    },
    { label: "E-Mail", value: address.email },
    {
      label: "Nur intern",
      field: "internal_only",
      value: address.internal_only ? <Badge tone="info">Ja</Badge> : "Nein",
      edit: (
        <input
          type="checkbox"
          checked={form.internal_only}
          onChange={(e) => setForm({ ...form, internal_only: e.target.checked })}
        />
      ),
    },
    { label: "Weiterleitungen", value: address.forwards.join(", ") || "—" },
    {
      label: "Teilnehmende",
      field: "to_members",
      value: address.to_members.map((m) => m.name).join(", ") || "—",
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
      label: "Gruppen",
      field: "to_groups",
      value: address.to_groups.map((g) => g.name).join(", ") || "—",
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
      label: "Erlaubte Absender",
      field: "allowed_senders",
      value: address.allowed_senders.map((g) => g.name).join(", ") || "—",
      edit: (
        <MultiSelect
          options={groupOptions}
          selected={form.allowed_senders}
          onChange={(v) => setForm({ ...form, allowed_senders: v })}
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
        mutation.mutate(form);
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
              <Button
                type="button"
                variant="danger"
                busy={deletion.isPending}
                onClick={async () => {
                  if (
                    await confirm({
                      message: "Adresse wirklich löschen?",
                      danger: true,
                      confirmLabel: "Löschen",
                    })
                  )
                    deletion.mutate(undefined);
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
      <EditableDetail rows={withHints(rows, "emailaddress")} editing={editing} errors={fieldErrors} />
    </form>
  );
}

/* --- shared form --------------------------------------------------------- */

type AddressFormState = EmailAddressIn;

function emptyAddress(): AddressFormState {
  return {
    name: "",
    internal_only: false,
    to_members: [],
    to_groups: [],
    allowed_senders: [],
  };
}

function addressToForm(a: EmailAddressOut): AddressFormState {
  return {
    name: a.name,
    internal_only: a.internal_only,
    to_members: a.to_members.map((m) => m.id),
    to_groups: a.to_groups.map((g) => g.id),
    allowed_senders: a.allowed_senders.map((g) => g.id),
  };
}

function EmailAddressForm({
  initial,
  submitLabel,
  onSubmit,
  onSuccess,
  onCancel,
  invalidate = [["mailer", "email-addresses"]],
}: {
  initial: AddressFormState;
  submitLabel: string;
  onSubmit: (body: EmailAddressIn) => Promise<EmailAddressOut>;
  onSuccess: (a: EmailAddressOut) => void;
  onCancel?: () => void;
  invalidate?: unknown[][];
}) {
  const toast = useToast();
  const [form, setForm] = useState<AddressFormState>(initial);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const members = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groups = useApiQuery(["members", "groups"], () =>
    unwrap(client.GET("/api/members/groups")),
  );

  const mutation = useApiMutation((body: EmailAddressIn) => onSubmit(body), {
    invalidate,
    onSuccess: (a) => {
      toast.success("Gespeichert.");
      onSuccess(a);
    },
    onError: (e: Error) => {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      toast.error(e.message);
    },
  });

  const memberOptions: Option[] = (members.data ?? []).map((m) => ({ value: m.id, label: m.name }));
  const groupOptions: Option[] = (groups.data ?? []).map((g) => ({ value: g.id, label: g.name }));

  return (
    <form
      className="stack"
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        mutation.mutate(form);
      }}
    >
      <Field label="Name" hint="Ergibt zusammen mit der Domain die Adresse.">
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          required
        />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
      </Field>
      <Field label="Nur interne Absender">
        <input
          type="checkbox"
          checked={form.internal_only}
          onChange={(e) => setForm({ ...form, internal_only: e.target.checked })}
        />
      </Field>
      <Field
        label="Weiterleiten an Gruppen"
        hint="Gruppe oder mindestens eine teilnehmende Person ist erforderlich."
      >
        <MultiSelect
          options={groupOptions}
          selected={form.to_groups}
          onChange={(v) => setForm({ ...form, to_groups: v })}
          placeholder="Gruppe hinzufügen"
        />
        {fieldErrors.to_groups && (
          <div className="field-error">{fieldErrors.to_groups.join(" ")}</div>
        )}
      </Field>
      <Field label="Weiterleiten an Teilnehmende">
        <MultiSelect
          options={memberOptions}
          selected={form.to_members}
          onChange={(v) => setForm({ ...form, to_members: v })}
          placeholder="Teilnehmende hinzufügen"
        />
        {fieldErrors.to_members && (
          <div className="field-error">{fieldErrors.to_members.join(" ")}</div>
        )}
      </Field>
      <Field label="Erlaubte Absender-Gruppen">
        <MultiSelect
          options={groupOptions}
          selected={form.allowed_senders}
          onChange={(v) => setForm({ ...form, allowed_senders: v })}
          placeholder="Gruppe hinzufügen"
        />
        {fieldErrors.allowed_senders && (
          <div className="field-error">{fieldErrors.allowed_senders.join(" ")}</div>
        )}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          {submitLabel}
        </Button>
        {onCancel && (
          <Button type="button" variant="ghost" onClick={onCancel}>
            Abbrechen
          </Button>
        )}
      </div>
    </form>
  );
}
