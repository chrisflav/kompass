import { Link } from "react-router-dom";

import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { ContourField } from "../../../components/Contour";
import { QueryBoundary } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { formatDate, Prose } from "./shared";

type IndexOut = components["schemas"]["IndexOut"];
type PostBrief = components["schemas"]["PublicPostBrief"];

function preview(text?: string | null): string {
  if (!text) return "";
  return text.length > 200 ? `${text.slice(0, 200)}…` : text;
}

function PostTeaserCard({ post }: { post: PostBrief }) {
  return (
    <article className="shortcut-card">
      <span className="shortcut-title">{post.title}</span>
      {post.date && <span className="muted small">{formatDate(post.date)}</span>}
      <Prose text={preview(post.website_text)} />
    </article>
  );
}

export function PublicIndex() {
  const query = useApiQuery(["public", "index"], () =>
    unwrap(client.GET("/api/startpage/public/index")),
  );

  return (
    <div>
      <header className="public-hero">
        <ContourField />
        <div className="public-hero-inner">
          <span className="public-hero-eyebrow">Jugend des Deutschen Alpenvereins</span>
          <h1>JDAV Ludwigsburg</h1>
          <p className="public-hero-lead">
            Klettern, Bergsteigen und gemeinsam draußen unterwegs — die Jugend des
            Deutschen Alpenvereins in Ludwigsburg.
          </p>
          <span className="public-hero-coords">48.8974° N · 9.1916° O</span>
        </div>
      </header>
      <QueryBoundary query={query}>
        {(data: IndexOut) => (
          <div className="stack">
            <section>
              <div className="page-header">
                <h2>Aktuelles</h2>
                <Link to="/aktuelles">Alle Neuigkeiten</Link>
              </div>
              {data.recent_posts.length === 0 ? (
                <p className="muted state">Keine aktuellen Beiträge.</p>
              ) : (
                <div className="card-grid">
                  {data.recent_posts.map((p) => (
                    <PostTeaserCard key={p.id} post={p} />
                  ))}
                </div>
              )}
            </section>
            <section>
              <div className="page-header">
                <h2>Berichte</h2>
                <Link to="/berichte">Alle Berichte</Link>
              </div>
              {data.reports.length === 0 ? (
                <p className="muted state">Keine Berichte.</p>
              ) : (
                <div className="card-grid">
                  {data.reports.map((p) => (
                    <PostTeaserCard key={p.id} post={p} />
                  ))}
                </div>
              )}
            </section>
          </div>
        )}
      </QueryBoundary>
    </div>
  );
}
