import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import { useDocumentTitle } from "../../../components/ui";
import type { components } from "../../../api/schema";

type PostBrief = components["schemas"]["PublicPostBrief"];

/**
 * Render a model's ``website_text`` (authored as Markdown in the backend) as
 * rich text: GitHub-flavoured Markdown plus LaTeX math via KaTeX (``$…$`` inline
 * and ``$$…$$`` display). KaTeX's stylesheet is loaded once globally in main.tsx.
 */
export function Prose({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

/** Shared heading + optional lead paragraph for a public page.
 *
 * Also sets the browser tab title, exactly as the admin's `PageHeader` does —
 * without this every public page was just "Kompass", which is the half that
 * actually gets bookmarked and shared.
 */
export function PublicPageHeader({ title, lead }: { title: string; lead?: ReactNode }) {
  useDocumentTitle(title);
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

/** Strip Markdown to a plain-text teaser (so a truncated preview never renders
 *  broken syntax), trimmed to a whole word near ``max``. */
export function excerpt(text: string | null | undefined, max = 320): string {
  if (!text) return "";
  const plain = text
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → label
    .replace(/[#>*_`~]/g, "") // heading/emphasis/code/quote markers
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 0 ? lastSpace : max)}…`;
}

/** A clickable post preview card (news / reports listings) linking to the post
 *  detail via its section + post urlname. */
export function PostTeaser({ post }: { post: PostBrief }) {
  return (
    <Link
      to={`/beitrag/${encodeURIComponent(post.section_urlname)}/${encodeURIComponent(post.urlname)}`}
      className="post-teaser"
    >
      <span className="post-teaser-title">{post.title}</span>
      {post.date && <time className="post-teaser-date">{formatDate(post.date)}</time>}
      <p className="post-teaser-excerpt">{excerpt(post.website_text)}</p>
      <span className="post-teaser-more">Weiterlesen →</span>
    </Link>
  );
}
