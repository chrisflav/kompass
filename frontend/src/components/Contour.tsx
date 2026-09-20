import { useMemo } from "react";

/**
 * Signature elements rooted in the product's subject: the Alpenvereinskarte (the
 * DAV's own topographic maps) and the compass the tool is named after ("Kompass").
 */

/** One closed, organically-perturbed contour ring as an SVG path string. */
function ring(cx: number, cy: number, r: number, seed: number): string {
  const steps = 72;
  let d = "";
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * Math.PI * 2;
    // Deterministic harmonic wobble (no randomness → stable, no hydration skew)
    // so the rings read as a real hillside rather than concentric circles.
    const wob =
      1 +
      0.06 * Math.sin(a * 3 + seed) +
      0.04 * Math.sin(a * 5 - seed * 1.7) +
      0.028 * Math.sin(a * 2 + seed * 0.6);
    const rr = r * wob;
    const x = cx + rr * Math.cos(a);
    const y = cy + rr * Math.sin(a) * 0.82; // vertical squash → slope, not target
    d += `${i === 0 ? "M" : "L"}${x.toFixed(1)} ${y.toFixed(1)}`;
  }
  return `${d}Z`;
}

/**
 * A field of nested topographic contour lines drawn around a summit. Purely
 * decorative (aria-hidden); colour is inherited from CSS `color` (var --contour).
 */
export function ContourField({
  className = "hero-contour",
  rings = 11,
  cx = 84,
  cy = 40,
}: {
  className?: string;
  rings?: number;
  cx?: number;
  cy?: number;
}) {
  const paths = useMemo(() => {
    const out: string[] = [];
    for (let i = 0; i < rings; i++) {
      const r = 5 + i * 6.5;
      // Centre drifts per ring so the contours describe a leaning slope.
      out.push(ring(cx + i * 1.7, cy + i * 1.15, r, i * 1.3));
    }
    return out;
  }, [rings, cx, cy]);

  return (
    <svg
      className={className}
      viewBox="0 0 120 90"
      preserveAspectRatio="xMidYMid slice"
      aria-hidden="true"
      focusable="false"
    >
      {paths.map((d, i) => (
        <path
          key={i}
          d={d}
          fill="none"
          stroke="currentColor"
          strokeWidth={1}
          vectorEffect="non-scaling-stroke"
          opacity={0.5 - i * 0.028}
        />
      ))}
    </svg>
  );
}

/**
 * The Kompass brand mark — the section's own compass-needle-in-a-ring logo
 * (shared with the Django admin favicon, served from /kompass.svg). Decorative;
 * the adjacent "Kompass"/section wordmark carries the accessible name.
 */
export function KompassMark({ size = 22 }: { size?: number }) {
  return (
    <img
      className="compass-mark"
      src="/kompass.svg"
      width={size}
      height={size}
      alt=""
      aria-hidden="true"
      draggable={false}
    />
  );
}
