import { NavLink, Outlet, Navigate, Link, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useAuth } from "../auth";
import { ContourField, KompassMark } from "./Contour";

/** Route guard: redirects to /login when there is no token. */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

interface NavGroup {
  label: string;
  items: { to: string; label: string }[];
}

/** Admin navigation mirrors the Django admin's app/model grouping. */
const NAV: NavGroup[] = [
  {
    label: "Mitglieder",
    items: [
      { to: "/app/members", label: "Mitglieder" },
      { to: "/app/registrations", label: "Registrierungen" },
      { to: "/app/waiters", label: "Warteliste" },
      { to: "/app/trainings", label: "Ausbildungen" },
    ],
  },
  {
    label: "Aktivitäten",
    items: [
      { to: "/app/groups", label: "Gruppen" },
      { to: "/app/excursions", label: "Ausfahrten" },
      { to: "/app/klettertreff", label: "Klettertreff" },
      { to: "/app/events", label: "Termine" },
    ],
  },
  {
    label: "Finanzen",
    items: [
      { to: "/app/finance/statements", label: "Abrechnungen" },
      { to: "/app/finance/bills", label: "Belege" },
      { to: "/app/finance/transactions", label: "Buchungen" },
      { to: "/app/finance/ledgers", label: "Konten" },
    ],
  },
  {
    label: "Kommunikation",
    items: [
      { to: "/app/mailer/messages", label: "Nachrichten" },
      { to: "/app/mailer/addresses", label: "E-Mail-Adressen" },
    ],
  },
  {
    label: "Material",
    items: [
      { to: "/app/material", label: "Material" },
      { to: "/app/material/categories", label: "Materialkategorien" },
    ],
  },
  {
    label: "Website",
    items: [
      { to: "/app/cms/posts", label: "Beiträge" },
      { to: "/app/cms/sections", label: "Bereiche" },
      { to: "/app/cms/faqs", label: "FAQ" },
      { to: "/app/cms/links", label: "Links" },
    ],
  },
];

export function AppLayout() {
  const { logout } = useAuth();
  const { pathname } = useLocation();
  // Longest matching nav path wins, so e.g. /app/material/categories highlights
  // only "Materialkategorien", not also the parent "Material" (/app/material).
  const allPaths = NAV.flatMap((g) => g.items.map((i) => i.to));
  const activePath = allPaths
    .filter((to) => pathname === to || pathname.startsWith(to + "/"))
    .sort((a, b) => b.length - a.length)[0];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <ContourField rings={7} cx={96} cy={26} />
          <Link to="/app" className="brand">
            <KompassMark size={24} />
            Kompass
          </Link>
        </div>
        <nav>
          {NAV.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-group-label">{group.label}</span>
              {group.items.map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={item.to === activePath ? "nav-item active" : "nav-item"}
                >
                  {item.label}
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <button className="btn ghost logout" onClick={logout}>
          Abmelden
        </button>
      </aside>
      <main className="app-content">
        <Outlet />
      </main>
    </div>
  );
}

/** Layout for the public-facing website. */
export function PublicLayout() {
  return (
    <div className="public-shell">
      <header className="public-header">
        <Link to="/" className="brand">
          <KompassMark size={24} />
          JDAV Ludwigsburg
        </Link>
        <nav className="public-nav">
          <NavLink to="/aktuelles">Aktuelles</NavLink>
          <NavLink to="/berichte">Berichte</NavLink>
          <NavLink to="/gruppen">Gruppen</NavLink>
          <NavLink to="/gruppen/faq">FAQ</NavLink>
          <NavLink to="/impressum">Impressum</NavLink>
          <NavLink to="/login" className="public-login">
            Anmelden
          </NavLink>
        </nav>
      </header>
      <main className="public-content">
        <Outlet />
      </main>
      <footer className="public-footer">
        <span className="muted">JDAV Ludwigsburg · Kompass</span>
      </footer>
    </div>
  );
}
