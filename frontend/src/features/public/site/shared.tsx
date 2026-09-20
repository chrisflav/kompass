import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

import { useDocumentTitle } from "../../../components/ui";
import type { components } from "../../../api/schema";

type PostBrief = components["schemas"]["PublicPostBrief"];

/**
 * What raw HTML inside a ``website_text`` is allowed to be.
 *
 * Starts from hast-util-sanitize's GitHub schema — which already drops
 * ``<script>`` with its body, every event handler such as ``onerror``, and every
 * url on a protocol other than http/https/mailto — and re-adds the two
 * attributes the old Django site's bleach whitelist allowed and existing posts
 * rely on: ``class`` and ``style``. Neither can execute anything; they only let
 * an author keep the layout they wrote. The ``code`` entry names remark-math's
 * ``math-inline``/``math-display`` markers explicitly, so they keep reaching
 * KaTeX even if that blanket ``class`` allowance is ever narrowed again.
 */
const sanitizeSchema = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [["className", /^language-./, "math-display", "math-inline"]],
    "*": [...(defaultSchema.attributes?.["*"] ?? []), "className", "style"],
  },
};

/**
 * Render a model's ``website_text`` (authored as Markdown in the backend) as
 * rich text: GitHub-flavoured Markdown plus LaTeX math via KaTeX (``$…$`` inline
 * and ``$$…$$`` display). KaTeX's stylesheet is loaded once globally in main.tsx.
 *
 * markdownx lets authors write raw HTML and years of posts do — the old Django
 * site fed them to ``markdownify``, so they have to keep coming out as markup
 * instead of as visible tags. The plugin order is what makes that safe:
 * ``rehype-raw`` parses the author's HTML into real nodes, ``rehype-sanitize``
 * then throws the dangerous ones away, and only afterwards does ``rehype-katex``
 * add markup of its own — so KaTeX's classes and MathML are never up for
 * sanitation, which is what a schema running last would strip.
 */
export function Prose({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <div className="prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeRaw, [rehypeSanitize, sanitizeSchema], rehypeKatex]}
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

/** The few named entities that turn up in hand-written post HTML. */
const ENTITIES: Record<string, string> = {
  "&nbsp;": " ",
  "&amp;": "&",
  "&lt;": "<",
  "&gt;": ">",
  "&quot;": '"',
  "&#39;": "'",
};

/** Strip Markdown *and* raw HTML to a plain-text teaser (so a truncated preview
 *  never renders broken syntax or a mouthful of tags), trimmed to a whole word
 *  near ``max``. */
export function excerpt(text: string | null | undefined, max = 320): string {
  if (!text) return "";
  const plain = text
    .replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1\s*>/gi, "") // scripts, bodies and all
    .replace(/<!--[\s\S]*?-->/g, "") // comments
    .replace(/<[^>]*>/g, " ") // every remaining tag
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → label
    .replace(/[#>*_`~]/g, "") // heading/emphasis/code/quote markers
    .replace(/&(?:nbsp|amp|lt|gt|quot|#39);/gi, (e) => ENTITIES[e.toLowerCase()] ?? e)
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
