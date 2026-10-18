import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiQuery } from "../../api/hooks";
import { ListToolbar, useListView, type ListViewConfig } from "../../components/list";
import { Badge, DataTable, formatDate, PageHeader, QueryBoundary, Tabs } from "../../components/ui";
import { BASE, PartStatus, StockTabs, Whereabouts } from "./shared";
import type { components } from "../../api/schema";

type PsaRow = components["schemas"]["PsaRow"];

function DaysLeft({ row }: { row: PsaRow }) {
  if (row.days_left === null) return <span className="muted">—</span>;
  if (row.days_left < 0) return <Badge tone="danger">{-row.days_left} Tage überfällig</Badge>;
  if (row.days_left < 30) return <Badge tone="warning">{row.days_left} Tage</Badge>;
  return <span className="mono">{row.days_left} Tage</span>;
}

function Register({ retired }: { retired: boolean }) {
  const navigate = useNavigate();
  const query = useApiQuery(["material", "psa", retired], () =>
    unwrap(client.GET("/api/material/psa", { params: { query: { retired } } })),
  );
  const rows = query.data ?? [];
  const config: ListViewConfig<PsaRow> = useMemo(
    () => ({
      search: (r) => [r.label, r.product_type.name, r.holder?.name, r.location?.name],
      filters: [
        {
          key: "state",
          label: "Zustand",
          options: [
            { value: "overdue", label: "Prüfung überfällig" },
            { value: "soon", label: "in 30 Tagen fällig" },
            { value: "usage", label: "Nutzungsdauer überschritten" },
            { value: "incomplete", label: "Angaben fehlen" },
          ],
          match: (r, v) =>
            v === "overdue"
              ? (r.days_left ?? 0) < 0
              : v === "soon"
                ? r.days_left !== null && r.days_left >= 0 && r.days_left < 30
                : v === "usage"
                  ? r.past_usage_period
                  : r.incomplete,
        },
      ],
      sort: {
        id: (r) => r.label,
        type: (r) => r.product_type.name,
        next: (r) => r.next_inspection,
      },
    }),
    [],
  );
  const view = useListView(rows, config);
  return (
    <>
      <ListToolbar view={view} />
      <QueryBoundary query={query} empty="Keine PSA erfasst.">
        {() => (
          <DataTable
            rows={view.rows}
            rowKey={(r) => r.id}
            onRowClick={(r) => navigate(`${BASE}/parts/${r.id}`)}
            sort={view.sort}
            onSort={view.toggleSort}
            columns={[
              { header: "PSA-ID", cell: (r) => <span className="mono">{r.label}</span>, sortKey: "id" },
              { header: "Typ", cell: (r) => r.product_type.name, sortKey: "type" },
              { header: "Gehört", cell: (r) => r.group?.name ?? "Sektion" },
              { header: "Wo", cell: (r) => <Whereabouts part={r} /> },
              {
                header: "Letzte Prüfung",
                cell: (r) =>
                  r.last_inspection
                    ? `${formatDate(r.last_inspection.date)} · ${r.last_inspection.result === "ok" ? "ok" : "ausgesondert"}`
                    : "—",
              },
              { header: "Nächste Prüfung", cell: (r) => formatDate(r.next_inspection), sortKey: "next" },
              { header: "Noch", cell: (r) => <DaysLeft row={r} /> },
              {
                header: "",
                cell: (r) => (
                  <span className="badge-row">
                    <PartStatus status={r.status} />
                    {r.past_usage_period && <Badge tone="danger">Nutzungsdauer</Badge>}
                    {r.incomplete && <Badge tone="warning">Angaben fehlen</Badge>}
                  </span>
                ),
              },
            ]}
          />
        )}
      </QueryBoundary>
    </>
  );
}

/** The PSA register: every unit, the next inspection due first. */
export function Psa() {
  const [tab, setTab] = useState("current");
  return (
    <div>
      <PageHeader breadcrumbs={[{ label: "Material", to: BASE }, { label: "Bestand", to: `${BASE}/stock` }, { label: "PSA-Prüfungen" }]} />
      <StockTabs />
      <Tabs
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "current", label: "Im Bestand", content: tab === "current" && <Register retired={false} /> },
          { id: "retired", label: "Ausgesondert", content: tab === "retired" && <Register retired /> },
        ]}
      />
    </div>
  );
}
