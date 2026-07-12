import { getToken } from "../auth";
import { API_BASE, client } from "./client";

/** Error carrying the HTTP status and any parsed `{detail}` body. */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(ApiError.messageFor(status, detail));
    this.status = status;
    this.detail = detail;
  }

  /** Per-field validation errors ({field: [messages]}) from a 422, if present. */
  get fieldErrors(): Record<string, string[]> {
    if (this.detail && typeof this.detail === "object" && "errors" in this.detail) {
      const errs = (this.detail as { errors: unknown }).errors;
      if (errs && typeof errs === "object") return errs as Record<string, string[]>;
    }
    return {};
  }

  static messageFor(status: number, detail: unknown): string {
    if (detail && typeof detail === "object" && "detail" in detail) {
      const d = (detail as { detail: unknown }).detail;
      if (typeof d === "string") return d;
      if (Array.isArray(d)) return d.join(" ");
    }
    if (status === 401) return "Nicht angemeldet.";
    if (status === 403) return "Keine Berechtigung.";
    if (status === 404) return "Nicht gefunden.";
    return `Fehler ${status}.`;
  }
}

/**
 * Resolve an openapi-fetch result, throwing {@link ApiError} on failure so
 * TanStack Query treats it as an error. Preserves the fully-typed `data`.
 */
export async function unwrap<T>(
  p: Promise<{ data?: T; error?: unknown; response: Response }>,
): Promise<T> {
  const { data, error, response } = await p;
  if (!response.ok || error !== undefined) {
    throw new ApiError(response.status, error);
  }
  return data as T;
}

/** The typed openapi-fetch client, re-exported for query/mutation functions. */
export { client };

/**
 * Fetch a binary artifact (PDF/xlsx/docx) from a document endpoint and trigger a
 * browser download. Document routes return raw files, not JSON, so they bypass
 * openapi-fetch. The bearer token is attached exactly like {@link client}.
 */
export async function downloadArtifact(
  path: string,
  opts: { method?: "GET" | "POST"; body?: unknown; filename?: string } = {},
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(opts.body !== undefined ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
  });
  if (!res.ok) {
    let detail: unknown = undefined;
    try {
      detail = await res.json();
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
  }
  const blob = await res.blob();
  const filename = opts.filename ?? filenameFromResponse(res) ?? "download";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function filenameFromResponse(res: Response): string | null {
  const cd = res.headers.get("Content-Disposition");
  if (!cd) return null;
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  return match ? decodeURIComponent(match[1]) : null;
}
