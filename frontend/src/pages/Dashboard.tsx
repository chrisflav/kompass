import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import { client, unwrap } from "../api/http";
import { useApiQuery } from "../api/hooks";
import { useMe } from "../api/me";
import { ContourField, KompassMark } from "../components/Contour";
import { Badge } from "../components/ui";
import type { components } from "../api/schema";

type GroupOut = components["schemas"]["GroupOut"];
type ExcursionBrief = components["schemas"]["ExcursionBrief"];
type StatementBrief = components["schemas"]["StatementBrief"];

const today = new Date().toLocaleDateString("de-DE", {
  day: "2-digit",
  month: "long",
  year: "numeric",
});

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString("de-DE");
}

/** Section header: an eyebrow plus an optional "see all" link on the right. */
function SectionHead({ label, to, seeAll }: { label: string; to?: string; seeAll?: string }) {
  return (
    <div className="dash-head">
      <p className="eyebrow">{label}</p>
      {to && seeAll && (
        <Link to={to} className="dash-seeall">
          {seeAll}
        </Link>
      )}
    </div>
  );
}

/** A compact panel of linked rows, with loading / empty fallbacks. */
function ListPanel({
  loading,
  empty,
  children,
}: {
  loading: boolean;
  empty: string;
  children: ReactNode[];
}) {
  if (loading) return <div className="dash-list dash-state muted">Lädt…</div>;
  if (children.length === 0) return <div className="dash-list dash-state muted">{empty}</div>;
  return <div className="dash-list">{children}</div>;
}

function Row({
  to,
  main,
  sub,
  meta,
}: {
  to: string;
  main: ReactNode;
  sub?: ReactNode;
  meta?: ReactNode;
}) {
  return (
    <Link to={to} className="dash-row">
      <span className="dash-row-text">
        <span className="dash-row-main">{main}</span>
        {sub && <span className="dash-row-sub">{sub}</span>}
      </span>
      {meta && <span className="dash-row-meta">{meta}</span>}
    </Link>
  );
}

export function Dashboard() {
  const me = useMe();
  const memberId = me.data?.member_id ?? null;
  const firstName = me.data?.name?.split(" ")[0];

  const groups = useApiQuery(["groups"], () => unwrap(client.GET("/api/members/groups")));
  const excursions = useApiQuery(["excursions"], () =>
    unwrap(client.GET("/api/members/excursions")),
  );
  const statements = useApiQuery(["finance", "statements"], () =>
    unwrap(client.GET("/api/finance/statements")),
  );
  const links = useApiQuery(["startpage", "links"], () =>
    unwrap(client.GET("/api/startpage/links")),
  );

  const myGroups: GroupOut[] = (groups.data ?? [])
    .filter((g) => memberId !== null && g.leiters.some((l) => l.id === memberId))
    .slice(0, 3);
  const recentExcursions: ExcursionBrief[] = (excursions.data ?? []).slice(0, 3);
  const recentStatements: StatementBrief[] = (statements.data ?? []).slice(0, 3);
  const visibleLinks = (links.data ?? []).filter((l) => l.visible);

  return (
    <div className="dashboard">
      <header className="dash-hero">
        <ContourField rings={9} cx={104} cy={30} />
        <KompassMark size={44} />
        <div className="dash-hero-text">
          <h2 className="dash-hero-title">
            {firstName && memberId !== null ? (
              <>
                Willkommen,{" "}
                <Link to={`/app/members/${memberId}`} className="dash-hero-name">
                  {firstName}
                </Link>
              </>
            ) : firstName ? (
              `Willkommen, ${firstName}`
            ) : (
              "Willkommen zurück"
            )}
          </h2>
          <p className="dash-hero-sub">Kompass · Verwaltung der JDAV Ludwigsburg</p>
        </div>
        <div className="dash-hero-side">
          <Link to="/app/mailer/messages?compose=1" className="btn dash-hero-cta">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <rect x="3" y="5" width="18" height="14" rx="2" />
              <path d="m3 7 9 6 9-6" />
            </svg>
            Nachricht senden
          </Link>
          <span className="dash-hero-meta">Stand · {today}</span>
        </div>
      </header>

      <div className="dash-columns">
        <section className="dash-section">
          <SectionHead label="Meine Gruppen" to="/app/groups" seeAll="Alle Gruppen →" />
          <ListPanel loading={groups.isLoading} empty="Du leitest aktuell keine Gruppe.">
            {myGroups.map((g) => (
              <Row
                key={g.id}
                to={`/app/groups/${g.id}/members`}
                main={g.name}
                sub={g.time_info || undefined}
                meta={g.age_info || undefined}
              />
            ))}
          </ListPanel>
        </section>

        <section className="dash-section">
          <SectionHead label="Neueste Ausfahrten" to="/app/excursions" seeAll="Alle Ausfahrten →" />
          <ListPanel loading={excursions.isLoading} empty="Keine Ausfahrten.">
            {recentExcursions.map((e) => (
              <Row
                key={e.id}
                to={`/app/excursions/${e.id}`}
                main={e.name || e.code || "Ausfahrt"}
                sub={e.place || undefined}
                meta={formatDate(e.date)}
              />
            ))}
          </ListPanel>
        </section>

        <section className="dash-section">
          <SectionHead
            label="Neueste Abrechnungen"
            to="/app/finance/statements"
            seeAll="Alle Abrechnungen →"
          />
          <ListPanel loading={statements.isLoading} empty="Keine Abrechnungen.">
            {recentStatements.map((s) => (
              <Row
                key={s.id}
                to={`/app/finance/statements/${s.id}`}
                main={s.title || "Abrechnung"}
                sub={s.status_display ? <Badge>{s.status_display}</Badge> : undefined}
                meta={s.total_pretty || undefined}
              />
            ))}
          </ListPanel>
        </section>

        {visibleLinks.length > 0 && (
          <section className="dash-section">
            <SectionHead label="Nützliche Links" />
            <div className="dash-list">
              {visibleLinks.map((l) => (
                <a
                  key={l.id}
                  href={l.url}
                  target="_blank"
                  rel="noreferrer"
                  className="dash-row"
                >
                  <span className="dash-row-text">
                    <span className="dash-row-main">{l.title || l.url}</span>
                    <span className="dash-row-sub">{l.url}</span>
                  </span>
                  <span className="dash-row-meta" aria-hidden="true">
                    ↗
                  </span>
                </a>
              ))}
            </div>
          </section>
        )}
      </div>
    </div>
  );
}
