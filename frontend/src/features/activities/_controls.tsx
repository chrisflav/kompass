import { useMemo, useState } from "react";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { InlineTable } from "../../components/inline";
import { Button, MultiSelect, Select, useToast } from "../../components/ui";
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
 */
export function ParticipantsInline({
  title,
  editing,
  queryKey,
  listFn,
  createFn,
  invalidate,
}: {
  title: string;
  editing: boolean;
  queryKey: unknown[];
  listFn: () => Promise<ExcursionParticipantOut[]>;
  createFn: (body: ExcursionParticipantCreate) => Promise<unknown>;
  invalidate: unknown[][];
}) {
  const toast = useToast();
  const listQuery = useApiQuery(queryKey, listFn);
  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const [memberId, setMemberId] = useState("");
  const [comments, setComments] = useState("");
  const [drafts, setDrafts] = useState<Record<number, string>>({});

  const create = useApiMutation(
    (body: ExcursionParticipantCreate) => createFn(body),
    {
      invalidate,
      onSuccess: () => {
        toast.success("Hinzugefügt.");
        setMemberId("");
        setComments("");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );
  const remove = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/participants/{participant_id}", {
          params: { path: { participant_id: id } },
        }),
      ),
    {
      invalidate,
      onSuccess: () => toast.success("Entfernt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );
  const patch = useApiMutation(
    (vars: { id: number; comments: string }) =>
      unwrap(
        client.PATCH("/api/members/participants/{participant_id}", {
          params: { path: { participant_id: vars.id } },
          body: { comments: vars.comments },
        }),
      ),
    {
      invalidate,
      onSuccess: () => toast.success("Gespeichert."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const rows = listQuery.data ?? [];
  const draftFor = (row: ExcursionParticipantOut) => drafts[row.id] ?? row.comments ?? "";

  return (
    <InlineTable
      title={title}
      rows={rows}
      rowKey={(r) => r.id}
      editing={editing}
      onDelete={(r) => remove.mutate(r.id)}
      columns={[
        { header: "Mitglied", cell: (r) => r.member.name },
        {
          header: "Kommentar",
          cell: (r) =>
            editing ? (
              <div className="stack">
                <input
                  value={draftFor(r)}
                  onChange={(e) => setDrafts((d) => ({ ...d, [r.id]: e.target.value }))}
                />
                <Button
                  type="button"
                  variant="ghost"
                  busy={patch.isPending}
                  onClick={() => patch.mutate({ id: r.id, comments: draftFor(r) })}
                >
                  Kommentar speichern
                </Button>
              </div>
            ) : (
              r.comments || "—"
            ),
        },
      ]}
      renderAdd={() => (
        <div className="stack">
          <Select
            value={memberId}
            onChange={(v) => setMemberId(v)}
            options={memberOptions}
            placeholder="Mitglied wählen …"
          />
          <input
            placeholder="Kommentar"
            value={comments}
            onChange={(e) => setComments(e.target.value)}
          />
          <Button
            type="button"
            busy={create.isPending}
            onClick={() => {
              if (memberId === "") {
                toast.error("Bitte ein Mitglied wählen.");
                return;
              }
              create.mutate({ member_id: Number(memberId), comments });
            }}
          >
            Hinzufügen
          </Button>
        </div>
      )}
    />
  );
}
