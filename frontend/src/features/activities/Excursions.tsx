import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { usePermissions } from "../../api/me";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useFieldsetHelp, useRowHints, useSectionHelp } from "../../api/helpTexts";
import { InlineTable } from "../../components/inline";
import { useFlushRegistry, useInlineDraft, type DraftRow } from "../../components/inlineDraft";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { StatementBillsInline } from "../finance/Statements";
import {
  Badge,
  Button,
  DataTable,
  DownloadButton,
  EditableDetail,
  Field,
  Menu,
  Modal,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  type DetailRow,
  useConfirmDialog,
  useToast,
} from "../../components/ui";
import {
  ChoiceSelect,
  DIFFICULTY_OPTIONS,
  LJP_GOAL_OPTIONS,
  LJP_NOT_BW_REASON_OPTIONS,
  LJP_PROPOSAL_CATEGORY_OPTIONS,
  MultiSelect,
  ParticipantsInline,
  TOUR_APPROACH_OPTIONS,
  TOUR_TYPE_OPTIONS,
  fromDatetimeLocal,
  toDatetimeLocal,
  type Option,
} from "./_controls";
import type { components } from "../../api/schema";

type ExcursionBrief = components["schemas"]["ExcursionBrief"];
type ExcursionOut = components["schemas"]["ExcursionOut"];
type ExcursionUpdate = components["schemas"]["ExcursionUpdate"];
type ExcursionCreate = components["schemas"]["ExcursionCreate"];
type LJPProposalOut = components["schemas"]["LJPProposalOut"];
type LJPProposalCreate = components["schemas"]["LJPProposalCreate"];
type LJPProposalUpdate = components["schemas"]["LJPProposalUpdate"];
type LJPInterventionOut = components["schemas"]["LJPInterventionOut"];
type StatementOut = components["schemas"]["StatementOut"];
type StatementUpdate = components["schemas"]["StatementUpdate"];
type FinanceOverviewOut = components["schemas"]["FinanceOverviewOut"];
type MemberBrief = components["schemas"]["MemberBrief"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
}

function euro(value: number | null | undefined): string {
  return `${(Number(value) || 0).toFixed(2)} €`;
}

function approvedBadge(approved: boolean | null | undefined) {
  if (approved === true) return <Badge tone="success">Genehmigt</Badge>;
  if (approved === false) return <Badge tone="danger">Abgelehnt</Badge>;
  return <Badge tone="warning">Unbekannt</Badge>;
}

/* --- list ----------------------------------------------------------------
 * Admin FreizeitAdmin: list_display (__str__/name, date "Begin", place,
 * approved), search_fields (name), ordering (-date), list_filter (has_participant,
 * groups, approved). We port the place + approved columns, name search, the
 * approved filter, and sortable date defaulting to newest first. */

export function ExcursionsList() {
  const { can } = usePermissions();
  const navigate = useNavigate();
  const [creating, setCreating] = useState(false);
  const query = useApiQuery(["excursions"], () => unwrap(client.GET("/api/members/excursions")));
  const rows = query.data ?? [];
  // Members back the participant filter's labels (the Brief carries only ids).
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));

  // Group filter options = the distinct groups actually present in the list.
  const groupOptions = useMemo(() => {
    const byId = new Map<number, string>();
    rows.forEach((e) => e.groups.forEach((g) => byId.set(g.id, g.name)));
    return [...byId.entries()]
      .sort((a, b) => a[1].localeCompare(b[1]))
      .map(([id, name]) => ({ value: String(id), label: name }));
  }, [rows]);

  const memberOptions = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: String(m.id), label: m.name })),
    [membersQuery.data],
  );

  const config: ListViewConfig<ExcursionBrief> = useMemo(
    () => ({
      search: (e) => [e.name, e.code, e.place],
      filters: [
        {
          key: "approved",
          label: "Genehmigt",
          options: [
            { value: "yes", label: "Genehmigt" },
            { value: "no", label: "Abgelehnt" },
            { value: "unknown", label: "Unbekannt" },
          ],
          match: (e, v) =>
            v === "yes"
              ? e.approved === true
              : v === "no"
                ? e.approved === false
                : e.approved === null || e.approved === undefined,
        },
        {
          key: "group",
          label: "Gruppe",
          options: groupOptions,
          match: (e, v) => e.groups.some((g) => String(g.id) === v),
        },
        {
          key: "participant",
          label: "Teilnehmer*in",
          options: memberOptions,
          match: (e, v) => e.participant_ids.includes(Number(v)),
        },
      ],
      sort: {
        code: (e) => e.code,
        name: (e) => e.name,
        date: (e) => e.date,
        place: (e) => e.place,
        approved: (e) => (e.approved === true ? 2 : e.approved === false ? 0 : 1),
      },
      defaultSort: { key: "date", dir: "desc" },
    }),
    [groupOptions, memberOptions],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Ausfahrten" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          <div className="row-actions">
            <Button variant="ghost" onClick={() => navigate("/kompass/activity-categories")}>
              Kategorien verwalten
            </Button>
            {can("members.add_global_freizeit") && (
              <Button onClick={() => setCreating(true)}>Neue Ausfahrt</Button>
            )}
          </div>
        }
      />
      {creating && (
        <Modal title="Neue Ausfahrt" onClose={() => setCreating(false)} size="lg">
          <ExcursionCreateForm onDone={() => setCreating(false)} />
        </Modal>
      )}
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Ausfahrten sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(e) => e.id}
            onRowClick={(e) => navigate(`/kompass/excursions/${e.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Code", cell: (e) => e.code, sortKey: "code" },
              { header: "Aktivität", cell: (e) => e.name || "—", sortKey: "name" },
              { header: "Datum", cell: (e) => formatDate(e.date), sortKey: "date" },
              { header: "Ort", cell: (e) => e.place || "—", sortKey: "place" },
              { header: "Genehmigt", cell: (e) => approvedBadge(e.approved), sortKey: "approved" },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
  );
}

/* --- create -------------------------------------------------------------- */

function ExcursionCreateForm({ onDone }: { onDone: () => void }) {
  const toast = useToast();
  const navigate = useNavigate();
  const [form, setForm] = useState({
    name: "",
    place: "",
    date: "",
    end: "",
    difficulty: "1",
    tour_type: "0",
    group_ids: [] as number[],
    jugendleiter_ids: [] as number[],
  });
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});

  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")));
  const groupOptions: Option[] = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );

  const mutation = useApiMutation(
    () => {
      const body: ExcursionCreate = {
        name: form.name,
        place: form.place || null,
        date: fromDatetimeLocal(form.date),
        end: fromDatetimeLocal(form.end),
        difficulty: Number(form.difficulty),
        tour_type: Number(form.tour_type),
        group_ids: form.group_ids,
        jugendleiter_ids: form.jugendleiter_ids,
        activity_ids: [],
      };
      return unwrap(client.POST("/api/members/excursions", { body }));
    },
    {
      invalidate: [["excursions"]],
      onSuccess: (created: ExcursionOut) => {
        toast.success("Ausfahrt angelegt.");
        onDone();
        navigate(`/kompass/excursions/${created.id}`);
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
        mutation.mutate(undefined);
      }}
    >
      <Field label="Aktivität">
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
        {fieldErrors.name && <div className="field-error">{fieldErrors.name.join(" ")}</div>}
      </Field>
      <Field label="Stützpunkt / Ort">
        <input value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} />
      </Field>
      <Field label="Von">
        <input
          type="datetime-local"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
      </Field>
      <Field label="Bis">
        <input
          type="datetime-local"
          value={form.end}
          onChange={(e) => setForm({ ...form, end: e.target.value })}
        />
      </Field>
      <Field label="Schwierigkeit">
        <ChoiceSelect
          value={form.difficulty}
          onChange={(v) => setForm({ ...form, difficulty: v })}
          options={DIFFICULTY_OPTIONS}
        />
      </Field>
      <Field label="Tourtyp">
        <ChoiceSelect
          value={form.tour_type}
          onChange={(v) => setForm({ ...form, tour_type: v })}
          options={TOUR_TYPE_OPTIONS}
        />
      </Field>
      <Field label="Gruppen">
        <MultiSelect
          options={groupOptions}
          selected={form.group_ids}
          onChange={(ids) => setForm({ ...form, group_ids: ids })}
        />
      </Field>
      <Field label="Jugendleiter*innen">
        <MultiSelect
          options={memberOptions}
          selected={form.jugendleiter_ids}
          onChange={(ids) => setForm({ ...form, jugendleiter_ids: ids })}
          searchable
        />
      </Field>
      <div className="row-actions">
        <Button type="submit" busy={mutation.isPending}>
          Anlegen
        </Button>
        <Button type="button" variant="ghost" onClick={onDone}>
          Abbrechen
        </Button>
      </div>
    </form>
  );
}

/* --- detail + edit ------------------------------------------------------- */

export function ExcursionDetailPage() {
  const { id } = useParams();
  const excursionId = Number(id);
  const query = useApiQuery(["excursions", excursionId], () =>
    unwrap(
      client.GET("/api/members/excursions/{excursion_id}", {
        params: { path: { excursion_id: excursionId } },
      }),
    ),
  );

  return (
    <QueryBoundary query={query}>
      {(excursion: ExcursionOut) => <ExcursionDetailBody excursion={excursion} />}
    </QueryBoundary>
  );
}

function makeForm(e: ExcursionOut) {
  return {
    name: e.name ?? "",
    place: e.place ?? "",
    postcode: e.postcode ?? "",
    destination: e.destination ?? "",
    date: toDatetimeLocal(e.date),
    end: toDatetimeLocal(e.end),
    description: e.description ?? "",
    difficulty: String(e.difficulty),
    tour_type: String(e.tour_type),
    tour_approach: String(e.tour_approach),
    kilometers_traveled: String(e.kilometers_traveled),
    group_ids: e.groups.map((g) => g.id),
    jugendleiter_ids: e.jugendleiter.map((j) => j.id),
    activity_ids: e.activity.map((a) => a.id),
    approved: e.approved === true ? "true" : e.approved === false ? "false" : "",
    approval_comments: e.approval_comments ?? "",
    approved_extra_youth_leader_count: String(e.approved_extra_youth_leader_count),
    // LJP-Antrag (seminar report) — a 1:1 extension of the excursion, edited as
    // a normal fieldset. Seeded async from the LJP endpoint (see the effect).
    ljp_title: "",
    ljp_category: "2",
    ljp_goal: "2",
    ljp_goal_strategy: "",
    ljp_not_bw_reason: "",
  };
}

function ExcursionDetailBody({ excursion }: { excursion: ExcursionOut }) {
  const navigate = useNavigate();
  const confirm = useConfirmDialog();
  const { can } = usePermissions();
  const removeMutation = useApiMutation(
    () =>
      unwrap(
        client.DELETE("/api/members/excursions/{excursion_id}", {
          params: { path: { excursion_id: excursion.id } },
        }),
      ),
    {
      invalidate: [["excursions"]],
      onSuccess: () => {
        toast.success("Ausfahrt gelöscht.");
        navigate("/kompass/excursions");
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const toast = useToast();
  // Attach recovered model help_text to each row by its backend field name.
  const withHints = useRowHints();
  // Recovered admin fieldset descriptions, keyed by the fieldset's first field.
  const fieldsetHelp = useFieldsetHelp();
  const fsetNote = (field: string) => {
    const note = fieldsetHelp("freizeit", field);
    return note ? <p className="fieldset-help">{note}</p> : null;
  };
  // Section intros recovered from the inline admins (participants / LJP).
  const sectionHelp = useSectionHelp();
  const sectionNote = (section: string) => {
    const note = sectionHelp(section);
    return note ? <p className="fieldset-help">{note}</p> : null;
  };
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeForm(excursion));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const [showFinance, setShowFinance] = useState(false);
  const { getRegistrar, runFlushes } = useFlushRegistry();

  const groupsQuery = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")), {
    enabled: editing,
  });
  const membersQuery = useApiQuery(["members"], () => unwrap(client.GET("/api/members/")), {
    enabled: editing,
  });
  const categoriesQuery = useApiQuery(
    ["activity-categories"],
    () => unwrap(client.GET("/api/members/activity-categories")),
    { enabled: editing },
  );
  const groupOptions: Option[] = useMemo(
    () => (groupsQuery.data ?? []).map((g) => ({ value: g.id, label: g.name })),
    [groupsQuery.data],
  );
  const memberOptions: Option[] = useMemo(
    () => (membersQuery.data ?? []).map((m) => ({ value: m.id, label: m.name })),
    [membersQuery.data],
  );
  const categoryOptions: Option[] = useMemo(
    () => (categoriesQuery.data ?? []).map((c) => ({ value: c.id, label: c.name })),
    [categoriesQuery.data],
  );

  const mutation = useApiMutation(
    (body: ExcursionUpdate) =>
      unwrap(
        client.PATCH("/api/members/excursions/{excursion_id}", {
          params: { path: { excursion_id: excursion.id } },
          body,
        }),
      ),
    { invalidate: [["excursions"], ["excursions", excursion.id]] },
  );

  // --- LJP-Antrag (seminar report): a 1:1 excursion extension, edited as a
  // normal fieldset that saves alongside the excursion on the shared Save. ---
  const ljpKey = ["excursions", excursion.id, "ljp-proposal"];
  const ljpQuery = useApiQuery<LJPProposalOut | null>(ljpKey, async () => {
    try {
      return await unwrap(
        client.GET("/api/members/excursions/{excursion_id}/ljp-proposal", {
          params: { path: { excursion_id: excursion.id } },
        }),
      );
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) return null;
      throw e;
    }
  });
  const ljp = ljpQuery.data ?? null;

  function seedLjp(target: LJPProposalOut | null) {
    setForm((f) => ({
      ...f,
      ljp_title: target?.title ?? "",
      ljp_category: target ? String(target.category) : "2",
      ljp_goal: target ? String(target.goal) : "2",
      ljp_goal_strategy: target?.goal_strategy ?? "",
      ljp_not_bw_reason:
        target?.not_bw_reason === null || target?.not_bw_reason === undefined
          ? ""
          : String(target.not_bw_reason),
    }));
  }

  // Seed the LJP draft fields once the proposal loads, unless mid-edit.
  useEffect(() => {
    if (!editing) seedLjp(ljp);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ljpQuery.data]);

  const ljpCreate = useApiMutation(
    (payload: LJPProposalCreate) =>
      unwrap(
        client.POST("/api/members/excursions/{excursion_id}/ljp-proposal", {
          params: { path: { excursion_id: excursion.id } },
          body: payload,
        }),
      ),
    { invalidate: [ljpKey] },
  );
  const ljpUpdate = useApiMutation(
    (vars: { id: number; payload: LJPProposalUpdate }) =>
      unwrap(
        client.PATCH("/api/members/ljp-proposals/{proposal_id}", {
          params: { path: { proposal_id: vars.id } },
          body: vars.payload,
        }),
      ),
    { invalidate: [ljpKey] },
  );

  function startEditing() {
    setForm(makeForm(excursion));
    seedLjp(ljp);
    setFieldErrors({});
    setEditing(true);
  }

  const generalRows: DetailRow[] = [
    { label: "Code", value: excursion.code },
    {
      label: "Aktivität",
      field: "name",
      value: excursion.name || "—",
      edit: (
        <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
      ),
    },
    {
      label: "Stützpunkt / Ort",
      field: "place",
      value: excursion.place || "—",
      edit: (
        <input value={form.place} onChange={(e) => setForm({ ...form, place: e.target.value })} />
      ),
    },
    {
      label: "PLZ",
      field: "postcode",
      value: excursion.postcode || "—",
      edit: (
        <input
          value={form.postcode}
          onChange={(e) => setForm({ ...form, postcode: e.target.value })}
        />
      ),
    },
    {
      label: "Ziel",
      field: "destination",
      value: excursion.destination || "—",
      edit: (
        <input
          value={form.destination}
          onChange={(e) => setForm({ ...form, destination: e.target.value })}
        />
      ),
    },
    {
      label: "Von",
      field: "date",
      value: formatDate(excursion.date),
      edit: (
        <input
          type="datetime-local"
          value={form.date}
          onChange={(e) => setForm({ ...form, date: e.target.value })}
        />
      ),
    },
    {
      label: "Bis",
      field: "end",
      value: formatDate(excursion.end),
      edit: (
        <input
          type="datetime-local"
          value={form.end}
          onChange={(e) => setForm({ ...form, end: e.target.value })}
        />
      ),
    },
    {
      label: "Beschreibung",
      field: "description",
      value: excursion.description || "—",
      edit: (
        <textarea
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
        />
      ),
    },
    {
      label: "Gruppen",
      field: "groups",
      value: excursion.groups.length ? excursion.groups.map((g) => g.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={groupOptions}
          selected={form.group_ids}
          onChange={(ids) => setForm({ ...form, group_ids: ids })}
        />
      ),
    },
    {
      label: "Jugendleiter*innen",
      field: "jugendleiter",
      value: excursion.jugendleiter.length
        ? excursion.jugendleiter.map((j) => j.name).join(", ")
        : "—",
      edit: (
        <MultiSelect
          options={memberOptions}
          selected={form.jugendleiter_ids}
          onChange={(ids) => setForm({ ...form, jugendleiter_ids: ids })}
          searchable
        />
      ),
    },
    {
      label: "Kategorien",
      field: "activity",
      value: excursion.activity.length ? excursion.activity.map((a) => a.name).join(", ") : "—",
      edit: (
        <MultiSelect
          options={categoryOptions}
          selected={form.activity_ids}
          onChange={(ids) => setForm({ ...form, activity_ids: ids })}
        />
      ),
    },
    {
      label: "Schwierigkeit",
      field: "difficulty",
      value: excursion.difficulty_str || "—",
      edit: (
        <ChoiceSelect
          value={form.difficulty}
          onChange={(v) => setForm({ ...form, difficulty: v })}
          options={DIFFICULTY_OPTIONS}
        />
      ),
    },
    {
      label: "Tourtyp",
      field: "tour_type",
      value: excursion.tour_type_str || "—",
      edit: (
        <ChoiceSelect
          value={form.tour_type}
          onChange={(v) => setForm({ ...form, tour_type: v })}
          options={TOUR_TYPE_OPTIONS}
        />
      ),
    },
    {
      label: "Verkehrsmittel",
      field: "tour_approach",
      value: excursion.tour_approach_str || "—",
      edit: (
        <ChoiceSelect
          value={form.tour_approach}
          onChange={(v) => setForm({ ...form, tour_approach: v })}
          options={TOUR_APPROACH_OPTIONS}
        />
      ),
    },
    {
      label: "Fahrstrecke (km)",
      field: "kilometers_traveled",
      value: excursion.kilometers_traveled,
      edit: (
        <input
          type="number"
          value={form.kilometers_traveled}
          onChange={(e) => setForm({ ...form, kilometers_traveled: e.target.value })}
        />
      ),
    },
  ];

  const approvalRows: DetailRow[] = [
    {
      label: "Genehmigt",
      field: "approved",
      value: approvedBadge(excursion.approved),
      edit: (
        <Select
          value={form.approved}
          onChange={(v) => setForm({ ...form, approved: v })}
          options={[
            { value: "true", label: "Genehmigt" },
            { value: "false", label: "Abgelehnt" },
          ]}
          placeholder="Unbekannt"
          allowEmpty
          emptyLabel="Unbekannt"
        />
      ),
    },
    {
      label: "Genehmigungskommentar",
      field: "approval_comments",
      value: excursion.approval_comments || "—",
      edit: (
        <textarea
          value={form.approval_comments}
          onChange={(e) => setForm({ ...form, approval_comments: e.target.value })}
        />
      ),
    },
    {
      label: "Zusätzliche Jugendleiter*innen",
      field: "approved_extra_youth_leader_count",
      value: excursion.approved_extra_youth_leader_count,
      edit: (
        <input
          type="number"
          value={form.approved_extra_youth_leader_count}
          onChange={(e) => setForm({ ...form, approved_extra_youth_leader_count: e.target.value })}
        />
      ),
    },
  ];

  const ljpRows: DetailRow[] = [
    {
      label: "Titel",
      field: "title",
      value: ljp?.title || "—",
      edit: (
        <input
          value={form.ljp_title}
          onChange={(e) => setForm({ ...form, ljp_title: e.target.value })}
        />
      ),
    },
    {
      label: "Kategorie",
      field: "category",
      value: ljp?.category_display ?? "—",
      edit: (
        <ChoiceSelect
          value={form.ljp_category}
          onChange={(v) => setForm({ ...form, ljp_category: v })}
          options={LJP_PROPOSAL_CATEGORY_OPTIONS}
        />
      ),
    },
    {
      label: "Bildungsziel",
      field: "goal",
      value: ljp?.goal_display ?? "—",
      edit: (
        <ChoiceSelect
          value={form.ljp_goal}
          onChange={(v) => setForm({ ...form, ljp_goal: v })}
          options={LJP_GOAL_OPTIONS}
        />
      ),
    },
    {
      label: "Zielverfolgung und -erreichung",
      field: "goal_strategy",
      value: ljp?.goal_strategy || "—",
      edit: (
        <textarea
          value={form.ljp_goal_strategy}
          onChange={(e) => setForm({ ...form, ljp_goal_strategy: e.target.value })}
        />
      ),
    },
    {
      label: "Begründung außerhalb Baden-Württembergs",
      field: "not_bw_reason",
      value: ljp?.not_bw_reason_display || "—",
      edit: (
        <ChoiceSelect
          value={form.ljp_not_bw_reason}
          onChange={(v) => setForm({ ...form, ljp_not_bw_reason: v })}
          options={LJP_NOT_BW_REASON_OPTIONS}
          allowEmpty
        />
      ),
    },
  ];

  async function submit() {
    setFieldErrors({});
    const body: ExcursionUpdate = {
      name: form.name,
      place: form.place,
      postcode: form.postcode || null,
      destination: form.destination || null,
      date: fromDatetimeLocal(form.date),
      end: fromDatetimeLocal(form.end),
      description: form.description || null,
      difficulty: Number(form.difficulty),
      tour_type: Number(form.tour_type),
      tour_approach: Number(form.tour_approach),
      kilometers_traveled: Number(form.kilometers_traveled),
      group_ids: form.group_ids,
      jugendleiter_ids: form.jugendleiter_ids,
      activity_ids: form.activity_ids,
    };
    // Approval fields are permission-gated server-side (manage_approval_excursion).
    // Only send them when the user actually changed one, so a non-approver editing
    // the general fields is not rejected with 403.
    const origApproved =
      excursion.approved === true ? "true" : excursion.approved === false ? "false" : "";
    if (form.approved !== origApproved) {
      body.approved = form.approved === "" ? null : form.approved === "true";
    }
    if ((form.approval_comments || "") !== (excursion.approval_comments || "")) {
      body.approval_comments = form.approval_comments || null;
    }
    if (
      Number(form.approved_extra_youth_leader_count) !== excursion.approved_extra_youth_leader_count
    ) {
      body.approved_extra_youth_leader_count = Number(form.approved_extra_youth_leader_count);
    }
    try {
      await mutation.mutateAsync(body);
      // Persist the LJP fieldset on the same Save: update if it exists, create
      // once the user has filled something in, otherwise leave it absent.
      const ljpBody = {
        title: form.ljp_title,
        category: Number(form.ljp_category),
        goal: Number(form.ljp_goal),
        goal_strategy: form.ljp_goal_strategy,
        not_bw_reason: form.ljp_not_bw_reason === "" ? null : Number(form.ljp_not_bw_reason),
      };
      if (ljp) {
        await ljpUpdate.mutateAsync({ id: ljp.id, payload: ljpBody });
      } else if (form.ljp_title || form.ljp_goal_strategy) {
        await ljpCreate.mutateAsync(ljpBody);
      }
      await runFlushes();
      toast.success("Gespeichert.");
      setEditing(false);
    } catch (e) {
      if (e instanceof ApiError) setFieldErrors(e.fieldErrors);
      toast.error(e instanceof Error ? e.message : "Speichern fehlgeschlagen.");
    }
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        submit();
      }}
    >
      <PageHeader
        breadcrumbs={[
          { label: "Ausfahrten", to: "/kompass/excursions" },
          { label: excursion.name || excursion.code },
        ]}
        actions={
          editing ? (
            <>
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Abbrechen
              </Button>
              <Button
                type="submit"
                busy={mutation.isPending || ljpCreate.isPending || ljpUpdate.isPending}
              >
                Speichern
              </Button>
            </>
          ) : (
            <>
              <Button type="button" variant="ghost" onClick={() => history.back()}>
                Zurück
              </Button>
              {excursion.statement_id != null && (
                <Button type="button" variant="ghost" onClick={() => setShowFinance(true)}>
                  Finanzübersicht
                </Button>
              )}
              <Menu label="Dokumente">
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/crisis-intervention-list`}
                  method="POST"
                  filename={`${excursion.code}_Kriseninterventionsliste.pdf`}
                >
                  Kriseninterventionsliste
                </DownloadButton>
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/notes-list`}
                  method="POST"
                  filename={`${excursion.code}_Notizen.pdf`}
                >
                  Notizenliste
                </DownloadButton>
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/seminar-vbk`}
                  method="POST"
                  filename={`${excursion.code}_V-BK.xlsx`}
                >
                  Seminar V-BK
                </DownloadButton>
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/seminar-report-docx`}
                  method="POST"
                  filename={`${excursion.code}_Seminarbericht.docx`}
                >
                  Seminarbericht (docx)
                </DownloadButton>
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/seminar-report-costs`}
                  method="POST"
                  filename={`${excursion.code}_TN_Kosten.pdf`}
                >
                  Seminar TN/Kosten
                </DownloadButton>
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/ljp-proofs`}
                  method="POST"
                  filename={`${excursion.code}_LJP_Nachweis.pdf`}
                >
                  LJP-Nachweis
                </DownloadButton>
                {/* sjr-application requires a body; bill_id=null omits the invoice
                    attachment. BACKEND-GAP: no endpoint to enumerate an excursion's
                    bills, so the invoice cannot be selected here. */}
                <DownloadButton
                  path={`/api/members/documents/excursions/${excursion.id}/sjr-application`}
                  method="POST"
                  body={{ bill_id: null }}
                  filename={`${excursion.code}_SJR_Antrag.pdf`}
                >
                  SJR-Antrag
                </DownloadButton>
              </Menu>
              {can("members.delete_global_freizeit") && (
                <Button
                  type="button"
                  variant="danger"
                  busy={removeMutation.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message: `„${excursion.name || excursion.code}“ wirklich löschen?`,
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
            id: "allgemein",
            label: "Allgemein",
            content: (
              <>
                {fsetNote("name")}
                <EditableDetail
                  rows={withHints(generalRows, "freizeit")}
                  editing={editing}
                  errors={fieldErrors}
                />
              </>
            ),
          },
          {
            id: "genehmigung",
            label: "Genehmigung",
            content: (
              <>
                {fsetNote("approved")}
                <EditableDetail
                  rows={withHints(approvalRows, "freizeit")}
                  editing={editing}
                  errors={fieldErrors}
                />
              </>
            ),
          },
          {
            id: "teilnehmer",
            label: "Teilnehmer*innen",
            content: (
              <>
                {sectionNote("participants")}
                <ParticipantsInline
                  title="Teilnehmer*innen"
                  editing={editing}
                  queryKey={["excursions", excursion.id, "participants"]}
                  listFn={() =>
                    unwrap(
                      client.GET("/api/members/excursions/{excursion_id}/participants", {
                        params: { path: { excursion_id: excursion.id } },
                      }),
                    )
                  }
                  createFn={(body) =>
                    unwrap(
                      client.POST("/api/members/excursions/{excursion_id}/participants", {
                        params: { path: { excursion_id: excursion.id } },
                        body,
                      }),
                    )
                  }
                  invalidate={[
                    ["excursions", excursion.id, "participants"],
                    ["excursions", excursion.id],
                  ]}
                  registerFlush={getRegistrar("participants")}
                />
              </>
            ),
          },
          {
            id: "ljp",
            label: "LJP-Antrag",
            content: (
              <>
                {sectionNote("ljp")}
                <EditableDetail
                  rows={withHints(ljpRows, "ljpproposal")}
                  editing={editing}
                  errors={fieldErrors}
                />
                <InterventionsInline
                  proposalId={ljp?.id ?? null}
                  interventions={ljp?.interventions ?? []}
                  editing={editing}
                  invalidate={[ljpKey]}
                  registerFlush={getRegistrar("interventions")}
                />
              </>
            ),
          },
          {
            id: "abrechnung",
            label: "Abrechnung",
            content: (
              <StatementSection
                excursion={excursion}
                editing={editing}
                jugendleiter={excursion.jugendleiter}
                registerFlush={getRegistrar("statement")}
                registerBillsFlush={getRegistrar("statement-bills")}
              />
            ),
          },
        ]}
      />

      {showFinance && excursion.statement_id != null && (
        <FinanceOverviewModal
          statementId={excursion.statement_id}
          excursionId={excursion.id}
          onClose={() => setShowFinance(false)}
        />
      )}
    </form>
  );
}

/* --- Abrechnung (statement) tab ------------------------------------------ */

type StatementDraft = {
  short_description: string;
  explanation: string;
  night_cost: string;
  allowance_to_ids: number[];
  subsidy_to_id: string;
  ljp_to_id: string;
};

function statementToDraft(s: StatementOut): StatementDraft {
  return {
    short_description: s.short_description ?? "",
    explanation: s.explanation ?? "",
    night_cost: String(s.night_cost ?? "0"),
    allowance_to_ids: (s.allowance_to ?? []).map((m) => m.id),
    subsidy_to_id: s.subsidy_to ? String(s.subsidy_to.id) : "",
    ljp_to_id: s.ljp_to ? String(s.ljp_to.id) : "",
  };
}

/**
 * The excursion's statement, edited inline exactly like the admin's
 * ``StatementOnListInline`` (+ its nested ``BillOnExcursionInline``): the
 * night-cost and the allowance / subsidy / LJP recipients (restricted to the
 * excursion's youth leaders), plus the bills. When there is no statement yet a
 * button creates one; once the statement is **submitted** every field is frozen
 * (matching ``StatementAdmin.get_readonly_fields``). Field edits are flushed with
 * the excursion's Save (they never save on their own).
 */
function StatementSection({
  excursion,
  editing,
  jugendleiter,
  registerFlush,
  registerBillsFlush,
}: {
  excursion: ExcursionOut;
  editing: boolean;
  jugendleiter: MemberBrief[];
  registerFlush: (fn: () => Promise<void>) => void;
  registerBillsFlush: (fn: () => Promise<void>) => void;
}) {
  const toast = useToast();
  const statementId = excursion.statement_id;

  const statementQuery = useApiQuery(
    ["finance", "statements", statementId],
    () =>
      unwrap(
        client.GET("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statementId as number } },
        }),
      ),
    { enabled: statementId != null },
  );
  const statement = statementQuery.data ?? null;
  const submitted = statement?.submitted ?? false;

  const createM = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements", {
          body: {
            short_description: excursion.name || excursion.code,
            explanation: "",
            excursion_id: excursion.id,
            night_cost: 0,
          },
        }),
      ),
    {
      invalidate: [["excursions", excursion.id], ["excursions"], ["finance", "statements"]],
      onSuccess: () => toast.success("Abrechnung angelegt."),
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const patchM = useApiMutation(
    (body: StatementUpdate) =>
      unwrap(
        client.PATCH("/api/finance/statements/{statement_id}", {
          params: { path: { statement_id: statementId as number } },
          body,
        }),
      ),
    {
      invalidate: [
        ["finance", "statements"],
        ["finance", "statements", statementId],
        ["excursions", excursion.id],
      ],
    },
  );

  // Always starts empty: the statement query cannot have resolved during this
  // component's first render, and the effect below seeds the draft as soon as it
  // does (and whenever edit mode toggles).
  const [draft, setDraft] = useState<StatementDraft>(() => ({
    short_description: "",
    explanation: "",
    night_cost: "0",
    allowance_to_ids: [],
    subsidy_to_id: "",
    ljp_to_id: "",
  }));

  // Reseed the draft when the statement (re)loads or when edit mode toggles; a
  // stable statement identity means in-progress edits are preserved mid-edit.
  useEffect(() => {
    if (statement) setDraft(statementToDraft(statement));
  }, [statement, editing]);

  // Register the field flush with the excursion's Save. It PATCHes the editable
  // statement fields, but never a submitted (frozen) statement.
  const flushImpl = useRef<() => Promise<void>>(async () => {});
  flushImpl.current = async () => {
    if (statementId == null || submitted) return;
    await patchM.mutateAsync({
      short_description: draft.short_description,
      explanation: draft.explanation,
      night_cost: Number(draft.night_cost) || 0,
      allowance_to_ids: draft.allowance_to_ids,
      subsidy_to_id: draft.subsidy_to_id ? Number(draft.subsidy_to_id) : null,
      ljp_to_id: draft.ljp_to_id ? Number(draft.ljp_to_id) : null,
    });
  };
  const flush = useCallback(() => flushImpl.current(), []);
  useEffect(() => registerFlush(flush), [registerFlush, flush]);

  const ylOptions = useMemo(
    () => jugendleiter.map((j) => ({ value: j.id, label: j.name })),
    [jugendleiter],
  );

  if (statementId == null) {
    return (
      <div className="stack">
        <p className="muted">Diese Ausfahrt hat noch keine Abrechnung.</p>
        <div>
          <Button type="button" onClick={() => createM.mutate(undefined)} busy={createM.isPending}>
            Abrechnung anlegen
          </Button>
        </div>
      </div>
    );
  }

  return (
    <QueryBoundary query={statementQuery}>
      {(s: StatementOut) => {
        const editable = editing && !submitted;
        const recipientName = (m: MemberBrief | null | undefined) => (m ? m.name : "—");
        const rows: DetailRow[] = [
          { label: "Titel", value: <Link to={`/kompass/finance/statements/${s.id}`}>{s.title}</Link> },
          {
            label: "Status",
            value: (
              <Badge tone={s.confirmed ? "success" : s.submitted ? "info" : "warning"}>
                {s.status_display}
              </Badge>
            ),
          },
          {
            label: "Preis pro Übernachtung",
            value: euro(Number(s.night_cost) || 0),
            edit: editable ? (
              <input
                type="number"
                step="0.01"
                value={draft.night_cost}
                onChange={(e) => setDraft({ ...draft, night_cost: e.target.value })}
              />
            ) : undefined,
          },
          {
            label: "Aufwandsentschädigung an",
            value: s.allowance_to.length ? s.allowance_to.map((m) => m.name).join(", ") : "—",
            edit: editable ? (
              <MultiSelect
                options={ylOptions}
                selected={draft.allowance_to_ids}
                onChange={(ids) => setDraft({ ...draft, allowance_to_ids: ids })}
              />
            ) : undefined,
          },
          {
            label: "Zuschuss an",
            value: recipientName(s.subsidy_to),
            edit: editable ? (
              <Select
                value={draft.subsidy_to_id}
                onChange={(v) => setDraft({ ...draft, subsidy_to_id: v })}
                options={ylOptions}
                placeholder="— niemand —"
                allowEmpty
                emptyLabel="— niemand —"
              />
            ) : undefined,
          },
          {
            label: "LJP-Beitrag an",
            value: recipientName(s.ljp_to),
            edit: editable ? (
              <Select
                value={draft.ljp_to_id}
                onChange={(v) => setDraft({ ...draft, ljp_to_id: v })}
                options={ylOptions}
                placeholder="— niemand —"
                allowEmpty
                emptyLabel="— niemand —"
              />
            ) : undefined,
          },
        ];
        return (
          <div className="stack">
            {submitted && (
              <p className="fieldset-help">
                Die Abrechnung wurde eingereicht und kann nicht mehr geändert werden.
              </p>
            )}
            <EditableDetail rows={rows} editing={editable} />
            <StatementBillsInline
              statement={s}
              editing={editable}
              registerFlush={registerBillsFlush}
            />
          </div>
        );
      }}
    </QueryBoundary>
  );
}

/* --- Finance overview modal (the admin "Finance overview" estimate) ------ */

function OverviewTable({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <table className="data-table">
      <thead>
        <tr>
          {head.map((h) => (
            <th key={h}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i}>
            {r.map((c, j) => (
              <td key={j}>{c}</td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/**
 * The excursion finance overview (admin ``FreizeitAdmin.finance_overview``): an
 * estimate of the excursion's expenses vs. the association's contributions, with
 * the option to submit the statement (which then freezes it). Mirrors
 * ``admin/freizeit_finance_overview.html``.
 */
function FinanceOverviewModal({
  statementId,
  excursionId,
  onClose,
}: {
  statementId: number;
  excursionId: number;
  onClose: () => void;
}) {
  const toast = useToast();
  const confirm = useConfirmDialog();
  const query = useApiQuery(["finance", "statements", statementId, "overview"], () =>
    unwrap(
      client.GET("/api/finance/statements/{statement_id}/overview", {
        params: { path: { statement_id: statementId } },
      }),
    ),
  );

  const submitM = useApiMutation(
    () =>
      unwrap(
        client.POST("/api/finance/statements/{statement_id}/submit", {
          params: { path: { statement_id: statementId } },
        }),
      ),
    {
      invalidate: [
        ["finance", "statements"],
        ["finance", "statements", statementId],
        ["finance", "statements", statementId, "overview"],
        ["excursions", excursionId],
      ],
      onSuccess: () => {
        toast.success("Abrechnung eingereicht.");
        onClose();
      },
      onError: (e: Error) => toast.error(e.message),
    },
  );

  const bool = (v: boolean) => (v ? "✓" : "✗");

  return (
    <Modal title="Finanzübersicht" onClose={onClose} size="lg">
      <QueryBoundary query={query}>
        {(o: FinanceOverviewOut) => (
          <div className="stack">
            <p className="muted">
              Geschätzte Kosten und Zuschüsse — dies ist kein garantierter Kostenplan.
            </p>

            <h3 className="fieldset-title">Ausgaben</h3>
            <OverviewTable
              head={["Beschreibung", "Erklärung", "Betrag", "Bezahlt von", "IBAN gültig"]}
              rows={o.bills.map((b) => [
                b.short_description,
                b.explanation,
                euro(b.amount),
                b.paid_by_name ?? "—",
                bool(b.paid_by_iban_valid),
              ])}
            />
            <p>Erwartete Gesamtausgaben: {euro(o.total_bills_theoretic)}</p>

            <h3 className="fieldset-title">Zuschüsse durch den Verein</h3>
            <p>{o.staff_count} Jugendleiter*in(nen) erhalten laut Richtlinien je:</p>
            <ul>
              <li>
                {o.nights} Übernachtungen à {euro(o.price_per_night)} = {euro(o.nights_per_yl)}
              </li>
              <li>
                {o.duration} Tage à {euro(o.allowance_per_day)} = {euro(o.allowance_per_yl)}
              </li>
              <li>
                {o.kilometers_traveled} km ({o.means_of_transport}, {euro(o.euro_per_km)}/km) ={" "}
                {euro(o.transportation_per_yl)}
              </li>
            </ul>
            {o.allowances_paid > 0 ? (
              <>
                <p>Aufwandsentschädigung ausgezahlt an:</p>
                <OverviewTable
                  head={["Name", "IBAN gültig"]}
                  rows={o.allowance_to.map((m) => [m.name, bool(m.iban_valid)])}
                />
              </>
            ) : (
              <p className="muted">Keine Empfänger*innen der Aufwandsentschädigung.</p>
            )}
            {!o.allowance_to_valid && (
              <p className="field-error">
                Achtung: Die Empfänger*innen der Aufwandsentschädigung entsprechen nicht den
                Vorgaben (evtl. mehr als die zulässige Anzahl Jugendleiter*innen).
              </p>
            )}
            {o.subsidy_to ? (
              <p>
                Zuschuss ({euro(o.total_subsidies)}) an {o.subsidy_to.name} (IBAN{" "}
                {bool(o.subsidy_to.iban_valid)})
              </p>
            ) : (
              <p className="muted">Keine Empfänger*in des Zuschusses.</p>
            )}

            {o.total_org_fee > 0 && (
              <>
                <h3 className="fieldset-title">Organisationspauschale</h3>
                <p>
                  {o.old_participant_count} Teilnehmende sind 27 oder älter. Je Person und Tag
                  fallen {euro(o.org_fee)} an — bei {o.duration} Tagen insgesamt{" "}
                  {euro(o.total_org_fee_theoretical)}.
                </p>
              </>
            )}

            <h3 className="fieldset-title">LJP-Beiträge</h3>
            {o.ljp_to ? (
              <p>
                Dokumentierte {o.total_seminar_days} Seminartage für {o.ljp_participant_count}{" "}
                Teilnehmende ergeben einen Beitrag von {euro(o.ljp_contributions)}, ausgezahlt an{" "}
                {o.ljp_to.name} (IBAN {bool(o.ljp_to.iban_valid)}).
              </p>
            ) : (
              <p className="muted">
                Möglicher LJP-Beitrag von bis zu {euro(o.ljp_contributions)} — bislang keine
                Empfänger*in festgelegt.
              </p>
            )}
            {o.seminar_days.length > 0 && (
              <OverviewTable
                head={["Tag", "Seminarstunden", "Seminartage"]}
                rows={o.seminar_days.map((d) => [d.day, d.total_duration, d.sum_days])}
              />
            )}
            {o.theoretic_ljp_participant_count < 5 && (
              <p className="field-error">
                Achtung: LJP-Beiträge sind nur ab 5 Teilnehmenden möglich (aktuell{" "}
                {o.theoretic_ljp_participant_count}).
              </p>
            )}

            <h3 className="fieldset-title">Zusammenfassung</h3>
            <OverviewTable
              head={["Position", "Betrag"]}
              rows={[
                ["Ausgaben", euro(o.total_bills_theoretic)],
                ["Organisationspauschale", euro(o.total_org_fee)],
                ["Zuschüsse durch den Verein", `-${euro(o.total_subsidies)}`],
                [
                  o.ljp_to ? "LJP-Beiträge" : "Potenzielle LJP-Beiträge",
                  `-${euro(o.ljp_contributions)}`,
                ],
                ["Verbleibende Kosten", euro(o.total_relative_costs)],
              ]}
            />

            <div className="row-actions">
              {!o.submitted && (
                <Button
                  type="button"
                  busy={submitM.isPending}
                  onClick={async () => {
                    if (
                      await confirm({
                        message:
                          "Abrechnung wirklich einreichen? Danach sind keine Änderungen mehr möglich.",
                        confirmLabel: "Einreichen",
                      })
                    )
                      submitM.mutate(undefined);
                  }}
                >
                  Einreichen
                </Button>
              )}
              <Button type="button" variant="ghost" onClick={onClose}>
                Schließen
              </Button>
            </div>
          </div>
        )}
      </QueryBoundary>
    </Modal>
  );
}

/* --- LJP interventions (the seminar time schedule) ----------------------- */

type InterventionData = { date_start: string; duration: string; activity: string };

const emptyIntervention: InterventionData = { date_start: "", duration: "0", activity: "" };

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleString("de-DE");
}

/**
 * The LJP proposal's "time schedule" (Django admin ``InterventionOnLJPInline``):
 * the seminar's program points, each with a start time, duration in hours and an
 * activity/method. Editable inline (add / edit / delete) and flushed with the
 * excursion's Save. Interventions belong to the LJP proposal, so they can only be
 * added once the proposal exists — until then the section shows a hint.
 */
function InterventionsInline({
  proposalId,
  interventions,
  editing,
  invalidate,
  registerFlush,
}: {
  proposalId: number | null;
  interventions: LJPInterventionOut[];
  editing: boolean;
  invalidate: unknown[][];
  registerFlush: (fn: () => Promise<void>) => void;
}) {
  const createM = useApiMutation(
    (vars: { proposalId: number; d: InterventionData }) =>
      unwrap(
        client.POST("/api/members/ljp-proposals/{proposal_id}/interventions", {
          params: { path: { proposal_id: vars.proposalId } },
          body: {
            date_start: fromDatetimeLocal(vars.d.date_start) ?? vars.d.date_start,
            duration: vars.d.duration,
            activity: vars.d.activity,
          },
        }),
      ),
    { invalidate },
  );
  const updateM = useApiMutation(
    (vars: { id: number; d: InterventionData }) =>
      unwrap(
        client.PATCH("/api/members/interventions/{intervention_id}", {
          params: { path: { intervention_id: vars.id } },
          body: {
            date_start: fromDatetimeLocal(vars.d.date_start) ?? vars.d.date_start,
            duration: vars.d.duration,
            activity: vars.d.activity,
          },
        }),
      ),
    { invalidate },
  );
  const deleteM = useApiMutation(
    (id: number) =>
      unwrap(
        client.DELETE("/api/members/interventions/{intervention_id}", {
          params: { path: { intervention_id: id } },
        }),
      ),
    { invalidate },
  );

  const serverRows = interventions.map((i) => ({
    id: i.id,
    data: {
      date_start: toDatetimeLocal(i.date_start),
      duration: String(i.duration),
      activity: i.activity,
    } as InterventionData,
  }));

  const { rows, setRow, removeRow, addRow } = useInlineDraft<InterventionData>({
    serverRows,
    editing,
    create: (d) => createM.mutateAsync({ proposalId: proposalId as number, d }),
    update: (id, d) => updateM.mutateAsync({ id, d }),
    remove: (id) => deleteM.mutateAsync(id),
    registerFlush,
  });
  const [adding, setAdding] = useState<InterventionData | null>(null);

  return (
    <>
      <InlineTable
        title="Zeitplan"
        rows={rows}
        rowKey={(row) => row.key}
        editing={editing}
        onDelete={(row) => removeRow(row)}
        onAdd={proposalId !== null ? () => setAdding({ ...emptyIntervention }) : undefined}
        addLabel="Programmpunkt"
        empty={
          proposalId === null
            ? "Bitte zuerst den LJP-Antrag speichern, um Programmpunkte anzulegen."
            : "Keine Programmpunkte."
        }
        columns={[
          {
            header: "Beginn",
            cell: (row: DraftRow<InterventionData>) =>
              editing ? (
                <input
                  type="datetime-local"
                  value={row.data.date_start}
                  onChange={(e) => setRow(row, { ...row.data, date_start: e.target.value })}
                />
              ) : (
                formatDateTime(fromDatetimeLocal(row.data.date_start))
              ),
          },
          {
            header: "Dauer (h)",
            cell: (row: DraftRow<InterventionData>) =>
              editing ? (
                <input
                  type="number"
                  step="0.25"
                  value={row.data.duration}
                  onChange={(e) => setRow(row, { ...row.data, duration: e.target.value })}
                />
              ) : (
                row.data.duration
              ),
          },
          {
            header: "Aktion / Methode",
            cell: (row: DraftRow<InterventionData>) =>
              editing ? (
                <input
                  value={row.data.activity}
                  onChange={(e) => setRow(row, { ...row.data, activity: e.target.value })}
                />
              ) : (
                row.data.activity || "—"
              ),
          },
        ]}
      />
      {adding && (
        <Modal title="Programmpunkt hinzufügen" onClose={() => setAdding(null)} size="sm">
          <div className="stack">
            <Field label="Beginn">
              <input
                type="datetime-local"
                value={adding.date_start}
                onChange={(e) => setAdding({ ...adding, date_start: e.target.value })}
              />
            </Field>
            <Field label="Dauer (Stunden)">
              <input
                type="number"
                step="0.25"
                value={adding.duration}
                onChange={(e) => setAdding({ ...adding, duration: e.target.value })}
              />
            </Field>
            <Field label="Aktion / Methode">
              <input
                value={adding.activity}
                onChange={(e) => setAdding({ ...adding, activity: e.target.value })}
              />
            </Field>
            <div className="row-actions">
              <Button
                type="button"
                disabled={!adding.date_start || !adding.activity.trim()}
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
