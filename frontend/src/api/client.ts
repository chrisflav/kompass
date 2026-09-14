import createClient from "openapi-fetch";

import { getToken } from "../auth";
import type { paths } from "./schema";

// Backend origin. Override with VITE_API_BASE when the API is elsewhere.
export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

/** Resolve a media path (``/media/...``) against the API host.
 *
 * Uploaded files are served by the backend, which is a different origin from
 * the SPA in development. */
export function mediaUrl(path: string): string {
  return /^https?:\/\//.test(path) ? path : `${API_BASE}${path}`;
}

export const client = createClient<paths>({
  baseUrl: API_BASE,
  // Resolve `fetch` per request instead of letting openapi-fetch snapshot
  // `globalThis.fetch` when this module is first imported. Anything that swaps
  // the global afterwards — a test's request mock, a polyfill — is then
  // actually used, rather than silently bypassed.
  fetch: (request) => globalThis.fetch(request),
});

// Attach the bearer token (if any) to every request.
client.use({
  onRequest({ request }) {
    const token = getToken();
    if (token) {
      request.headers.set("Authorization", `Bearer ${token}`);
    }
    return request;
  },
});
