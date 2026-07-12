import { Link } from "react-router-dom";
import type { ReactNode } from "react";

import { client, unwrap } from "../api/http";
import { useApiQuery } from "../api/hooks";
import { ContourField, KompassMark } from "../components/Contour";

interface Group {
  label: string;
  items: { to: string; label: string; hint: string }[];
}

const GROUPS: Group[] = [
  {
    label: "Mitglieder",
    items: [
      { to: "/app/members", label: "Mitglieder", hint: "Mitglieder verwalten" },
      { to: "/app/registrations", label: "Registrierungen", hint: "Neue Anmeldungen bestätigen" },
      { to: "/app/waiters", label: "Warteliste", hint: "Wartende einladen" },
      { to: "/app/trainings", label: "Ausbildungen", hint: "Schulungen & Nachweise" },
    ],
  },
  {
    label: "Aktivitäten",
    items: [
      { to: "/app/groups", label: "Gruppen", hint: "Gruppen & Jahrgänge" },
      { to: "/app/excursions", label: "Ausfahrten", hint: "Fahrten & Freizeiten" },
      { to: "/app/events", label: "Termine", hint: "Terminplanung" },
    ],
  },
  {
    label: "Finanzen",
    items: [
      { to: "/app/finance/statements", label: "Abrechnungen", hint: "Belege & Erstattungen" },
      { to: "/app/finance/transactions", label: "Buchungen", hint: "Zahlungen" },
    ],
  },
  {
    label: "Kommunikation",
    items: [
      { to: "/app/mailer/messages", label: "Nachrichten", hint: "Rundmails versenden" },
      { to: "/app/mailer/addresses", label: "E-Mail-Adressen", hint: "Verteiler" },
    ],
  },
  {
    label: "Website",
    items: [
      { to: "/app/cms/posts", label: "Beiträge", hint: "Aktuelles & Berichte" },
      { to: "/app/cms/sections", label: "Bereiche", hint: "Seitenstruktur" },
      { to: "/app/cms/faqs", label: "FAQ", hint: "Häufige Fragen" },
      { to: "/app/cms/links", label: "Links", hint: "Externe Links" },
    ],
  },
];

const today = new Date().toLocaleDateString("de-DE", {
  day: "2-digit",
  month: "long",
  year: "numeric",
});

/** Live count for a list endpoint, shown large; renders a placeholder while the
 *  query is loading or if it fails so the dashboard never breaks on one call. */
function StatTile({
  to,
  label,
  caption,
  query,
  attention,
}: {
  to: string;
  label: string;
  caption: string;
  query: { data?: unknown[]; isLoading: boolean; error: unknown };
  /** Highlight (needle-red accent) when the count is above zero — a to-do. */
  attention?: boolean;
}) {
  const count = query.data?.length;
  const flagged = attention && typeof count === "number" && count > 0;
  return (
    <Link to={to} className={flagged ? "stat-tile attention" : "stat-tile"}>
      <span className="stat-num">
        {query.isLoading ? "…" : query.error || count === undefined ? "–" : count}
      </span>
      <span className="stat-label">{label}</span>
      <span className="stat-caption">{caption}</span>
    </Link>
  );
}

export function Dashboard() {
  const registrations = useApiQuery(["registrations"], () =>
    unwrap(client.GET("/api/members/registrations")),
  );
  const waiters = useApiQuery(["waiters"], () => unwrap(client.GET("/api/members/waiters")));

  // Configurable external links (startpage Link model), as on the old admin
  // dashboard (custom_admin_view → external_links).
  const links = useApiQuery(["startpage", "links"], () =>
    unwrap(client.GET("/api/startpage/links")),
  );
  const visibleLinks = (links.data ?? []).filter((l) => l.visible);

  return (
    <div>
      <header className="dash-hero">
        <ContourField rings={9} cx={104} cy={30} />
        <KompassMark size={44} />
        <div className="dash-hero-text">
          <h2 className="dash-hero-title">Willkommen zurück</h2>
          <p className="dash-hero-sub">Kompass · Verwaltung der JDAV Ludwigsburg</p>
        </div>
        <span className="dash-hero-meta">Stand · {today}</span>
      </header>

      <section className="dash-section">
        <SectionEyebrow>Zu erledigen</SectionEyebrow>
        <div className="stat-grid">
          <StatTile
            to="/app/registrations"
            label="Offene Registrierungen"
            caption="warten auf Bestätigung"
            query={registrations}
            attention
          />
          <StatTile
            to="/app/waiters"
            label="Warteliste"
            caption="Wartende einladen"
            query={waiters}
          />
        </div>
      </section>

      <section className="dash-section">
        <SectionEyebrow>Bereiche</SectionEyebrow>
        {GROUPS.map((group) => (
          <div key={group.label} className="dash-group">
            <h3 className="dash-group-title">{group.label}</h3>
            <div className="card-grid">
              {group.items.map((s) => (
                <Link key={s.to} to={s.to} className="shortcut-card">
                  <span className="shortcut-title">{s.label}</span>
                  <span className="muted small">{s.hint}</span>
                </Link>
              ))}
            </div>
          </div>
        ))}
      </section>

      {visibleLinks.length > 0 && (
        <section className="dash-section">
          <SectionEyebrow>Nützliche Links</SectionEyebrow>
          <div className="card-grid">
            {visibleLinks.map((l) => (
              <a
                key={l.id}
                href={l.url}
                target="_blank"
                rel="noreferrer"
                className="shortcut-card"
              >
                <span className="shortcut-title">{l.title || l.url}</span>
                <span className="muted small">{l.url}</span>
              </a>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function SectionEyebrow({ children }: { children: ReactNode }) {
  return <p className="eyebrow dash-eyebrow">{children}</p>;
}
