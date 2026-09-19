import { useMemo, useState, type ReactNode } from "react";
import { Link, Route, useNavigate, useParams, useSearchParams } from "react-router-dom";

import climberIcon from "../../assets/climber.png";
import { usePermissions } from "../../api/me";
import { getToken } from "../../auth";
import { API_BASE } from "../../api/client";
import { ApiError, client, downloadArtifact, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useRowHints, useSectionHelp } from "../../api/helpTexts";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft, type DraftRow } from "../../components/inlineDraft";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { MeineGruppen } from "./Meine";
import { RegistrationDetailPage, RegistrationsList } from "./Registrations";
import { TrainingDetailPage, TrainingsList } from "./Trainings";
import { WaiterDetailPage, WaitersList } from "./Waiters";
import {
  Badge,
  Button,
  DataTable,
  EditableDetail,
  Field,
  Menu,
  Modal,
  MultiSelect,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  type Crumb,
  type DetailRow,
  useConfirmDialog,
  useRowSelection,
  useToast,
} from "../../components/ui";
import type { components } from "../../api/schema";

type MemberBrief = components["schemas"]["MemberBrief"];
type MemberOut = components["schemas"]["MemberOut"];
type MemberCreate = components["schemas"]["MemberCreate"];
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
type TrainingOut = components["schemas"]["TrainingOut"];
type MemberTrainingUpdate = components["schemas"]["MemberTrainingUpdate"];

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

/** Upload / replace / clear a member's photo (multipart), shown in edit mode. */
function MemberImageEdit({ member }: { member: MemberOut }) {
  const toast = useToast();
  const [file, setFile] = useState<File | null>(null);

  const upload = useApiMutation(
    async (f: File) => {
      const fd = new FormData();
      fd.append("f", f);
      const res = await fetch(`${API_BASE}/api/members/${member.id}/image`, {
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
        toast.success("Bild hochgeladen.");
        setFile(null);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const clear = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/{member_id}/image", {
          params: { path: { member_id: member.id } },
        }),
      ),
    {
      invalidate: [["members"], ["members", member.id]],
      onSuccess: () => toast.success("Bild entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div className="stack">
      {member.image && (
        <a href={documentHref(member.image)} target="_blank" rel="noreferrer">
          Aktuelles Bild öffnen
        </a>
      )}
      <input
        type="file"
        accept="image/jpeg,image/png,image/gif"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
      />
      <div className="field-hint">JPEG, PNG oder GIF, maximal 5 MiB.</div>
      <div className="row-actions">
        <Button
          type="button"
          busy={upload.isPending}
          disabled={!file}
          onClick={() => file && upload.mutate(file)}
        >
          Hochladen
        </Button>
        {member.image && (
          <Button
            type="button"
            variant="ghost"
            busy={clear.isPending}
            onClick={() => clear.mutate(undefined)}
          >
            Entfernen
          </Button>
        )}
      </div>
    </div>
  );
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
  "active" | "swimming_badge" | "photos_may_be_taken" | "has_key" | "has_free_ticket_gym";

/* --- list ----------------------------------------------------------------
 * Full parity with the Django MemberAdmin changelist: all list_display columns
 * (name, birth date, age, groups, email, phone, echoed, comments, activity),
 * search (prename/lastname/email), filters (echoed, group), sortable headers,
 * default ordering by lastname. This is the reference list for the SPA. */

function MembersList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
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
        {
          key: "group",
          label: "Gruppe",
          options: groupOptions,
          match: (m, v) => m.groups.includes(v),
        },
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
  const selection = useRowSelection<number>();
  const selectedMembers = useMemo(
    () => rows.filter((m) => selection.selected.has(m.id)),
    [rows, selection.selected],
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Teilnehmende" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          can("members.add_global_member") && (
            <Button onClick={() => setCreating(true)}>Neues Mitglied</Button>
          )
        }
      />
      {creating && (
        <Modal title="Neues Mitglied" onClose={() => setCreating(false)}>
          <MemberCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      {selection.count > 0 && (
        <MemberBulkActions members={selectedMembers} onDone={selection.clear} />
      )}
      <QueryBoundary query={query} empty="Keine Teilnehmende sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/kompass/members/${m.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            selection={{
              selected: selection.selected as Set<string | number>,
              onToggle: (k) => selection.toggle(Number(k)),
              onToggleAll: (keys) => selection.toggleAll(keys.map(Number)),
            }}
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

/* --- bulk actions ---------------------------------------------------------
 * The Django changelist's ``MemberAdmin.actions``: request an echo from, invite
 * as users, or unconfirm the selected members, plus ``create_object_from``,
 * which builds a note list / excursion / message / crisis-intervention list out
 * of the selection. */

function MemberBulkActions({ members, onDone }: { members: MemberBrief[]; onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const [crisisOpen, setCrisisOpen] = useState(false);
  const ids = members.map((m) => m.id);
  const names = members.map((m) => m.name).join(", ");

  /** Runs `call` for every selected member, reporting how many succeeded. */
  const bulk = useApiMutation(
    async (a: { call: (id: number) => Promise<unknown>; success: (n: number) => string }) => {
      let ok = 0;
      const failures: string[] = [];
      for (const m of members) {
        try {
          await a.call(m.id);
          ok += 1;
        } catch (e) {
          failures.push(`${m.name}: ${e instanceof Error ? e.message : "Fehler"}`);
        }
      }
      return { ok, failures, success: a.success };
    },
    {
      invalidate: [["members"], ["registrations"]],
      onSuccess: (r: { ok: number; failures: string[]; success: (n: number) => string }) => {
        if (r.ok) toast.success(r.success(r.ok));
        // Report the failures too — a partial run must not look like a success.
        if (r.failures.length) toast.error(r.failures.join(" · "));
        onDone();
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const run = async (
    label: string,
    question: string,
    success: (n: number) => string,
    call: (id: number) => Promise<unknown>,
    danger = false,
  ) => {
    if (await confirm({ title: label, message: question, confirmLabel: label, danger }))
      bulk.mutate({ call, success });
  };

  const createNoteList = useApiMutation(
    async () => {
      const list = await unwrap(
        client.POST("/api/members/note-lists", {
          body: { title: `Liste (${members.length} Teilnehmende)`, date: null },
        }),
      );
      for (const id of ids) {
        await unwrap(
          client.POST("/api/members/note-lists/{notelist_id}/participants", {
            params: { path: { notelist_id: list.id } },
            body: { member_id: id, comments: "" },
          }),
        );
      }
      return list;
    },
    {
      invalidate: [["note-lists"]],
      onSuccess: (list: { id: number }) => {
        toast.success("Notizliste aus der Auswahl angelegt.");
        onDone();
        navigate(`/kompass/notelists/${list.id}`);
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  return (
    <div className="bulk-bar">
      <span className="bulk-count">{members.length} ausgewählt</span>
      <Menu label="Aktionen für Auswahl">
        {can("members.change_global_member") && (
          <Button
            type="button"
            variant="ghost"
            busy={bulk.isPending}
            onClick={() =>
              run(
                "Echo anfordern",
                `${members.length} Teilnehmende per E-Mail auffordern, ihre Daten zu prüfen? (${names})`,
                (n) => `Rückmeldung von ${n} Teilnehmenden angefordert.`,
                (id) =>
                  unwrap(
                    client.POST("/api/members/{member_id}/request-echo", {
                      params: { path: { member_id: id } },
                    }),
                  ),
              )
            }
          >
            Echo anfordern
          </Button>
        )}
        {can("members.change_global_member") && (
          <Button
            type="button"
            variant="ghost"
            busy={bulk.isPending}
            onClick={() =>
              run(
                "Als Nutzer einladen",
                `${members.length} Teilnehmende einladen, einen Kompass-Zugang anzulegen?`,
                (n) => `${n} Einladungen verschickt.`,
                (id) =>
                  unwrap(
                    client.POST("/api/members/{member_id}/invite-as-user", {
                      params: { path: { member_id: id } },
                    }),
                  ),
              )
            }
          >
            Als Nutzer einladen
          </Button>
        )}
        {can("members.add_membernotelist") && (
          <Button
            type="button"
            variant="ghost"
            busy={createNoteList.isPending}
            onClick={() => createNoteList.mutate(undefined)}
          >
            Notizliste aus Auswahl
          </Button>
        )}
        <Button type="button" variant="ghost" onClick={() => setCrisisOpen(true)}>
          Kriseninterventionsliste
        </Button>
        {can("members.change_global_member") && (
          <Button
            type="button"
            variant="danger"
            busy={bulk.isPending}
            onClick={() =>
              run(
                "Bestätigung aufheben",
                `Die Bestätigung von ${members.length} Teilnehmenden aufheben? Sie werden wieder zu offenen Registrierungen.`,
                (n) => `${n} Bestätigungen aufgehoben.`,
                (id) =>
                  unwrap(
                    client.POST("/api/members/{member_id}/unconfirm", {
                      params: { path: { member_id: id } },
                    }),
                  ),
                true,
              )
            }
          >
            Bestätigung aufheben
          </Button>
        )}
      </Menu>
      <Button type="button" variant="ghost" onClick={onDone}>
        Auswahl aufheben
      </Button>
      {crisisOpen && (
        <CrisisInterventionListModal members={members} onClose={() => setCrisisOpen(false)} />
      )}
    </div>
  );
}

/** The admin's ad-hoc crisis intervention list over a free member selection
 *  (``MemberAdmin.create_crisis_intervention_list_view``). */
function CrisisInterventionListModal({
  members,
  onClose,
}: {
  members: MemberBrief[];
  onClose: () => void;
}) {
  const toast = useToast();
  const [form, setForm] = useState({
    activity: "",
    place: "",
    start_date: "",
    end_date: "",
    description: "",
  });
  const [busy, setBusy] = useState(false);

  const complete = form.activity.trim() && form.place.trim() && form.start_date && form.end_date;

  return (
    <Modal title="Kriseninterventionsliste erstellen" onClose={onClose}>
      <form
        className="stack"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          try {
            await downloadArtifact("/api/members/documents/crisis-intervention-list", {
              method: "POST",
              body: { ...form, member_ids: members.map((m) => m.id) },
              filename: `Kriseninterventionsliste_${form.activity || "Aktivitaet"}.pdf`,
            });
            onClose();
          } catch (err) {
            toast.error(err instanceof Error ? err.message : "Download fehlgeschlagen.");
          } finally {
            setBusy(false);
          }
        }}
      >
        <p className="fieldset-help">
          Für die {members.length} ausgewählten Teilnehmenden. Die Angaben erscheinen im Kopf der
          Liste.
        </p>
        <Field label="Aktivität *">
          <input
            value={form.activity}
            onChange={(e) => setForm({ ...form, activity: e.target.value })}
            required
          />
        </Field>
        <Field label="Ort *">
          <input
            value={form.place}
            onChange={(e) => setForm({ ...form, place: e.target.value })}
            required
          />
        </Field>
        <Field label="Von *">
          <input
            type="date"
            value={form.start_date}
            onChange={(e) => setForm({ ...form, start_date: e.target.value })}
            required
          />
        </Field>
        <Field label="Bis *">
          <input
            type="date"
            value={form.end_date}
            onChange={(e) => setForm({ ...form, end_date: e.target.value })}
            required
          />
        </Field>
        <Field label="Beschreibung">
          <textarea
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </Field>
        <div className="row-actions">
          <Button type="submit" busy={busy} disabled={!complete}>
            PDF erzeugen
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </form>
    </Modal>
  );
}

/* --- create -------------------------------------------------------------- */

function MemberCreateForm({ onDone }: { onDone: () => void }) {
  const navigate = useNavigate();
  const toast = useToast();
  const [prename, setPrename] = useState("");
  const [lastname, setLastname] = useState("");
  const [gender, setGender] = useState("");
  const [email, setEmail] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");
  const [groupIds, setGroupIds] = useState<number[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const enumsQuery = useApiQuery(["members", "enums"], () =>
    unwrap(client.GET("/api/members/enums")),
  );
  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const genderChoices = enumsQuery.data?.gender ?? [];
  const groups: GroupOut[] = groupsQuery.data ?? [];

  const mutation = useApiMutation<MemberOut, MemberCreate>(
    (body: MemberCreate) => unwrap(client.POST("/api/members/", { body })),
    {
      invalidate: [["members"]],
      onSuccess: (created: MemberOut) => {
        toast.success("Mitglied angelegt.");
        onDone();
        navigate(`/kompass/members/${created.id}`);
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
          prename,
          lastname,
          gender: Number(gender),
          email: email || null,
          birth_date: birthDate || null,
          phone_number: phoneNumber || null,
          group_ids: groupIds,
        });
      }}
    >
      <Field label="Vorname">
        <input value={prename} onChange={(e) => setPrename(e.target.value)} required />
        {fieldErrors.prename && <div className="field-error">{fieldErrors.prename.join(" ")}</div>}
      </Field>
      <Field label="Nachname">
        <input value={lastname} onChange={(e) => setLastname(e.target.value)} required />
        {fieldErrors.lastname && (
          <div className="field-error">{fieldErrors.lastname.join(" ")}</div>
        )}
      </Field>
      <Field label="Geschlecht">
        <Select
          value={gender}
          onChange={(v) => setGender(v)}
          options={genderChoices.map((c: EnumChoice) => ({
            value: String(c.value),
            label: c.label,
          }))}
          placeholder="Geschlecht wählen …"
        />
        {fieldErrors.gender && <div className="field-error">{fieldErrors.gender.join(" ")}</div>}
      </Field>
      <Field label="E-Mail">
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
        {fieldErrors.email && <div className="field-error">{fieldErrors.email.join(" ")}</div>}
      </Field>
      <Field label="Geburtsdatum">
        <input type="date" value={birthDate} onChange={(e) => setBirthDate(e.target.value)} />
        {fieldErrors.birth_date && (
          <div className="field-error">{fieldErrors.birth_date.join(" ")}</div>
        )}
      </Field>
      <Field label="Telefon">
        <input value={phoneNumber} onChange={(e) => setPhoneNumber(e.target.value)} />
        {fieldErrors.phone_number && (
          <div className="field-error">{fieldErrors.phone_number.join(" ")}</div>
        )}
      </Field>
      <Field label="Gruppen">
        <MultiSelect
          options={groups.map((g) => ({ value: g.id, label: g.name }))}
          selected={groupIds}
          onChange={(ids) => setGroupIds(ids)}
          placeholder="Gruppe hinzufügen"
        />
        {fieldErrors.group_ids && (
          <div className="field-error">{fieldErrors.group_ids.join(" ")}</div>
        )}
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending} disabled={gender === ""}>
          Anlegen
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}

/* --- detail + edit + actions -------------------------------------------- */

function MemberDetailPage() {
  const { id } = useParams();
  const memberId = Number(id);
  const [sp] = useSearchParams();
  const groupId = sp.get("group");
  const query = useApiQuery(["members", memberId], () =>
    unwrap(client.GET("/api/members/{member_id}", { params: { path: { member_id: memberId } } })),
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
  const memberName = query.data?.name ?? "Teilnehmende";
  // Breadcrumb trail: from the group members view when a ?group is carried,
  // otherwise from the flat members list.
  const crumbs: Crumb[] = groupId
    ? [
        { label: "Gruppen", to: "/kompass/groups" },
        { label: groupQuery.data?.name ?? "Gruppe", to: `/kompass/groups/${groupId}/members` },
        { label: memberName },
      ]
    : [{ label: "Teilnehmende", to: "/kompass/members" }, { label: memberName }];

  return (
    <QueryBoundary query={query}>
      {(member: MemberOut) => <MemberDetailBody member={member} crumbs={crumbs} />}
    </QueryBoundary>
  );
}

/** Members of a single group (group-based navigation). Rows carry the group in
 *  the query string so the member detail breadcrumb reflects the trail. */
function MembersOfGroup() {
  const { groupId } = useParams();
  const gid = Number(groupId);
  const navigate = useNavigate();
  const groupQuery = useApiQuery(["groups", gid], () =>
    unwrap(client.GET("/api/members/groups/{group_id}", { params: { path: { group_id: gid } } })),
  );
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groupName = groupQuery.data?.name;
  const rows = (membersQuery.data ?? []).filter(
    (m) => groupName !== undefined && m.groups.includes(groupName),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Gruppen", to: "/kompass/groups" }, { label: groupName ?? "Gruppe" }]}
        subtitle={`${rows.length} Teilnehmende`}
        actions={
          <>
            <Button variant="ghost" onClick={() => history.back()}>
              Zurück
            </Button>
            <Button variant="ghost" onClick={() => navigate(`/kompass/groups/${gid}`)}>
              Gruppe bearbeiten
            </Button>
          </>
        }
      />
      <QueryBoundary query={membersQuery} empty="Keine Teilnehmende in dieser Gruppe.">
        {() => (
          <DataTable
            rows={rows}
            rowKey={(m) => m.id}
            onRowClick={(m) => navigate(`/kompass/members/${m.id}?group=${gid}`)}
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

function MemberDetailBody({ member, crumbs }: { member: MemberOut; crumbs: Crumb[] }) {
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const removeMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/{member_id}", { params: { path: { member_id: member.id } } }),
      ),
    {
      invalidate: [["members"]],
      onSuccess: () => {
        toast.success("Mitglied gelöscht.");
        navigate("/kompass/members");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const toast = useToast();
  // Attach recovered model help_text to each row by its backend field name.
  const withHints = useRowHints();
  // Recovered admin inline `description` intros for the related-object sections.
  const sectionHelp = useSectionHelp();
  const sectionNote = (section: string) => {
    const note = sectionHelp(section);
    return note ? <p className="fieldset-help">{note}</p> : null;
  };
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeMemberDraft(member));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const enumsQuery = useApiQuery(
    ["members", "enums"],
    () => unwrap(client.GET("/api/members/enums")),
    { enabled: editing },
  );
  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")), {
    enabled: editing,
  });
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
    { invalidate: [["members"], ["members", member.id]] },
  );

  // Inline editors (Notfallkontakte / Dokumente / Ausbildungen / Berechtigungen)
  // stage their changes and register a flush; the main Save applies the member
  // PATCH and then every inline flush, so there is no separate per-inline save.
  const { getRegistrar, runFlushes } = useFlushRegistry();
  const [saving, setSaving] = useState(false);

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
    {
      label: "Alternative E-Mail",
      value: member.alternative_email || "—",
      edit: text("alternative_email"),
      field: "alternative_email",
    },
    {
      label: "Telefon",
      value: member.phone_number || "—",
      edit: text("phone_number"),
      field: "phone_number",
    },
    {
      label: "Geburtsdatum",
      value: formatDate(member.birth_date),
      edit: text("birth_date", "date"),
      field: "birth_date",
    },
    { label: "Alter", value: member.age ?? "—" },
    {
      label: "Geschlecht",
      value: member.gender_display || member.gender_str,
      edit: genderEdit,
      field: "gender",
    },
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
    {
      label: "Bild",
      value: member.image ? (
        <a href={documentHref(member.image)} target="_blank" rel="noreferrer">
          Öffnen
        </a>
      ) : (
        "—"
      ),
      edit: <MemberImageEdit member={member} />,
    },
    {
      label: "Eintrittsdatum",
      value: formatDate(member.join_date),
      edit: text("join_date", "date"),
      field: "join_date",
    },
    {
      label: "Austrittsdatum",
      value: formatDate(member.leave_date),
      edit: text("leave_date", "date"),
      field: "leave_date",
    },
    {
      label: "Kommentare",
      value: member.comments || "—",
      edit: area("comments"),
      field: "comments",
    },
    {
      label: "Erziehungsberechtigte",
      value: member.legal_guardians || "—",
      edit: text("legal_guardians"),
      field: "legal_guardians",
    },
    { label: "Aktiv", value: boolBadge(member.active), edit: check("active"), field: "active" },
    { label: "Echo erhalten", value: boolBadge(member.echoed) },
    { label: "Nutzer", value: member.user_display || "—" },
    { label: "Newsletter", value: boolBadge(member.gets_newsletter) },
    { label: "Bestätigt", value: boolBadge(member.confirmed) },
  ];

  const contactRows: DetailRow[] = [
    {
      label: "Straße und Hausnummer",
      value: member.street || "—",
      edit: text("street"),
      field: "street",
    },
    { label: "PLZ", value: member.plz || "—", edit: text("plz"), field: "plz" },
    { label: "Ort", value: member.town || "—", edit: text("town"), field: "town" },
    {
      label: "Adresszusatz",
      value: member.address_extra || "—",
      edit: text("address_extra"),
      field: "address_extra",
    },
    { label: "Land", value: member.country || "—", edit: text("country"), field: "country" },
    {
      label: "IBAN",
      value: member.iban ? (
        <>
          {member.iban}{" "}
          {member.iban_valid ? (
            <Badge tone="success">gültig</Badge>
          ) : (
            <Badge tone="danger">ungültig</Badge>
          )}
        </>
      ) : (
        "—"
      ),
      edit: text("iban"),
      field: "iban",
    },
  ];

  const skillsRows: DetailRow[] = [
    {
      label: "Schwimmabzeichen",
      value: boolBadge(member.swimming_badge),
      edit: check("swimming_badge"),
      field: "swimming_badge",
    },
    {
      label: "Kletterabzeichen",
      value: member.climbing_badge || "—",
      edit: text("climbing_badge"),
      field: "climbing_badge",
    },
    {
      label: "Alpine Erfahrung",
      value: member.alpine_experience || "—",
      edit: area("alpine_experience"),
      field: "alpine_experience",
    },
    {
      label: "Ausflüge",
      value: member.activities.length
        ? member.activities.map((a) => a.name || a.code).join(", ")
        : "—",
    },
  ];

  const othersRows: DetailRow[] = [
    {
      label: "DAV-Ausweisnummer",
      value: member.dav_badge_no || "—",
      edit: text("dav_badge_no"),
      field: "dav_badge_no",
    },
    {
      label: "Ticketnummer",
      value: member.ticket_no || "—",
      edit: text("ticket_no"),
      field: "ticket_no",
    },
    {
      label: "Allergien",
      value: member.allergies || "—",
      edit: area("allergies"),
      field: "allergies",
    },
    {
      label: "Tetanusimpfung",
      value: member.tetanus_vaccination || "—",
      edit: text("tetanus_vaccination"),
      field: "tetanus_vaccination",
    },
    {
      label: "Medikamente",
      value: member.medication || "—",
      edit: area("medication"),
      field: "medication",
    },
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
    {
      label: "Schlüssel",
      value: boolBadge(member.has_key),
      edit: check("has_key"),
      field: "has_key",
    },
    {
      label: "Freikarte Halle",
      value: boolBadge(member.has_free_ticket_gym),
      edit: check("has_free_ticket_gym"),
      field: "has_free_ticket_gym",
    },
  ];

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setFieldErrors({});
        setSaving(true);
        const body: MemberUpdate = {
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
        };
        try {
          await mutation.mutateAsync(body);
          await runFlushes();
          toast.success("Gespeichert.");
          setEditing(false);
        } catch (err) {
          if (err instanceof ApiError) setFieldErrors(err.fieldErrors);
          toast.error(err instanceof Error ? err.message : "Fehler beim Speichern.");
        } finally {
          setSaving(false);
        }
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
              <Button type="submit" busy={saving}>
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              <MemberActions member={member} />
              {can("members.delete_global_member") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={removeMutation.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${member.name}“ wirklich löschen?`,
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
            id: "stammdaten",
            label: "Stammdaten",
            content: (
              <EditableDetail
                rows={withHints(mainRows, "member")}
                editing={editing}
                errors={fieldErrors}
              />
            ),
          },
          {
            id: "kontakt",
            label: "Kontaktdaten",
            content: (
              <EditableDetail
                rows={withHints(contactRows, "member")}
                editing={editing}
                errors={fieldErrors}
              />
            ),
          },
          {
            id: "skills",
            label: "Fähigkeiten",
            content: (
              <EditableDetail
                rows={withHints(skillsRows, "member")}
                editing={editing}
                errors={fieldErrors}
              />
            ),
          },
          {
            id: "sonstiges",
            label: "Sonstiges",
            content: (
              <EditableDetail
                rows={withHints(othersRows, "member")}
                editing={editing}
                errors={fieldErrors}
              />
            ),
          },
          {
            id: "org",
            label: "Organisatorisch",
            content: (
              <EditableDetail
                rows={withHints(orgRows, "member")}
                editing={editing}
                errors={fieldErrors}
              />
            ),
          },
          {
            id: "notfall",
            label: "Notfallkontakte",
            content: (
              <>
                {sectionNote("emergency-contacts")}
                <EmergencyContactsInline
                  memberId={member.id}
                  editing={editing}
                  registerFlush={getRegistrar("notfall")}
                />
              </>
            ),
          },
          {
            id: "dokumente",
            label: "Dokumente",
            content: (
              <>
                {sectionNote("documents")}
                <DocumentsInline
                  memberId={member.id}
                  editing={editing}
                  registerFlush={getRegistrar("dokumente")}
                />
              </>
            ),
          },
          {
            id: "ausbildungen",
            label: "Ausbildungen",
            content: (
              <>
                {sectionNote("trainings")}
                <TrainingsInline
                  memberId={member.id}
                  editing={editing}
                  registerFlush={getRegistrar("trainings")}
                />
              </>
            ),
          },
          {
            id: "berechtigungen",
            label: "Berechtigungen",
            content: (
              <PermissionMembersInline
                memberId={member.id}
                editing={editing}
                registerFlush={getRegistrar("berechtigungen")}
              />
            ),
          },
        ]}
      />
    </form>
  );
}

/* --- inline: Notfallkontakte (staged edit/add/delete, flushed on Save) ---- */

type EmergencyDraft = { prename: string; lastname: string; email: string; phone_number: string };
const emptyEmergency: EmergencyDraft = { prename: "", lastname: "", email: "", phone_number: "" };

function EmergencyContactsInline({
  memberId,
  editing,
  registerFlush,
}: {
  memberId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const listKey = ["members", memberId, "emergency-contacts"];
  const query = useApiQuery<EmergencyContactOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/emergency-contacts", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );
  const createM = useApiMutation<EmergencyContactOut, EmergencyContactCreate>(
    (body) =>
      unwrap(
        client.POST("/api/members/{member_id}/emergency-contacts", {
          params: { path: { member_id: memberId } },
          body,
        }),
      ),
    { invalidate: [listKey, ["members", memberId]] },
  );
  const updateM = useApiMutation<EmergencyContactOut, { id: number; body: EmergencyContactUpdate }>(
    ({ id, body }) =>
      unwrap(
        client.PATCH("/api/members/emergency-contacts/{contact_id}", {
          params: { path: { contact_id: id } },
          body,
        }),
      ),
    { invalidate: [listKey, ["members", memberId]] },
  );
  const delM = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/emergency-contacts/{contact_id}", {
          params: { path: { contact_id: id } },
        }),
      ),
    { invalidate: [listKey, ["members", memberId]] },
  );

  const serverRows = (query.data ?? []).map((r) => ({
    id: r.id,
    data: {
      prename: r.prename,
      lastname: r.lastname,
      email: r.email ?? "",
      phone_number: r.phone_number,
    } as EmergencyDraft,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<EmergencyDraft>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(d),
    update: (id, d) => updateM.mutateAsync({ id, body: d }),
    remove: (id) => delM.mutateAsync(id),
    registerFlush,
  });

  const [adding, setAdding] = useState<EmergencyDraft | null>(null);

  const field = (row: DraftRow<EmergencyDraft>, key: keyof EmergencyDraft, type = "text") =>
    editing ? (
      <input
        type={type}
        value={row.data[key]}
        onChange={(e) => setRow(row, { ...row.data, [key]: e.target.value })}
      />
    ) : (
      row.data[key] || "—"
    );

  return (
    <>
      <InlineTable
        title="Notfallkontakte"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ ...emptyEmergency })}
        addLabel="Notfallkontakt"
        columns={[
          { header: "Vorname", cell: (row) => field(row, "prename") },
          { header: "Nachname", cell: (row) => field(row, "lastname") },
          { header: "E-Mail", cell: (row) => field(row, "email", "email") },
          { header: "Telefonnummer (mobil)", cell: (row) => field(row, "phone_number") },
        ]}
      />
      {adding && (
        <Modal title="Notfallkontakt hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Vorname *">
              <input
                value={adding.prename}
                onChange={(e) => setAdding({ ...adding, prename: e.target.value })}
              />
            </Field>
            <Field label="Nachname *">
              <input
                value={adding.lastname}
                onChange={(e) => setAdding({ ...adding, lastname: e.target.value })}
              />
            </Field>
            <Field label="E-Mail">
              <input
                type="email"
                value={adding.email}
                onChange={(e) => setAdding({ ...adding, email: e.target.value })}
              />
            </Field>
            <Field label="Telefonnummer (mobil) *">
              <input
                value={adding.phone_number}
                onChange={(e) => setAdding({ ...adding, phone_number: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={
                  !adding.prename.trim() || !adding.lastname.trim() || !adding.phone_number.trim()
                }
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

/** A document row: existing rows carry a filename + url; a staged new row carries
 *  the File to upload on Save (uploaded, not editable, in place). */
type DocumentDraft = { filename: string; file: File | null; file_url: string | null };

function DocumentsInline({
  memberId,
  editing,
  registerFlush,
}: {
  memberId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const listKey = ["members", memberId, "documents"];
  const query = useApiQuery<MemberDocumentOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/documents", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );
  const createM = useApiMutation<MemberDocumentOut, File>(
    (f) => {
      const fd = new FormData();
      fd.append("f", f);
      return postMemberDocument(memberId, fd);
    },
    { invalidate: [listKey] },
  );
  const delM = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/member-documents/{document_id}", {
          params: { path: { document_id: id } },
        }),
      ),
    { invalidate: [listKey] },
  );

  const serverRows = (query.data ?? []).map((r) => ({
    id: r.id,
    data: { filename: r.filename, file: null, file_url: r.file_url ?? null } as DocumentDraft,
  }));

  const { rows, removeRow, addRow } = useInlineDraft<DocumentDraft>({
    serverRows,
    editing,
    // Documents are not editable in place, so only create (upload) / delete run.
    create: (d) => (d.file ? createM.mutateAsync(d.file) : Promise.resolve()),
    update: () => Promise.resolve(),
    remove: (id) => delM.mutateAsync(id),
    registerFlush,
  });

  const [adding, setAdding] = useState(false);
  const [file, setFile] = useState<File | null>(null);

  return (
    <>
      <InlineTable
        title="Dokumente"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => {
          setFile(null);
          setAdding(true);
        }}
        addLabel="Dokument"
        columns={[
          {
            header: "Datei",
            cell: (row) =>
              row.data.file_url ? (
                <a href={documentHref(row.data.file_url)} target="_blank" rel="noreferrer">
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
        <Modal title="Dokument hinzufügen" onClose={() => setAdding(false)} size="sm">
          <div className="stack">
            <Field label="Datei" hint="PDF oder Bild, maximal 5 MiB.">
              <input
                type="file"
                accept="application/pdf,image/jpeg,image/png,image/gif"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={!file}
                onClick={() => {
                  if (file) addRow({ filename: file.name, file, file_url: null });
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

/* --- inline: Ausbildungen -------------------------------------------------
 * Edit-in-place for the straightforward fields (title, date, participated,
 * passed) plus add / remove, all flushed on the main Save — matching the
 * admin's ``TrainingOnMemberInline`` (which had ``extra = 1``). The activities
 * of a training are still edited on its own detail page (the title links there);
 * the certificate of attendance is uploaded from the row. */

type TrainingData = {
  title: string;
  date: string;
  participated: boolean;
  passed: boolean;
  category_name: string;
  category_id: number | null;
  certificate: string | null;
};

function TrainingsInline({
  memberId,
  editing,
  registerFlush,
}: {
  memberId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const query = useApiQuery<TrainingBrief[]>(["members", "trainings"], () =>
    unwrap(client.GET("/api/members/trainings")),
  );
  const updateM = useApiMutation<TrainingOut, { id: number; body: MemberTrainingUpdate }>(
    ({ id, body }) =>
      unwrap(
        client.PATCH("/api/members/trainings/{training_id}", {
          params: { path: { training_id: id } },
          body,
        }),
      ),
    { invalidate: [["members", "trainings"]] },
  );
  const createM = useApiMutation<TrainingOut, TrainingData>(
    (d) =>
      unwrap(
        client.POST("/api/members/trainings", {
          body: {
            member_id: memberId,
            category_id: d.category_id as number,
            title: d.title,
            date: d.date || null,
            activity_ids: [],
          },
        }),
      ),
    { invalidate: [["members", "trainings"]] },
  );
  const removeM = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/trainings/{training_id}", {
          params: { path: { training_id: id } },
        }),
      ),
    { invalidate: [["members", "trainings"]] },
  );
  const categories = useApiQuery(["training-categories"], () =>
    unwrap(client.GET("/api/members/training-categories")),
  );
  const [adding, setAdding] = useState<TrainingData | null>(null);

  const serverRows = (query.data ?? [])
    .filter((t) => t.member_id === memberId)
    .map((t) => ({
      id: t.id,
      data: {
        title: t.title ?? "",
        date: t.date ?? "",
        participated: t.participated ?? false,
        passed: t.passed ?? false,
        category_name: t.category_name,
        category_id: t.category_id ?? null,
        certificate: t.certificate ?? null,
      } as TrainingData,
    }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<TrainingData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(d),
    update: (id, d) =>
      updateM.mutateAsync({
        id,
        body: {
          title: d.title,
          date: d.date || null,
          participated: d.participated,
          passed: d.passed,
        },
      }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });

  const categoryOptions = (categories.data ?? []).map((c) => ({ value: c.id, label: c.name }));

  return (
    <>
      <InlineTable
        title="Ausbildungen"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        empty="Keine Ausbildungen."
        onDelete={(row) => removeRow(row)}
        onAdd={
          categoryOptions.length
            ? () =>
                setAdding({
                  title: "",
                  date: "",
                  participated: false,
                  passed: false,
                  category_name: categoryOptions[0].label,
                  category_id: categoryOptions[0].value,
                  certificate: null,
                })
            : undefined
        }
        addLabel="Ausbildung"
        columns={[
          { header: "Kategorie", cell: (row) => row.data.category_name },
          {
            header: "Titel",
            cell: (row) =>
              editing ? (
                <input
                  value={row.data.title}
                  onChange={(e) => setRow(row, { ...row.data, title: e.target.value })}
                />
              ) : (
                <Link to={`/kompass/trainings/${row.id}`}>{row.data.title || "—"}</Link>
              ),
          },
          {
            header: "Datum",
            cell: (row) =>
              editing ? (
                <input
                  type="date"
                  value={row.data.date}
                  onChange={(e) => setRow(row, { ...row.data, date: e.target.value })}
                />
              ) : (
                formatDate(row.data.date)
              ),
          },
          {
            header: "Teilgenommen",
            cell: (row) =>
              editing ? (
                <input
                  type="checkbox"
                  checked={row.data.participated}
                  onChange={(e) => setRow(row, { ...row.data, participated: e.target.checked })}
                />
              ) : (
                boolBadge(row.data.participated)
              ),
          },
          {
            header: "Bestanden",
            cell: (row) =>
              editing ? (
                <input
                  type="checkbox"
                  checked={row.data.passed}
                  onChange={(e) => setRow(row, { ...row.data, passed: e.target.checked })}
                />
              ) : (
                boolBadge(row.data.passed)
              ),
          },
          {
            header: "Nachweis",
            cell: (row) =>
              row.id === null ? (
                <span className="muted small">nach dem Speichern</span>
              ) : (
                <TrainingCertificate
                  trainingId={row.id}
                  url={row.data.certificate}
                  editing={editing}
                />
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Ausbildung hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Kategorie *">
              <Select
                value={String(adding.category_id ?? "")}
                onChange={(v) => {
                  const opt = categoryOptions.find((o) => String(o.value) === v);
                  setAdding({ ...adding, category_id: Number(v), category_name: opt?.label ?? "" });
                }}
                options={categoryOptions}
              />
            </Field>
            <Field label="Titel *">
              <input
                value={adding.title}
                onChange={(e) => setAdding({ ...adding, title: e.target.value })}
              />
            </Field>
            <Field label="Datum">
              <input
                type="date"
                value={adding.date}
                onChange={(e) => setAdding({ ...adding, date: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={!adding.title.trim() || !adding.category_id}
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

/** Upload / open a training's certificate of attendance (multipart). */
function TrainingCertificate({
  trainingId,
  url,
  editing,
}: {
  trainingId: number;
  url: string | null;
  editing: boolean;
}) {
  const toast = useToast();
  const upload = useApiMutation(
    async (f: File) => {
      const fd = new FormData();
      fd.append("f", f);
      const res = await fetch(`${API_BASE}/api/members/trainings/${trainingId}/certificate`, {
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
      invalidate: [["members", "trainings"]],
      onSuccess: () => toast.success("Nachweis hochgeladen."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  if (!editing) {
    return url ? (
      <a href={documentHref(url)} target="_blank" rel="noreferrer">
        Öffnen
      </a>
    ) : (
      <span className="muted">—</span>
    );
  }
  return (
    <div className="stack">
      {url && (
        <a href={documentHref(url)} target="_blank" rel="noreferrer">
          Aktuellen Nachweis öffnen
        </a>
      )}
      <input
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/gif"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) upload.mutate(f);
        }}
      />
    </div>
  );
}

/* --- inline: Berechtigungen (PermissionMember ACL, SENSITIVE) ------------ */

type PermData = {
  list_member_ids: number[];
  view_member_ids: number[];
  change_member_ids: number[];
  delete_member_ids: number[];
  list_group_ids: number[];
  view_group_ids: number[];
  change_group_ids: number[];
  delete_group_ids: number[];
};

const emptyPerm: PermData = {
  list_member_ids: [],
  view_member_ids: [],
  change_member_ids: [],
  delete_member_ids: [],
  list_group_ids: [],
  view_group_ids: [],
  change_group_ids: [],
  delete_group_ids: [],
};

const PERM_ROWS = [
  { label: "Auflisten", mk: "list_member_ids", gk: "list_group_ids" },
  { label: "Ansehen", mk: "view_member_ids", gk: "view_group_ids" },
  { label: "Ändern", mk: "change_member_ids", gk: "change_group_ids" },
  { label: "Löschen", mk: "delete_member_ids", gk: "delete_group_ids" },
] as const;

function PermissionMembersInline({
  memberId,
  editing,
  registerFlush,
}: {
  memberId: number;
  editing: boolean;
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const listKey = ["members", memberId, "permission-members"];
  const query = useApiQuery<MemberPermissionOut[]>(listKey, () =>
    unwrap(
      client.GET("/api/members/{member_id}/permission-members", {
        params: { path: { member_id: memberId } },
      }),
    ),
  );

  const optionsEnabled = editing || (query.data?.length ?? 0) > 0;
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

  const createM = useApiMutation<MemberPermissionOut, MemberPermissionIn>(
    (body) =>
      unwrap(
        client.POST("/api/members/{member_id}/permission-members", {
          params: { path: { member_id: memberId } },
          body,
        }),
      ),
    { invalidate: [listKey] },
  );
  const updateM = useApiMutation<MemberPermissionOut, { id: number; body: MemberPermissionIn }>(
    ({ id, body }) =>
      unwrap(
        client.PATCH("/api/members/permission-members/{permission_id}", {
          params: { path: { permission_id: id } },
          body,
        }),
      ),
    { invalidate: [listKey] },
  );
  const delM = useApiMutation<unknown, number>(
    (id) =>
      unwrap(
        client.DELETE("/api/members/permission-members/{permission_id}", {
          params: { path: { permission_id: id } },
        }),
      ),
    { invalidate: [listKey] },
  );

  const serverRows = (query.data ?? []).map((r) => ({
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
    } as PermData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<PermData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync(d),
    update: (id, d) => updateM.mutateAsync({ id, body: d }),
    remove: (id) => delM.mutateAsync(id),
    registerFlush,
  });

  const memberSelect = (values: number[], onChange: (v: number[]) => void) => (
    <MultiSelect
      options={memberOpts.map((m) => ({ value: m.id, label: m.name }))}
      selected={values}
      onChange={onChange}
      placeholder="Teilnehmende"
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

  return (
    <InlineTable
      title="Berechtigungen"
      rows={rows}
      rowKey={(row) => row.key}
      editing={editing}
      onDelete={(row) => removeRow(row)}
      onAdd={() => addRow({ ...emptyPerm })}
      addLabel="Berechtigungssatz"
      empty="Keine Berechtigungen."
      columns={PERM_ROWS.map((p) => ({
        header: p.label,
        cell: (row: DraftRow<PermData>) =>
          editing ? (
            <div className="stack">
              {memberSelect(row.data[p.mk], (v) =>
                setRow(row, { ...row.data, [p.mk]: v } as PermData),
              )}
              {groupSelect(row.data[p.gk], (v) =>
                setRow(row, { ...row.data, [p.gk]: v } as PermData),
              )}
            </div>
          ) : (
            <div className="small">
              <div>
                Teilnehmende:{" "}
                {row.data[p.mk].length ? row.data[p.mk].map(memberName).join(", ") : "—"}
              </div>
              <div>
                Gruppen: {row.data[p.gk].length ? row.data[p.gk].map(groupName).join(", ") : "—"}
              </div>
            </div>
          ),
      }))}
    />
  );
}

/** Workflow-action buttons that POST to the members action endpoints. */
function MemberActions({ member }: { member: MemberOut }) {
  const toast = useToast();
  const navigate = useNavigate();
  const confirm = useConfirmDialog();

  const recipient = member.email || member.name;

  const action = (
    label: string,
    question: string,
    success: string,
    run: () => Promise<unknown>,
  ) => ({ label, question, success, run });

  // Each of these sends an e-mail immediately, so each asks first and then says
  // what was sent and to whom.
  const actions = [
    action(
      "Echo anfordern",
      `${member.name} per E-Mail an ${recipient} auffordern, die eigenen Daten zu prüfen?`,
      `Rückmeldungs-Anfrage an ${recipient} verschickt.`,
      () =>
        unwrap(
          client.POST("/api/members/{member_id}/request-echo", {
            params: { path: { member_id: member.id } },
          }),
        ),
    ),
    action(
      "Als Nutzer einladen",
      `${member.name} per E-Mail an ${recipient} einladen, einen Kompass-Zugang anzulegen?`,
      `Einladung an ${recipient} verschickt.`,
      () =>
        unwrap(
          client.POST("/api/members/{member_id}/invite-as-user", {
            params: { path: { member_id: member.id } },
          }),
        ),
    ),
    action(
      "Passwort-Reset anfordern",
      `${member.name} per E-Mail an ${recipient} einen Link zum Zurücksetzen des Passworts schicken?`,
      `Passwort-Link an ${recipient} verschickt.`,
      () =>
        unwrap(
          client.POST("/api/members/{member_id}/request-password-reset", {
            params: { path: { member_id: member.id } },
          }),
        ),
    ),
    action(
      "Anmeldebogen anfordern",
      `${member.name} per E-Mail an ${recipient} auffordern, den unterschriebenen Anmeldebogen hochzuladen?`,
      `Anfrage an ${recipient} verschickt.`,
      () =>
        unwrap(
          client.POST("/api/members/{member_id}/request-registration-form", {
            params: { path: { member_id: member.id } },
          }),
        ),
    ),
  ];

  const mutation = useApiMutation((a: (typeof actions)[number]) => a.run(), {
    invalidate: [["members"], ["members", member.id]],
    onSuccess: (_data, a) => toast.success(a.success),
    onError: (e: Error) => toast.error(e.message),
  });

  // Unconfirming turns the member back into an unconfirmed registration, so it
  // needs a confirmation and then navigates to where the record now lives —
  // staying on this page would 404 (the member-only endpoint no longer resolves).
  const unconfirmMutation = useApiMutation<unknown, void>(
    () =>
      unwrap(
        client.POST("/api/members/{member_id}/unconfirm", {
          params: { path: { member_id: member.id } },
        }),
      ),
    {
      invalidate: [["members"], ["members", member.id], ["registrations"]],
      onSuccess: () => {
        toast.success("Bestätigung aufgehoben.");
        navigate("/kompass/registrations");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const busy = mutation.isPending || unconfirmMutation.isPending;

  return (
    <Menu label="Aktionen">
      {actions.map((a) => (
        <Button
          key={a.label}
          type="button"
          variant="ghost"
          busy={busy}
          onClick={async () => {
            if (await confirm({ title: a.label, message: a.question, confirmLabel: "Senden" }))
              mutation.mutate(a);
          }}
        >
          {a.label}
        </Button>
      ))}
      <Button
        type="button"
        variant="danger"
        busy={busy}
        onClick={async () => {
          if (
            await confirm({
              title: "Bestätigung aufheben",
              message: `Die Bestätigung von ${member.name} aufheben? Der Eintrag wird wieder zu einer offenen Registrierung.`,
              confirmLabel: "Aufheben",
              danger: true,
            })
          )
            unconfirmMutation.mutate();
        }}
      >
        Bestätigung aufheben
      </Button>
    </Menu>
  );
}

/* --- route fragment ------------------------------------------------------ */
export const membersRoutes = (
  <>
    <Route path="meine/gruppen" element={<MeineGruppen />} />
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
