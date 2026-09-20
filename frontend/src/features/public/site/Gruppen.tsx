import { useNavigate } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { PublicPageHeader } from "./shared";

type PublicGroupBrief = components["schemas"]["PublicGroupBrief"];

export function PublicGruppen() {
  const navigate = useNavigate();
  const query = useApiQuery(["public", "groups"], () =>
    unwrap(client.GET("/api/startpage/public/groups")),
  );

  return (
    <div>
      <PublicPageHeader
        title="Gruppen"
        lead="Unsere Jugendgruppen. Wähle eine Gruppe für weitere Informationen."
      />
      <QueryBoundary query={query} empty="Zurzeit sind keine Gruppen öffentlich gelistet.">
        {(groups: PublicGroupBrief[]) => (
          <div className="card-grid">
            {groups.map((group) => (
              <button
                key={group.id}
                type="button"
                className="shortcut-card"
                style={{ cursor: "pointer", textAlign: "left" }}
                onClick={() => navigate(`/gruppe/${encodeURIComponent(group.name)}`)}
              >
                <span className="shortcut-title">{group.name}</span>
              </button>
            ))}
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
