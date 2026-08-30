import { useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { usePermissions } from "../../api/me";
import { useSectionHelp } from "../../api/helpTexts";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Menu,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useConfirmDialog,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type RegistrationBrief = components["schemas"]["RegistrationBrief"];
type MemberOut = components["schemas"]["MemberOut"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

function boolBadge(value: boolean | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value ? <Badge tone="success">Ja</Badge> : <Badge tone="warning">Nein</Badge>;
}

/* --- list ----------------------------------------------------------------
 * Full parity with MemberUnconfirmedAdmin: all list_display columns (name,
 * birth date, age, group, email confirmed, alternative email confirmed,
 * registration form), search over prename/lastname/email, filters (group,
 * email confirmed, alternative email confirmed, registration form). */

export function RegistrationsList() {
  const navigate = useNavigate();
  const query = useApiQuery(["registrations"], () =>
    unwrap(client.GET("/api/members/registrations")),
  );
  const rows = query.data ?? [];

  const groupOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((r) => r.groups.forEach((g) => names.add(g)));
    return [...names].sort().map((g) => ({ value: g, label: g }));
  }, [rows]);

  const config: ListViewConfig<RegistrationBrief> = useMemo(
    () => ({
      search: (r) => [r.name, r.prename, r.lastname, r.email],
      filters: [
        {
          key: "group",
          label: "Gruppe",
          options: groupOptions,
          match: (r, v) => r.groups.includes(v),
        },
        {
          key: "confirmed_mail",
          label: "E-Mail bestätigt",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (r, v) => (v === "yes") === Boolean(r.confirmed_mail),
        },
        {
          key: "confirmed_alternative_mail",
          label: "Alt. E-Mail bestätigt",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (r, v) => (v === "yes") === Boolean(r.confirmed_alternative_mail),
        },
        {
          key: "registration_form",
          label: "Anmeldeformular",
          options: [
            { value: "yes", label: "Hochgeladen" },
            { value: "no", label: "Fehlt" },
          ],
          match: (r, v) => (v === "yes") === Boolean(r.registration_form_uploaded),
        },
      ],
      sort: {
        name: (r) => r.lastname,
        birth_date: (r) => r.birth_date,
        age: (r) => r.age,
        confirmed_mail: (r) => r.confirmed_mail,
      },
      defaultSort: { key: "name", dir: "asc" },
    }),
    [groupOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Registrierungen" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine offenen Registrierungen.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(r) => r.id}
            onRowClick={(r) => navigate(`/app/registrations/${r.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (r) => r.name, sortKey: "name" },
              {
                header: "Geburtsdatum",
                cell: (r) => formatDate(r.birth_date),
                sortKey: "birth_date",
              },
              { header: "Alter", cell: (r) => r.age ?? "—", sortKey: "age" },
              { header: "Gruppen", cell: (r) => r.groups.join(", ") || "—" },
              {
                header: "E-Mail bestätigt",
                cell: (r) => (r.confirmed_mail ? <Badge tone="success">Ja</Badge> : "—"),
                sortKey: "confirmed_mail",
              },
              {
                header: "Alt. E-Mail bestätigt",
                cell: (r) => (r.alternative_email ? boolBadge(r.confirmed_alternative_mail) : "—"),
              },
              {
                header: "Anmeldeformular",
                cell: (r) =>
                  r.registration_form_uploaded ? <Badge tone="success">Ja</Badge> : "—",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail + registration actions --------------------------------------- */

export function RegistrationDetailPage() {
  const { id } = useParams();
  const memberId = Number(id);
  // Registrations are unconfirmed members, which the default /{member_id} route
  // (Member.objects, confirmed-only) 404s on — use the registrations detail route.
  const query = useApiQuery(["registrations", memberId], () =>
    unwrap(
      client.GET("/api/members/registrations/{registration_id}", {
        params: { path: { registration_id: memberId } },
      }),
    ),
  );
  const crumbs: Crumb[] = [
    { label: "Registrierungen", to: "/app/registrations" },
    { label: query.data?.name ?? "Registrierung" },
  ];

  return (
    <QueryBoundary query={query}>
      {(member: MemberOut) => <RegistrationDetailBody member={member} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

/** The subset of fields ``MemberUnconfirmedAdmin``'s change form exposes. */
function makeRegistrationForm(m: MemberOut) {
  return {
    prename: m.prename ?? "",
    lastname: m.lastname ?? "",
    email: m.email ?? "",
    alternative_email: m.alternative_email ?? "",
    phone_number: m.phone_number ?? "",
    birth_date: m.birth_date ?? "",
    gender: String(m.gender ?? ""),
    comments: m.comments ?? "",
    legal_guardians: m.legal_guardians ?? "",
    street: m.street ?? "",
    plz: m.plz ?? "",
    town: m.town ?? "",
    address_extra: m.address_extra ?? "",
    allergies: m.allergies ?? "",
    medication: m.medication ?? "",
    photos_may_be_taken: Boolean(m.photos_may_be_taken),
  };
}

function fileRow(label: string, url: string | null | undefined): DetailRow {
  return {
    label,
    value: url ? (
      <a href={url} target="_blank" rel="noreferrer">
        Öffnen
      </a>
    ) : (
      "—"
    ),
  };
}

/* Grouped display of the MemberUnconfirmed change-view fieldsets, editable in
 * place (the admin's change form) plus the registration workflow actions. */
function RegistrationDetailBody({ member, crumbs }: { member: MemberOut; crumbs: Crumb[] }) {
  const toast = useToast();
  const { can } = usePermissions();
  const [editing, setEditing] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [form, setForm] = useState(() => makeRegistrationForm(member));
  const enumsQuery = useApiQuery(
    ["members", "enums"],
    () => unwrap(client.GET("/api/members/enums")),
    { enabled: editing },
  );
  const genderChoices = enumsQuery.data?.gender ?? [];

  const save = useApiMutation(
    () =>
      unwrap(
        client.PATCH("/api/members/registrations/{registration_id}", {
          params: { path: { registration_id: member.id } },
          body: {
            ...form,
            gender: form.gender === "" ? undefined : Number(form.gender),
            birth_date: form.birth_date || null,
          },
        }),
      ),
    {
      invalidate: [["registrations"], ["registrations", member.id]],
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

  const text = (key: keyof typeof form, type = "text") => (
    <input
      type={type}
      value={String(form[key] ?? "")}
      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
    />
  );
  const area = (key: keyof typeof form) => (
    <textarea
      value={String(form[key] ?? "")}
      onChange={(e) => setForm({ ...form, [key]: e.target.value })}
    />
  );
  const check = (key: keyof typeof form) => (
    <input
      type="checkbox"
      checked={Boolean(form[key])}
      onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
    />
  );

  const mainRows: DetailRow[] = [
    { label: "Name", value: member.name },
    { label: "Vorname", field: "prename", value: member.prename, edit: text("prename") },
    { label: "Nachname", field: "lastname", value: member.lastname, edit: text("lastname") },
    { label: "E-Mail", field: "email", value: member.email || "—", edit: text("email", "email") },
    { label: "E-Mail bestätigt", value: boolBadge(member.confirmed_mail) },
    {
      label: "Alternative E-Mail",
      field: "alternative_email",
      value: member.alternative_email || "—",
      edit: text("alternative_email", "email"),
    },
    { label: "Alternative E-Mail bestätigt", value: boolBadge(member.confirmed_alternative_mail) },
    {
      label: "Telefon",
      field: "phone_number",
      value: member.phone_number || "—",
      edit: text("phone_number"),
    },
    {
      label: "Geburtsdatum",
      field: "birth_date",
      value: formatDate(member.birth_date),
      edit: text("birth_date", "date"),
    },
    { label: "Alter", value: member.age ?? "—" },
    {
      label: "Geschlecht",
      field: "gender",
      value: member.gender_display || member.gender_str,
      edit: (
        <Select
          value={String(form.gender)}
          onChange={(v) => setForm({ ...form, gender: v })}
          options={genderChoices.map((c) => ({ value: String(c.value), label: c.label }))}
        />
      ),
    },
    {
      label: "Gruppen",
      value: member.groups.length ? member.groups.map((g) => g.name).join(", ") : "—",
    },
    fileRow("Anmeldeformular", member.registration_form),
    fileRow("Bild", member.image),
    { label: "Eintrittsdatum", value: formatDate(member.join_date) },
    { label: "Austrittsdatum", value: formatDate(member.leave_date) },
    {
      label: "Kommentare",
      field: "comments",
      value: member.comments || "—",
      edit: area("comments"),
    },
    {
      label: "Erziehungsberechtigte",
      field: "legal_guardians",
      value: member.legal_guardians || "—",
      edit: area("legal_guardians"),
    },
    { label: "DAV-Ausweisnummer", value: member.dav_badge_no || "—" },
    { label: "Echo erhalten", value: boolBadge(member.echoed) },
    { label: "Nutzer", value: member.user_display || "—" },
    { label: "Bestätigt", value: boolBadge(member.confirmed) },
    { label: "Erstellt", value: formatDate(member.created) },
  ];

  const contactRows: DetailRow[] = [
    {
      label: "Straße und Hausnummer",
      field: "street",
      value: member.street || "—",
      edit: text("street"),
    },
    { label: "PLZ", field: "plz", value: member.plz || "—", edit: text("plz") },
    { label: "Ort", field: "town", value: member.town || "—", edit: text("town") },
    {
      label: "Adresszusatz",
      field: "address_extra",
      value: member.address_extra || "—",
      edit: text("address_extra"),
    },
    { label: "Land", value: member.country || "—" },
    { label: "IBAN", value: member.iban || "—" },
  ];

  const skillsRows: DetailRow[] = [
    { label: "Schwimmabzeichen", value: boolBadge(member.swimming_badge) },
    { label: "Kletterabzeichen", value: member.climbing_badge || "—" },
    { label: "Alpine Erfahrung", value: member.alpine_experience || "—" },
  ];

  const othersRows: DetailRow[] = [
    {
      label: "Allergien",
      field: "allergies",
      value: member.allergies || "—",
      edit: area("allergies"),
    },
    { label: "Tetanusimpfung", value: member.tetanus_vaccination || "—" },
    {
      label: "Medikamente",
      field: "medication",
      value: member.medication || "—",
      edit: area("medication"),
    },
    {
      label: "Fotos dürfen gemacht werden",
      field: "photos_may_be_taken",
      value: boolBadge(member.photos_may_be_taken),
      edit: check("photos_may_be_taken"),
    },
  ];

  const orgRows: DetailRow[] = [
    {
      label: "Führungszeugnis vorgelegt am",
      value: formatDate(member.good_conduct_certificate_presented_date),
    },
    { label: "Führungszeugnis gültig", value: boolBadge(member.good_conduct_certificate_valid) },
    { label: "Schlüssel", value: boolBadge(member.has_key) },
    { label: "Freikarte Halle", value: boolBadge(member.has_free_ticket_gym) },
  ];

  const panel = (rows: DetailRow[]) => (
    <EditableDetail rows={rows} editing={editing} errors={fieldErrors} />
  );

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setFieldErrors({});
        save.mutate(undefined);
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
              <Button type="submit" busy={save.isPending}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <RegistrationActions member={member} />
              {can("members.change_memberunconfirmedproxy") && (
                <Button
                  type="button"
                  onClick={() => {
                    setForm(makeRegistrationForm(member));
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
      <Tabs
        tabs={[
          { id: "stammdaten", label: "Stammdaten", content: panel(mainRows) },
          { id: "kontakt", label: "Kontaktdaten", content: panel(contactRows) },
          { id: "skills", label: "Fähigkeiten", content: panel(skillsRows) },
          { id: "sonstiges", label: "Sonstiges", content: panel(othersRows) },
          { id: "org", label: "Organisatorisch", content: panel(orgRows) },
          {
            id: "notfall",
            label: "Notfallkontakte",
            content: <RegistrationEmergencyContacts registrationId={member.id} />,
          },
        ]}
      />
    </form>
  );
}

/** Read-only emergency contacts for an unconfirmed registration (admin
 * `EmergencyContactInline` on `MemberUnconfirmedAdmin`). */
function RegistrationEmergencyContacts({ registrationId }: { registrationId: number }) {
  const sectionHelp = useSectionHelp();
  const query = useApiQuery(["registrations", registrationId, "emergency-contacts"], () =>
    unwrap(
      client.GET("/api/members/registrations/{registration_id}/emergency-contacts", {
        params: { path: { registration_id: registrationId } },
      }),
    ),
  );
  const note = sectionHelp("emergency-contacts");
  return (
    <div>
      {note && <p className="fieldset-help">{note}</p>}
      <QueryBoundary query={query} empty="Keine Notfallkontakte hinterlegt.">
        {(rows: components["schemas"]["MemberEmergencyContactOut"][]) => (
          <DataTable
            rows={rows}
            rowKey={(c) => c.id}
            columns={[
              { header: "Vorname", cell: (c) => c.prename || "—" },
              { header: "Nachname", cell: (c) => c.lastname || "—" },
              { header: "E-Mail", cell: (c) => c.email || "—" },
              { header: "Telefon", cell: (c) => c.phone_number || "—" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/** Registration workflow actions (mirrors the MemberUnconfirmed admin). */
function RegistrationActions({ member }: { member: MemberOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();

  const confirmMutation = useApiMutation<MemberOut, void>(
    () =>
      unwrap(
        client.POST("/api/members/{member_id}/confirm", {
          params: { path: { member_id: member.id } },
        }),
      ),
    {
      invalidate: [["members"], ["registrations"], ["members", member.id]],
      // Once confirmed the record is a full member and no longer resolvable as a
      // registration, so move to its new home rather than leaving a dead page.
      onSuccess: () => {
        toast.success("Registrierung bestätigt.");
        navigate(`/app/members/${member.id}`);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const mailConfirmMutation = useApiMutation<MemberOut, boolean>(
    (rerequest: boolean) =>
      unwrap(
        client.POST("/api/members/{member_id}/request-mail-confirmation", {
          params: { path: { member_id: member.id }, query: { rerequest } },
        }),
      ),
    {
      invalidate: [["members"], ["registrations"], ["members", member.id]],
      onSuccess: () => toast.success("E-Mail-Bestätigung angefordert."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const registrationFormMutation = useApiMutation<MemberOut, void>(
    () =>
      unwrap(
        client.POST("/api/members/{member_id}/request-registration-form", {
          params: { path: { member_id: member.id } },
        }),
      ),
    {
      invalidate: [["members"], ["registrations"], ["members", member.id]],
      onSuccess: () => toast.success("Anfrage für den Anmeldebogen verschickt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const demoteMutation = useApiMutation<undefined, void>(
    () =>
      unwrap(
        client.POST("/api/members/{member_id}/demote-to-waiter", {
          params: { path: { member_id: member.id } },
        }),
      ),
    {
      invalidate: [["members"], ["registrations"], ["members", member.id], ["waiters"]],
      // Now a waiting-list entry, not a registration — land on the waiting list.
      onSuccess: () => {
        toast.success("Auf die Warteliste zurückgestuft.");
        navigate("/app/waiters");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const busy =
    confirmMutation.isPending ||
    mailConfirmMutation.isPending ||
    registrationFormMutation.isPending ||
    demoteMutation.isPending;

  return (
    <Menu label="Aktionen">
      <Button
        type="button"
        variant="ghost"
        busy={busy}
        onClick={async () => {
          if (
            await confirm({
              title: "Registrierung bestätigen",
              message: `${member.name} als Mitglied bestätigen?`,
              confirmLabel: "Bestätigen",
            })
          )
            confirmMutation.mutate();
        }}
      >
        Bestätigen
      </Button>
      <Button
        type="button"
        variant="ghost"
        busy={busy}
        onClick={() => mailConfirmMutation.mutate(true)}
      >
        Bestätigungsmail an alle Adressen senden
      </Button>
      <Button
        type="button"
        variant="ghost"
        busy={busy}
        onClick={() => mailConfirmMutation.mutate(false)}
      >
        Bestätigungsmail nur an offene Adressen
      </Button>
      <Button
        type="button"
        variant="ghost"
        busy={busy}
        onClick={async () => {
          if (
            await confirm({
              title: "Anmeldebogen anfordern",
              message: `${member.name} per E-Mail auffordern, den unterschriebenen Anmeldebogen hochzuladen?`,
              confirmLabel: "Senden",
            })
          )
            registrationFormMutation.mutate();
        }}
      >
        Anmeldebogen anfordern
      </Button>
      <Button
        type="button"
        variant="danger"
        busy={busy}
        onClick={async () => {
          if (
            await confirm({
              title: "Auf Warteliste zurückstufen",
              message: `${member.name} auf die Warteliste zurückstufen?`,
              confirmLabel: "Zurückstufen",
              danger: true,
            })
          )
            demoteMutation.mutate();
        }}
      >
        Auf Warteliste zurückstufen
      </Button>
    </Menu>
  );
}
