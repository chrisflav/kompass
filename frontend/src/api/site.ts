import { useApiQuery } from "./hooks";
import { client, unwrap } from "./http";
import type { components } from "./schema";

/** The section running this deployment, from `GET /api/startpage/public/site`. */
export type Site = components["schemas"]["PublicSiteOut"];

/**
 * What the chrome shows until the endpoint has answered.
 *
 * The name is the one thing every surface carries, and it sits in the top bar
 * on the very first paint. A blank wordmark would flash on every cold load, and
 * guessing a section would show the wrong one, so the fallback is the part that
 * is true of every deployment: the organisation without its section.
 */
const FALLBACK: Site = {
  name: "",
  display_name: "JDAV",
  dav_section: "",
  street: "",
  town: "",
  telephone: "",
  telefax: "",
  contact_mail: "",
  board_mail: "",
  responsible_mail: "",
  latitude: null,
  longitude: null,
};

/**
 * The section this Kompass belongs to — its name, its postal details and,
 * optionally, its position.
 *
 * Deployment configuration, not content: it cannot change while the tab is
 * open, so it is fetched once and never refetched. Public (no token needed), so
 * the login screen and the public site can read it too.
 *
 * Returns the data directly rather than a query: every caller only ever wants
 * the current value, and {@link FALLBACK} stands in while the request is in
 * flight or if it fails — a header that renders is better than one that throws.
 */
export function useSite(): Site {
  const query = useApiQuery(
    ["public", "site"],
    () => unwrap(client.GET("/api/startpage/public/site")),
    { staleTime: Infinity, gcTime: Infinity, retry: false },
  );
  return query.data ?? FALLBACK;
}

/**
 * A position as a map bearing: `48.8974° N · 9.1916° O`.
 *
 * Empty unless both halves are configured — the readout is a flourish, and half
 * a coordinate is worse than none.
 */
export function formatCoordinates(site: Site): string {
  const { latitude, longitude } = site;
  if (latitude === null || latitude === undefined) return "";
  if (longitude === null || longitude === undefined) return "";
  const lat = `${Math.abs(latitude).toFixed(4)}° ${latitude < 0 ? "S" : "N"}`;
  const lon = `${Math.abs(longitude).toFixed(4)}° ${longitude < 0 ? "W" : "O"}`;
  return `${lat} · ${lon}`;
}
