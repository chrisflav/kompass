import { Outlet, Navigate, useLocation } from "react-router-dom";
import type { ReactNode } from "react";

import { useSite } from "../api/site";
import { useAuth } from "../auth";
import { SiteHeader } from "./SiteHeader";

/** Route guard: redirects to /login when there is no token, carrying the page
 *  that was asked for so the login flow can return to it. */
export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { token } = useAuth();
  const location = useLocation();
  if (!token) {
    const from = `${location.pathname}${location.search}`;
    return <Navigate to="/login" state={{ from }} replace />;
  }
  return <>{children}</>;
}

/**
 * Authenticated Kompass workspace. Shares the exact chrome + geometry of the
 * public site (one top bar, one centered content column) so moving between the
 * two is seamless; the section navigation lives in the top bar.
 */
export function AppLayout() {
  return (
    <div className="site">
      <SiteHeader variant="app" />
      <main className="site-main">
        <Outlet />
      </main>
    </div>
  );
}

/** Public-facing website — same shell as the Kompass workspace. */
export function PublicLayout() {
  const site = useSite();
  return (
    <div className="site">
      <SiteHeader variant="public" />
      <main className="site-main">
        <Outlet />
      </main>
      <footer className="public-footer">
        <span className="muted">{site.display_name} · Kompass</span>
      </footer>
    </div>
  );
}
