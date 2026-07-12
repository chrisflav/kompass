import { Link, useParams } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { DetailList, QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { Prose, PublicPageHeader } from "./shared";

type PublicGroupDetail = components["schemas"]["PublicGroupDetail"];
type PublicMemberBrief = components["schemas"]["PublicMemberBrief"];

function LeaderGrid({ people }: { people: PublicMemberBrief[] }) {
  if (people.length === 0) return null;
  return (
    <section style={{ marginTop: "1.5rem" }}>
      <h2>Jugendleiter:innen</h2>
      <div className="card-grid">
        {people.map((person) => (
          <div key={person.id} className="shortcut-card" style={{ alignItems: "center" }}>
            {person.image && (
              <img
                src={person.image}
                alt={person.name}
                style={{ maxWidth: "100%", borderRadius: "var(--radius)" }}
              />
            )}
            <span className="shortcut-title">{person.name}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

export function PublicGruppeDetail() {
  const { name } = useParams();
  const groupName = name ?? "";
  const query = useApiQuery(["public", "group", groupName], () =>
    unwrap(
      client.GET("/api/startpage/public/groups/{group_name}", {
        params: { path: { group_name: groupName } },
      }),
    ),
  );

  return (
    <div>
      <p>
        <Link to="/gruppen">← Alle Gruppen</Link>
      </p>
      <QueryBoundary query={query}>
        {(group: PublicGroupDetail) => {
          const items: [string, string][] = [];
          if (group.show_website_year && group.has_age_info) {
            items.push(["Jahrgang", group.age_info]);
          }
          if (group.show_website_weekday && group.weekday_display) {
            items.push(["Wochentag", group.weekday_display]);
          }
          if (group.show_website_time && group.time_slot) {
            items.push(["Zeiten", group.time_slot]);
          }
          if (group.show_website_contact_email && group.contact_email) {
            items.push(["Kontakt", group.contact_email]);
          }
          return (
            <>
              <PublicPageHeader title={group.name} />
              <Prose text={group.description} />
              {items.length > 0 && <DetailList items={items} />}
              {group.has_registration_password && (
                <p className="muted">
                  Für diese Gruppe ist eine Anmeldung mit Passwort möglich.
                </p>
              )}
              <LeaderGrid people={group.people} />
            </>
          );
        }}
      </QueryBoundary>
    </div>
  );
}
