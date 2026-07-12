import { useEffect, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";

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

/** Public site navigation (shown to everyone). */
const PUBLIC_NAV: NavLeaf[] = [
  { to: "/aktuelles", label: "Aktuelles" },
  { to: "/berichte", label: "Berichte" },
  { to: "/gruppen", label: "Gruppen" },
  { to: "/gruppen/faq", label: "FAQ" },
  { to: "/impressum", label: "Impressum" },
];

/**
 * Kompass (admin) navigation, reorganised per NAVIGATION.md: intake ("Aufnahme")
 * is split from the maintenance of existing members, and the long tail collapses
 * into "Mehr" so the primary bar stays scannable.
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
  { label: "Mehr", items: [
    { to: "/app/events", label: "Termine" },
    { to: "/app/material", label: "Material" },
    { to: "/app/material/categories", label: "Materialkategorien" },
    { to: "/app/cms/posts", label: "Beiträge" },
    { to: "/app/cms/sections", label: "Bereiche" },
    { to: "/app/cms/faqs", label: "FAQ" },
    { to: "/app/cms/links", label: "Links" },
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

        {/* Primary navigation (desktop). */}
        <nav className="topnav" aria-label="Hauptnavigation">
          {variant === "public"
            ? PUBLIC_NAV.map((i) => (
                <NavLink
                  key={i.to}
                  to={i.to}
                  end={i.to === "/gruppen"}
                  className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
                >
                  {i.label}
                </NavLink>
              ))
            : ADMIN_NAV.map((area) => (
                <NavArea key={area.label} area={area} activePath={pathname} />
              ))}
        </nav>

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
          {variant === "public" ? (
            <div className="drawer-group">
              {PUBLIC_NAV.map((i) => (
                <NavLink key={i.to} to={i.to} end={i.to === "/gruppen"} className="drawer-item">
                  {i.label}
                </NavLink>
              ))}
            </div>
          ) : (
            <>
              {ADMIN_NAV.map((area) => (
                <div className="drawer-group" key={area.label}>
                  <span className="drawer-label">{area.label}</span>
                  {area.items.map((i) => (
                    <NavLink key={i.to} to={i.to} className="drawer-item">
                      {i.label}
                    </NavLink>
                  ))}
                </div>
              ))}
            </>
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
