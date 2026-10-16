import { lazy, Suspense, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { mediaUrl } from "../../../api/client";
import { ChunkBoundary } from "../../../components/ChunkBoundary";
import { useDocumentTitle } from "../../../components/ui";
import type { components } from "../../../api/schema";

type PostBrief = components["schemas"]["PublicPostBrief"];
type MemberBrief = components["schemas"]["PublicMemberBrief"];

const Markdown = lazy(() => import("./Markdown"));

/**
 * Render a model's ``website_text`` (authored as Markdown in the backend) as
 * rich text — see ./Markdown for what that covers and how raw HTML in it is
 * kept safe. The renderer is fetched on first use, so pages without authored
 * text never download it. No loading state while it does: a page such as the
 * FAQ holds many of these, and a status message apiece would only flicker.
 */
export function Prose({ text }: { text?: string | null }) {
  if (!text) return null;
  return (
    <ChunkBoundary>
      <Suspense fallback={null}>
        <Markdown text={text} />
      </Suspense>
    </ChunkBoundary>
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
 *  left out entirely counts as absent too. ``PublicMemberBrief`` declares
 *  ``prename``/``lastname`` required and the resolver backing it always sends
 *  them (see the schema-contract tests in `tests_public.py`, taxis #506) — but
 *  this component is deliberately tolerant of a payload that names someone in
 *  one piece (``name`` only), which the tests two call sites down exercise on
 *  purpose, so the coercion stays. */
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
