import { useMemo, useState, type ReactNode } from "react";
import { Link, Route, useNavigate, useParams, useSearchParams } from "react-router-dom";

import climberIcon from "../../assets/climber.png";
import { getToken } from "../../auth";
import { API_BASE } from "../../api/client";
import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { InlineTable } from "../../components/inline";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { RegistrationDetailPage, RegistrationsList } from "./Registrations";
import { TrainingDetailPage, TrainingsList } from "./Trainings";
import { WaiterDetailPage, WaitersList } from "./Waiters";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useToast,
  type Crumb,
  type DetailRow,
} from "../../components/ui";
import type { components } from "../../api/schema";

type MemberBrief = components["schemas"]["MemberBrief"];
type MemberOut = components["schemas"]["MemberOut"];
type MemberUpdate = components["schemas"]["MemberUpdate"];
type GroupOut = components["schemas"]["GroupOut"];
type EnumChoice = components["schemas"]["MemberEnumChoice"];
type EmergencyContactOut = components["schemas"]["MemberEmergencyContactOut"];
type EmergencyContactCreate = components["schemas"]["MemberEmergencyContactCreate"];
type EmergencyContactUpdate = components["schemas"]["MemberEmergencyContactUpdate"];
type MemberDocumentOut = components["schemas"]["MemberInlineDocumentOut"];
type MemberPermissionOut = components["schemas"]["MemberPermissionOut"];
type MemberPermissionIn = components["schemas"]["MemberPermissionIn"];
type TrainingBrief = components["schemas"]["TrainingBrief"];


function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

function boolBadge(value: boolean | null | undefined) {
  if (value === null || value === undefined) return "—";
  return value ? <Badge tone="success">Ja</Badge> : <Badge tone="warning">Nein</Badge>;
}

/** Raw activity score → level 1–5, matching the admin's thresholds. */
function activityLevel(score: number): number {
  if (score < 5) return 1;
  if (score < 10) return 2;
  if (score < 20) return 3;
  if (score < 30) return 4;
  return 5;
}

/** Render the activity score as 1–5 climber icons (the old admin's display). */
function activityClimbers(score: number | null | undefined): ReactNode {
  if (score === null || score === undefined) return "—";
  const level = activityLevel(score);
  return (
    <span title={`Aktivität: ${score}`} style={{ whiteSpace: "nowrap" }}>
      {Array.from({ length: level }, (_, i) => (
        <img key={i} src={climberIcon} alt="" height={18} style={{ verticalAlign: "middle" }} />
      ))}
    </span>
  );
}

/** Upload / replace a member's registration form (multipart), shown in edit mode. */
function RegistrationFormEdit({ member }: { member: MemberOut }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);
  const upload = useApiMutation(
    async (f: File) => {
      const fd = new FormData();
      fd.append("f", f);
      const res = await fetch(`${API_BASE}/api/members/${member.id}/registration-form`, {
        method: "POST",
        headers: { Authorization: `Bearer ${getToken()}` },
        body: fd,
      });
      if (!res.ok) {
        let detail: unknown = null;
        try {
          detail = await res.json();
        } catch {
          /* non-JSON error body */
        }
        throw new ApiError(res.status, detail);
      }
      return res.json();
    },
    {
      invalidate: [["members"], ["members", member.id]],
      onSuccess: () => {
        toast.success("Anmeldeformular hochgeladen.");
        setFile(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );
  return (
    <div className="stack">
      {member.registration_form && (
        <a href={documentHref(member.registration_form)} target="_blank" rel="noreferrer">
          Aktuelles Formular öffnen
        </a>
      )}
      <input
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/gif"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <div className="row-actions">
        <Button
          type="button"
          busy={upload.isPending}
          disabled={!file}
          onClick={() => file && upload.mutate(file)}
        >
          Hochladen
        </Button>
      </div>
    </div>
  );
}

function fileRow(label: string, url: string | null | undefined): DetailRow {
  return {
    label,
    value: url ? (
      <a href={documentHref(url)} target="_blank" rel="noreferrer">
        Öffnen
      </a>
    ) : (
      "—"
    ),
  };
}

function makeMemberDraft(m: MemberOut) {
  return {
    prename: m.prename ?? "",
    lastname: m.lastname ?? "",
    email: m.email ?? "",
    alternative_email: m.alternative_email ?? "",
    phone_number: m.phone_number ?? "",
    birth_date: m.birth_date ?? "",
    gender: String(m.gender ?? ""),
    group_ids: m.groups.map((g) => g.id),
    join_date: m.join_date ?? "",
    leave_date: m.leave_date ?? "",
    comments: m.comments ?? "",
    legal_guardians: m.legal_guardians ?? "",
    active: m.active ?? false,
    street: m.street ?? "",
    plz: m.plz ?? "",
    town: m.town ?? "",
    address_extra: m.address_extra ?? "",
    country: m.country ?? "",
    iban: m.iban ?? "",
    swimming_badge: m.swimming_badge ?? false,
    climbing_badge: m.climbing_badge ?? "",
    alpine_experience: m.alpine_experience ?? "",
    dav_badge_no: m.dav_badge_no ?? "",
    ticket_no: m.ticket_no ?? "",
    allergies: m.allergies ?? "",
    tetanus_vaccination: m.tetanus_vaccination ?? "",
    medication: m.medication ?? "",
    photos_may_be_taken: m.photos_may_be_taken ?? false,
    may_cancel:
      m.may_cancel_appointment_independently === null ||
      m.may_cancel_appointment_independently === undefined
        ? ""
        : String(m.may_cancel_appointment_independently),
    good_conduct_certificate_presented_date: m.good_conduct_certificate_presented_date ?? "",
    has_key: m.has_key ?? false,
    has_free_ticket_gym: m.has_free_ticket_gym ?? false,
  };
}

type MemberDraft = ReturnType<typeof makeMemberDraft>;
type MemberTextKey =
  | "prename"
  | "lastname"
  | "email"
  | "alternative_email"
  | "phone_number"
  | "birth_date"
  | "street"
  | "plz"
  | "town"
  | "address_extra"
  | "country"
  | "iban"
  | "join_date"
  | "leave_date"
  | "dav_badge_no"
  | "ticket_no"
  | "climbing_badge"
  | "legal_guardians"
  | "tetanus_vaccination"
  | "good_conduct_certificate_presented_date";
type MemberAreaKey = "comments" | "alpine_experience" | "allergies" | "medication";
type MemberBoolKey =
  | "active"
  | "swimming_badge"
  | "photos_may_be_taken"
  | "has_key"
  | "has_free_ticket_gym";

/* --- list ----------------------------------------------------------------
 * Full parity with the Django MemberAdmin changelist: all list_display columns
 * (name, birth date, age, groups, email, phone, echoed, comments, activity),
 * search (prename/lastname/email), filters (echoed, group), sortable headers,
 * default ordering by lastname. This is the reference list for the SPA. */

function MembersList() {
  const navigate = useNavigate();
  const query = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const rows = query.data ?? [];

  const groupOptions = useMemo(() => {
    const names = new Set<string>();
    rows.forEach((m) => m.groups.forEach((g) => names.add(g)));
    return [...names].sort().map((g) => ({ value: g, label: g }));
  }, [rows]);

  const config: ListViewConfig<MemberBrief> = useMemo(
    () => ({
      search: (m) => [m.name, m.email, m.phone_number],
      filters: [
        {
          key: "echoed",
          label: "Echo",
          options: [
            { value: "yes", label: "Ja" },
            { value: "no", label: "Nein" },
          ],
          match: (m, v) => (v === "yes") === Boolean(m.echoed),
        },
        { key: "group", label: "Gruppe", options: groupOptions, match: (m, v) => m.groups.includes(v) },
      ],
      sort: {
        lastname: (m) => m.lastname,
        birth_date: (m) => m.birth_date,
        age: (m) => m.age,
        email: (m) => m.email,
        phone: (m) => m.phone_number,
        echoed: (m) => m.echoed,
        activity: (m) => m.activity_score,
      },
      defaultSort: { key: "lastname", dir: "asc" },
    }),
    [groupOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Mitglieder" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Mitglieder sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/app/members/${m.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Name", cell: (m) => m.name, sortKey: "lastname" },
              { header: "Geburtsdatum", cell: (m) => m.birth_date ?? "—", sortKey: "birth_date" },
              { header: "Alter", cell: (m) => m.age ?? "—", sortKey: "age" },
              { header: "Gruppen", cell: (m) => m.groups.join(", ") || "—" },
              { header: "E-Mail", cell: (m) => m.email || "—", sortKey: "email" },
              { header: "Telefon", cell: (m) => m.phone_number || "—", sortKey: "phone" },
              {
                header: "Echo",
                cell: (m) => (m.echoed ? <Badge tone="success">Ja</Badge> : "—"),
                sortKey: "echoed",
              },
              { header: "Kommentar", cell: (m) => m.comments || "—" },
              {
                header: "Aktivität",
                cell: (m) => activityClimbers(m.activity_score),
                sortKey: "activity",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- detail + edit + actions -------------------------------------------- */

function MemberDetailPage() {
  const { id } = useParams();
  const memberId = Number(id);
  const [sp] = useSearchParams();
  const groupId = sp.get("group");
  const query = useApiQuery(["members", memberId], () =>
    unwrap(
      client.GET("/api/members/{member_id}", { params: { path: { member_id: memberId } } }),
    ),
  );
  const groupQuery = useApiQuery(
    ["groups", Number(groupId)],
    () =>
      unwrap(
        client.GET("/api/members/groups/{group_id}", {
          params: { path: { group_id: Number(groupId) } },
        }),
      ),
    { enabled: Boolean(groupId) },
  );
  const memberName = query.data?.name ?? "Mitglied";
  // Breadcrumb trail: from the group members view when a ?group is carried,
  // otherwise from the flat members list.
  const crumbs: Crumb[] = groupId
    ? [
        { label: "Gruppen", to: "/app/groups" },
        { label: groupQuery.data?.name ?? "Gruppe", to: `/app/groups/${groupId}/members` },
        { label: memberName },
      ]
    : [{ label: "Mitglieder", to: "/app/members" }, { label: memberName }];

  return (
    <div>
      <PageHeader
        breadcrumbs={crumbs}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(member: MemberOut) => <MemberDetailBody member={member} />}
      </QueryBoundary>
    </div>
  );
}

/** Members of a single group (group-based navigation). Rows carry the group in
 *  the query string so the member detail breadcrumb reflects the trail. */
function MembersOfGroup() {
  const { groupId } = useParams();
  const gid = Number(groupId);
  const navigate = useNavigate();
  const groupQuery = useApiQuery(["groups", gid], () =>
    unwrap(
      client.GET("/api/members/groups/{group_id}", { params: { path: { group_id: gid } } }),
    ),
  );
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groupName = groupQuery.data?.name;
  const rows = (membersQuery.data ?? []).filter(
    (m) => groupName !== undefined && m.groups.includes(groupName),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Gruppen", to: "/app/groups" }, { label: groupName ?? "Gruppe" }]}
        subtitle={`${rows.length} Mitglieder`}
        actions={
          <Button variant="ghost" onClick={() => navigate(`/app/groups/${gid}`)}>
            Gruppe bearbeiten
          </Button>
        }
      />
      <QueryBoundary query={membersQuery} empty="Keine Mitglieder in dieser Gruppe.">
        {() => (
          <DataTable
            rows={rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/app/members/${m.id}?group=${gid}`)}
            columns={[
              { header: "Name", cell: (m) => m.name },
              { header: "Vorname", cell: (m) => m.prename },
              { header: "Nachname", cell: (m) => m.lastname },
              { header: "E-Mail", cell: (m) => m.email || "—" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

function MemberDetailBody({ member }: { member: MemberOut }) {
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeMemberDraft(member));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const enumsQuery = useApiQuery(
    ["members", "enums"],
    () => unwrap(client.GET("/api/members/enums")),
    { enabled: editing },
  );
  const groupsQuery = useApiQuery(
    ["groups"],
    () => unwrap(client.GET("/api/members/groups")),
    { enabled: editing },
  );
  const genderChoices = enumsQuery.data?.gender ?? [];
  const groups: GroupOut[] = groupsQuery.data ?? [];

  const mutation = useApiMutation<MemberOut, MemberUpdate>(
    (body: MemberUpdate) =>
      unwrap(
        client.PATCH("/api/members/{member_id}", {
          params: { path: { member_id: member.id } },
          body,
        }),
      ),
    {
      invalidate: [["members"], ["members", member.id]],
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
    // Re-sync the draft from the (possibly refetched) member before editing.
    setForm(makeMemberDraft(member));
    setFieldErrors({});
    setEditing(true);
  }

  function setField<K extends keyof MemberDraft>(key: K, value: MemberDraft[K]) {
    setForm((f) => {
      const next = { ...f };
      next[key] = value;
      return next;
    });
  }

  const text = (key: MemberTextKey, type = "text") => (
    <input type={type} value={form[key]} onChange={(e) => setField(key, e.target.value)} />
  );
  const area = (key: MemberAreaKey) => (
    <textarea value={form[key]} onChange={(e) => setField(key, e.target.value)} />
  );
  const check = (key: MemberBoolKey) => (
    <input type="checkbox" checked={form[key]} onChange={(e) => setField(key, e.target.checked)} />
  );

  const genderEdit = (
    <Select
      value={form.gender}
      onChange={(v) => setField("gender", v)}
      options={genderChoices.map((c: EnumChoice) => ({ value: String(c.value), label: c.label }))}
      placeholder="Geschlecht wählen …"
    />
  );

  const groupEdit = (
    <MultiSelect
      options={groups.map((g) => ({ value: g.id, label: g.name }))}
      selected={form.group_ids}
      onChange={(ids) => setField("group_ids", ids)}
      placeholder="Gruppe hinzufügen"
    />
  );

  const mayCancelEdit = (
    <Select
      value={form.may_cancel}
      onChange={(v) => setField("may_cancel", v)}
      options={[
        { value: "true", label: "Ja" },
        { value: "false", label: "Nein" },
      ]}
      allowEmpty
      emptyLabel="Unbekannt"
      placeholder="Unbekannt"
    />
  );

  const mainRows: DetailRow[] = [
    { label: "Name", value: member.name },
    { label: "Vorname", value: member.prename, edit: text("prename"), field: "prename" },
    { label: "Nachname", value: member.lastname, edit: text("lastname"), field: "lastname" },
    { label: "E-Mail", value: member.email || "—", edit: text("email"), field: "email" },
    { label: "Alternative E-Mail", value: member.alternative_email || "—", edit: text("alternative_email"), field: "alternative_email" },
    { label: "Telefon", value: member.phone_number || "—", edit: text("phone_number"), field: "phone_number" },
    { label: "Geburtsdatum", value: formatDate(member.birth_date), edit: text("birth_date", "date"), field: "birth_date" },
    { label: "Alter", value: member.age ?? "—" },
    { label: "Geschlecht", value: member.gender_display || member.gender_str, edit: genderEdit, field: "gender" },
    {
      label: "Gruppen",
      value: member.groups.length ? member.groups.map((g) => g.name).join(", ") : "—",
      edit: groupEdit,
      field: "group",
    },
    {
      label: "Anmeldeformular",
      value: member.registration_form ? (
        <a href={documentHref(member.registration_form)} target="_blank" rel="noreferrer">
          Öffnen
        </a>
      ) : (
        "—"
      ),
      edit: <RegistrationFormEdit member={member} />,
    },
    fileRow("Bild", member.image),
    { label: "Eintrittsdatum", value: formatDate(member.join_date), edit: text("join_date", "date"), field: "join_date" },
    { label: "Austrittsdatum", value: formatDate(member.leave_date), edit: text("leave_date", "date"), field: "leave_date" },
    { label: "Kommentare", value: member.comments || "—", edit: area("comments"), field: "comments" },
    { label: "Erziehungsberechtigte", value: member.legal_guardians || "—", edit: text("legal_guardians"), field: "legal_guardians" },
    { label: "Aktiv", value: boolBadge(member.active), edit: check("active"), field: "active" },
    { label: "Echo erhalten", value: boolBadge(member.echoed) },
    { label: "Nutzer", value: member.user_display || "—" },
    { label: "Newsletter", value: boolBadge(member.gets_newsletter) },
    { label: "Bestätigt", value: boolBadge(member.confirmed) },
  ];

  const contactRows: DetailRow[] = [
    { label: "Straße und Hausnummer", value: member.street || "—", edit: text("street"), field: "street" },
    { label: "PLZ", value: member.plz || "—", edit: text("plz"), field: "plz" },
    { label: "Ort", value: member.town || "—", edit: text("town"), field: "town" },
    { label: "Adresszusatz", value: member.address_extra || "—", edit: text("address_extra"), field: "address_extra" },
    { label: "Land", value: member.country || "—", edit: text("country"), field: "country" },
    {
      label: "IBAN",
      value: member.iban ? (
        <>
          {member.iban} {member.iban_valid ? <Badge tone="success">gültig</Badge> : <Badge tone="danger">ungültig</Badge>}
        </>
      ) : (
        "—"
      ),
      edit: text("iban"),
      field: "iban",
    },
  ];

  const skillsRows: DetailRow[] = [
    { label: "Schwimmabzeichen", value: boolBadge(member.swimming_badge), edit: check("swimming_badge"), field: "swimming_badge" },
    { label: "Kletterabzeichen", value: member.climbing_badge || "—", edit: text("climbing_badge"), field: "climbing_badge" },
    { label: "Alpine Erfahrung", value: member.alpine_experience || "—", edit: area("alpine_experience"), field: "alpine_experience" },
    {
      label: "Ausflüge",
      value: member.activities.length
        ? member.activities.map((a) => a.name || a.code).join(", ")
        : "—",
    },
  ];

  const othersRows: DetailRow[] = [
    { label: "DAV-Ausweisnummer", value: member.dav_badge_no || "—", edit: text("dav_badge_no"), field: "dav_badge_no" },
    { label: "Ticketnummer", value: member.ticket_no || "—", edit: text("ticket_no"), field: "ticket_no" },
    { label: "Allergien", value: member.allergies || "—", edit: area("allergies"), field: "allergies" },
    { label: "Tetanusimpfung", value: member.tetanus_vaccination || "—", edit: text("tetanus_vaccination"), field: "tetanus_vaccination" },
    { label: "Medikamente", value: member.medication || "—", edit: area("medication"), field: "medication" },
    {
      label: "Fotos dürfen gemacht werden",
      value: boolBadge(member.photos_may_be_taken),
      edit: check("photos_may_be_taken"),
      field: "photos_may_be_taken",
    },
    {
      label: "Darf Termine selbstständig absagen",
      value: boolBadge(member.may_cancel_appointment_independently),
      edit: mayCancelEdit,
      field: "may_cancel_appointment_independently",
    },
  ];

  const orgRows: DetailRow[] = [
    {
      label: "Führungszeugnis vorgelegt am",
      value: formatDate(member.good_conduct_certificate_presented_date),
      edit: text("good_conduct_certificate_presented_date", "date"),
      field: "good_conduct_certificate_presented_date",
    },
    { label: "Führungszeugnis gültig", value: boolBadge(member.good_conduct_certificate_valid) },
    { label: "Schlüssel", value: boolBadge(member.has_key), edit: check("has_key"), field: "has_key" },
    { label: "Freikarte Halle", value: boolBadge(member.has_free_ticket_gym), edit: check("has_free_ticket_gym"), field: "has_free_ticket_gym" },
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
          alternative_email: form.alternative_email || null,
          phone_number: form.phone_number,
          birth_date: form.birth_date || null,
          gender: form.gender === "" ? null : Number(form.gender),
          group_ids: form.group_ids,
          join_date: form.join_date || null,
          leave_date: form.leave_date || null,
          comments: form.comments,
          legal_guardians: form.legal_guardians,
          active: form.active,
          street: form.street,
          plz: form.plz,
          town: form.town,
          address_extra: form.address_extra,
          country: form.country,
          iban: form.iban || null,
          swimming_badge: form.swimming_badge,
          climbing_badge: form.climbing_badge,
          alpine_experience: form.alpine_experience,
          dav_badge_no: form.dav_badge_no,
          ticket_no: form.ticket_no,
          allergies: form.allergies,
          tetanus_vaccination: form.tetanus_vaccination,
          medication: form.medication,
          photos_may_be_taken: form.photos_may_be_taken,
          may_cancel_appointment_independently:
            form.may_cancel === "" ? null : form.may_cancel === "true",
          good_conduct_certificate_presented_date:
            form.good_conduct_certificate_presented_date || null,
          has_key: form.has_key,
          has_free_ticket_gym: form.has_free_ticket_gym,
        });
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
            <Button type="button" onClick={startEditing}>
              Bearbeiten
            </Button>
            <MemberActions member={member} />
          </>
        )}
      </div>
      <Tabs
        tabs={[
          { id: "stammdaten", label: "Stammdaten", content: <EditableDetail rows={mainRows} editing={editing} errors={fieldErrors} /> },
          { id: "kontakt", label: "Kontaktdaten", content: <EditableDetail rows={contactRows} editing={editing} errors={fieldErrors} /> },
          { id: "skills", label: "Fähigkeiten", content: <EditableDetail rows={skillsRows} editing={editing} errors={fieldErrors} /> },
          { id: "sonstiges", label: "Sonstiges", content: <EditableDetail rows={othersRows} editing={editing} errors={fieldErrors} /> },
          { id: "org", label: "Organisatorisch", content: <EditableDetail rows={orgRows} editing={editing} errors={fieldErrors} /> },
          { id: "notfall", label: "Notfallkontakte", content: <EmergencyContactsInline memberId={member.id} editing={editing} /> },
          { id: "dokumente", label: "Dokumente", content: <DocumentsInline memberId={member.id} editing={editing} /> },
          { id: "ausbildungen", label: "Ausbildungen", content: <TrainingsInline memberId={member.id} /> },
          { id: "berechtigungen", label: "Berechtigungen", content: <PermissionMembersInline memberId={member.id} editing={editing} /> },
        ]}
      />
    </form>
  );
}

/* --- inline: Notfallkontakte (add + edit + delete) ----------------------- */

function EmergencyContactsInline({ memberId, editing }: { memberId: number; editing: boolean }) {
  const toast = useToast();
  const listKey = ["members", memberId, "emergency-contacts"];
  const query = useApiQuery<EmergencyContactOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/emergency-contacts", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );
  const rows = query.data ?? [];

  const emptyDraft = { prename: "", lastname: "", email: "", phone_number: "" };
  const [draft, setDraft] = useState(emptyDraft);
  const [editRow, setEditRow] = useState<
    { id: number; prename: string; lastname: string; email: string; phone_number: string } | null
  >(null);

  const create = useApiMutation<EmergencyContactOut, EmergencyContactCreate>(
    (body) =>
      unwrap(
        client.POST("/api/members/{member_id}/emergency-contacts", {
          params: { path: { member_id: memberId } },
          body,
        }),
      ),
    {
      invalidate: [listKey, ["members", memberId]],
      onSuccess: () => {
        toast.success("Notfallkontakt hinzugefügt.");
        setDraft(emptyDraft);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const update = useApiMutation<EmergencyContactOut, { id: number; body: EmergencyContactUpdate }>(
    ({ id, body }) =>
      unwrap(
        client.PATCH("/api/members/emergency-contacts/{contact_id}", {
          params: { path: { contact_id: id } },
          body,
        }),
      ),
    {
      invalidate: [listKey, ["members", memberId]],
      onSuccess: () => {
        toast.success("Notfallkontakt gespeichert.");
        setEditRow(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const del = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/emergency-contacts/{contact_id}", {
          params: { path: { contact_id: id } },
        }),
      ),
    {
      invalidate: [listKey, ["members", memberId]],
      onSuccess: () => toast.success("Notfallkontakt entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const columns: { header: string; cell: (row: EmergencyContactOut) => ReactNode }[] = [
    {
      header: "Vorname",
      cell: (r) =>
        editRow?.id === r.id ? (
          <input
            value={editRow.prename}
            onChange={(e) => setEditRow({ ...editRow, prename: e.target.value })}
          />
        ) : (
          r.prename
        ),
    },
    {
      header: "Nachname",
      cell: (r) =>
        editRow?.id === r.id ? (
          <input
            value={editRow.lastname}
            onChange={(e) => setEditRow({ ...editRow, lastname: e.target.value })}
          />
        ) : (
          r.lastname
        ),
    },
    {
      header: "E-Mail",
      cell: (r) =>
        editRow?.id === r.id ? (
          <input
            type="email"
            value={editRow.email}
            onChange={(e) => setEditRow({ ...editRow, email: e.target.value })}
          />
        ) : (
          r.email || "—"
        ),
    },
    {
      header: "Telefonnummer (mobil)",
      cell: (r) =>
        editRow?.id === r.id ? (
          <input
            value={editRow.phone_number}
            onChange={(e) => setEditRow({ ...editRow, phone_number: e.target.value })}
          />
        ) : (
          r.phone_number
        ),
    },
  ];
  if (editing) {
    columns.push({
      header: "Aktionen",
      cell: (r) =>
        editRow?.id === r.id ? (
          <div className="row-actions">
            <Button
              type="button"
              busy={update.isPending}
              onClick={() =>
                update.mutate({
                  id: r.id,
                  body: {
                    prename: editRow.prename,
                    lastname: editRow.lastname,
                    email: editRow.email,
                    phone_number: editRow.phone_number,
                  },
                })
              }
            >
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditRow(null)}>
              Abbrechen
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              setEditRow({
                id: r.id,
                prename: r.prename,
                lastname: r.lastname,
                email: r.email ?? "",
                phone_number: r.phone_number,
              })
            }
          >
            Bearbeiten
          </Button>
        ),
    });
  }

  return (
    <InlineTable
      title="Notfallkontakte"
      rows={rows}
      columns={columns}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => del.mutate(r.id)}
      renderAdd={() => (
        <div className="row-actions">
          <input
            placeholder="Vorname"
            value={draft.prename}
            onChange={(e) => setDraft({ ...draft, prename: e.target.value })}
          />
          <input
            placeholder="Nachname"
            value={draft.lastname}
            onChange={(e) => setDraft({ ...draft, lastname: e.target.value })}
          />
          <input
            type="email"
            placeholder="E-Mail"
            value={draft.email}
            onChange={(e) => setDraft({ ...draft, email: e.target.value })}
          />
          <input
            placeholder="Telefonnummer (mobil)"
            value={draft.phone_number}
            onChange={(e) => setDraft({ ...draft, phone_number: e.target.value })}
          />
          <Button
            type="button"
            busy={create.isPending}
            disabled={!draft.prename || !draft.lastname}
            onClick={() => create.mutate(draft)}
          >
            Hinzufügen
          </Button>
        </div>
      )}
    />
  );
}

/* --- inline: Dokumente (add multipart + delete) -------------------------- */

async function postMemberDocument(memberId: number, form: FormData): Promise<MemberDocumentOut> {
  const token = getToken();
  const res = await fetch(`${API_BASE}/api/members/${memberId}/documents`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: form,
  });
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as MemberDocumentOut;
}

function documentHref(url: string): string {
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}

function DocumentsInline({ memberId, editing }: { memberId: number; editing: boolean }) {
  const toast = useToast();
  const listKey = ["members", memberId, "documents"];
  const query = useApiQuery<MemberDocumentOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/documents", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );
  const rows = query.data ?? [];

  const [file, setFile] = useState<File | null>(null);

  const create = useApiMutation<MemberDocumentOut, File>(
    (f) => {
      const fd = new FormData();
      fd.append("f", f);
      return postMemberDocument(memberId, fd);
    },
    {
      invalidate: [listKey],
      onSuccess: () => {
        toast.success("Dokument hochgeladen.");
        setFile(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const del = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/member-documents/{document_id}", {
          params: { path: { document_id: id } },
        }),
      ),
    {
      invalidate: [listKey],
      onSuccess: () => toast.success("Dokument entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <InlineTable
      title="Dokumente"
      rows={rows}
      columns={[
        {
          header: "Datei",
          cell: (r: MemberDocumentOut) =>
            r.file_url ? (
              <a href={documentHref(r.file_url)} target="_blank" rel="noreferrer">
                {r.filename}
              </a>
            ) : (
              r.filename
            ),
        },
      ]}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => del.mutate(r.id)}
      renderAdd={() => (
        <div className="row-actions">
          <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
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

/* --- inline: Ausbildungen (read-only, links to training page) ------------ */

function TrainingsInline({ memberId }: { memberId: number }) {
  const query = useApiQuery<TrainingBrief[]>(["members", "trainings"], () =>
    unwrap(client.GET("/api/members/trainings")),
  );
  const rows = (query.data ?? []).filter((t) => t.member_id === memberId);

  return (
    <InlineTable
      title="Ausbildungen"
      rows={rows}
      columns={[
        { header: "Kategorie", cell: (t: TrainingBrief) => t.category_name },
        {
          header: "Titel",
          cell: (t: TrainingBrief) => <Link to={`/app/trainings/${t.id}`}>{t.title || "—"}</Link>,
        },
        { header: "Datum", cell: (t: TrainingBrief) => formatDate(t.date) },
        { header: "Teilgenommen", cell: (t: TrainingBrief) => boolBadge(t.participated) },
        { header: "Bestanden", cell: (t: TrainingBrief) => boolBadge(t.passed) },
      ]}
      rowKey={(t) => t.id}
      editing={false}
      empty="Keine Ausbildungen."
    />
  );
}

/* --- inline: Berechtigungen (PermissionMember ACL, SENSITIVE) ------------ */

type PermDraft = {
  id: number;
  list_member_ids: number[];
  view_member_ids: number[];
  change_member_ids: number[];
  delete_member_ids: number[];
  list_group_ids: number[];
  view_group_ids: number[];
  change_group_ids: number[];
  delete_group_ids: number[];
};

const PERM_ROWS = [
  { label: "Auflisten", mk: "list_member_ids", gk: "list_group_ids" },
  { label: "Ansehen", mk: "view_member_ids", gk: "view_group_ids" },
  { label: "Ändern", mk: "change_member_ids", gk: "change_group_ids" },
  { label: "Löschen", mk: "delete_member_ids", gk: "delete_group_ids" },
] as const;

function PermissionMembersInline({ memberId, editing }: { memberId: number; editing: boolean }) {
  const toast = useToast();
  const listKey = ["members", memberId, "permission-members"];
  const query = useApiQuery<MemberPermissionOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/permission-members", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );
  const rows = query.data ?? [];

  const optionsEnabled = editing || rows.length > 0;
  const membersQuery = useApiQuery<MemberBrief[]>(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: optionsEnabled },
  );
  const groupsQuery = useApiQuery<GroupOut[]>(
    ["groups"],
    () => unwrap(client.GET("/api/members/groups")),
    { enabled: optionsEnabled },
  );
  const memberOpts = membersQuery.data ?? [];
  const groupOpts = groupsQuery.data ?? [];
  const memberName = (id: number) => memberOpts.find((m) => m.id === id)?.name ?? `#${id}`;
  const groupName = (id: number) => groupOpts.find((g) => g.id === id)?.name ?? `#${id}`;

  const [editRow, setEditRow] = useState<PermDraft | null>(null);

  const create = useApiMutation<MemberPermissionOut, MemberPermissionIn>(
    (body) =>
      unwrap(
        client.POST("/api/members/{member_id}/permission-members", {
          params: { path: { member_id: memberId } },
          body,
        }),
      ),
    {
      invalidate: [listKey],
      onSuccess: () => toast.success("Berechtigungssatz hinzugefügt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const update = useApiMutation<MemberPermissionOut, { id: number; body: MemberPermissionIn }>(
    ({ id, body }) =>
      unwrap(
        client.PATCH("/api/members/permission-members/{permission_id}", {
          params: { path: { permission_id: id } },
          body,
        }),
      ),
    {
      invalidate: [listKey],
      onSuccess: () => {
        toast.success("Berechtigungen gespeichert.");
        setEditRow(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const del = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/permission-members/{permission_id}", {
          params: { path: { permission_id: id } },
        }),
      ),
    {
      invalidate: [listKey],
      onSuccess: () => toast.success("Berechtigungssatz entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const memberSelect = (values: number[], onChange: (v: number[]) => void) => (
    <MultiSelect
      options={memberOpts.map((m) => ({ value: m.id, label: m.name }))}
      selected={values}
      onChange={onChange}
      placeholder="Mitglied"
    />
  );
  const groupSelect = (values: number[], onChange: (v: number[]) => void) => (
    <MultiSelect
      options={groupOpts.map((g) => ({ value: g.id, label: g.name }))}
      selected={values}
      onChange={onChange}
      placeholder="Gruppe"
    />
  );

  const columns: { header: string; cell: (row: MemberPermissionOut) => ReactNode }[] = PERM_ROWS.map(
    (p) => ({
      header: p.label,
      cell: (r: MemberPermissionOut) => {
        const memberIds = r[p.mk];
        const groupIds = r[p.gk];
        if (editRow?.id === r.id) {
          return (
            <div className="stack">
              {memberSelect(editRow[p.mk], (v) =>
                setEditRow({ ...editRow, [p.mk]: v } as PermDraft),
              )}
              {groupSelect(editRow[p.gk], (v) =>
                setEditRow({ ...editRow, [p.gk]: v } as PermDraft),
              )}
            </div>
          );
        }
        return (
          <div className="small">
            <div>Mitglieder: {memberIds.length ? memberIds.map(memberName).join(", ") : "—"}</div>
            <div>Gruppen: {groupIds.length ? groupIds.map(groupName).join(", ") : "—"}</div>
          </div>
        );
      },
    }),
  );
  if (editing) {
    columns.push({
      header: "Aktionen",
      cell: (r) =>
        editRow?.id === r.id ? (
          <div className="row-actions">
            <Button
              type="button"
              busy={update.isPending}
              onClick={() =>
                update.mutate({
                  id: r.id,
                  body: {
                    list_member_ids: editRow.list_member_ids,
                    view_member_ids: editRow.view_member_ids,
                    change_member_ids: editRow.change_member_ids,
                    delete_member_ids: editRow.delete_member_ids,
                    list_group_ids: editRow.list_group_ids,
                    view_group_ids: editRow.view_group_ids,
                    change_group_ids: editRow.change_group_ids,
                    delete_group_ids: editRow.delete_group_ids,
                  },
                })
              }
            >
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditRow(null)}>
              Abbrechen
            </Button>
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              setEditRow({
                id: r.id,
                list_member_ids: r.list_member_ids ?? [],
                view_member_ids: r.view_member_ids ?? [],
                change_member_ids: r.change_member_ids ?? [],
                delete_member_ids: r.delete_member_ids ?? [],
                list_group_ids: r.list_group_ids ?? [],
                view_group_ids: r.view_group_ids ?? [],
                change_group_ids: r.change_group_ids ?? [],
                delete_group_ids: r.delete_group_ids ?? [],
              })
            }
          >
            Bearbeiten
          </Button>
        ),
    });
  }

  return (
    <InlineTable
      title="Berechtigungen"
      rows={rows}
      columns={columns}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => del.mutate(r.id)}
      empty="Keine Berechtigungen."
      renderAdd={() => (
        <div className="row-actions">
          <Button type="button" busy={create.isPending} onClick={() => create.mutate({})}>
            Berechtigungssatz hinzufügen
          </Button>
        </div>
      )}
    />
  );
}

/** Workflow-action buttons that POST to the members action endpoints. */
function MemberActions({ member }: { member: MemberOut }) {
  const toast = useToast();

  const action = (label: string, run: () => Promise<unknown>, invalidate = true) => ({
    label,
    run,
    invalidate,
  });

  const actions = [
    action("Echo anfordern", () =>
      unwrap(
        client.POST("/api/members/{member_id}/request-echo", {
          params: { path: { member_id: member.id } },
        }),
      ),
    ),
    action("Als Nutzer einladen", () =>
      unwrap(
        client.POST("/api/members/{member_id}/invite-as-user", {
          params: { path: { member_id: member.id } },
        }),
      ),
    ),
    action("Passwort-Reset anfordern", () =>
      unwrap(
        client.POST("/api/members/{member_id}/request-password-reset", {
          params: { path: { member_id: member.id } },
        }),
      ),
    ),
    action("Bestätigung aufheben", () =>
      unwrap(
        client.POST("/api/members/{member_id}/unconfirm", {
          params: { path: { member_id: member.id } },
        }),
      ),
    ),
  ];

  const mutation = useApiMutation(
    (run: () => Promise<unknown>) => run(),
    {
      invalidate: [["members"], ["members", member.id]],
      onSuccess: () => toast.success("Aktion ausgeführt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div className="row-actions">
      {actions.map((a) => (
        <Button
          key={a.label}
          type="button"
          variant="ghost"
          busy={mutation.isPending}
          onClick={() => mutation.mutate(a.run)}
        >
          {a.label}
        </Button>
      ))}
    </div>
  );
}

/* --- route fragment ------------------------------------------------------ */
export const membersRoutes = (
  <>
    <Route path="members" element={<MembersList />} />
    <Route path="members/:id" element={<MemberDetailPage />} />
    <Route path="groups/:groupId/members" element={<MembersOfGroup />} />
    <Route path="registrations" element={<RegistrationsList />} />
    <Route path="registrations/:id" element={<RegistrationDetailPage />} />
    <Route path="waiters" element={<WaitersList />} />
    <Route path="waiters/:id" element={<WaiterDetailPage />} />
    <Route path="trainings" element={<TrainingsList />} />
    <Route path="trainings/:id" element={<TrainingDetailPage />} />
  </>
);
