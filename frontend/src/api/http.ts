import { getToken } from "../auth";
import { API_BASE, client } from "./client";

/* --- error normalisation --------------------------------------------------
 *
 * Three different error shapes reach the client and all of them used to leak
 * raw internals into the UI:
 *
 * 1. django-ninja request validation -> `{detail: [{type, loc, msg, ctx}, ...]}`.
 *    Joining that array produced the literal string "[object Object]".
 * 2. Our own `ValidationError` -> `{detail: ["..."], errors: {field: ["..."]}}`.
 * 3. The permission layer -> `{detail: "members.view_group"}` on a 403, i.e. a
 *    Django permission codename that must never be shown to a user.
 */

/** One entry of django-ninja's request-validation error list. */
interface NinjaValidationItem {
  loc?: (string | number)[];
  msg?: string;
  type?: string;
}

function isNinjaValidationList(d: unknown): d is NinjaValidationItem[] {
  return (
    Array.isArray(d) &&
    d.length > 0 &&
    d.every((i) => i !== null && typeof i === "object" && "msg" in (i as object))
  );
}

/** German equivalents for the pydantic error types we can actually hit. */
const VALIDATION_TEXT: Record<string, string> = {
  missing: "Dieses Feld ist erforderlich.",
  string_too_short: "Dieses Feld darf nicht leer sein.",
  string_too_long: "Dieser Wert ist zu lang.",
  int_parsing: "Bitte eine ganze Zahl eingeben.",
  float_parsing: "Bitte eine Zahl eingeben.",
  decimal_parsing: "Bitte einen Betrag eingeben.",
  date_parsing: "Bitte ein gültiges Datum eingeben.",
  date_from_datetime_parsing: "Bitte ein gültiges Datum eingeben.",
  datetime_parsing: "Bitte einen gültigen Zeitpunkt eingeben.",
  bool_parsing: "Bitte Ja oder Nein wählen.",
  value_error: "Dieser Wert ist ungültig.",
  greater_than: "Dieser Wert ist zu klein.",
  less_than: "Dieser Wert ist zu groß.",
};

function messageForItem(item: NinjaValidationItem): string {
  return (item.type && VALIDATION_TEXT[item.type]) || item.msg || "Ungültige Eingabe.";
}

/**
 * The field a validation item belongs to. ninja's `loc` is prefixed with the
 * request part and the payload name (`["body", "payload", "prename"]`), and for
 * nested lists it carries an index (`[..., "emergency_contacts", 0, "phone"]`).
 * The last string segment is the field the SPA knows by name.
 */
function fieldForItem(item: NinjaValidationItem): string | null {
  const loc = item.loc ?? [];
  for (let i = loc.length - 1; i >= 0; i--) {
    const part = loc[i];
    if (typeof part === "string" && part !== "body" && part !== "payload" && part !== "query") {
      return part;
    }
  }
  return null;
}

/** Error carrying the HTTP status and any parsed `{detail}` body. */
export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(ApiError.messageFor(status, detail));
    this.status = status;
    this.detail = detail;
  }

  /** Per-field validation errors ({field: [messages]}), from either error shape. */
  get fieldErrors(): Record<string, string[]> {
    if (this.detail && typeof this.detail === "object") {
      if ("errors" in this.detail) {
        const errs = (this.detail as { errors: unknown }).errors;
        if (errs && typeof errs === "object") return errs as Record<string, string[]>;
      }
      const d = (this.detail as { detail?: unknown }).detail;
      if (isNinjaValidationList(d)) {
        const out: Record<string, string[]> = {};
        for (const item of d) {
          const field = fieldForItem(item);
          if (!field) continue;
          (out[field] ??= []).push(messageForItem(item));
        }
        return out;
      }
    }
    return {};
  }

  static messageFor(status: number, detail: unknown): string {
    // A 401/403 body normally carries internals (a permission codename,
    // "Unauthorized"), so the status decides the wording, not the payload.
    if (status === 401) return "Nicht angemeldet. Bitte melde dich erneut an.";
    if (status === 403) {
      // …except where the API marks the refusal as written for the user. Those
      // explain a rule rather than name a permission ("a sent message can no
      // longer be edited"), and replacing them with a generic sentence left the
      // actual reason invisible.
      if (detail && typeof detail === "object" && "displayable" in detail) {
        const body = detail as { displayable?: unknown; detail?: unknown };
        if (body.displayable === true && typeof body.detail === "string" && body.detail.trim()) {
          return body.detail;
        }
      }
      return "Dazu fehlt dir die Berechtigung.";
    }

    if (detail && typeof detail === "object" && "detail" in detail) {
      // Whatever a 5xx body holds — a crash message, an error page some proxy put
      // in front of us — it is developer-facing text like the 404's below, in any
      // shape; the status decides the wording before the payload gets a say.
      if (status >= 500) {
        return "Serverfehler — die Aktion konnte nicht ausgeführt werden. Bitte versuche es erneut.";
      }
      const d = (detail as { detail: unknown }).detail;
      if (isNinjaValidationList(d)) {
        // Name the offending fields so the toast is useful even where the form
        // cannot render per-field errors.
        const parts = d.map((item) => {
          const field = fieldForItem(item);
          return field ? `${field}: ${messageForItem(item)}` : messageForItem(item);
        });
        return parts.join(" ");
      }
      if (Array.isArray(d)) return d.map((x) => String(x)).join(" ");
      // Django's get_object_or_404 text ("No Member matches the given query")
      // is developer-facing and untranslated; a 404 always reads the same.
      if (status === 404) return "Nicht gefunden.";
      if (typeof d === "string" && d.trim() !== "") return d;
    }

    if (status === 404) return "Nicht gefunden.";
    if (status === 413) return "Die Datei ist zu groß.";
    if (status >= 500) {
      return "Serverfehler — die Aktion konnte nicht ausgeführt werden. Bitte versuche es erneut.";
    }
    return `Die Anfrage ist fehlgeschlagen (Fehler ${status}).`;
  }
}

/* --- session expiry -------------------------------------------------------
 *
 * An access token expires while the app is open, and every request then 401s.
 * The AuthProvider registers a handler here so a single place can drop the
 * stale token and send the user back to the login screen, instead of every
 * page rendering an "unauthorized" error state.
 */
let onUnauthorized: (() => void) | null = null;

export function setUnauthorizedHandler(handler: (() => void) | null) {
  onUnauthorized = handler;
}

function raise(status: number, detail: unknown): never {
  if (status === 401) onUnauthorized?.();
  throw new ApiError(status, detail);
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
    raise(response.status, error);
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
    raise(res.status, detail);
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
