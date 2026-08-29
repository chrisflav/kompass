import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
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
        { key: "group", label: "Gruppe", options: groupOptions, match: (r, v) => r.groups.includes(v) },
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
              { header: "Geburtsdatum", cell: (r) => formatDate(r.birth_date), sortKey: "birth_date" },
              { header: "Alter", cell: (r) => r.age ?? "—", sortKey: "age" },
              { header: "Gruppen", cell: (r) => r.groups.join(", ") || "—" },
              {
                header: "E-Mail bestätigt",
                cell: (r) => (r.confirmed_mail ? <Badge tone="success">Ja</Badge> : "—"),
                sortKey: "confirmed_mail",
              },
              {
                header: "Alt. E-Mail bestätigt",
                cell: (r) =>
                  r.alternative_email ? boolBadge(r.confirmed_alternative_mail) : "—",
              },
              {
                header: "Anmeldeformular",
                cell: (r) => (r.registration_form_uploaded ? <Badge tone="success">Ja</Badge> : "—"),
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

/* Grouped read-only display of the MemberUnconfirmed change-view fieldsets.
 * Registrations are edited on the member change view (same underlying object);
 * this view surfaces every field plus the registration workflow actions. */
function RegistrationDetailBody({ member, crumbs }: { member: MemberOut; crumbs: Crumb[] }) {
  const mainRows: DetailRow[] = [
    { label: "Name", value: member.name },
    { label: "Vorname", value: member.prename },
    { label: "Nachname", value: member.lastname },
    { label: "E-Mail", value: member.email || "—" },
    { label: "E-Mail bestätigt", value: boolBadge(member.confirmed_mail) },
    { label: "Alternative E-Mail", value: member.alternative_email || "—" },
    { label: "Alternative E-Mail bestätigt", value: boolBadge(member.confirmed_alternative_mail) },
    { label: "Telefon", value: member.phone_number || "—" },
    { label: "Geburtsdatum", value: formatDate(member.birth_date) },
    { label: "Alter", value: member.age ?? "—" },
    { label: "Geschlecht", value: member.gender_display || member.gender_str },
    { label: "Gruppen", value: member.groups.length ? member.groups.map((g) => g.name).join(", ") : "—" },
    fileRow("Anmeldeformular", member.registration_form),
    fileRow("Bild", member.image),
    { label: "Eintrittsdatum", value: formatDate(member.join_date) },
    { label: "Austrittsdatum", value: formatDate(member.leave_date) },
    { label: "Kommentare", value: member.comments || "—" },
    { label: "Erziehungsberechtigte", value: member.legal_guardians || "—" },
    { label: "DAV-Ausweisnummer", value: member.dav_badge_no || "—" },
    { label: "Echo erhalten", value: boolBadge(member.echoed) },
    { label: "Nutzer", value: member.user_display || "—" },
    { label: "Bestätigt", value: boolBadge(member.confirmed) },
    { label: "Erstellt", value: formatDate(member.created) },
  ];

  const contactRows: DetailRow[] = [
    { label: "Straße und Hausnummer", value: member.street || "—" },
    { label: "PLZ", value: member.plz || "—" },
    { label: "Ort", value: member.town || "—" },
    { label: "Adresszusatz", value: member.address_extra || "—" },
    { label: "Land", value: member.country || "—" },
    { label: "IBAN", value: member.iban || "—" },
  ];

  const skillsRows: DetailRow[] = [
    { label: "Schwimmabzeichen", value: boolBadge(member.swimming_badge) },
    { label: "Kletterabzeichen", value: member.climbing_badge || "—" },
    { label: "Alpine Erfahrung", value: member.alpine_experience || "—" },
  ];

  const othersRows: DetailRow[] = [
    { label: "Allergien", value: member.allergies || "—" },
    { label: "Tetanusimpfung", value: member.tetanus_vaccination || "—" },
    { label: "Medikamente", value: member.medication || "—" },
    { label: "Fotos dürfen gemacht werden", value: boolBadge(member.photos_may_be_taken) },
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

  return (
    <div>
      <PageHeader
        breadcrumbs={crumbs}
        actions={
          <>
            <Button type="button" variant="ghost" onClick={() => history.back()}>
              Zurück
            </Button>
            <RegistrationActions member={member} />
          </>
        }
      />
      <Tabs
        tabs={[
          { id: "stammdaten", label: "Stammdaten", content: <EditableDetail rows={mainRows} editing={false} /> },
          { id: "kontakt", label: "Kontaktdaten", content: <EditableDetail rows={contactRows} editing={false} /> },
          { id: "skills", label: "Fähigkeiten", content: <EditableDetail rows={skillsRows} editing={false} /> },
          { id: "sonstiges", label: "Sonstiges", content: <EditableDetail rows={othersRows} editing={false} /> },
          { id: "org", label: "Organisatorisch", content: <EditableDetail rows={orgRows} editing={false} /> },
          { id: "notfall", label: "Notfallkontakte", content: <RegistrationEmergencyContacts registrationId={member.id} /> },
        ]}
      />
    </div>
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
    confirmMutation.isPending || mailConfirmMutation.isPending || demoteMutation.isPending;

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
        E-Mail-Bestätigung anfordern
      </Button>
      <Button
        type="button"
        variant="ghost"
        busy={busy}
        onClick={() => mailConfirmMutation.mutate(false)}
      >
        Fehlende Bestätigungen erneut anfordern
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
