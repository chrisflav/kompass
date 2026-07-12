import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError, client, unwrap } from "../../api/http";
import { useApiMutation, useApiQuery } from "../../api/hooks";
import { useFlushRegistry } from "../../components/inlineDraft";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import {
  Badge,
  Button,
  DataTable,
  DetailList,
  DownloadButton,
  EditableDetail,
  Menu,
  PageHeader,
  QueryBoundary,
  Select,
  Tabs,
  useToast,
  type DetailRow,
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
type LJPProposalOut = components["schemas"]["LJPProposalOut"];
type LJPProposalCreate = components["schemas"]["LJPProposalCreate"];
type LJPProposalUpdate = components["schemas"]["LJPProposalUpdate"];

function formatDate(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString("de-DE");
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
  const navigate = useNavigate();
  const query = useApiQuery(["excursions"], () => unwrap(client.GET("/api/members/excursions")));
  const rows = query.data ?? [];

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
        // BACKEND-GAP: the admin also filters by group, but ExcursionBrief does
        // not expose the excursion's groups, so a group filter is not possible
        // client-side (needs groups in the Brief or a server ?group= param).
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
    [],
  );

  const view = useListView(rows, config);

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Ausfahrten" }]}
        subtitle={`${view.rows.length} / ${view.total}`}
        actions={
          <Button variant="ghost" onClick={() => navigate("/app/activity-categories")}>
            Kategorien verwalten
          </Button>
        }
      />
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine Ausfahrten sichtbar.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(e) => e.id}
            onRowClick={(e) => navigate(`/app/excursions/${e.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "Code", cell: (e) => e.code, sortKey: "code" },
              { header: "Aktivität", cell: (e) => e.name || "—", sortKey: "name" },
              { header: "Datum", cell: (e) => formatDate(e.date), sortKey: "date" },
              { header: "Ort", cell: (e) => e.place || "—", sortKey: "place" },
              {
                header: "Genehmigt",
                cell: (e) => approvedBadge(e.approved),
                sortKey: "approved",
              },
            ]}
          />
        )}
      </QueryBoundary>
    </div>
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
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Ausfahrten", to: "/app/excursions" },
          { label: query.data ? query.data.name || query.data.code : "Ausfahrt" },
        ]}
        actions={
          <Button variant="ghost" onClick={() => history.back()}>
            Zurück
          </Button>
        }
      />
      <QueryBoundary query={query}>
        {(excursion: ExcursionOut) => <ExcursionDetailBody excursion={excursion} />}
      </QueryBoundary>
    </div>
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
  const toast = useToast();
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState(() => makeForm(excursion));
  const [fieldErrors, setFieldErrors] = useState<Record<string, string[]>>({});
  const { getRegistrar, runFlushes } = useFlushRegistry();

  const groupsQuery = useApiQuery(
    ["groups"],
    () => unwrap(client.GET("/api/members/groups")),
    { enabled: editing },
  );
  const membersQuery = useApiQuery(
    ["members"],
    () => unwrap(client.GET("/api/members/")),
    { enabled: editing },
  );
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
          onChange={(e) =>
            setForm({ ...form, approved_extra_youth_leader_count: e.target.value })
          }
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
    if (Number(form.approved_extra_youth_leader_count) !== excursion.approved_extra_youth_leader_count) {
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
      <div className="detail-actions">
        {editing ? (
          <>
            <Button
              type="submit"
              busy={mutation.isPending || ljpCreate.isPending || ljpUpdate.isPending}
            >
              Speichern
            </Button>
            <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
              Abbrechen
            </Button>
          </>
        ) : (
          <Button type="button" onClick={startEditing}>
            Bearbeiten
          </Button>
        )}
      </div>

      <div className="row-actions">
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
        <Menu label="Seminarbericht">
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
        </Menu>
        <DownloadButton
          path={`/api/members/documents/excursions/${excursion.id}/ljp-proofs`}
          method="POST"
          filename={`${excursion.code}_LJP_Nachweis.pdf`}
        >
          LJP-Nachweis
        </DownloadButton>
        {/* sjr-application requires a body; bill_id=null omits the invoice attachment.
            BACKEND-GAP: no endpoint to enumerate an excursion's bills, so the invoice
            cannot be selected here. */}
        <DownloadButton
          path={`/api/members/documents/excursions/${excursion.id}/sjr-application`}
          method="POST"
          body={{ bill_id: null }}
          filename={`${excursion.code}_SJR_Antrag.pdf`}
        >
          SJR-Antrag
        </DownloadButton>
      </div>

      <Tabs
        tabs={[
          {
            id: "allgemein",
            label: "Allgemein",
            content: <EditableDetail rows={generalRows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "genehmigung",
            label: "Genehmigung",
            content: <EditableDetail rows={approvalRows} editing={editing} errors={fieldErrors} />,
          },
          {
            id: "kennzahlen",
            label: "Kennzahlen",
            content: (
              <DetailList
                items={[
                  ["Übernachtungen", excursion.night_count],
                  ["Dauer (Tage)", excursion.duration],
                  ["Jugendleiter*innen", excursion.staff_count],
                  ["Teilnehmende", excursion.participant_count],
                  ["Personen gesamt", excursion.head_count],
                ]}
              />
            ),
          },
          {
            id: "teilnehmer",
            label: "Teilnehmer*innen",
            content: (
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
            ),
          },
          {
            id: "ljp",
            label: "LJP-Antrag",
            content: <EditableDetail rows={ljpRows} editing={editing} errors={fieldErrors} />,
          },
        ]}
      />
    </form>
  );
}
