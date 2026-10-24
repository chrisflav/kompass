import { useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useMembers } from "../../api/queries";
import { InlineTable } from "../../components/inline";
import { useInlineDraft } from "../../components/inlineDraft";
import { Button, Field, Modal, MultiSelect, Select, formatDate } from "../../components/ui";
import type { components } from "../../api/schema";

// Re-export the shared searchable-badge MultiSelect so activities call sites
// (Groups/Excursions/Klettertreff) pick it up unchanged.
export { MultiSelect };

/**
 * Shared edit controls for the activities feature. The members `/enums` endpoint
 * only exposes the choice fields of the `Member` model, so the choice fields on
 * Group / Freizeit / ActivityCategory (weekday, difficulty, tour type, transport,
 * LJP category) are declared here as static option lists mirroring the admin
 * choices. FK/M2M options are fetched from the related list endpoints at the call
 * site and passed to {@link MultiSelect}.
 */

export interface Option {
  value: number;
  label: string;
}

/** LJPProposal.category choices (IntegerField choices=LJP_CATEGORIES). */
export const LJP_PROPOSAL_CATEGORY_OPTIONS: Option[] = [
  { value: 2, label: "Themenorientierte Bildungsmaßnahme" },
  { value: 1, label: "Jugendleiter*innenweiterbildung" },
];

/** LJPProposal.goal choices (IntegerField choices=LJP_GOALS). */
export const LJP_GOAL_OPTIONS: Option[] = [
  { value: 1, label: "Qualifizierung" },
  { value: 2, label: "Partizipation" },
  { value: 3, label: "Persönlichkeitsentwicklung" },
  { value: 4, label: "Umwelt" },
];

/** LJPProposal.not_bw_reason choices (IntegerField choices=NOT_BW_REASONS). */
export const LJP_NOT_BW_REASON_OPTIONS: Option[] = [
  { value: 1, label: "aufgrund der Lehrgangsinhalte" },
  { value: 2, label: "trägereigene Räumlichkeiten" },
  { value: 3, label: "Grenznähe" },
  { value: 4, label: "wirtschaftliche Sparsamkeit" },
];

/** Weekday choices (Group.weekday, IntegerField choices=WEEKDAYS). */
export const WEEKDAY_OPTIONS: Option[] = [
  { value: 0, label: "Montag" },
  { value: 1, label: "Dienstag" },
  { value: 2, label: "Mittwoch" },
  { value: 3, label: "Donnerstag" },
  { value: 4, label: "Freitag" },
  { value: 5, label: "Samstag" },
  { value: 6, label: "Sonntag" },
];

/** Freizeit.difficulty choices. */
export const DIFFICULTY_OPTIONS: Option[] = [
  { value: 1, label: "leicht" },
  { value: 2, label: "mittel" },
  { value: 3, label: "schwer" },
];

/** Freizeit.tour_type choices. */
export const TOUR_TYPE_OPTIONS: Option[] = [
  { value: 0, label: "Gemeinschaftstour" },
  { value: 1, label: "Führungstour" },
  { value: 2, label: "Ausbildung" },
];

/** Freizeit.tour_approach ("Verkehrsmittel") choices. */
export const TOUR_APPROACH_OPTIONS: Option[] = [
  { value: 0, label: "Muskelkraft" },
  { value: 1, label: "ÖPNV" },
  { value: 2, label: "Fahrgemeinschaften" },
];

/** ActivityCategory.ljp_category choices (CharField choices=LJP_CATEGORIES). */
export const LJP_CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: "Winter", label: "Winter" },
  { value: "Skibergsteigen", label: "Skibergsteigen" },
  { value: "Klettern", label: "Klettern" },
  { value: "Bergsteigen", label: "Bergsteigen" },
  { value: "Theorie", label: "Theorie" },
  { value: "Sonstiges", label: "Sonstiges" },
];

/** Single-select over integer choices ("" = unset); styled searchable dropdown. */
export function ChoiceSelect({
  value,
  onChange,
  options,
  allowEmpty = false,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Option[];
  allowEmpty?: boolean;
}) {
  return <Select value={value} onChange={onChange} options={options} allowEmpty={allowEmpty} />;
}

/**
 * Picks several members at once to stage on an inline: the klettertreff
 * attendees and the excursion / note-list participants. Members already on the
 * list (saved or staged) are not offered again, so none is added twice.
 */
export function AddMembersModal({
  options,
  loading,
  excludeIds,
  onAdd,
  onClose,
  children,
}: {
  options: Option[];
  /** The member list is still being fetched. */
  loading: boolean;
  excludeIds: (number | null)[];
  /** Receives the picked members in the order of `options`. */
  onAdd: (members: Option[]) => void;
  onClose: () => void;
  /** Further fields that apply to every picked member (e.g. a comment). */
  children?: ReactNode;
}) {
  const [selected, setSelected] = useState<number[]>([]);
  const taken = new Set(excludeIds);
  const available = options.filter((o) => !taken.has(o.value));
  const emptyText = loading
    ? "Mitglieder werden geladen …"
    : available.length === 0 && options.length > 0
      ? "Alle Mitglieder sind bereits eingetragen."
      : "Keine Treffer.";

  return (
    <Modal title="Teilnehmende hinzufügen" onClose={onClose} size="sm">
      <div className="stack">
        <Field label="Teilnehmende" group>
          <MultiSelect
            options={available}
            selected={selected}
            onChange={setSelected}
            placeholder="Mitglieder wählen…"
            emptyText={emptyText}
          />
        </Field>
        {children}
        <div className="row-actions">
          <Button
            type="button"
            disabled={selected.length === 0}
            onClick={() => onAdd(available.filter((o) => selected.includes(o.value)))}
          >
            Hinzufügen
          </Button>
          <Button type="button" variant="ghost" onClick={onClose}>
            Abbrechen
          </Button>
        </div>
      </div>
    </Modal>
  );
}

/** ISO datetime → value for `<input type="datetime-local">` (local time, no tz). */
export function toDatetimeLocal(value: string | null | undefined): string {
  if (!value) return "";
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return "";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

/** `<input type="datetime-local">` value → ISO string for the API (or null). */
export function fromDatetimeLocal(value: string): string | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

type ExcursionParticipantOut = components["schemas"]["ExcursionParticipantOut"];
type ExcursionParticipantCreate = components["schemas"]["ExcursionParticipantCreate"];

/**
 * Member-on-list inline (Django admin `MemberOnListInline`), shared by the
 * excursion and note-list change views. A `MemberOnList` row links a member to
 * the parent (Freizeit or MemberNoteList) with an optional per-entry comment.
 * The parent-scoped list/create endpoints differ, so the caller supplies the
 * list query key, the fetcher and the creator; removal and comment edits go
 * through the shared `/participants/{id}` endpoint. Supports add, per-row
 * comment edit and delete.
 *
 * Each name links to the member's record when the API says the viewer may open
 * it (leading an excursion shows its list, not every participant's record). A
 * further column shows the age — on an excursion the age on its first day — or,
 * switched by its header, the birth date; the choice is remembered per browser.
 */
type ParticipantData = {
  member_id: number | null;
  member_name: string;
  comments: string;
  /** Read-only facts from the server; unknown for a row not yet saved. */
  age?: number | null;
  birth_date?: string | null;
  may_view_member?: boolean;
};

type BirthColumn = "age" | "birth_date";
const BIRTH_COLUMN_KEY = "kompass.participants.birthColumn";

function readBirthColumn(): BirthColumn {
  try {
    if (localStorage.getItem(BIRTH_COLUMN_KEY) === "birth_date") return "birth_date";
  } catch {
    // Unreadable storage: fall through to the default.
  }
  return "age";
}

function storeBirthColumn(choice: BirthColumn) {
  try {
    localStorage.setItem(BIRTH_COLUMN_KEY, choice);
  } catch {
    // Unwritable storage: the choice still holds for this page, just not beyond.
  }
}

export function ParticipantsInline({
  title,
  editing,
  queryKey,
  listFn,
  createFn,
  invalidate,
  registerFlush,
  ageLabel = "Alter",
}: {
  title: string;
  editing: boolean;
  queryKey: unknown[];
  listFn: () => Promise<ExcursionParticipantOut[]>;
  createFn: (body: ExcursionParticipantCreate) => Promise<unknown>;
  invalidate: unknown[][];
  registerFlush: (fn: () => Promise<void>) => void;
  /** Header of the age column; an excursion names the date the age is taken on. */
  ageLabel?: string;
}) {
  const listQuery = useApiQuery(queryKey, listFn);
  const membersQuery = useMembers({ enabled: editing });
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const createM = useApiMutation((body: ExcursionParticipantCreate) => createFn(body), { invalidate });
  const removeM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/participants/{participant_id}", {
          params: { path: { participant_id: id } },
        }),
      ),
    { invalidate },
  );
  const patchM = useApiMutation(
    (vars: { id: number; comments: string }) =>
      unwrap(
        client.PATCH("/api/members/participants/{participant_id}", {
          params: { path: { participant_id: vars.id } },
          body: { comments: vars.comments },
        }),
      ),
    { invalidate },
  );

  const serverRows = (listQuery.data ?? []).map((r) => ({
    id: r.id,
    data: {
      member_id: r.member.id,
      member_name: r.member.name,
      comments: r.comments ?? "",
      age: r.age_at_excursion ?? r.member.age,
      birth_date: r.member.birth_date,
      may_view_member: r.may_view_member,
    } as ParticipantData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<ParticipantData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync({ member_id: d.member_id ?? 0, comments: d.comments }),
    update: (id, d) => patchM.mutateAsync({ id, comments: d.comments }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });

  // The comment typed while adding, applied to every picked member; null when
  // the dialog is closed.
  const [adding, setAdding] = useState<string | null>(null);
  const [birthColumn, setBirthColumn] = useState<BirthColumn>(readBirthColumn);
  const toggleBirthColumn = () => {
    const next = birthColumn === "age" ? "birth_date" : "age";
    setBirthColumn(next);
    storeBirthColumn(next);
  };

  return (
    <>
      <InlineTable
        title={title}
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding("")}
        addLabel="Teilnehmende"
        columns={[
          {
            header: "Teilnehmende",
            cell: (row) =>
              // No link while editing: leaving the page would drop the unsaved draft.
              !editing && row.data.may_view_member && row.data.member_id !== null ? (
                <Link to={`/kompass/members/${row.data.member_id}`}>{row.data.member_name}</Link>
              ) : (
                row.data.member_name || "—"
              ),
          },
          {
            header: "Alter / Geburtsdatum",
            headerCell: (
              <button
                type="button"
                className="th-sort"
                onClick={toggleBirthColumn}
                title={birthColumn === "age" ? "Geburtsdatum anzeigen" : `${ageLabel} anzeigen`}
              >
                {birthColumn === "age" ? ageLabel : "Geburtsdatum"}
                <span className="sort-arrow" aria-hidden="true">
                  ⇄
                </span>
              </button>
            ),
            cell: (row) =>
              birthColumn === "age" ? (row.data.age ?? "—") : formatDate(row.data.birth_date),
          },
          {
            header: "Kommentar",
            cell: (row) =>
              editing ? (
                <input
                  value={row.data.comments}
                  onChange={(e) => setRow(row, { ...row.data, comments: e.target.value })}
                />
              ) : (
                row.data.comments || "—"
              ),
          },
        ]}
      />
      {adding !== null && (
        <AddMembersModal
          options={memberOptions}
          loading={membersQuery.isLoading}
          excludeIds={rows.map((row) => row.data.member_id)}
          onAdd={(members) => {
            members.forEach((m) =>
              addRow({ member_id: m.value, member_name: m.label, comments: adding }),
            );
            setAdding(null);
          }}
          onClose={() => setAdding(null)}
        >
          <Field label="Kommentar">
            <input value={adding} onChange={(e) => setAdding(e.target.value)} />
          </Field>
        </AddMembersModal>
      )}
    </>
  );
}
