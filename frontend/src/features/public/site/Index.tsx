import { Link } from "react-router-dom";

import { mediaUrl } from "../../../api/client";
import { client, unwrap } from "../../../api/http";
import { useApiQuery } from "../../../api/hooks";
import { ContourField } from "../../../components/Contour";
import { QueryBoundary, useDocumentTitle } from "../../../components/ui";
import type { components } from "../../../api/schema";
import { excerpt, formatDate } from "./shared";

type IndexOut = components["schemas"]["IndexOut"];
type PostBrief = components["schemas"]["PublicPostBrief"];

function postHref(post: PostBrief): string {
  return `/beitrag/${encodeURIComponent(post.section_urlname)}/${encodeURIComponent(post.urlname)}`;
}

/** A date split into its parts, for the ledger's mono rail. */
function shortDate(iso?: string | null): { day: string; rest: string } {
  if (!iso) return { day: "", rest: "" };
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return { day: "", rest: iso };
  return {
    day: String(d.getDate()).padStart(2, "0"),
    rest: d.toLocaleDateString("de-DE", { month: "short", year: "numeric" }),
  };
}

/**
 * The public landing page.
 *
 * Two audiences meet here: a parent deciding whether this is for their kid and
 * how to join, and a member checking what is on. It previously answered neither
 * — every post in both sections was dumped into two identical grids of narrow
 * equal-weight cards, so nothing was foregrounded and there was no way to sign
 * up at all.
 *
 * Now the page reads in one order: the newest story leads, the rest of the news
 * follows as a dated ledger, joining sits beside it as the one call to action,
 * and the trip reports close as a picture strip. News and reports are
 * deliberately shaped differently — one is timely, the other is an archive.
 */
export function PublicIndex() {
  useDocumentTitle("JDAV Ludwigsburg");
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
        {(data: IndexOut) => {
          const [lead, ...rest] = data.recent_posts;
          return (
            <div className="start">
                <section className="start-news">
                  <div className="start-head">
                    <h2>Aktuelles</h2>
                    <Link to="/aktuelles" className="section-more">
                      Alle Neuigkeiten →
                    </Link>
                  </div>

                  {lead ? <LeadPost post={lead} /> : <p className="muted state">Keine aktuellen Beiträge.</p>}

                  {rest.length > 0 && (
                    <ul className="ledger">
                      {rest.map((p) => {
                        const d = shortDate(p.date);
                        return (
                          <li key={p.id}>
                            <Link to={postHref(p)} className="ledger-row">
                              <span className="ledger-date">
                                <span className="ledger-day">{d.day}</span>
                                <span className="ledger-rest">{d.rest}</span>
                              </span>
                              <span className="ledger-title">{p.title}</span>
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  )}
                </section>

              <JoinBand />

              <section className="start-reports">
                <div className="start-head">
                  <h2>Berichte</h2>
                  <Link to="/berichte" className="section-more">
                    Alle Berichte →
                  </Link>
                </div>
                {data.reports.length === 0 ? (
                  <p className="muted state">Keine Berichte.</p>
                ) : (
                  <ul className="report-strip">
                    {data.reports.map((p) => (
                      <li key={p.id}>
                        <Link to={postHref(p)} className="report-card">
                          <span className="report-figure">
                            {p.image ? (
                              <img src={mediaUrl(p.image)} alt="" loading="lazy" />
                            ) : (
                              <ContourField />
                            )}
                          </span>
                          <span className="report-title">{p.title}</span>
                          <time className="report-date">{formatDate(p.date)}</time>
                        </Link>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          );
        }}
      </QueryBoundary>
    </div>
  );
}

/** The newest story, given the space that says it is the newest. */
function LeadPost({ post }: { post: PostBrief }) {
  return (
    <Link to={postHref(post)} className="lead">
      {post.image && (
        <span className="lead-figure">
          <img src={mediaUrl(post.image)} alt="" />
        </span>
      )}
      <span className="lead-body">
        {post.date && <time className="lead-date">{formatDate(post.date)}</time>}
        <span className="lead-title">{post.title}</span>
        <span className="lead-excerpt">{excerpt(post.website_text, 220)}</span>
        <span className="lead-more">Weiterlesen →</span>
      </span>
    </Link>
  );
}

/**
 * The one thing a new visitor needs, which the page previously never offered:
 * a way in. Joining runs through the waiting list, so that is the filled action.
 *
 * It sits in the page's own column between the news and the reports rather than
 * beside them — as a sidebar card it read as an advert pinned next to the page
 * instead of part of it. The placement is also the natural pivot: this is what
 * we do, want in?, here is where we have been.
 */
function JoinBand() {
  return (
    <section className="join">
      <div className="join-text">
        <span className="join-eyebrow">Mitmachen</span>
        <h2 className="join-title">Komm mit uns raus</h2>
        <p>
          Unsere Gruppen treffen sich wöchentlich zum Klettern — dazu Ausfahrten und Freizeiten
          übers Jahr. Wer mitmachen will, trägt sich auf der Warteliste ein und bekommt Bescheid,
          sobald in einer passenden Gruppe ein Platz frei wird.
        </p>
      </div>
      <div className="join-actions">
        <Link to="/warteliste" className="btn primary">
          Auf die Warteliste
        </Link>
        <Link to="/gruppen" className="btn ghost">
          Unsere Gruppen
        </Link>
      </div>
    </section>
  );
}
