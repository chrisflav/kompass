// jsdom never matches `:hover`, so a test that asks "what colour is this button
// under the pointer?" resolves the app's own stylesheet by hand: every rule that
// matches the element (with `:hover` taken as matching) is ranked by
// specificity, then by source order, and the winner's value is returned — the
// browser's cascade, for the plain class/pseudo-class selectors buttons use.
import { readFileSync } from "node:fs";
import { join } from "node:path";

// Read from disk: Vitest stubs every CSS import, `?raw` included, to "".
const styles = readFileSync(join(__dirname, "../styles.css"), "utf8");

const HOVER = "data-test-hover";

type Rank = [number, number, number];

let parsed: CSSStyleRule[] | null = null;

function rules(): CSSStyleRule[] {
  if (!parsed) {
    const style = document.createElement("style");
    style.textContent = styles;
    document.head.append(style);
    parsed = Array.from((style.sheet as CSSStyleSheet).cssRules).filter(
      (rule): rule is CSSStyleRule => rule instanceof CSSStyleRule,
    );
    style.remove();
  }
  return parsed;
}

/** (ids, classes/attributes/pseudo-classes, types) of one compound selector. */
function specificity(selector: string): Rank {
  // `:not(x)` counts as its argument; pseudo-elements never match an element.
  const flat = selector.replace(/:not\(([^)]*)\)/g, " $1").replace(/::[\w-]+/g, "");
  const ids = (flat.match(/#[\w-]+/g) ?? []).length;
  const classes = (flat.match(/\.[\w-]+|\[[^\]]+\]|:[\w-]+/g) ?? []).length;
  const types = (flat.match(/(^|[\s>+~])[a-zA-Z][\w-]*/g) ?? []).length;
  return [ids, classes, types];
}

function outranks(a: Rank, b: Rank) {
  for (let i = 0; i < 3; i++) if (a[i] !== b[i]) return a[i] > b[i];
  return true; // equal specificity: the later rule wins
}

/** The value `property` cascades to on `element` while the pointer rests on it. */
export function hoveredValue(element: Element, property: string): string | null {
  element.setAttribute(HOVER, "");
  try {
    let best: { rank: Rank; value: string } | null = null;
    for (const rule of rules()) {
      const value = rule.style.getPropertyValue(property);
      if (!value) continue;
      for (const selector of rule.selectorText.split(",").map((s) => s.trim())) {
        let matches = false;
        try {
          matches = element.matches(selector.replace(/:hover/g, `[${HOVER}]`));
        } catch {
          continue; // a pseudo-class jsdom cannot evaluate
        }
        if (!matches) continue;
        const rank = specificity(selector);
        if (!best || outranks(rank, best.rank)) best = { rank, value };
      }
    }
    return best?.value ?? null;
  } finally {
    element.removeAttribute(HOVER);
  }
}
