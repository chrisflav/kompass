import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { PostTeaser, Prose, PublicPageHeader } from "./shared";

type SectionPostsOut = components["schemas"]["SectionPostsOut"];

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
                  <PostTeaser key={post.id} post={post} />
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
