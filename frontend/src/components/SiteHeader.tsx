import { useEffect, useId, useRef, useState } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useApiQuery } from "../api/hooks";
import { client, unwrap } from "../api/http";
import { useMe, usePermissions } from "../api/me";
import { useSite } from "../api/site";
import { useAuth } from "../auth";
import { useThemeChoice, type ThemeChoice } from "../theme";
import { KompassMark } from "./Contour";
import { FeedbackButton } from "./FeedbackButton";

/* --- navigation model ----------------------------------------------------- */

interface NavLeaf {
  to: string;
  label: string;
  /** Shown only to those holding one of these permissions ("app.codename"). */
  perms?: string[];
  /** Further path prefixes that belong to this entry, such as the tabs of a page. */
  match?: string[];
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
        // Joining is the point of the group pages, so the sign-up sits with
        // them; the route existed but nothing linked to it.
        { to: "/warteliste", label: "Auf die Warteliste" },
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
    { to: "/kompass/members", label: "Alle Teilnehmende" },
    { to: "/kompass/trainings", label: "Ausbildungen" },
    { to: "/kompass/registrations", label: "Registrierungen" },
    { to: "/kompass/waiters", label: "Warteliste" },
  ] },
  { label: "Aktivitäten", items: [
    { to: "/kompass/groups", label: "Gruppen" },
    { to: "/kompass/excursions", label: "Ausfahrten" },
    { to: "/kompass/klettertreff", label: "Klettertreffs" },
    { to: "/kompass/notelists", label: "Notizlisten" },
    { to: "/kompass/categories", label: "Kategorien" },
  ] },
  { label: "Finanzen", items: [
    { to: "/kompass/finance/statements", label: "Abrechnungen" },
    { to: "/kompass/finance/bills", label: "Belege" },
    { to: "/kompass/finance/transactions", label: "Buchungen" },
    { to: "/kompass/finance/ledgers", label: "Konten" },
  ] },
  { label: "Kommunikation", items: [
    { to: "/kompass/mailer/messages", label: "Nachrichten" },
    { to: "/kompass/mailer/addresses", label: "E-Mail-Adressen" },
  ] },
  // The startpage content has its own area again (FRONTEND_ISSUES asked for
  // this; the NAVIGATION.md rework had folded it into a catch-all "Mehr").
  { label: "Website", items: [
    { to: "/kompass/cms/posts", label: "Beiträge" },
    { to: "/kompass/cms/sections", label: "Bereiche" },
    { to: "/kompass/cms/faqs", label: "FAQ" },
    { to: "/kompass/cms/links", label: "Links" },
  ] },
  { label: "Material", items: [
    { to: "/kompass/material", label: "Materialbrowser" },
    { to: "/kompass/material/mine", label: "Mein Material" },
    { to: "/kompass/material/desk", label: "Ausgabe", perms: ["equipment.manage_lending"] },
    // PSA, wishlist, locations and tags are tabs of the Bestand.
    {
      to: "/kompass/material/stock",
      label: "Bestand",
      perms: ["equipment.manage_inventory", "equipment.manage_lending"],
      match: [
        "/kompass/material/psa",
        "/kompass/material/deficits",
        "/kompass/material/locations",
        "/kompass/material/categories",
      ],
    },
  ] },
  { label: "Verwaltung", items: [
    { to: "/kompass/events", label: "Termine" },
    { to: "/kompass/users", label: "Benutzer*innen" },
    { to: "/kompass/permission-groups", label: "Rechtegruppen" },
    { to: "/kompass/registration-passwords", label: "Registrierungspasswörter" },
    { to: "/kompass/feedback", label: "Feedback" },
  ] },
];

/** {@link ADMIN_NAV} without the entries the user lacks the permission for. */
function useAdminNav(): NavArea[] {
  const { canAny } = usePermissions();
  return ADMIN_NAV.map((area) => ({
    ...area,
    items: area.items.filter((i) => !i.perms || canAny(...i.perms)),
  }));
}

/**
 * The item of an area the path belongs to: the longest matching link (or extra
 * prefix of an item's ``match``), so a parent route ("/kompass/material") does
 * not light up beside its children.
 */
function activeItem(items: NavLeaf[], path: string): string | undefined {
  let best: { to: string; length: number } | undefined;
  for (const item of items) {
    for (const prefix of [item.to, ...(item.match ?? [])]) {
      const matches = path === prefix || path.startsWith(prefix + "/");
      if (matches && (!best || prefix.length > best.length)) best = { to: item.to, length: prefix.length };
    }
  }
  return best?.to;
}

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
  const current = activeItem(area.items, activePath);
  return (
    <div className="nav-area" ref={ref}>
      <button
        type="button"
        className={current ? "nav-area-btn active" : "nav-area-btn"}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {area.label}
        <span className="nav-caret" aria-hidden="true">▾</span>
      </button>
      {open && (
        <div className="nav-dropdown" onClick={() => setOpen(false)}>
          {area.items.map((i) => (
            <Link key={i.to} to={i.to} className={i.to === current ? "nav-drop-item active" : "nav-drop-item"}>
              {i.label}
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

/** Personal access tokens are offered to those who may create one. */
const TOKENS_PERMISSION = "logindata.create_personalaccesstoken";

/** The signed-in user's menu: name → profile, access tokens, plus logout. */
function UserMenu({ memberId, name }: { memberId: number | null; name: string }) {
  const { logout } = useAuth();
  const { can } = usePermissions();
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
            <Link to={`/kompass/members/${memberId}`} className="nav-drop-item">
              Mein Profil
            </Link>
          ) : (
            <span className="nav-drop-item muted">Kein Teilnehmenden-Profil</span>
          )}
          {can(TOKENS_PERMISSION) && (
            <Link to="/kompass/tokens" className="nav-drop-item">
              Zugangstokens
            </Link>
          )}
          <button type="button" className="nav-drop-item as-button" onClick={logout}>
            Abmelden
          </button>
        </div>
      )}
    </div>
  );
}

const THEME_OPTIONS: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Hell" },
  { value: "dark", label: "Dunkel" },
];

/** The theme's glyph: a sun, a crescent, or for "System" a disc half in each. */
function ThemeIcon({ choice }: { choice: ThemeChoice }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {choice === "light" && (
        <>
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M2 12h2M20 12h2" />
          <path d="M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </>
      )}
      {choice === "dark" && <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />}
      {choice === "system" && (
        <>
          <circle cx="12" cy="12" r="9" />
          <path d="M12 3a9 9 0 0 1 0 18z" fill="currentColor" />
        </>
      )}
    </svg>
  );
}

/**
 * Light, dark, or whatever the system asks for. Open to everyone, signed in or
 * not, and like the feedback button it survives the mobile collapse — it is a
 * property of the screen in front of you, not of the account. On a phone too
 * narrow for one more button it moves into the drawer instead.
 */
function ThemeSwitch() {
  const [choice] = useThemeChoice();
  const [open, setOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const ref = useOutsideClose(() => setOpen(false));
  const current = THEME_OPTIONS.find((o) => o.value === choice)!;

  // Opening moves focus onto the selected option, so the arrow keys pick
  // straight away.
  useEffect(() => {
    if (open) ref.current?.querySelector<HTMLInputElement>("input:checked")?.focus();
  }, [open, ref]);

  return (
    <div
      className="theme-switch"
      ref={ref}
      // Escape from inside the panel hands focus back to the button rather than
      // dropping it on the page; a click elsewhere leaves focus where it lands.
      onKeyDown={(e) => {
        if (e.key === "Escape") buttonRef.current?.focus();
      }}
    >
      <button
        ref={buttonRef}
        type="button"
        className="theme-btn"
        aria-label={`Darstellung: ${current.label}`}
        title={`Darstellung: ${current.label}`}
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        <ThemeIcon choice={choice} />
      </button>
      {open && (
        <div className="nav-dropdown right theme-menu">
          <ThemeOptions />
        </div>
      )}
    </div>
  );
}

/** The three choices as a radio group: one per switch, so each gets its own name. */
function ThemeOptions() {
  const [choice, setChoice] = useThemeChoice();
  const name = useId();
  return (
    <fieldset className="theme-options">
      <legend>Darstellung</legend>
      {THEME_OPTIONS.map((o) => (
        <label key={o.value} className="theme-option">
          <input
            type="radio"
            name={name}
            value={o.value}
            checked={choice === o.value}
            onChange={() => setChoice(o.value)}
          />
          <ThemeIcon choice={o.value} />
          {o.label}
        </label>
      ))}
    </fieldset>
  );
}

/* --- header --------------------------------------------------------------- */

/** Set on <html> while the mobile drawer is open; locks the page's scrolling. */
const DRAWER_OPEN_CLASS = "nav-drawer-open";

export function SiteHeader({ variant }: { variant: "public" | "app" }) {
  const { token } = useAuth();
  const me = useMe();
  const site = useSite();
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const publicNav = usePublicNav(variant === "public");
  const adminNav = useAdminNav();
  const { can } = usePermissions();

  // Close the mobile drawer whenever the route changes.
  useEffect(() => setDrawer(false), [pathname]);

  // While the drawer is open the page behind it must not scroll: otherwise a
  // swipe on a phone moves the page first and the drawer only after it. The
  // class is released on close and on unmount; the stylesheet applies the lock
  // only where the drawer is actually shown. Escape closes the drawer.
  useEffect(() => {
    if (!drawer) return;
    const root = document.documentElement;
    root.classList.add(DRAWER_OPEN_CLASS);
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setDrawer(false);
    }
    document.addEventListener("keydown", onKey);
    return () => {
      root.classList.remove(DRAWER_OPEN_CLASS);
      document.removeEventListener("keydown", onKey);
    };
  }, [drawer]);

  const name = me.data?.name ?? "Konto";
  const memberId = me.data?.member_id ?? null;

  return (
    <header className="topbar">
      <div className="topbar-inner">
        {/* Stay within the current mode: the brand lands on the Kompass
            dashboard in the app, on the public home on the website. */}
        <Link to={variant === "app" ? "/kompass" : "/"} className="brand topbar-brand">
          <KompassMark size={24} />
          <span>{site.display_name}</span>
        </Link>

        <div className="topbar-right">
          {/* Outside the auth branch: feedback is for everyone, signed in or
              not, and stays reachable when the rest collapses on mobile. */}
          <FeedbackButton />
          <ThemeSwitch />
          {token ? (
            <>
              {/* The public ↔ Kompass seam, present in both worlds. */}
              <div className="context-switch" role="group" aria-label="Bereich wechseln">
                <NavLink to="/" end className={variant === "public" ? "ctx active" : "ctx"}>
                  Website
                </NavLink>
                <NavLink to="/kompass" className={variant === "app" ? "ctx active" : "ctx"}>
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
          {(variant === "public" ? publicNav : adminNav).map((entry) =>
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
              <NavLink to="/kompass" className={variant === "app" ? "ctx active" : "ctx"}>
                Kompass
              </NavLink>
            </div>
          )}
          {(variant === "public" ? publicNav : adminNav).map((entry) =>
            isArea(entry) ? (
              <div className="drawer-group" key={entry.label}>
                <span className="drawer-label">{entry.label}</span>
                {entry.items.map((i) => (
                  <Link
                    key={i.to}
                    to={i.to}
                    className={i.to === activeItem(entry.items, pathname) ? "drawer-item active" : "drawer-item"}
                  >
                    {i.label}
                  </Link>
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
          <div className="drawer-group drawer-theme">
            <ThemeOptions />
          </div>
          {token ? (
            <div className="drawer-group">
              {memberId !== null && (
                <NavLink to={`/kompass/members/${memberId}`} className="drawer-item">
                  Mein Profil
                </NavLink>
              )}
              {can(TOKENS_PERMISSION) && (
                <NavLink to="/kompass/tokens" className="drawer-item">
                  Zugangstokens
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
