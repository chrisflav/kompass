import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

import { useApiQuery } from "../api/hooks";
import { client, unwrap } from "../api/http";
import { useMe } from "../api/me";
import { useAuth } from "../auth";
import { KompassMark } from "./Contour";

/* --- navigation model ----------------------------------------------------- */

interface NavLeaf {
  to: string;
  label: string;
}
interface NavArea {
  label: string;
  /** Landing route for the area (the group header is itself a link). */
  to?: string;
  items: NavLeaf[];
}
/** A top-bar entry is either a dropdown area or a plain link. */
type NavEntry = NavArea | NavLeaf;

function isArea(entry: NavEntry): entry is NavArea {
  return "items" in entry;
}

/**
 * Public site navigation, built from the live startpage navigation (mirrors the
 * old Django dropdown navbar's organisation): an "Aktuelles/Berichte" area, one
 * top-level entry per custom Section that opts into the nav, a Gruppen dropdown
 * listing the public groups, and Impressum.
 */
function usePublicNav(enabled: boolean): NavEntry[] {
  const query = useApiQuery(
    ["public", "navigation"],
    () => unwrap(client.GET("/api/startpage/public/navigation")),
    { staleTime: 5 * 60_000, enabled },
  );
  const data = query.data;
  const rootId = data?.root_section?.id;
  const sections = (data?.sections ?? []).filter(
    (s) => s.show_in_navigation && s.id !== rootId,
  );
  const groups = data?.groups ?? [];

  return [
    {
      label: data?.root_section?.title || "Verein",
      items: [
        { to: "/aktuelles", label: "Aktuelles" },
        { to: "/berichte", label: "Berichte" },
      ],
    },
    ...sections.map((s) => ({
      to: `/bereich/${encodeURIComponent(s.urlname)}`,
      label: s.title,
    })),
    {
      label: "Gruppen",
      to: "/gruppen",
      items: [
        { to: "/gruppen", label: "Alle Gruppen" },
        ...groups.map((g) => ({ to: `/gruppe/${encodeURIComponent(g.name)}`, label: g.name })),
        { to: "/gruppen/faq", label: "FAQ" },
      ],
    },
    { to: "/impressum", label: "Impressum" },
  ];
}

/**
 * Kompass (admin) navigation, reorganised per NAVIGATION.md: intake ("Aufnahme")
 * is split from the maintenance of existing members. Every area is a top-level
 * entry on the nav rail — the rail has the full container width, so the list
 * does not need a catch-all "Mehr" to stay inside the bar.
 */
const ADMIN_NAV: NavArea[] = [
  { label: "Teilnehmende", items: [
    { to: "/app/members", label: "Alle Teilnehmende" },
    { to: "/app/trainings", label: "Ausbildungen" },
    { to: "/app/registrations", label: "Registrierungen" },
    { to: "/app/waiters", label: "Warteliste" },
  ] },
  { label: "Aktivitäten", items: [
    { to: "/app/groups", label: "Gruppen" },
    { to: "/app/excursions", label: "Ausfahrten" },
    { to: "/app/klettertreff", label: "Klettertreffs" },
    { to: "/app/notelists", label: "Notizlisten" },
    { to: "/app/activity-categories", label: "Aktivitätskategorien" },
    { to: "/app/training-categories", label: "Ausbildungskategorien" },
  ] },
  { label: "Finanzen", items: [
    { to: "/app/finance/statements", label: "Abrechnungen" },
    { to: "/app/finance/bills", label: "Belege" },
    { to: "/app/finance/transactions", label: "Buchungen" },
    { to: "/app/finance/ledgers", label: "Konten" },
  ] },
  { label: "Kommunikation", items: [
    { to: "/app/mailer/messages", label: "Nachrichten" },
    { to: "/app/mailer/addresses", label: "E-Mail-Adressen" },
  ] },
  // The startpage content has its own area again (FRONTEND_ISSUES asked for
  // this; the NAVIGATION.md rework had folded it into a catch-all "Mehr").
  { label: "Website", items: [
    { to: "/app/cms/posts", label: "Beiträge" },
    { to: "/app/cms/sections", label: "Bereiche" },
    { to: "/app/cms/faqs", label: "FAQ" },
    { to: "/app/cms/links", label: "Links" },
  ] },
  { label: "Verwaltung", items: [
    { to: "/app/events", label: "Termine" },
    { to: "/app/material", label: "Material" },
    { to: "/app/material/categories", label: "Materialkategorien" },
    { to: "/app/users", label: "Benutzer" },
    { to: "/app/permission-groups", label: "Rechtegruppen" },
    { to: "/app/registration-passwords", label: "Registrierungspasswörter" },
  ] },
];

/* --- small popover primitive --------------------------------------------- */

function useOutsideClose(onClose: () => void) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    }
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);
  return ref;
}

/** A top-bar area button that opens a dropdown of its sub-items. */
function NavArea({ area, activePath }: { area: NavArea; activePath: string }) {
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(() => setOpen(false));
  const active = area.items.some((i) => activePath === i.to || activePath.startsWith(i.to + "/"));
  return (
    <div className="nav-area" ref={ref}>
      <button
        type="button"
        className={active ? "nav-area-btn active" : "nav-area-btn"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {area.label}
        <span className="nav-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="nav-dropdown" onClick={() => setOpen(false)}>
          {area.items.map((i) => (
            <NavLink
              key={i.to}
              to={i.to}
              className={({ isActive }) => (isActive ? "nav-drop-item active" : "nav-drop-item")}
            >
              {i.label}
            </NavLink>
          ))}
        </div>
      )}
    </div>
  );
}

/** The signed-in user's menu: name → profile, plus logout. */
function UserMenu({ memberId, name }: { memberId: number | null; name: string }) {
  const { logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useOutsideClose(() => setOpen(false));
  return (
    <div className="user-menu" ref={ref}>
      <button
        type="button"
        className="user-menu-btn"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="user-avatar" aria-hidden="true">
          {name.slice(0, 1).toUpperCase()}
        </span>
        <span className="user-name">{name}</span>
        <span className="nav-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="nav-dropdown right" onClick={() => setOpen(false)}>
          {memberId !== null ? (
            <Link to={`/app/members/${memberId}`} className="nav-drop-item">
              Mein Profil
            </Link>
          ) : (
            <span className="nav-drop-item muted">Kein Teilnehmenden-Profil</span>
          )}
          <button type="button" className="nav-drop-item as-button" onClick={logout}>
            Abmelden
          </button>
        </div>
      )}
    </div>
  );
}

/* --- header --------------------------------------------------------------- */

export function SiteHeader({ variant }: { variant: "public" | "app" }) {
  const { token } = useAuth();
  const me = useMe();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const publicNav = usePublicNav(variant === "public");

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setDrawer(false), [pathname]);

  const name = me.data?.name ?? "Konto";
  const memberId = me.data?.member_id ?? null;

  return (
    <header className="topbar">
      <div className="topbar-inner">
        {/* Stay within the current mode: the brand lands on the Kompass
            dashboard in the app, on the public home on the website. */}
        <Link to={variant === "app" ? "/app" : "/"} className="brand topbar-brand">
          <KompassMark size={24} />
          <span>JDAV Ludwigsburg</span>
        </Link>

        <div className="topbar-right">
          {token ? (
            <>
              {/* The public ↔ Kompass seam, present in both worlds. */}
              <div className="context-switch" role="group" aria-label="Bereich wechseln">
                <NavLink to="/" end className={variant === "public" ? "ctx active" : "ctx"}>
                  Website
                </NavLink>
                <NavLink to="/app" className={variant === "app" ? "ctx active" : "ctx"}>
                  Kompass
                </NavLink>
              </div>
              <UserMenu memberId={memberId} name={name} />
            </>
          ) : (
            <NavLink to="/login" className="btn topbar-login">
              Anmelden
            </NavLink>
          )}

          <button
            type="button"
            className="hamburger"
            aria-label="Menü"
            aria-expanded={drawer}
            onClick={() => setDrawer((d) => !d)}
          >
            ☰
          </button>
        </div>
      </div>

      {/* Primary navigation, on its own full-width rail below the brand row.
          It shares the row with nothing, so the areas have the whole container
          to themselves and the bar cannot collide with the account cluster. */}
      <div className="navrail">
        <nav className="topnav" aria-label="Hauptnavigation">
          {(variant === "public" ? publicNav : ADMIN_NAV).map((entry) =>
            isArea(entry) ? (
              <NavArea key={entry.label} area={entry} activePath={pathname} />
            ) : (
              <NavLink
                key={entry.to}
                to={entry.to}
                className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
              >
                {entry.label}
              </NavLink>
            ),
          )}
        </nav>
      </div>

      {/* Mobile drawer: the same navigation, fully expanded. */}
      {drawer && (
        <div className="topnav-drawer">
          {token && (
            <div className="drawer-switch">
              <NavLink to="/" end className={variant === "public" ? "ctx active" : "ctx"}>
                Website
              </NavLink>
              <NavLink to="/app" className={variant === "app" ? "ctx active" : "ctx"}>
                Kompass
              </NavLink>
            </div>
          )}
          {(variant === "public" ? publicNav : ADMIN_NAV).map((entry) =>
            isArea(entry) ? (
              <div className="drawer-group" key={entry.label}>
                <span className="drawer-label">{entry.label}</span>
                {entry.items.map((i) => (
                  <NavLink key={i.to} to={i.to} className="drawer-item">
                    {i.label}
                  </NavLink>
                ))}
              </div>
            ) : (
              <div className="drawer-group" key={entry.to}>
                <NavLink to={entry.to} className="drawer-item">
                  {entry.label}
                </NavLink>
              </div>
            ),
          )}
          {token ? (
            <div className="drawer-group">
              {memberId !== null && (
                <NavLink to={`/app/members/${memberId}`} className="drawer-item">
                  Mein Profil
                </NavLink>
              )}
              <LogoutDrawerItem />
            </div>
          ) : (
            <div className="drawer-group">
              <NavLink to="/login" className="drawer-item">
                Anmelden
              </NavLink>
            </div>
          )}
        </div>
      )}
    </header>
  );
}

function LogoutDrawerItem() {
  const { logout } = useAuth();
  return (
    <button type="button" className="drawer-item as-button" onClick={logout}>
      Abmelden
    </button>
  );
}
