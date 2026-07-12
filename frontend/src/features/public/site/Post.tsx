import { useParams } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { formatDate, Prose, PublicPageHeader } from "./shared";

type PublicPostDetail = components["schemas"]["PublicPostDetail"];
type PublicMemberBrief = components["schemas"]["PublicMemberBrief"];
type PublicMemberOnPost = components["schemas"]["PublicMemberOnPost"];

function PeopleGrid({ people }: { people: PublicMemberBrief[] }) {
  return (
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
  );
}

export function PublicPost() {
  const { section, post } = useParams();
  const sectionName = section ?? "";
  const postName = post ?? "";
  const query = useApiQuery(["public", "post", sectionName, postName], () =>
    unwrap(
      client.GET("/api/startpage/public/sections/{section_name}/posts/{post_name}", {
        params: { path: { section_name: sectionName, post_name: postName } },
      }),
    ),
  );

  return (
    <div>
      <QueryBoundary query={query}>
        {(data: PublicPostDetail) => (
          <>
            <PublicPageHeader
              title={data.title}
              lead={data.date ? formatDate(data.date) : undefined}
            />
            <Prose text={data.website_text} />

            {data.people_on_post.map((group: PublicMemberOnPost) => (
              <section key={group.id} style={{ marginTop: "1.5rem" }}>
                <h2>{group.tag || "Beteiligte"}</h2>
                {group.description && <Prose text={group.description} />}
                <PeopleGrid people={group.members} />
              </section>
            ))}

            {data.people.length > 0 && (
              <section style={{ marginTop: "1.5rem" }}>
                <h2>Gruppenmitglieder</h2>
                <PeopleGrid people={data.people} />
              </section>
            )}
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
