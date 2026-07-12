import type { ReactNode } from "react";

/**
 * Render a model's ``website_text`` (stored as Markdown in the backend). No
 * Markdown dependency may be added here, so the raw text is shown with its
 * paragraph/line breaks preserved via ``white-space: pre-wrap``.
 */
export function Prose({ text }: { text?: string | null }) {
  if (!text) return null;
  return <div style={{ whiteSpace: "pre-wrap", lineHeight: 1.6 }}>{text}</div>;
}

/** Shared heading + optional lead paragraph for a public page. */
export function PublicPageHeader({ title, lead }: { title: string; lead?: ReactNode }) {
  return (
    <header style={{ marginBottom: "1.5rem" }}>
      <h1 style={{ margin: 0 }}>{title}</h1>
      {lead && <p className="muted">{lead}</p>}
    </header>
  );
}

/** Format an ISO date (``YYYY-MM-DD``) as a German date, tolerating null. */
export function formatDate(iso?: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString("de-DE", { day: "2-digit", month: "long", year: "numeric" });
}
