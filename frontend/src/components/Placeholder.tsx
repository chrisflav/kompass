import { Link } from "react-router-dom";

import { PageHeader } from "./ui";

/**
 * Stand-in for a surface that has not been built yet. Phase C replaces the
 * feature module that renders this with the real list/detail/action pages.
 */
export function Placeholder({ title }: { title: string }) {
  return (
    <div>
      <PageHeader title={title} subtitle="Diese Ansicht wird noch aufgebaut." />
      <p className="muted state">Noch nicht implementiert.</p>
    </div>
  );
}

export function NotFound() {
  return (
    <div className="login">
      <div className="card">
        <h1>404</h1>
        <p className="muted">Diese Seite existiert nicht.</p>
        <Link to="/">Zur Startseite</Link>
      </div>
    </div>
  );
}
