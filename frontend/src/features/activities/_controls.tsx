import { useMemo, useState } from "react";

import { client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { InlineTable } from "../../components/inline";
import { useInlineDraft } from "../../components/inlineDraft";
import { Button, Field, Modal, MultiSelect, Select } from "../../components/ui";
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
type ParticipantData = { member_id: number | null; member_name: string; comments: string };

export function ParticipantsInline({
  title,
  editing,
  queryKey,
  listFn,
  createFn,
  invalidate,
  registerFlush,
}: {
  title: string;
  editing: boolean;
  queryKey: unknown[];
  listFn: () => Promise<ExcursionParticipantOut[]>;
  createFn: (body: ExcursionParticipantCreate) => Promise<unknown>;
  invalidate: unknown[][];
  registerFlush: (fn: () => Promise<void>) => void;
}) {
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
    data: { member_id: r.member.id, member_name: r.member.name, comments: r.comments ?? "" } as ParticipantData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<ParticipantData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync({ member_id: d.member_id ?? 0, comments: d.comments }),
    update: (id, d) => patchM.mutateAsync({ id, comments: d.comments }),
    remove: (id) => removeM.mutateAsync(id),
    registerFlush,
  });

  const [adding, setAdding] = useState<ParticipantData | null>(null);

  return (
    <>
      <InlineTable
        title={title}
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={() => setAdding({ member_id: null, member_name: "", comments: "" })}
        addLabel="Teilnehmende"
        columns={[
          { header: "Teilnehmende", cell: (row) => row.data.member_name || "—" },
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
      {adding && (
        <Modal title="Teilnehmende hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Teilnehmende">
              <Select
                value={adding.member_id === null ? "" : String(adding.member_id)}
                onChange={(v) =>
                  setAdding({
                    ...adding,
                    member_id: v === "" ? null : Number(v),
                    member_name: memberOptions.find((o) => String(o.value) === v)?.label ?? "",
                  })
                }
                options={memberOptions}
                placeholder="Teilnehmende wählen …"
              />
            </Field>
            <Field label="Kommentar">
              <input
                value={adding.comments}
                onChange={(e) => setAdding({ ...adding, comments: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={adding.member_id === null}
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
