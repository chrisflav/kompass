import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema, type Options as SanitizeSchema } from "rehype-sanitize";
// KaTeX math styling (fonts bundled by Vite, no CDN). Imported here rather than
// globally, so it travels in this chunk with the renderer that needs it.
import "katex/dist/katex.min.css";

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
 * and ``$$…$$`` display). KaTeX's stylesheet is imported above.
 *
 * markdownx lets authors write raw HTML and years of posts do — the old Django
 * site fed them to ``markdownify``, so they have to keep coming out as markup
 * instead of as visible tags. The plugin order is what makes that safe:
 * ``rehype-raw`` parses the author's HTML into real nodes, ``rehype-sanitize``
 * then throws the dangerous ones away, and only afterwards does ``rehype-katex``
 * add markup of its own — so KaTeX's classes and MathML are never up for
 * sanitation, which is what a schema running last would strip.
 *
 * Loaded lazily through ``Prose`` in ./shared: this stack (KaTeX and the HTML
 * parser above all) is close to half the bundle, and only a page showing
 * authored text needs it.
 */
export default function Markdown({ text }: { text: string }) {
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
