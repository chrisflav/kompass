import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema, type Options as SanitizeSchema } from "rehype-sanitize";

import { mediaUrl } from "../../../api/client";
import { useDocumentTitle } from "../../../components/ui";
import type { components } from "../../../api/schema";

type PostBrief = components["schemas"]["PublicPostBrief"];
type MemberBrief = components["schemas"]["PublicMemberBrief"];

/**
 * What raw HTML inside a ``website_text`` is allowed to be.
 *
 * Starts from hast-util-sanitize's GitHub schema — which already drops
 * ``<script>`` with its body, every event handler such as ``onerror``, and every
 * url on a protocol other than http/https/mailto — and adjusts it to the content
 * the old Django site's bleach whitelist has been letting through for years.
 */
const sanitizeSchema = {
  ...defaultSchema,
  // A `<style>` block is not rendered by the default schema but its CSS is kept
  // as text, so it would show up as a mouthful of declarations mid-article.
  strip: [...(defaultSchema.strip ?? []), "style"],
  tagNames: [
    // `<picture>`/`<source>` were never allowed by bleach, so no post can depend
    // on them — and the schema checks no protocol on `srcSet`, which would let a
    // post fetch from anywhere and so hand out its readers' addresses.
    ...(defaultSchema.tagNames ?? []).filter((tag) => tag !== "picture" && tag !== "source"),
    // Both are on bleach's list, and `<acronym>` — obsolete since HTML5 — is
    // exactly what an author of the vintage this is rescuing reached for.
    "abbr",
    "acronym",
  ],
  attributes: {
    // The GitHub schema pins `class` to a pattern on a handful of tags
    // (`language-*` on `<code>`, `sr-only` on `<h2>`, the task-list classes on
    // `<li>`/`<ul>`/`<ol>`, and so on). A tag's own definition wins over the `*`
    // one and, for a list-valued property such as `className`, never falls back
    // to it — so those patterns would quietly empty an author's class and leave
    // a bare `class=""` behind, on `<a class="button">` above all. Drop every
    // per-tag `class` rule and let the one below answer for all of them.
    ...Object.fromEntries(
      Object.entries(defaultSchema.attributes ?? {}).map(([tag, definitions]) => [
        tag,
        definitions.filter((it) => (typeof it === "string" ? it : it[0]) !== "className"),
      ]),
    ),
    // The two attributes bleach allowed and existing posts lay themselves out
    // with. Neither can execute anything.
    "*": [...(defaultSchema.attributes?.["*"] ?? []), "className", "style"],
  },
} satisfies SanitizeSchema;

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
    // Every remaining tag: a name is required, so a bare `5 < 10` stays prose,
    // and quoted attribute values are consumed whole, so an `alt="a > b"` does
    // not spill the rest of its tag into the teaser. It cannot backtrack
    // catastrophically, though it is quadratic on input built to hurt it (a
    // 96 kB run of `<a"` takes seconds; 960 kB of ordinary markup, 14 ms).
    // Mismatched quoting fails open: `<img alt="offen>` is left standing in the
    // teaser rather than swallowing the sentence behind it.
    .replace(/<\/?[a-zA-Z][^>"']*(?:(?:"[^"]*"|'[^']*')[^>"']*)*>/g, " ")
    .replace(/!\[[^\]]*\]\([^)]*\)/g, "") // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1") // links → label
    .replace(/[#>*_`~]/g, "") // heading/emphasis/code/quote markers
    .replace(/&(?:nbsp|amp|lt|gt|quot|#39);/g, (entity) => ENTITIES[entity])
    .replace(/\s+/g, " ")
    .trim();
  if (plain.length <= max) return plain;
  const cut = plain.slice(0, max);
  const lastSpace = cut.lastIndexOf(" ");
  return `${cut.slice(0, lastSpace > 0 ? lastSpace : max)}…`;
}

/** The first letters of a name: its first word and, where there is one, its
 *  last. Words are trimmed first, so a field holding nothing but spaces counts
 *  as absent rather than contributing a blank letter — and a field the payload
 *  left out entirely counts as absent too, whatever the schema promises. */
function lettersOf(words: (string | null | undefined)[]): string {
  const real = words.map((word) => (word ?? "").trim()).filter(Boolean);
  const first = real[0] ?? "";
  const last = real.length > 1 ? real[real.length - 1] : "";
  return `${first.slice(0, 1)}${last.slice(0, 1)}`.toUpperCase();
}

/** The one or two letters that stand in for a portrait nobody uploaded.
 *
 *  Prefers the member's own name fields, but falls back to splitting the
 *  rendered ``name`` whenever they yield less — a payload carrying only
 *  ``name`` is one case, a member with no ``lastname`` on file another. */
export function initials(person: MemberBrief): string {
  const named = lettersOf([person.prename, person.lastname]);
  if (named.length === 2) return named;
  return lettersOf((person.name ?? "").split(/\s+/)) || named || "?";
}

/**
 * A person as the public site shows them: their photo, or — where none was
 * uploaded — their initials in exactly the same square, so a grid of leaders
 * keeps its rhythm whether or not everybody sent a picture.
 *
 * The initials are the signed-in user's avatar treatment at portrait size, and
 * they are decorative: the name underneath is what a screen reader reads, and
 * it is there either way.
 */
export function PersonPortrait({ person }: { person: MemberBrief }) {
  return (
    <div className="shortcut-card portrait-card">
      <span className="portrait">
        {person.image ? (
          <img src={mediaUrl(person.image)} alt={person.name} loading="lazy" />
        ) : (
          <span className="portrait-initials" aria-hidden="true">
            {initials(person)}
          </span>
        )}
      </span>
      <span className="shortcut-title">{person.name}</span>
    </div>
  );
}

/** The public site's people listings: group leaders, the people on a post. */
export function PortraitGrid({ people }: { people: MemberBrief[] }) {
  return (
    <div className="card-grid">
      {people.map((person) => (
        <PersonPortrait key={person.id} person={person} />
      ))}
    </div>
  );
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
