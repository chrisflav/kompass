import { Link } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { formatDate, Prose, PublicPageHeader } from "./shared";

type SectionPostsOut = components["schemas"]["SectionPostsOut"];

function preview(text?: string | null): string {
  if (!text) return "";
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

/**
 * News- / reports-style listing: a section heading plus a card per post linking
 * to its detail page. ``endpoint`` selects the aktuelles or berichte route; both
 * return the identical {@link SectionPostsOut} shape.
 */
function SectionPosts({
  endpoint,
  title,
}: {
  endpoint: "/api/startpage/public/aktuelles" | "/api/startpage/public/berichte";
  title: string;
}) {
  const query = useApiQuery(["public", endpoint], () => unwrap(client.GET(endpoint)));

  return (
    <div>
      <QueryBoundary query={query}>
        {(data: SectionPostsOut) => (
          <>
            <PublicPageHeader title={data.section.title || title} />
            <Prose text={data.section.website_text} />
            {data.posts.length === 0 ? (
              <p className="muted state">Keine Beiträge vorhanden.</p>
            ) : (
              <div className="card-grid" style={{ marginTop: "1rem" }}>
                {data.posts.map((post) => (
                  <Link
                    key={post.id}
                    to={`/beitrag/${data.section.urlname}/${post.urlname}`}
                    className="shortcut-card"
                  >
                    <span className="shortcut-title">{post.title}</span>
                    {post.date && <span className="muted small">{formatDate(post.date)}</span>}
                    <Prose text={preview(post.website_text)} />
                  </Link>
                ))}
              </div>
            )}
          </>
        )}
      </QueryBoundary>
    </div>
  );
}

export function PublicAktuelles() {
  return <SectionPosts endpoint="/api/startpage/public/aktuelles" title="Aktuelles" />;
}

export function PublicBerichte() {
  return <SectionPosts endpoint="/api/startpage/public/berichte" title="Berichte" />;
}
