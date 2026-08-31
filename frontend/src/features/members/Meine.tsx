import { useNavigate } from "react-router-dom";

import { client, unwrap } from "../../api/http";
import { useApiQuery } from "../../api/hooks";
import { useMe } from "../../api/me";
import { DataTable, EmptyState, PageHeader, QueryBoundary } from "../../components/ui";
import type { components } from "../../api/schema";

type GroupOut = components["schemas"]["GroupOut"];

/**
 * "Meine Gruppen" — the groups the signed-in user leads. The groups list is not
 * server-scoped (holders of `view_group` see every group), so it is filtered
 * client-side against the current member via each group's `leiters`.
 */
export function MeineGruppen() {
  const navigate = useNavigate();
  const me = useMe();
  const memberId = me.data?.member_id ?? null;
  const query = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));

  const rows = (query.data ?? []).filter(
    (g: GroupOut) => memberId !== null && g.leiters.some((l) => l.id === memberId),
  );

  return (
    <div>
      <PageHeader
        breadcrumbs={[{ label: "Meine Gruppen" }]}
        subtitle="Gruppen, die ich leite."
      />
      {memberId === null ? (
        <EmptyState>Dein Konto ist mit keinem Teilnehmenden-Profil verknüpft.</EmptyState>
      ) : (
        <QueryBoundary query={query} empty="Du leitest aktuell keine Gruppe.">
          {() =>
            rows.length === 0 ? (
              <EmptyState>Du leitest aktuell keine Gruppe.</EmptyState>
            ) : (
              <DataTable
                rows={rows}
                rowKey={(g) => g.id}
                onRowClick={(g) => navigate(`/kompass/groups/${g.id}/members`)}
                columns={[
                  { header: "Gruppe", cell: (g) => g.name },
                  { header: "Treffen", cell: (g) => g.time_info || "—" },
                  { header: "Jahrgänge", cell: (g) => g.age_info || "—" },
                  { header: "Kontakt", cell: (g) => g.contact_email_display || "—" },
                ]}
              />
            )
          }
        </QueryBoundary>
      )}
    </div>
  );
}
